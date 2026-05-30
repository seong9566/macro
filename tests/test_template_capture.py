import os
import cv2
import numpy as np
import pytest

from template_capture import imread_unicode


def test_imread_unicode_reads_korean_path(tmp_path):
    korean_dir = tmp_path / "여포기마병"
    korean_dir.mkdir()
    fpath = str(korean_dir / "기마병_left.png")

    img = np.full((20, 30, 3), (40, 80, 120), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    with open(fpath, "wb") as f:
        f.write(buf.tobytes())

    loaded = imread_unicode(fpath)
    assert loaded is not None
    assert loaded.shape == (20, 30, 3)


def test_imread_unicode_missing_file_returns_none():
    assert imread_unicode("존재하지_않는_파일.png") is None


from template_capture import display_rect_to_image_rect, save_template


def test_display_rect_to_image_rect_scales_up():
    rect = display_rect_to_image_rect(
        disp_rect=(50, 30, 100, 60),
        disp_size=(400, 300),
        img_size=(800, 600),
    )
    assert rect == (100, 60, 200, 120)


def test_display_rect_to_image_rect_clamps_to_bounds():
    rect = display_rect_to_image_rect(
        disp_rect=(380, 280, 100, 100),
        disp_size=(400, 300),
        img_size=(400, 300),
    )
    x, y, w, h = rect
    assert x + w <= 400
    assert y + h <= 300
    assert w >= 0 and h >= 0


def test_save_template_writes_crop(tmp_path):
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[20:60, 10:50] = (10, 120, 200)
    target = str(tmp_path / "여포기마병")

    path = save_template(frame, (10, 20, 40, 40), target, "기마병_left.png")
    assert os.path.exists(path)

    loaded = imread_unicode(path)
    assert loaded is not None
    assert loaded.shape == (40, 40, 3)


def test_save_template_empty_rect_raises(tmp_path):
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        save_template(frame, (10, 10, 0, 0), str(tmp_path), "x.png")
