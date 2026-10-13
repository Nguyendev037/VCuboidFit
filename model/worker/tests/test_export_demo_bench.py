"""D2: `scripts/export_demo_bench.py` — schema C1, nguyên văn label/conclusion, chép hình
(SPEC-P01 §2). Report mẫu: mini_bench của M8c (hồ sơ 11).

Chạy từ `model/worker`: `python -m pytest -q tests/test_export_demo_bench.py`.
Đổi nguồn report mẫu bằng biến môi trường `VCF_DEMO_BENCH_REPORT` (dùng cho phép đo ĐỎ).
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

WORKER = Path(__file__).resolve().parents[1]
SCRIPT = WORKER / "scripts" / "export_demo_bench.py"
SAMPLE_DEFAULT = (Path(__file__).resolve().parents[5] / "planning"
                  / "11_2026-10-13_clip-context-fleet" / "evidence" / "M8c" / "mini_bench"
                  / "report_pitch.json")

# Giá trị NGUYÊN VĂN của report mẫu — cố định ở đây để phép đo bắt được thay đổi ở nguồn.
SAMPLE_LABEL = "mini · minh hoạ · in-sample"
SAMPLE_CONCLUSION = "not shown / underpowered"
C1_KEYS = {"schema", "source", "label", "pool", "scenes", "capture_primary", "budget_B",
           "methods", "primary", "reachability", "figures"}


def _load_module():
    spec = importlib.util.spec_from_file_location("export_demo_bench", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export = _load_module()


def _sample() -> Path:
    return Path(os.environ.get("VCF_DEMO_BENCH_REPORT", SAMPLE_DEFAULT))


def _fake_report(conclusion="not shown / underpowered") -> dict:
    return {
        "mode": "mini",
        "label": "mini · minh hoạ · in-sample",
        "capture_primary": "rare_form",
        "prereg_sha256": "590a7a6a17fd55b63f778dbd79c4b01ed6f33add705d84225d7db7b890a0a75d",
        "pool": 404,
        "scenes": 10,
        "B": 21,
        "reachability": {"radius_m": 1.0, "n_targets": 20,
                         "methods": {"M2": {"reach": 0.55, "n_reachable": 11, "n_targets": 20}}},
        "methods": {
            "M0": {"iy": 0.08666666666666666, "ci95": [0.03177869040750474, 0.14525955568042587],
                   "ny": 0.0},
            "M1": {"iy": 0.047619047619047616, "ci95": [0.0, 0.1601666666666665],
                   "ny": -0.0451045104510451},
            "M2": {"iy": 0.09523809523809523, "ci95": [0.0, 0.25], "ny": 0.009900990099009908},
            "M3": {"status": "chưa đo"},
        },
        "primary_delta": {"delta": 0.047619047619047616, "lo": -0.1176642156862745,
                          "hi": 0.22738135026737957, "n_boot": 1000},
        "conclusion": conclusion,
    }


def _write_figures(directory: Path, names) -> None:
    for name in names:
        (directory / name).write_bytes(b"\x89PNG\r\n\x1a\n")


def test_schema_c1_and_figures_copied(tmp_path):
    report = tmp_path / "report_pitch.json"
    report.write_text(json.dumps(_fake_report(), ensure_ascii=False), encoding="utf-8")
    _write_figures(tmp_path, ("fig_iy_budget.png", "fig_context.png"))  # thiếu fig_examples
    out = tmp_path / "demo"

    assert export.main(["--report", str(report), "--out", str(out)]) == 0

    payload = json.loads((out / "bench_pitch.json").read_text(encoding="utf-8"))
    assert set(payload) == C1_KEYS
    assert payload["schema"] == "vcf-demo-bench-v1"
    assert payload["label"] == "mini · minh hoạ · in-sample"
    assert (payload["pool"], payload["scenes"]) == (404, 10)
    assert payload["capture_primary"] == "rare_form"
    assert payload["budget_B"] == 21
    assert payload["source"]["report_sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()
    assert payload["source"]["run_id"] == tmp_path.name
    assert payload["source"]["prereg_sha256"] == _fake_report()["prereg_sha256"]
    assert payload["methods"]["M0"] == {"name": "Random", "iy": 0.08666666666666666,
                                        "ci_lo": 0.03177869040750474,
                                        "ci_hi": 0.14525955568042587, "ny": 0.0, "status": "ok"}
    assert payload["methods"]["M3"] == {"name": "multisensor", "iy": None, "ci_lo": None,
                                        "ci_hi": None, "status": "chưa đo"}
    # con số nguyên văn, không làm tròn
    assert payload["primary"]["delta"] == 0.047619047619047616
    assert (payload["primary"]["ci_lo"], payload["primary"]["ci_hi"]) == (
        -0.1176642156862745, 0.22738135026737957)
    assert payload["primary"]["pair"] == "M2-M1"
    assert payload["reachability"] == {"radius_m": 1.0, "n_targets": 20,
                                       "methods": {"M2": {"reach": 0.55, "n_reachable": 11,
                                                          "n_targets": 20}}}
    assert payload["figures"] == ["fig_iy_budget.png", "fig_context.png"]
    assert (out / "fig_iy_budget.png").is_file() and (out / "fig_context.png").is_file()
    assert not (out / "fig_examples.png").exists()


def test_sample_mini_report_verbatim(tmp_path):
    sample = _sample()
    assert sample.is_file(), f"thiếu report mẫu của SPEC-P01 §2: {sample}"
    out = tmp_path / "demo"

    assert export.main(["--report", str(sample), "--out", str(out)]) == 0

    payload = json.loads((out / "bench_pitch.json").read_text(encoding="utf-8"))
    assert payload["label"] == SAMPLE_LABEL
    assert payload["primary"]["conclusion"] == SAMPLE_CONCLUSION
    assert payload["budget_B"] == 21 and payload["capture_primary"] == "rare_form"
    assert payload["methods"]["M3"]["status"] == "ok"
    assert all(payload["methods"][m]["ci_lo"] is not None for m in ("M0", "M1", "M2", "M3"))
    assert payload["source"]["report_sha256"] == hashlib.sha256(sample.read_bytes()).hexdigest()
    assert payload["figures"] == ["fig_iy_budget.png", "fig_context.png", "fig_examples.png"]


def test_tampered_conclusion_is_rejected_fail_closed(tmp_path):
    """`conclusion` ngoài contract C1 ⇒ exit 2, KHÔNG ghi file (chống âm thầm sửa kết luận)."""
    sample = _sample()
    assert sample.is_file(), f"thiếu report mẫu của SPEC-P01 §2: {sample}"
    raw = json.loads(sample.read_text(encoding="utf-8"))
    raw["conclusion"] = "shown ✅ đổi tay"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "demo"

    assert export.main(["--report", str(tampered), "--out", str(out)]) == 2
    assert not (out / "bench_pitch.json").exists()


def test_missing_report_exits_2(tmp_path):
    out = tmp_path / "demo"
    assert export.main(["--report", str(tmp_path / "absent.json"), "--out", str(out)]) == 2
    assert not (out / "bench_pitch.json").exists()
