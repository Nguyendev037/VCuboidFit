"""Test dashboard.render():
- HTML không chứa http (không gọi mạng / không CDN).
- HTML có đủ 9 tiêu đề D1–D9.
- PNG đúng 1600×900 px.
- D7 đọc crop `bench/report/examples/*.jpg` và fallback cắt 6 khung từ job.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image


# ── Fixture: report_judge giả (đủ khoá theo §7 01-CONTRACTS) ─────────────────
@pytest.fixture()
def fake_report() -> dict:
    return {
        "schema": "bench-report/1",
        "dataset": "nuscenes-pilot",
        "label": "pilot",
        "prereg_sha256": "aabbcc",
        "selections_sha256": "ddeeff",
        "split_sha256": "112233",
        "repo_sha": "deadbeef",
        "B": 6,
        "n_pool": 1400,
        "judges": {
            "JA": {"tau": 0.35, "iou_thr": 0.5, "validity": {"ok": True, "recall_easy": 0.92,
                                                               "auroc_unc_vs_miss": 0.80}},
            "JB": {"tau": 0.40, "iou_thr": 0.5, "validity": {"ok": True, "recall_easy": 0.91,
                                                               "auroc_unc_vs_miss": 0.78}},
        },
        "kappa_JA_JB": 0.62,
        "methods": {
            "OURS": {"SY_JA": 0.55, "SY_JB": 0.53, "UNC_JA": 0.40, "UNC_JB": 0.38,
                     "NY_JA": 1.10, "NY_JB": 1.08, "empty_rate": 0.05, "IY_internal": None},
            "X1":   {"SY_JA": 0.45, "SY_JB": 0.43, "UNC_JA": 0.35, "UNC_JB": 0.33,
                     "NY_JA": 0.90, "NY_JB": 0.88, "empty_rate": 0.08, "IY_internal": None},
            "X2":   {"SY_JA": 0.42, "SY_JB": 0.40, "UNC_JA": 0.33, "UNC_JB": 0.31,
                     "NY_JA": 0.85, "NY_JB": 0.82, "empty_rate": 0.10, "IY_internal": None},
            "X3":   {"SY_JA": 0.40, "SY_JB": 0.38, "UNC_JA": 0.30, "UNC_JB": 0.28,
                     "NY_JA": 0.80, "NY_JB": 0.78, "empty_rate": 0.12, "IY_internal": None},
            "N1":   {"SY_JA": 0.30, "SY_JB": 0.28, "UNC_JA": 0.22, "UNC_JB": 0.20,
                     "NY_JA": 0.60, "NY_JB": 0.58, "empty_rate": 0.15, "IY_internal": None},
            "N2":   {"SY_JA": 0.28, "SY_JB": 0.26, "UNC_JA": 0.20, "UNC_JB": 0.18,
                     "NY_JA": 0.55, "NY_JB": 0.53, "empty_rate": 0.18, "IY_internal": None},
            "M1":   {"SY_JA": 0.38, "SY_JB": 0.36, "UNC_JA": 0.28, "UNC_JB": 0.26,
                     "NY_JA": 0.76, "NY_JB": 0.74, "empty_rate": 0.11, "IY_internal": None},
            "M2":   {"SY_JA": 0.50, "SY_JB": 0.48, "UNC_JA": 0.37, "UNC_JB": 0.35,
                     "NY_JA": 1.00, "NY_JB": 0.98, "empty_rate": 0.06, "IY_internal": None},
        },
        "random": {"SY_JA_mean": 0.25, "SY_JA_p95": 0.32, "SY_JB_mean": 0.24, "SY_JB_p95": 0.31},
        "oracle": {"SY_JA": 0.75, "SY_JB": 0.73},
        "contrasts": [
            {"a": "OURS", "b": "X1", "judge": "JA", "delta": 0.10, "lo": 0.02,
             "hi": 0.18, "p": 0.01, "p_holm": None},
            {"a": "OURS", "b": "X2", "judge": "JA", "delta": 0.13, "lo": 0.05,
             "hi": 0.21, "p": 0.005, "p_holm": 0.01},
            {"a": "OURS", "b": "X1", "judge": "JB", "delta": 0.10, "lo": 0.03,
             "hi": 0.17, "p": 0.01, "p_holm": None},
        ],
        "curve": {
            "0.01": {"methods": {"OURS": {"SY_JA": 0.40}, "X1": {"SY_JA": 0.30}},
                     "random": {"SY_JA_mean": 0.15, "SY_JA_p95": 0.20},
                     "oracle": {"SY_JA": 0.60}, "contrasts": []},
            "0.02": {"methods": {"OURS": {"SY_JA": 0.44}, "X1": {"SY_JA": 0.34}},
                     "random": {"SY_JA_mean": 0.18, "SY_JA_p95": 0.24},
                     "oracle": {"SY_JA": 0.65}, "contrasts": []},
            "0.05": {"methods": {"OURS": {"SY_JA": 0.55, "SY_JB": 0.53,
                                          "UNC_JA": 0.40, "UNC_JB": 0.38,
                                          "NY_JA": 1.10, "NY_JB": 1.08,
                                          "empty_rate": 0.05, "IY_internal": None},
                                 "X1":   {"SY_JA": 0.45, "SY_JB": 0.43,
                                          "UNC_JA": 0.35, "UNC_JB": 0.33,
                                          "NY_JA": 0.90, "NY_JB": 0.88,
                                          "empty_rate": 0.08, "IY_internal": None},
                                 "N1":   {"SY_JA": 0.30, "SY_JB": 0.28,
                                          "UNC_JA": 0.22, "UNC_JB": 0.20,
                                          "NY_JA": 0.60, "NY_JB": 0.58,
                                          "empty_rate": 0.15, "IY_internal": None},
                                 "N2":   {"SY_JA": 0.28, "SY_JB": 0.26,
                                          "UNC_JA": 0.20, "UNC_JB": 0.18,
                                          "NY_JA": 0.55, "NY_JB": 0.53,
                                          "empty_rate": 0.18, "IY_internal": None},
                                 },
                     "random": {"SY_JA_mean": 0.25, "SY_JA_p95": 0.32},
                     "oracle": {"SY_JA": 0.75},
                     "contrasts": [
                         {"a": "OURS", "b": "X1", "judge": "JA", "delta": 0.10,
                          "lo": 0.02, "hi": 0.18, "p": 0.01, "p_holm": None},
                     ]},
            "0.10": {"methods": {"OURS": {"SY_JA": 0.58}, "X1": {"SY_JA": 0.48}},
                     "random": {"SY_JA_mean": 0.28, "SY_JA_p95": 0.36},
                     "oracle": {"SY_JA": 0.80}, "contrasts": []},
        },
        "verdict": {"win": False, "text": "Chạy khô pipeline, không phải kết quả."},
        "power": None,
        "limitations": [],
    }


def _jpeg(path: Path, color=(40, 80, 120)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (96, 64), color).save(path)


def _job_with_frames(tmp_path: Path) -> Path:
    job = tmp_path / "job"
    (job / "index").mkdir(parents=True)
    (job / "gt").mkdir(parents=True)
    (job / "bench" / "judge").mkdir(parents=True)

    tokens = [f"tok{i:02d}" for i in range(8)]
    frame_rows, gt_rows, det_rows, struggle_rows = [], [], [], []
    for i, token in enumerate(tokens):
        image = tmp_path / "images" / f"{token}.jpg"
        _jpeg(image, (20 * i, 40, 80))
        frame_rows.append({"sample_token": token, "cam": "CAM_FRONT",
                           "img_path": str(image)})
        gt_rows.append({"sample_token": token, "cam": "CAM_FRONT",
                        "ann_token": f"ann{i}", "category": "human.pedestrian.adult",
                        "x1": 10.0, "y1": 10.0, "x2": 40.0, "y2": 50.0,
                        "depth": 12.0})
        det_rows.append({"sample_token": token, "cam": "CAM_FRONT",
                         "score": 0.9, "x1": 12.0, "y1": 12.0, "x2": 38.0, "y2": 48.0})
        struggle_rows.append({"sample_token": token, "ann_token": f"ann{i}",
                              "struggle": True})

    pd.DataFrame(frame_rows).to_parquet(job / "index" / "frames.parquet", index=False)
    pd.DataFrame(gt_rows).to_parquet(job / "gt" / "gt_boxes_2d.parquet", index=False)
    pd.DataFrame(det_rows).to_parquet(
        job / "bench" / "judge" / "judge_det_JA_pool.parquet", index=False)
    pd.DataFrame(struggle_rows).to_parquet(
        job / "bench" / "judge" / "judge_struggle_JA_pool.parquet", index=False)

    selections = {
        "B": 6,
        "methods": {
            "OURS": {"tokens": tokens[:6]},
            "X1": {"tokens": tokens[6:]},
            "X2": {"tokens": []},
            "X3": {"tokens": []},
        },
    }
    (job / "bench" / "selections.json").write_text(
        json.dumps(selections), encoding="utf-8")
    return job


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_render_no_http(fake_report, tmp_path):
    """HTML không được chứa http:// (không CDN, không gọi mạng ngoài)."""
    from c4.bench.dashboard import render

    html_path = render(fake_report, None, None, tmp_path)
    html = html_path.read_text(encoding="utf-8")
    assert "http://" not in html, "HTML chứa http:// — vi phạm không CDN"
    assert "https://" not in html, "HTML chứa https:// — vi phạm không CDN"


def test_render_has_nine_sections(fake_report, tmp_path):
    """HTML phải có đủ 9 tiêu đề D1 đến D9."""
    from c4.bench.dashboard import render

    html_path = render(fake_report, None, None, tmp_path)
    html = html_path.read_text(encoding="utf-8")
    for d in range(1, 10):
        assert f'id="D{d}"' in html, f"Thiếu section D{d} trong dashboard HTML"


def test_render_png_size(fake_report, tmp_path):
    """PNG fig_*.png phải đúng 1600×900 px."""
    from c4.bench.dashboard import render

    render(fake_report, None, None, tmp_path)
    pngs = list(tmp_path.glob("fig_*.png"))
    assert pngs, "Không tìm thấy PNG nào sau khi render"
    for png_path in pngs:
        with Image.open(png_path) as img:
            w, h = img.size
            # cho phép sai lệch nhỏ do bbox_inches="tight" trim
            assert w >= 1550 and w <= 1650, f"{png_path.name}: width={w} (kỳ vọng ~1600)"
            assert h >= 850 and h <= 950, f"{png_path.name}: height={h} (kỳ vọng ~900)"


def test_render_with_report_train(fake_report, tmp_path):
    """render() với report_train vẫn tạo D8 không raise."""
    from c4.bench.dashboard import render

    report_train = {"methods": {
        "OURS": {"AP50_vru_mean": 0.60, "AP50_vru_ci_lo": 0.55, "AP50_vru_ci_hi": 0.65},
        "X0":   {"AP50_vru_mean": 0.50},
        "X1":   {"AP50_vru_mean": 0.48, "AP50_vru_ci_lo": 0.43, "AP50_vru_ci_hi": 0.53},
    }}
    html_path = render(fake_report, report_train, None, tmp_path)
    html = html_path.read_text(encoding="utf-8")
    assert 'id="D8"' in html
    assert "http://" not in html


def test_d7_uses_examples_directory(fake_report, tmp_path):
    """Có crop do report xuất ⇒ D7 hiển thị đúng 6 ảnh, không ghi chú thiếu ảnh."""
    from c4.bench.dashboard import _fig_examples

    job = tmp_path / "job"
    for i in range(6):
        _jpeg(job / "bench" / "report" / "examples" / f"ex{i}.jpg", (i * 30, 10, 10))

    fig, _ = _fig_examples(fake_report, job, tmp_path)
    assert len(fig.axes) == 6
    assert all(ax.images for ax in fig.axes)
    texts = " ".join(text.get_text() for ax in fig.axes for text in ax.texts)
    assert "chưa có ảnh" not in texts


def test_d7_fallback_draws_job_frames(fake_report, tmp_path):
    """Không có crop ⇒ D7 cắt 6 khung OURS không bị X* chọn từ job, có GT/det."""
    from c4.bench.dashboard import _fig_examples

    job = _job_with_frames(tmp_path)

    fig, _ = _fig_examples(fake_report, job, tmp_path)
    shown = [ax for ax in fig.axes if ax.images]
    assert len(shown) == 6
    patches = sum(len(ax.patches) for ax in fig.axes)
    assert patches >= 12, "mỗi khung phải có hộp GT xanh và detection đỏ"
    texts = " ".join(text.get_text() for ax in fig.axes for text in ax.texts)
    assert "chưa có ảnh" not in texts
