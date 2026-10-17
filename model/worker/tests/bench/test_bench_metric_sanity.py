"""G-M: ảnh rỗng không có điểm; chọn đúng vật bị bỏ sót đạt oracle."""
import pandas as pd

from c4.bench.metrics import empty_rate, struggle_frames, sy
from c4.rare.eval import oracle_instance


def test_empty_zero_and_missed_object_oracle():
    objs = pd.DataFrame(dict(sample_token=["hard", "hard", "easy"],
                             instance_token=["i1", "i2", "i3"], scene_token=["s"] * 3))
    st = objs.assign(struggle=[True, True, False])
    tf = struggle_frames(st)
    pool = ["empty", "hard", "easy"]
    assert sy(["empty"], tf) == 0
    assert empty_rate(["empty"], objs) == 1
    assert sy(["hard"], tf) == sy(oracle_instance(pool, 1, tf), tf) == 2
