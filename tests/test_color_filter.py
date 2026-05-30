import numpy as np

from color_filter import color_match_score, filter_by_color


def _solid(bgr, h=40, w=40):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = bgr
    return img


def test_color_match_same_color_high_score():
    blue = _solid((200, 50, 50))
    assert color_match_score(blue, blue) > 0.9


def test_color_match_different_color_low_score():
    blue = _solid((200, 50, 50))
    red = _solid((40, 40, 200))
    assert color_match_score(blue, red) < 0.5


def test_color_match_empty_returns_negative():
    blue = _solid((200, 50, 50))
    empty = np.zeros((0, 0, 3), dtype=np.uint8)
    assert color_match_score(empty, blue) == -1.0


def test_filter_by_color_removes_color_mismatch():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[30:70, 10:50] = (200, 50, 50)    # 파랑
    frame[30:70, 150:190] = (40, 40, 200)  # 빨강

    blue_tmpl = _solid((200, 50, 50))
    results = [
        (10, 30, 40, 40, 0.9, "mon_left.png"),
        (150, 30, 40, 40, 0.9, "mon_left.png"),
    ]
    name_to_color = {"mon_left.png": blue_tmpl}

    kept = filter_by_color(frame, results, name_to_color, threshold=0.5)
    assert len(kept) == 1
    assert kept[0][0] == 10


def test_filter_by_color_disabled_passthrough():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    results = [(0, 0, 10, 10, 0.9, "x.png")]
    assert filter_by_color(frame, results, {}, threshold=0.0) == results
