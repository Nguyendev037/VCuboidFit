import json

from c4.contracts import CAMS
from tests.fixtures.make_nuscenes import make_nuscenes

TABLES = ["scene", "sample", "sample_data", "sensor", "calibrated_sensor", "ego_pose", "log",
          "map", "category", "attribute", "visibility", "instance", "sample_annotation"]


def _load(root, name):
    return json.loads((root / "v1.0-mini" / f"{name}.json").read_text(encoding="utf-8"))


def _channels(root):
    sensor = {s["token"]: s["channel"] for s in _load(root, "sensor")}
    cal = {c["token"]: sensor[c["sensor_token"]] for c in _load(root, "calibrated_sensor")}
    return cal


def test_returns_data_root_and_tables_are_json_lists(tmp_path):
    root = make_nuscenes(tmp_path)
    assert root == tmp_path / "data"
    for name in TABLES:
        assert isinstance(_load(root, name), list), name
    assert len(_load(root, "scene")) == 2
    assert len(_load(root, "sample")) == 2 * 6


def test_keyframes_per_sample_are_six_cams_plus_lidar(tmp_path):
    root = make_nuscenes(tmp_path)
    chan = _channels(root)
    per_sample = {}
    for sd in _load(root, "sample_data"):
        if sd["is_key_frame"]:
            per_sample.setdefault(sd["sample_token"], []).append(
                chan[sd["calibrated_sensor_token"]])
    assert len(per_sample) == 12
    for chans in per_sample.values():
        assert sorted(chans) == sorted([*CAMS, "LIDAR_TOP"])


def test_sweeps_are_not_keyframes(tmp_path):
    root = make_nuscenes(tmp_path)
    sweeps = [sd for sd in _load(root, "sample_data") if not sd["is_key_frame"]]
    assert sweeps and all(sd["filename"].startswith("sweeps/") for sd in sweeps)


def test_files_exist_and_images_are_1600x900(tmp_path):
    from PIL import Image
    root = make_nuscenes(tmp_path)
    for sd in _load(root, "sample_data"):
        assert (root / sd["filename"]).is_file(), sd["filename"]
    one = next(sd for sd in _load(root, "sample_data") if "CAM_FRONT/" in sd["filename"])
    with Image.open(root / one["filename"]) as im:
        assert im.size == (1600, 900)
    lidar = next(sd for sd in _load(root, "sample_data") if "LIDAR_TOP/" in sd["filename"])
    assert (root / lidar["filename"]).stat().st_size == 300 * 5 * 4


def test_drop_cams_removes_exactly_those_files(tmp_path):
    root = make_nuscenes(tmp_path, drop_cams={"scene0": ["CAM_BACK"]})
    scene_tok = {s["name"]: s["token"] for s in _load(root, "scene")}
    sample_scene = {s["token"]: s["scene_token"] for s in _load(root, "sample")}
    missing = set()
    for sd in _load(root, "sample_data"):
        if sd["is_key_frame"] and not (root / sd["filename"]).exists():
            missing.add((sample_scene[sd["sample_token"]], sd["filename"].split("/")[1]))
    assert missing == {(scene_tok["scene0"], "CAM_BACK")}
    n_missing = sum(1 for sd in _load(root, "sample_data")
                    if sd["is_key_frame"] and not (root / sd["filename"]).exists())
    assert n_missing == 6  # frames_per_scene of scene0, rows stay in sample_data


def test_without_annotations_omits_the_two_tables(tmp_path):
    root = make_nuscenes(tmp_path, with_annotations=False)
    assert not (root / "v1.0-mini" / "instance.json").exists()
    assert not (root / "v1.0-mini" / "sample_annotation.json").exists()
    assert (root / "v1.0-mini" / "visibility.json").exists()


def test_annotations_one_pedestrian_one_motorcycle_per_sample(tmp_path):
    root = make_nuscenes(tmp_path)
    cat = {c["token"]: c["name"] for c in _load(root, "category")}
    inst = {i["token"]: cat[i["category_token"]] for i in _load(root, "instance")}
    per_sample = {}
    for a in _load(root, "sample_annotation"):
        per_sample.setdefault(a["sample_token"], []).append(inst[a["instance_token"]])
    assert len(per_sample) == 12
    for cats in per_sample.values():
        assert sorted(cats) == ["human.pedestrian.adult", "vehicle.motorcycle"]


def test_without_lidar_has_no_lidar_rows_or_files(tmp_path):
    root = make_nuscenes(tmp_path, with_lidar=False)
    chan = _channels(root)
    assert "LIDAR_TOP" not in {chan[sd["calibrated_sensor_token"]]
                               for sd in _load(root, "sample_data")}
    assert not list((root / "samples").glob("LIDAR_TOP/*"))


def test_night_and_rain_descriptions(tmp_path):
    root = make_nuscenes(tmp_path, n_scenes=3, night_scenes=(0,), rain_scenes=(2,))
    desc = {s["name"]: s["description"] for s in _load(root, "scene")}
    assert "Night" in desc["scene0"] and "Rain" not in desc["scene0"]
    assert "Night" not in desc["scene1"] and "Rain" not in desc["scene1"]
    assert "Rain" in desc["scene2"]


def test_corrupt_writes_zero_byte_files(tmp_path):
    bad = "samples/CAM_FRONT/scene1_f2__CAM_FRONT.jpg"
    root = make_nuscenes(tmp_path, corrupt=[bad])
    assert (root / bad).is_file() and (root / bad).stat().st_size == 0


def test_sample_chain_is_followed_not_file_order(tmp_path):
    root = make_nuscenes(tmp_path)
    samples = {s["token"]: s for s in _load(root, "sample")}
    for sc in _load(root, "scene"):
        tok, order = sc["first_sample_token"], []
        while tok:
            order.append(tok)
            tok = samples[tok]["next"]
        assert len(order) == sc["nbr_samples"] == 6
    file_order = [s["token"] for s in _load(root, "sample")]
    assert set(file_order) == set(samples) and file_order != sorted(file_order)
