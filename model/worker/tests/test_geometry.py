import numpy as np
import pytest

from c4.data.geometry import (
    box_corners,
    cam_to_pixel,
    ego_to_cam,
    global_to_ego,
    quat_to_mat,
)

K = np.array([[1266.4, 0.0, 800.0], [0.0, 1266.4, 450.0], [0.0, 0.0, 1.0]])
IDENTITY_CALIB = dict(translation=[0.0, 0.0, 0.0], rotation=[1.0, 0.0, 0.0, 0.0])


def test_quat_identity_is_eye():
    assert np.allclose(quat_to_mat([1, 0, 0, 0]), np.eye(3))


def test_quat_90_degree_yaw_maps_x_to_y():
    h = np.sqrt(0.5)
    m = quat_to_mat([h, 0, 0, h])
    assert np.allclose(m, [[0, -1, 0], [1, 0, 0], [0, 0, 1]], atol=1e-12)
    assert np.allclose(m @ [1, 0, 0], [0, 1, 0], atol=1e-12)
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-12)


def test_quat_is_normalised_before_use():
    assert np.allclose(quat_to_mat([2, 0, 0, 0]), np.eye(3))


def test_box_corners_unit_box_follows_nuscenes_order():
    c = box_corners([0, 0, 0], [1, 1, 1], [1, 0, 0, 0])
    assert c.shape == (3, 8)
    assert np.allclose(c[0], 0.5 * np.array([1, 1, 1, 1, -1, -1, -1, -1]))
    assert np.allclose(c[1], 0.5 * np.array([1, -1, -1, 1, 1, -1, -1, 1]))
    assert np.allclose(c[2], 0.5 * np.array([1, 1, -1, -1, 1, 1, -1, -1]))


def test_box_corners_size_is_w_l_h_and_front_face_is_plus_x():
    c = box_corners([0, 0, 0], [2.0, 4.0, 6.0], [1, 0, 0, 0])  # w=2, l=4, h=6
    assert np.allclose(c[0, :4], 2.0) and np.allclose(c[0, 4:], -2.0)  # l/2 trên x
    assert np.allclose(np.abs(c[1]), 1.0)  # w/2 trên y
    assert np.allclose(np.abs(c[2]), 3.0)  # h/2 trên z


def test_box_corners_translate_and_rotate():
    h = np.sqrt(0.5)
    c = box_corners([10, 5, 1], [1, 2, 1], [h, 0, 0, h])  # xoay 90° quanh z: x -> y
    assert np.allclose(c.mean(axis=1), [10, 5, 1])
    assert np.allclose(c[1, :4], 5 + 1.0)  # mặt trước (l/2 = 1) quay sang +y


def test_global_to_ego_inverts_pose():
    h = np.sqrt(0.5)
    pose = dict(translation=[100.0, 50.0, 0.0], rotation=[h, 0, 0, h])  # ego quay 90° quanh z
    p_global = np.array([[100.0], [60.0], [0.0]])  # cách ego 10 m theo +y toàn cục = phía trước
    assert np.allclose(global_to_ego(p_global, pose), [[10.0], [0.0], [0.0]], atol=1e-9)


def test_ego_to_cam_uses_calib_inverse():
    calib = dict(translation=[1.5, 0.0, 1.5], rotation=[1.0, 0.0, 0.0, 0.0])
    out = ego_to_cam(np.array([[11.5], [0.0], [1.5]]), calib)
    assert np.allclose(out, [[10.0], [0.0], [0.0]])


def test_cam_to_pixel_returns_uv_and_depth():
    p = np.array([[0.0, 1.0], [0.0, 0.0], [10.0, 10.0]])
    uv, z = cam_to_pixel(p, K)
    assert uv.shape == (2, 2) and z.shape == (2,)
    assert np.allclose(uv[:, 0], [800.0, 450.0])
    assert np.allclose(uv[:, 1], [800.0 + 126.64, 450.0])
    assert np.allclose(z, 10.0)


def test_box_10m_ahead_projects_to_image_centre():
    """Calib giả: camera nhìn +z, quay đơn vị. Hộp đặt (0,0,10) trong hệ camera."""
    corners = box_corners([0, 0, 10], [0.7, 0.7, 1.8], [1, 0, 0, 0])
    cam = ego_to_cam(corners, IDENTITY_CALIB)
    uv, z = cam_to_pixel(cam, K)
    assert (z > 0.1).all()
    centre = (uv.min(axis=1) + uv.max(axis=1)) / 2
    assert centre == pytest.approx([800.0, 450.0], abs=5)
    centre_pt, _ = cam_to_pixel(ego_to_cam(np.array([[0.0], [0.0], [10.0]]), IDENTITY_CALIB), K)
    assert centre_pt[:, 0] == pytest.approx([800.0, 450.0], abs=5)
