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


def _patch(pattern, dominant):
    img = np.full((40, 40, 3), 40, dtype=np.uint8)
    chan = 0 if dominant == "b" else 2
    img[:, :, chan] = np.clip(120 + pattern * 4, 0, 255).astype(np.uint8)
    return img


# 서로 다른 그레이 패턴 → 종류 간 교차 매칭 안 됨 (각자 자기 위치만 감지)
_PAT_A = ((_xx + _yy) % 16).astype(np.float32)            # 대각 줄무늬
_PAT_B = (((_xx // 4) % 2) * 15).astype(np.float32)       # 세로 굵은 줄무늬


def test_detect_per_monster_tags_and_independent_thresholds(tmp_path):
    from hunt_profile import MonsterEntry
    from monster_tracker import detect_per_monster, clear_template_cache
    clear_template_cache()

    dir_a = tmp_path / "A"; dir_a.mkdir()
    dir_b = tmp_path / "B"; dir_b.mkdir()
    blue = _patch(_PAT_A, "b")
    red = _patch(_PAT_B, "r")
    _write_png(str(dir_a / "A_left.png"), blue)
    _write_png(str(dir_b / "B_left.png"), red)

    frame = np.full((600, 800, 3), 60, dtype=np.uint8)
    frame[300:340, 100:140] = blue   # A 위치
    frame[300:340, 600:640] = red    # B 위치

    monsters = (
        MonsterEntry("A", str(dir_a), 0.9, 0.4, -20, color_confidence=0.5),
        MonsterEntry("B", str(dir_b), 0.9, 0.4, -20, color_confidence=0.0),
    )
    res = detect_per_monster(frame, monsters, scales=(1.0,))

    by_idx = {d[6]: d for d in res}
    assert set(by_idx.keys()) == {0, 1}
    assert 90 <= by_idx[0][0] <= 150   # A → 파랑 위치
    assert 590 <= by_idx[1][0] <= 650  # B → 빨강 위치
    clear_template_cache()


def test_tracker_uses_target_monster_settings():
    import types
    from hunt_profile import MonsterEntry
    from monster_tracker import MonsterTracker

    m0 = MonsterEntry("A", "images", 0.55, 0.40, -20, color_confidence=0.1)
    m1 = MonsterEntry("B", "images", 0.55, 0.30, -30, color_confidence=0.7)
    provider = types.SimpleNamespace(
        current=types.SimpleNamespace(monsters=(m0, m1))
    )
    t = MonsterTracker(profile_provider=provider)

    # 타겟 없음 → monsters[0] 폴백
    assert t._current_color_confidence() == 0.1
    assert t._current_tracking_confidence() == 0.40
    assert t._current_hp_bar_offset_y() == -20

    # 타겟이 B(idx1) → B 설정
    t.current_monster_idx = 1
    assert t._current_color_confidence() == 0.7
    assert t._current_tracking_confidence() == 0.30
    assert t._current_hp_bar_offset_y() == -30
