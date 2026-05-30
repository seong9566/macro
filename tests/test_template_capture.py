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
