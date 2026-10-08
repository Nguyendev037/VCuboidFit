# c4/mining/score.py · từ bảng theo ảnh sang bảng theo frame, chỉ dùng camera frame đó có
import numpy as np
import pandas as pd


def apply_quality(feat: pd.DataFrame, min_luma: float, min_blur_var: float) -> pd.DataFrame:
    """Tiêu chí 5: ảnh không quá tối, không mờ, và có ít nhất một proposal."""
    ok = (feat["q_bright"] >= min_luma) & (feat["q_blur"] >= min_blur_var) & (feat["det_n"] >= 1)
    return feat.assign(q_ok=ok.astype(bool))


def frame_scores(feat: pd.DataFrame, alpha: float, beta: float, gamma: float,
                 cameras) -> pd.DataFrame:
    f = feat.reset_index(drop=True).copy()
    eligible = f["q_ok"] & f["cam"].isin(list(cameras))
    for src, dst in [("nov_knn", "r_nov"), ("unc", "r_unc"), ("qry_max", "r_qry")]:
        # ảnh hỏng hoặc camera không tham gia: hạng 0, tức là bị loại trước khi chấm
        f[dst] = f[src].where(eligible).groupby(f["split"]).rank(pct=True).fillna(0.0)
    f["s"] = np.where(eligible, alpha * f["r_nov"] + beta * f["r_unc"] + gamma * f["r_qry"], 0.0)
    f["_elig"] = eligible
    order = pd.Index(pd.unique(f["sample_token"]))
    f["frame_emb_row"] = order.get_indexer(f["sample_token"])
    # ảnh đại diện: ảnh đủ điều kiện có s cao nhất; frame không có ảnh nào đủ điều kiện lấy ảnh đầu
    f["_key"] = np.where(eligible, f["s"], -1.0)
    best = f.loc[f.groupby("sample_token", sort=False)["_key"].idxmax()]
    agg = f.groupby("sample_token", sort=False).agg(
        S_nov=("r_nov", "max"), S_unc=("r_unc", "max"), S_qry=("r_qry", "max"),
        q_any=("_elig", "any"), n_cams=("cam", "size")).reset_index()
    out = best.rename(columns=dict(cam="best_cam", s="S_hybrid", emb_row="emb_row_best",
                                   det_n_conf="det_n_conf_best"))
    out = out.drop(columns=["q_ok"]).merge(agg, on="sample_token").rename(columns={"q_any": "q_ok"})
    return out.sort_values("frame_emb_row").reset_index(drop=True)


def frame_embeddings(Z_img: np.ndarray, feat: pd.DataFrame, cameras):
    """Embedding frame = trung bình embedding các camera đang có (lọc theo cameras nếu frame có),
    chuẩn hóa lại. Thứ tự dòng = thứ tự xuất hiện của sample_token trong feat."""
    in_cams = feat["cam"].isin(list(cameras))
    has = in_cams.groupby(feat["sample_token"], sort=False).transform("any")
    use = feat[in_cams | ~has]
    order = pd.Index(pd.unique(feat["sample_token"]))
    idx = order.get_indexer(use["sample_token"])
    Z = np.asarray(Z_img, np.float32)[use["emb_row"].to_numpy()]
    Zf = np.zeros((len(order), Z.shape[1]), np.float32)
    np.add.at(Zf, idx, Z)
    Zf /= np.maximum(np.linalg.norm(Zf, axis=1, keepdims=True), 1e-12)
    return Zf, order.to_numpy()
