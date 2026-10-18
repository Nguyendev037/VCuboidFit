"""Engine dispatch and additive adapters for the existing selection API."""
import hashlib
import json
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from c4.config import load_config
from c4.contracts import read_table, write_table
from c4.lidar.pipeline import run_selection_lidar, tier_available
from c4.pipeline import run_selection
from c4.rare.pipeline import run_rare_v24
from service.errors import ApiError
from service.models import FrameContext, SelectParamsIn, SelectionResult

# Request-local app resources keep route(job_id, params) safe across concurrent apps.
APP: ContextVar = ContextVar("selection_app")
AXES = ("illum", "glare", "lens", "weather")
TAGS = ("R1", "R2", "R3", "H", "C", "I")


def split_tags(value) -> list[str]:
    return str(value).split("|") if pd.notna(value) and value else []


def context_table(job: Path) -> pd.DataFrame | None:
    path = job / "cache" / "context_frame.parquet"
    return read_table(path, "context_frame") if path.is_file() else None


def frame_context(job: Path, token: str) -> FrameContext | None:
    ctx = context_table(job)
    if ctx is None:
        return None
    rows = ctx[ctx["sample_token"] == token]
    if rows.empty:
        return None
    per_cam = {}
    for row in rows.to_dict("records"):
        per_cam[row["cam"]] = dict(
            tags=[row[f"tag_{a}"] for a in AXES
                  if pd.notna(row[f"tag_{a}"]) and row[f"tag_{a}"]],
            probs={a: json.loads(row[f"p_{a}"]) if row[f"p_{a}"] else {} for a in AXES},
            cvFlags=split_tags(row["cv_flags"]), review=bool(row["review"]),
            reviewReasons=split_tags(row["review_reasons"]))
    sun = rows.loc[rows["cam"] == "CAM_FRONT", "sun_elev_deg"].dropna()
    if sun.empty:
        sun = rows["sun_elev_deg"].dropna()
    return FrameContext(per_cam=per_cam, sun_elev_deg=float(sun.iloc[0]) if len(sun) else None)


def context_summary(job: Path, tokens: list[str]) -> dict | None:
    ctx = context_table(job)
    if ctx is None:
        return None
    ctx = ctx[ctx["sample_token"].isin(tokens)]
    masks = {"night": ctx["tag_illum"] == "night",
             "glare": ctx["tag_glare"].isin(["headlight", "sun"]),
             "rain": ctx["tag_weather"] == "rain", "review": ctx["review"]}
    return {k: int(ctx.loc[m.fillna(False), "sample_token"].nunique()) for k, m in masks.items()}


def legacy_select(job: Path, params: SelectParamsIn) -> SelectionResult:
    from service.selection import LazyEncoder, to_selection_result
    app = APP.get()
    job_id = job.name
    if app.state.queue.status(job_id).pipeline == "lidar":
        result = run_selection_lidar(job, params.to_lidar_params())
    else:
        result = run_selection(job, params.to_select_params(), cfg=load_config(),
                               encoder=LazyEncoder(app.state.encoders))
    return to_selection_result(job_id, job, result)


def rare_select(job: Path, params: SelectParamsIn) -> SelectionResult:
    from service.selection import to_selection_result
    app = APP.get()
    meta = json.loads((job / "job.json").read_text(encoding="utf-8"))
    root = app.state.settings.datasets / meta["datasetId"] / "data"
    requested_profile = params.profile or "lidar_only"
    result, fallback_warnings = _run_rare_with_fallback(
        job, root, requested_profile, params.budget)
    source = result["selection_dir"]
    manifest = json.loads((source / "config_used.json").read_text(encoding="utf-8"))
    manifest["strategy"] = params.strategy or "balanced"
    if requested_profile == "multisensor":
        # planning 23 D5: keep the requested profile visible when camera cache is absent.
        manifest["profile_requested"] = "multisensor"
    warnings = list(result["warnings"]) + fallback_warnings
    if manifest["strategy"] != "balanced":
        warnings.append("STRATEGY_NOT_IMPLEMENTED")
    manifest["warnings"] = warnings
    # The strategy is recorded even when it has no effect on the ranking.
    sid = hashlib.sha1(f"{source.name}|{manifest['strategy']}".encode()).hexdigest()[:12]
    artifact = job / "engines" / "rare_v24" / sid
    artifact.mkdir(parents=True, exist_ok=True)
    frames = read_table(source / "rare_frames.parquet", "rare_frames")
    objects = read_table(source / "rare_objects.parquet", "rare_objects")
    for name, df in (("rare_frames", frames), ("rare_objects", objects)):
        write_table(df, artifact / f"{name}.parquet", name, selection_id=sid)
    _save_json(artifact / "config_used.json", manifest)

    index = read_table(job / "lidar" / "index.parquet", "lidar_index")
    fs = frames.set_index("sample_token").loc[index["sample_token"]].reset_index()
    scores = index[["sample_token", "scene_token", "split", "frame_idx"]].copy()
    scores["keep"] = fs["gate"].to_numpy() == "valid"
    for col in ("rar", "nov", "unc", "r_rar", "r_nov", "r_unc"):
        scores[col] = 0.0
    scores["s"] = fs["s_frame"].to_numpy()
    # Legacy frame pagination resolves B from len(scores); rare budgets use eligible frames.
    scores = scores[scores["keep"]].reset_index(drop=True)
    info = scores.set_index("sample_token")
    tags = {r.sample_token: split_tags(r.pred_tags) for r in frames.itertuples()}
    ranking = result["ranking"]
    selected = pd.DataFrame([
        dict(method="hybrid", seed=0, rank=i, sample_token=t, scene_token=info.loc[t, "scene_token"],
             s=float(info.loc[t, "s"]), max_sim=0.0, mmr_util=float(info.loc[t, "s"]),
             reason="rare_v24", budget_B=result["B"])
        for i, t in enumerate(ranking, 1)],
        columns=["method", "seed", "rank", "sample_token", "scene_token", "s", "max_sim",
                 "mmr_util", "reason", "budget_B"])
    preview = [dict(rank=i, sampleToken=t, sceneToken=str(info.loc[t, "scene_token"]),
                    frameIdx=int(info.loc[t, "frame_idx"]), bestCam="LIDAR_TOP",
                    S=float(info.loc[t, "s"]), rNov=0.0, rUnc=0.0, rQry=0.0,
                    reason="rare_v24", tags=tags[t], camsAvailable=[])
               for i, t in enumerate(result["selected"][:12], 1)]
    counts, bins = np.histogram(scores["s"], bins=np.linspace(0, 1, 21))
    response = dict(selectionId=sid, pipeline="lidar", engineVersion="rare_v24",
                    params=params.model_dump(by_alias=True, exclude_none=True),
                    poolSize=int(scores["keep"].sum()), budgetB=result["B"],
                    tierAvailable=tier_available(job), warnings=warnings, warningCodes=warnings,
                    metrics=None, preview=preview, evaluationAvailable=False,
                    gateSummary={g: int((frames["gate"] == g).sum())
                                 for g in ("valid", "suspect", "outlier")},
                    tagSummary={tag: sum(tag in tags[t] for t in result["selected"]) for tag in TAGS},
                    contextSummary=context_summary(job, result["selected"]),
                    analysis=dict(tags=tags,
                                  pool=dict(frames=len(index), scenes=int(index["scene_token"].nunique()),
                                            images=0, imagesByCam={}, hasLidar=True),
                                  selected=dict(scenesCovered=int(info.loc[result["selected"],
                                                                           "scene_token"].nunique())),
                                  histogram=dict(bins=bins.tolist(), counts=counts.tolist(),
                                                 budgetThreshold=min((float(info.loc[t, "s"])
                                                                      for t in result["selected"]), default=0))))
    # Compatibility artifacts keep existing frame/list/export endpoints usable.
    out = job / "out" / "selections" / sid
    out.mkdir(parents=True, exist_ok=True)
    write_table(scores, out / "scores.parquet", "lidar_scores", selection_id=sid)
    write_table(selected, out / "selected.csv", "lidar_selected", selection_id=sid)
    _save_json(out / "result.json", response)
    return to_selection_result(job.name, job, response)


def _run_rare_with_fallback(
    job: Path, root: Path, profile: str, budget: float
) -> tuple[dict, list[str]]:
    try:
        return (run_rare_v24(job, root, profile=profile, budget_frac=budget,
                             pool_split="all", ref_split="all"), [])
    except FileNotFoundError as exc:
        message = str(exc).replace("\\", "/")
        if profile != "multisensor" or "cache/" not in message or "lidar/" in message:
            raise
        result = run_rare_v24(job, root, profile="lidar_only", budget_frac=budget,
                              pool_split="all", ref_split="all")
        return result, ["CAMERA_CACHE_MISSING"]


def _save_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


ENGINES: dict[str, Callable[[Path, SelectParamsIn], SelectionResult]] = {
    "c4_legacy": legacy_select, "rare_v24": rare_select}


def route(job_id: str, params: SelectParamsIn) -> SelectionResult:
    engine = params.engine_version or os.getenv("VCF_ENGINE_DEFAULT", "c4_legacy")
    if engine not in ENGINES:
        raise ApiError(422, "UNKNOWN_ENGINE", "Engine được yêu cầu không tồn tại.")
    return ENGINES[engine](APP.get().state.settings.jobs / job_id, params)
