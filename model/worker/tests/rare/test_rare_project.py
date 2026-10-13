"""M3a · chiếu box ứng viên (hệ ego) sang camera: đúng camera, visible_frac hợp lệ (planning/11 SPEC-P06 §3)."""
import pandas as pd

from c4.contracts import CAMS, validate
from c4.rare.project import project_objects
from tests.fixtures.make_nuscenes import _INTRINSIC, _cam_rotation

K = [v for row in _INTRINSIC for v in row]


def _poses(tok="t0", cams=CAMS):
    return pd.DataFrame([dict(sample_token=tok, cam=c, translation=[0.0, 0.0, 0.0], rotation=_cam_rotation(c),
                              intrinsic=K) for c in cams])


def _obj(oid, cx, cy, cz=0.0, w=0.7, l=0.7, h=1.8):
    return dict(sample_token="t0", object_id=oid, cx=cx, cy=cy, cz=cz, l=l, w=w, h=h, yaw=0.0)


def test_project_objects_picks_right_camera():
    objs = pd.DataFrame([_obj("front", 12.0, 0.0), _obj("back", -12.0, 0.0), _obj("edge", 3.0, 1.9)])
    out = project_objects(objs, _poses()).set_index("object_id")
    validate(out.reset_index(), "rare_obj_cam")
    assert out.loc["front", "cam"] == "CAM_FRONT" and out.loc["back", "cam"] == "CAM_BACK"
    assert (out["visible_frac"] > 0).all() and (out["visible_frac"] <= 1).all() and out.index.is_unique
    assert out.loc["front", "visible_frac"] == 1.0                      # nằm trọn trong ảnh
    assert 0 < out.loc["edge", "visible_frac"] < 1.0                    # tràn ra rìa ảnh => bị cắt
    assert (out[["x1", "x2"]].to_numpy() >= 0).all() and (out[["x1", "x2"]].to_numpy() <= 1600).all()
    # chỉ còn CAM_FRONT: vật ở sau xe không camera nào thấy => không có hàng (không crop)
    only_front = project_objects(objs, _poses(cams=["CAM_FRONT"]))
    assert "back" not in set(only_front["object_id"]) and "front" in set(only_front["object_id"])
