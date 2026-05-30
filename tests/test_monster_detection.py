import os
import cv2
import numpy as np

import monster_tracker
from monster_tracker import _load_templates, clear_template_cache


def _write_png(path, img):
    ok, buf = cv2.imencode(".png", img)
    assert ok
    with open(path, "wb") as f:
        f.write(buf.tobytes())


def test_load_templates_from_korean_dir(tmp_path):
    clear_template_cache()
    korean_dir = tmp_path / "여포기마병"
    korean_dir.mkdir()
    img = np.full((30, 40, 3), (50, 90, 130), dtype=np.uint8)
    _write_png(str(korean_dir / "기마병_left.png"), img)

    templates = _load_templates(str(korean_dir))
    # left → right 자동 반전 포함 2개
    assert len(templates) == 2
    names = {os.path.basename(t[0]) for t in templates}
    assert "기마병_left.png" in names
    clear_template_cache()
