"""M1 · chỉ mục keyframe LIDAR_TOP. Không đọc nhãn, không đọc scene.description."""
import math
from pathlib import Path

import pandas as pd

from c4.contracts import LIDAR_INDEX, validate
from c4.data.nusc import NuscTables


def yaw_of(q) -> float:
    w, x, y, z = q
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def lidar_keyframes(t: NuscTables) -> dict[str, dict]:
    """sample_token → sample_data LIDAR_TOP keyframe."""
    chan = {tok: t.sensor[c["sensor_token"]]["channel"] for tok, c in t.calibrated_sensor.items()}
    return {sd["sample_token"]: sd for sd in t.sample_data.values()
            if sd["is_key_frame"] and chan[sd["calibrated_sensor_token"]] == "LIDAR_TOP"}


def build_lidar_index(t: NuscTables, data_root) -> pd.DataFrame:
    root = Path(data_root)
    lid = lidar_keyframes(t)
    rows = []
    for sc_tok, sc in t.scene.items():
        for idx, s in enumerate(t.scene_samples(sc_tok)):
            sd = lid.get(s["token"])
            if sd is None or not (root / sd["filename"]).is_file():
                continue
            pose = t.ego_pose[sd["ego_pose_token"]]
            rows.append(dict(sample_token=s["token"], scene_token=sc_tok, scene_name=sc["name"],
                             split="pool", frame_idx=idx, timestamp=sd["timestamp"],
                             lidar_path=sd["filename"], ego_x=pose["translation"][0],
                             ego_y=pose["translation"][1], ego_yaw=yaw_of(pose["rotation"])))
    df = pd.DataFrame(rows, columns=list(LIDAR_INDEX))
    df = df.sort_values(["scene_name", "frame_idx"]).reset_index(drop=True)
    return validate(df, "lidar_index")
