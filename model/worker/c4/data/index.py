"""S0a: bảng frames (mỗi dòng một ảnh camera tồn tại trên đĩa) và cam_poses."""
from pathlib import Path

import numpy as np
import pandas as pd

from c4.contracts import CAM_POSES, CAMS, FRAMES, validate
from c4.data.nusc import NuscTables


def build_frames(t: NuscTables, data_root: Path) -> pd.DataFrame:
    """Chỉ keyframe camera có file thật. Sắp scene_token, frame_idx, thứ tự CAMS."""
    data_root = Path(data_root)
    chan = {tok: t.sensor[c["sensor_token"]]["channel"] for tok, c in t.calibrated_sensor.items()}
    by_sample: dict[str, dict[str, dict]] = {}
    for sd in t.sample_data.values():
        cam = chan[sd["calibrated_sensor_token"]]
        if sd["is_key_frame"] and cam in CAMS and (data_root / sd["filename"]).is_file():
            by_sample.setdefault(sd["sample_token"], {})[cam] = sd
    rows = []
    for sc_tok, sc in t.scene.items():
        for idx, s in enumerate(t.scene_samples(sc_tok)):
            for cam, sd in by_sample.get(s["token"], {}).items():
                rows.append(dict(
                    sample_token=s["token"], cam=cam, sd_token=sd["token"], scene_token=sc_tok,
                    scene_name=sc["name"], scene_desc=sc["description"], split="pool",
                    frame_idx=idx, timestamp=sd["timestamp"], img_path=sd["filename"]))
    df = pd.DataFrame(rows, columns=list(FRAMES))
    df["_cam_rank"] = df["cam"].map({c: i for i, c in enumerate(CAMS)})
    df = df.sort_values(["scene_token", "frame_idx", "_cam_rank"]).drop(columns="_cam_rank")
    return validate(df.reset_index(drop=True), "frames")


def cam_poses(t: NuscTables, frames: pd.DataFrame) -> pd.DataFrame:
    """Pose camera→ego của từng dòng frames (cùng thứ tự)."""
    rows = []
    for sample_token, cam, sd_token in zip(frames["sample_token"], frames["cam"],
                                           frames["sd_token"]):
        cal = t.calibrated_sensor[t.sample_data[sd_token]["calibrated_sensor_token"]]
        rows.append(dict(
            sample_token=sample_token, cam=cam,
            translation=np.asarray(cal["translation"], dtype=np.float32),
            rotation=np.asarray(cal["rotation"], dtype=np.float32),
            intrinsic=np.asarray(cal["camera_intrinsic"], dtype=np.float32).reshape(9)))
    return validate(pd.DataFrame(rows, columns=list(CAM_POSES)), "cam_poses")
