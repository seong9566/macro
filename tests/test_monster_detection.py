import os
import cv2
import numpy as np

import monster_tracker
from monster_tracker import _load_templates, clear_template_cache, detect_monsters


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


# 텍스처(분산) 있는 패치. TM_CCOEFF_NORMED는 밝기/대비 불변이라 같은 패턴을
# 다른 색 채널에 넣으면 두 패치의 그레이스케일은 모두 템플릿과 ~1.0 상관(둘 다 감지)되고,
# 색(HSV)만 달라 색상 게이트가 색 불일치 후보를 제거하는지 검증한다.
# 주의: 단색 패치는 분산 0 → CCOEFF_NORMED 분모 0으로 degenerate하므로 금지.
_yy, _xx = np.mgrid[0:40, 0:40]
_PAT = ((_xx + _yy) % 16).astype(np.float32)


def _textured_patch(dominant):
    """dominant: 'b'(파랑) 또는 'r'(빨강). 같은 패턴, 다른 색 채널."""
    img = np.full((40, 40, 3), 40, dtype=np.uint8)
    chan = 0 if dominant == "b" else 2  # BGR: 0=B, 2=R
    img[:, :, chan] = np.clip(120 + _PAT * 4, 0, 255).astype(np.uint8)
    return img


def test_detect_monsters_color_gate_filters_mismatch():
    frame = np.full((600, 800, 3), 60, dtype=np.uint8)  # 회색 배경
    blue = _textured_patch("b")
    red = _textured_patch("r")
    frame[300:340, 100:140] = blue   # 파랑 (진짜)
    frame[300:340, 600:640] = red    # 빨강 (패턴 동일, 색 다름)

    blue_gray = cv2.cvtColor(blue, cv2.COLOR_BGR2GRAY)
    templates = [("fake/mon_left.png", blue, blue_gray)]

    off = detect_monsters(frame, templates, confidence=0.9,
                          scales=(1.0,), color_confidence=0.0)
    assert len(off) >= 2

    on = detect_monsters(frame, templates, confidence=0.9,
                         scales=(1.0,), color_confidence=0.5)
    assert len(on) == 1
    assert 90 <= on[0][0] <= 150
