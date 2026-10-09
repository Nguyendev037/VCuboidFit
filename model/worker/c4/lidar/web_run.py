"""Điểm vào duy nhất của luồng web: chọn (label-free), chấm nhãn (nếu có), ghi result.json."""
from c4.lidar.params import LidarParams
from c4.lidar.web_scoring import attach_truth
from c4.lidar.web_selection import select_for_web


def run_lidar_selection(job_dir, params: LidarParams, cfg=None) -> dict:
    sel = select_for_web(job_dir, params, cfg)
    if sel.cached is not None:
        return sel.cached
    result = attach_truth(sel, job_dir)
    sel.save(result)
    return result
