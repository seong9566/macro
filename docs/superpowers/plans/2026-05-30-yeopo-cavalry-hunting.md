# 여러 몬스터 사냥 지원 (여포기마병 포함) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 게임에 여러 종류의 몬스터가 있을 수 있음을 전제로, 사용자가 각 몬스터(여포기마병 등)를 앱에서 직접 캡처·등록하고 **종류마다 독립적인 감지/색상 임계값**으로 사냥하며, 미리보기에서 모든 등록 몬스터가 정확히 표시되도록 만든다.

**Architecture:** 네 갈래. (1) 한글 경로 대응 유니코드 이미지 I/O로 한글 폴더 템플릿이 실제 로딩되게 한다. (2) **몬스터별 독립 감지** — `detect_per_monster()`가 각 MonsterEntry를 자기 `detect_confidence`/`color_confidence`로 감지하고 `monster_idx`를 태깅, 합쳐서 종류 간 NMS를 적용한다. tracker는 `current_monster_idx`로 현재 타겟의 몬스터 정체를 기억해 추적/HP/색상 설정을 그 몬스터 기준으로 쓴다. (3) HSV 색상 히스토그램 게이트로 갈색 배경/게시판/수레 오탐을 종류별로 제거한다. (4) PyQt6 크롭 다이얼로그로 게임 화면에서 바로 템플릿을 잘라 저장하고, 미리보기를 등록 몬스터 기반으로 고친다. 순수 로직은 pytest로, GUI/비전은 수동 실행으로 검증한다.

**Tech Stack:** Python, OpenCV(opencv-python/contrib), NumPy, PyQt6, pytest. 기존 모듈: `monster_tracker.py`, `hunt_profile.py`, `profile_manager.py`, `macro_ui.py`, `screen_capture.py`, `macro_engine.py`.

---

## File Structure

새로 만들거나 손대는 파일과 책임:

- **Create `template_capture.py`** — 순수 로직: `imread_unicode()`(한글 경로 안전 읽기), `save_template()`(한글 경로 안전 쓰기 + 크롭 저장), `display_rect_to_image_rect()`(미리보기 좌표 → 원본 이미지 좌표 변환). GUI 의존성 없음 → 단위 테스트.
- **Create `color_filter.py`** — `color_match_score()`(HSV 히스토그램 상관도), `filter_by_color()`(색상 게이트). GUI 의존성 없음 → 단위 테스트.
- **Modify `hunt_profile.py`** — `MonsterEntry`에 `color_confidence: float = 0.0` 필드 추가(기본값으로 하위 호환).
- **Modify `monster_tracker.py`** — `_load_templates()`가 `imread_unicode` 사용. `detect_monsters()`에 `color_confidence` 파라미터. **신설 `detect_per_monster()`** (몬스터별 임계값 + monster_idx 태깅 + 종류 간 NMS). `MonsterTracker`에 `current_monster_idx`/`_target_monster()` + `_current_*` 헬퍼가 타겟 몬스터 우선, `detect()`/`_detect_nearest_available()`/`find_and_track()`/`_detect_in_roi()`가 몬스터별로 동작.
- **Modify `macro_ui.py`** — `CropDialog`/`_CropLabel`, 몬스터 탭 "화면에서 캡처" 버튼 + 색상 임계값 슬라이더, `_capture_preview()`를 `detect_per_monster` 기반으로 교체 + "감지 테스트" 체크박스.
- **Create `tests/test_template_capture.py`**, **`tests/test_color_filter.py`**, **`tests/test_monster_detection.py`** — 순수 로직 검증.

각 Task는 독립적으로 동작·검증 가능하다. Phase 순서대로 진행하면 의존성이 충족된다.

**핵심 데이터 형식 변경:** 몬스터별 감지를 위해 감지 결과 튜플을 확장한다.
- `detect_monsters()` / `detect_wolves()`: 기존대로 **6-튜플** `(x, y, w, h, score, name)` (하위 호환 유지).
- `detect_per_monster()` 및 `MonsterTracker.detect()`: **7-튜플** `(x, y, w, h, score, name, monster_idx)`. `monster_idx`는 `profile.monsters` 내 인덱스(폴백/레거시는 -1).

---

## Phase A — 유니코드 이미지 I/O (한글 폴더/파일명 대응)

> **왜 먼저인가:** `cv2.imread`/`cv2.imwrite`는 Windows에서 한글 경로를 처리하지 못해 조용히 실패한다. 프로젝트 루트가 `바탕 화면`이고 몬스터 폴더가 `images/여포기마병/`이 될 수 있으므로, 이 문제를 먼저 해결하지 않으면 이후 모든 감지가 무의미하다.

### Task 1: `template_capture.py` — 유니코드 안전 읽기

**Files:**
- Create: `template_capture.py`
- Test: `tests/test_template_capture.py`

- [ ] **Step 1: 테스트 디렉토리 준비**

Windows PowerShell: `New-Item -ItemType Directory -Force tests`

- [ ] **Step 2: 실패하는 테스트 작성 — 한글 경로 읽기**

Create `tests/test_template_capture.py`:

```python
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
```

- [ ] **Step 3: 테스트 실행하여 실패 확인**

Run: `python -m pytest tests/test_template_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'template_capture'`

- [ ] **Step 4: 최소 구현 작성**

Create `template_capture.py`:

```python
"""
템플릿 캡처/저장 유틸 — 순수 로직 (GUI 의존성 없음).

- imread_unicode / save_template: Windows 한글 경로 대응 이미지 I/O.
  (cv2.imread/imwrite는 한글 경로에서 조용히 실패하므로 np.fromfile +
   cv2.imdecode / cv2.imencode + open(wb) 조합으로 우회.)
- display_rect_to_image_rect: 미리보기(축소 표시) 좌표를 원본 이미지 좌표로 변환.
"""
import os
import cv2
import numpy as np


def imread_unicode(path, flags=cv2.IMREAD_COLOR):
    """
    한글 등 비ASCII 경로를 안전하게 읽는다.

    Returns:
        numpy.ndarray (BGR) 또는 None (파일 없음/디코드 실패).
    """
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, flags)
    except Exception:
        return None
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_template_capture.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: 커밋**

```bash
git add template_capture.py tests/test_template_capture.py
git commit -m "feat: template_capture — 한글 경로 안전 imread_unicode"
```

---

### Task 2: `monster_tracker._load_templates`를 유니코드 읽기로 교체

**Files:**
- Modify: `monster_tracker.py:82` (`cv2.imread(fpath)` 호출부) + 상단 import
- Test: `tests/test_monster_detection.py`

- [ ] **Step 1: 실패하는 테스트 작성 — 한글 폴더 템플릿 로딩**

Create `tests/test_monster_detection.py`:

```python
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
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

Run: `python -m pytest tests/test_monster_detection.py::test_load_templates_from_korean_dir -v`
Expected: FAIL — `assert 0 == 2` (cv2.imread가 한글 경로에서 None 반환)

- [ ] **Step 3: `_load_templates`의 imread 교체**

`monster_tracker.py` 상단 import에 추가 (`from logger import log` 위 줄, line 26 부근):

```python
from template_capture import imread_unicode
```

`monster_tracker.py:82`의:

```python
            tmpl_color = cv2.imread(fpath)
```

다음으로 교체:

```python
            tmpl_color = imread_unicode(fpath)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_monster_detection.py::test_load_templates_from_korean_dir -v`
Expected: PASS

- [ ] **Step 5: 전체 테스트 실행**

Run: `python -m pytest tests/ -v`
Expected: 모두 PASS

- [ ] **Step 6: 커밋**

```bash
git add monster_tracker.py tests/test_monster_detection.py
git commit -m "fix: 템플릿 로딩 한글 경로 대응 (cv2.imread → imread_unicode)"
```

---

## Phase B — 색상 필터 + 몬스터별 독립 튜닝

> **왜 필요한가:** (1) 그레이스케일 매칭은 형태만 본다. 여포기마병의 갈색 말 몸통은 게시판·수레·흙바닥과 회색조가 비슷해 오탐이 난다. HSV 색상 상관도로 거른다. (2) 게임에는 여러 종류의 몬스터가 동시에 나올 수 있고, 종류마다 적절한 임계값이 다르다. 감지·추적을 몬스터별로 분리해 각자 자기 설정을 쓰게 한다.

### Task 3: `color_filter.py` — 색상 상관도 + 필터

**Files:**
- Create: `color_filter.py`
- Test: `tests/test_color_filter.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/test_color_filter.py`:

```python
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
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

Run: `python -m pytest tests/test_color_filter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'color_filter'`

- [ ] **Step 3: 최소 구현 작성**

Create `color_filter.py`:

```python
"""
색상 확인 필터 — 그레이스케일 템플릿 매칭의 오탐을 HSV 색상 히스토그램
상관도로 제거한다. detect_monsters가 NMS 뒤에 적용.

threshold <= 0 이면 비활성(모든 후보 통과).
"""
import cv2
import numpy as np

_H_BINS = 50
_S_BINS = 60
_RANGES = [0, 180, 0, 256]
_CHANNELS = [0, 1]


def color_match_score(roi_bgr, template_bgr):
    """
    두 BGR 이미지의 HSV(H-S) 히스토그램 상관도를 반환.

    Returns:
        float — cv2.HISTCMP_CORREL 결과 (-1.0~1.0). 높을수록 색 분포 유사.
        둘 중 하나라도 비어 있으면 -1.0.
    """
    if roi_bgr is None or template_bgr is None:
        return -1.0
    if roi_bgr.size == 0 or template_bgr.size == 0:
        return -1.0

    hsv_roi = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    hsv_tmpl = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2HSV)

    hist_roi = cv2.calcHist([hsv_roi], _CHANNELS, None, [_H_BINS, _S_BINS], _RANGES)
    hist_tmpl = cv2.calcHist([hsv_tmpl], _CHANNELS, None, [_H_BINS, _S_BINS], _RANGES)
    cv2.normalize(hist_roi, hist_roi, 0, 1, cv2.NORM_MINMAX)
    cv2.normalize(hist_tmpl, hist_tmpl, 0, 1, cv2.NORM_MINMAX)

    return float(cv2.compareHist(hist_roi, hist_tmpl, cv2.HISTCMP_CORREL))


def filter_by_color(frame_bgr, results, name_to_color, threshold):
    """
    감지 결과를 색상 상관도로 필터링.

    Args:
        frame_bgr: 전체 BGR 프레임
        results: [(x, y, w, h, score, name), ...]
        name_to_color: {template_name: BGR 템플릿 이미지}
        threshold: 색상 상관도 임계값. <= 0 이면 비활성(원본 그대로 반환).

    Returns:
        필터링된 results (입력과 동일 형식)
    """
    if threshold <= 0:
        return results

    kept = []
    for item in results:
        x, y, w, h, score, name = item[:6]
        tmpl_color = name_to_color.get(name)
        if tmpl_color is None:
            kept.append(item)
            continue
        roi = frame_bgr[max(0, y):y + h, max(0, x):x + w]
        if color_match_score(roi, tmpl_color) >= threshold:
            kept.append(item)
    return kept
```

> 참고: `item[:6]`로 언패킹하므로 6-튜플과 7-튜플(monster_idx 포함) 모두 처리 가능하고, 원본 `item`을 그대로 보존해 태그가 유지된다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_color_filter.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add color_filter.py tests/test_color_filter.py
git commit -m "feat: color_filter — HSV 히스토그램 색상 확인 필터"
```

---

### Task 4: `MonsterEntry`에 `color_confidence` 필드 추가

**Files:**
- Modify: `hunt_profile.py:11-18` (`MonsterEntry`)
- Test: `tests/test_color_filter.py`

- [ ] **Step 1: 실패하는 테스트 작성 — 하위 호환 로딩**

`tests/test_color_filter.py` 끝에 추가:

```python
def test_monster_entry_color_confidence_default():
    from hunt_profile import MonsterEntry
    legacy = {
        "name": "wolf",
        "template_dir": "images",
        "detect_confidence": 0.55,
        "tracking_confidence": 0.40,
        "hp_bar_offset_y": -20,
    }
    m = MonsterEntry(**legacy)
    assert m.color_confidence == 0.0
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

Run: `python -m pytest tests/test_color_filter.py::test_monster_entry_color_confidence_default -v`
Expected: FAIL — `AttributeError: 'MonsterEntry' object has no attribute 'color_confidence'`

- [ ] **Step 3: 필드 추가**

`hunt_profile.py:11-18`의 `MonsterEntry`를:

```python
@dataclass(frozen=True)
class MonsterEntry:
    """단일 몬스터 종류의 검출 설정."""
    name: str                      # 표시명, 예: "wolf"
    template_dir: str              # 템플릿 폴더, 예: "images/wolf"
    detect_confidence: float       # 0.0~1.0, 전체 프레임 감지 임계값
    tracking_confidence: float     # 0.0~1.0, ROI 재탐색 임계값
    hp_bar_offset_y: int           # bbox 상단 기준 (음수 = 위쪽)
```

다음으로 교체:

```python
@dataclass(frozen=True)
class MonsterEntry:
    """단일 몬스터 종류의 검출 설정."""
    name: str                      # 표시명, 예: "wolf"
    template_dir: str              # 템플릿 폴더, 예: "images/wolf"
    detect_confidence: float       # 0.0~1.0, 전체 프레임 감지 임계값
    tracking_confidence: float     # 0.0~1.0, ROI 재탐색 임계값
    hp_bar_offset_y: int           # bbox 상단 기준 (음수 = 위쪽)
    color_confidence: float = 0.0  # HSV 색상 상관도 게이트 (0=비활성, 권장 0.3~0.5)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_color_filter.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 기존 default.json 로딩 회귀 확인**

Run: `python -c "from hunt_profile import load_profile; p = load_profile('profiles/default.json'); print([(m.name, m.color_confidence) for m in p.monsters])"`
Expected: 오류 없이 출력, `color_confidence`가 `0.0`

- [ ] **Step 6: 커밋**

```bash
git add hunt_profile.py tests/test_color_filter.py
git commit -m "feat: MonsterEntry.color_confidence 필드 (기본값 0.0, 하위 호환)"
```

---

### Task 5: `detect_monsters`에 색상 게이트 파라미터 추가

> 이 함수는 다음 Task의 `detect_per_monster`가 몬스터별로 재사용한다.

**Files:**
- Modify: `monster_tracker.py:269-326` (`detect_monsters`)
- Test: `tests/test_monster_detection.py`

- [ ] **Step 1: 실패하는 테스트 작성 — 색상 게이트가 오탐 제거**

`tests/test_monster_detection.py` 끝에 추가:

```python
from monster_tracker import detect_monsters

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
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

Run: `python -m pytest tests/test_monster_detection.py::test_detect_monsters_color_gate_filters_mismatch -v`
Expected: FAIL — `TypeError: detect_monsters() got an unexpected keyword argument 'color_confidence'`

- [ ] **Step 3: `detect_monsters` 시그니처 + 색상 게이트 추가**

`monster_tracker.py:269`의:

```python
def detect_monsters(frame, templates, confidence=0.55, scales=None):
```

다음으로 교체:

```python
def detect_monsters(frame, templates, confidence=0.55, scales=None,
                    color_confidence=0.0):
```

그리고 `monster_tracker.py:319-326`의:

```python
    picked = _nms_with_scores(bboxes, scores, overlap_thresh=0.3)
    results = []
    for i in picked:
        x, y, w, h = bboxes[i]
        results.append((x, y, w, h, scores[i], names[i]))
    if results:
        log.debug(f"몬스터 감지: {len(results)}마리 (template pool {len(templates)}개)")
    return results
```

다음으로 교체:

```python
    picked = _nms_with_scores(bboxes, scores, overlap_thresh=0.3)
    results = []
    for i in picked:
        x, y, w, h = bboxes[i]
        results.append((x, y, w, h, scores[i], names[i]))

    # 색상 확인 필터 — 형태는 맞지만 색이 다른 오탐(갈색 게시판/수레 등) 제거
    if color_confidence > 0 and results:
        from color_filter import filter_by_color
        name_to_color = {os.path.basename(fp): col for fp, col, _gray in templates}
        before = len(results)
        results = filter_by_color(frame, results, name_to_color, color_confidence)
        if len(results) < before:
            log.debug(f"색상 필터: {before} → {len(results)}개 (임계값 {color_confidence:.2f})")

    if results:
        log.debug(f"몬스터 감지: {len(results)}마리 (template pool {len(templates)}개)")
    return results
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_monster_detection.py::test_detect_monsters_color_gate_filters_mismatch -v`
Expected: PASS

- [ ] **Step 5: import 회귀 확인**

Run: `python -c "import monster_tracker; print('import ok')"`
Expected: `import ok`

- [ ] **Step 6: 커밋**

```bash
git add monster_tracker.py tests/test_monster_detection.py
git commit -m "feat: detect_monsters color_confidence 파라미터 (색상 게이트)"
```

---

### Task 6: `detect_per_monster()` — 몬스터별 독립 감지

**Files:**
- Modify: `monster_tracker.py` (`detect_monsters` 함수 정의 바로 아래에 `detect_per_monster` 추가)
- Test: `tests/test_monster_detection.py`

- [ ] **Step 1: 실패하는 테스트 작성 — 몬스터별 임계값 + monster_idx 태깅**

`tests/test_monster_detection.py` 끝에 추가:

```python
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

    # 각 몬스터가 자기 위치에서 1개씩, monster_idx로 태깅됨
    by_idx = {d[6]: d for d in res}
    assert set(by_idx.keys()) == {0, 1}
    assert 90 <= by_idx[0][0] <= 150   # A → 파랑 위치
    assert 590 <= by_idx[1][0] <= 650  # B → 빨강 위치
    clear_template_cache()
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

Run: `python -m pytest tests/test_monster_detection.py::test_detect_per_monster_tags_and_independent_thresholds -v`
Expected: FAIL — `ImportError: cannot import name 'detect_per_monster'`

- [ ] **Step 3: `detect_per_monster` 구현**

`monster_tracker.py`의 `detect_monsters` 함수 정의가 끝나는 곳(`return results` 다음, `_nms_with_scores` 정의 앞)에 추가:

```python
def detect_per_monster(frame, monsters, scales=None):
    """
    각 MonsterEntry를 자기 임계값(detect_confidence, color_confidence)으로 감지하고
    monster_idx 태그를 붙여 합친 뒤, 종류 간 위치 겹침을 전체 NMS로 제거.

    Args:
        frame: BGR 프레임
        monsters: MonsterEntry 시퀀스 (profile.monsters)
        scales: 탐색 스케일 (None이면 DETECT_SCALES)

    Returns:
        [(x, y, w, h, score, name, monster_idx), ...]
    """
    merged = []
    for idx, m in enumerate(monsters):
        templates = _load_templates(m.template_dir)
        if not templates:
            continue
        res = detect_monsters(frame, templates, m.detect_confidence,
                              scales=scales, color_confidence=m.color_confidence)
        for r in res:
            merged.append((r[0], r[1], r[2], r[3], r[4], r[5], idx))

    if not merged:
        return []

    # 종류 간 같은 위치 중복 제거 (전체 NMS, 높은 점수 우선)
    bboxes = [(c[0], c[1], c[2], c[3]) for c in merged]
    scores = [c[4] for c in merged]
    picked = _nms_with_scores(bboxes, scores, overlap_thresh=0.3)
    results = [merged[i] for i in picked]
    if results:
        log.debug(f"몬스터별 감지: {len(results)}개 (종류 {len(monsters)})")
    return results
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_monster_detection.py::test_detect_per_monster_tags_and_independent_thresholds -v`
Expected: PASS

- [ ] **Step 5: 전체 테스트 확인**

Run: `python -m pytest tests/ -v`
Expected: 모두 PASS

- [ ] **Step 6: 커밋**

```bash
git add monster_tracker.py tests/test_monster_detection.py
git commit -m "feat: detect_per_monster — 몬스터별 임계값 + monster_idx 태깅 + 종류간 NMS"
```

---

### Task 7: `MonsterTracker` 몬스터별 추적 통합

> tracker가 현재 타겟이 어느 몬스터인지(`current_monster_idx`) 기억하고, 추적/HP/색상/ROI 템플릿을 그 몬스터 기준으로 쓰게 한다. `detect()`는 7-튜플을 반환한다.

**Files:**
- Modify: `monster_tracker.py` — `__init__`, `_current_confidence/_current_tracking_confidence/_current_color_confidence/_current_hp_bar_offset_y`, `_target_monster`(신규), `detect`, `_detect_in_roi`, `_detect_nearest_available`, `find_and_track`, `_reset_combat_state`
- Test: `tests/test_monster_detection.py`

- [ ] **Step 1: 실패하는 테스트 작성 — 타겟 몬스터 기준 설정 적용**

`tests/test_monster_detection.py` 끝에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

Run: `python -m pytest tests/test_monster_detection.py::test_tracker_uses_target_monster_settings -v`
Expected: FAIL — `AttributeError: 'MonsterTracker' object has no attribute 'current_monster_idx'`

- [ ] **Step 3: `__init__`에 `current_monster_idx` 추가**

`monster_tracker.py`의 `__init__` 안, `self.has_target = False` 줄(line 384 부근) 다음에 추가:

```python
        self.current_monster_idx = -1        # 현재 타겟이 어느 몬스터(profile.monsters 인덱스)인지. -1=미상
```

- [ ] **Step 4: `_target_monster()` 헬퍼 추가 + `_current_*` 헬퍼 교체**

`monster_tracker.py`의 `_current_confidence` 메서드(line 432 부근) **바로 위**에 추가:

```python
    def _target_monster(self):
        """현재 추적 타겟의 MonsterEntry. 없으면 None."""
        if self.profile_provider is None:
            return None
        monsters = self.profile_provider.current.monsters
        if 0 <= self.current_monster_idx < len(monsters):
            return monsters[self.current_monster_idx]
        return None
```

그리고 기존 `_current_confidence` ~ `_current_hp_bar_offset_y` 네 메서드(line 432-454)를 다음으로 교체 (타겟 몬스터 우선, 없으면 monsters[0], 없으면 config 폴백):

```python
    def _current_confidence(self) -> float:
        """타겟 몬스터 우선, 없으면 monsters[0], 없으면 정적값."""
        m = self._target_monster()
        if m is not None:
            return m.detect_confidence
        if self.profile_provider is not None:
            prof = self.profile_provider.current
            if prof.monsters:
                return prof.monsters[0].detect_confidence
        return self.confidence

    def _current_tracking_confidence(self) -> float:
        """타겟 몬스터 우선, 없으면 monsters[0], 없으면 config 폴백."""
        m = self._target_monster()
        if m is not None:
            return m.tracking_confidence
        if self.profile_provider is not None:
            prof = self.profile_provider.current
            if prof.monsters:
                return prof.monsters[0].tracking_confidence
        return TRACKING_CONFIDENCE

    def _current_color_confidence(self) -> float:
        """타겟 몬스터 우선, 없으면 monsters[0], 없으면 0.0(비활성)."""
        m = self._target_monster()
        if m is not None:
            return m.color_confidence
        if self.profile_provider is not None:
            prof = self.profile_provider.current
            if prof.monsters:
                return prof.monsters[0].color_confidence
        return 0.0

    def _current_hp_bar_offset_y(self) -> int:
        """타겟 몬스터 우선, 없으면 monsters[0], 없으면 config 폴백."""
        m = self._target_monster()
        if m is not None:
            return m.hp_bar_offset_y
        if self.profile_provider is not None:
            prof = self.profile_provider.current
            if prof.monsters:
                return prof.monsters[0].hp_bar_offset_y
        return HP_BAR_OFFSET_Y
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_monster_detection.py::test_tracker_uses_target_monster_settings -v`
Expected: PASS

- [ ] **Step 6: `_reset_combat_state`에서 타겟 몬스터 초기화**

`monster_tracker.py`의 `_reset_combat_state` 메서드(line 618-625) 끝에 추가:

```python
        self.current_monster_idx = -1
```

- [ ] **Step 7: `detect()`를 `detect_per_monster` 기반 7-튜플로 교체**

`monster_tracker.py:483-485`의:

```python
        # profile에 등록된 모든 monster의 템플릿을 합쳐 사용
        templates = _load_all_active_templates(self.profile_provider, self.template_dir)
        return detect_monsters(frame, templates, self._current_confidence())
```

다음으로 교체:

```python
        # profile에 등록된 monster들을 각자 임계값으로 감지 (7-튜플: monster_idx 포함)
        monsters = (self.profile_provider.current.monsters
                    if self.profile_provider is not None else ())
        if monsters:
            return detect_per_monster(frame, monsters)
        # 폴백: 레거시 단일 폴더 → monster_idx = -1
        templates = _load_templates(self.template_dir)
        res = detect_monsters(frame, templates, self._current_confidence())
        return [(r[0], r[1], r[2], r[3], r[4], r[5], -1) for r in res]
```

- [ ] **Step 8: `_detect_nearest_available`가 7-튜플을 반환하도록 교체**

`monster_tracker.py:909-944`의 `_detect_nearest_available` 메서드 전체를 다음으로 교체:

```python
    def _detect_nearest_available(self, frame=None, player_pos=None):
        """
        스킵 목록에 없는 가장 가까운 몬스터의 7-튜플을 반환.

        Returns:
            (x, y, w, h, score, name, monster_idx) 또는 None
        """
        dets = self.detect(frame=frame)  # 7-튜플 리스트
        if not dets:
            return None

        if player_pos is None:
            if self.region:
                px = self.region[2] // 2
                py = self.region[3] // 2
            else:
                px, py = 960, 540
        else:
            px, py = player_pos
            if self.region:
                px -= self.region[0]
                py -= self.region[1]

        dets.sort(key=lambda d: (d[0] + d[2] // 2 - px) ** 2 + (d[1] + d[3] // 2 - py) ** 2)

        for d in dets:
            bbox = (d[0], d[1], d[2], d[3])
            if not self._is_skipped(bbox):
                log.info(f"가장 가까운 몬스터: ({d[0]},{d[1]}) score={d[4]:.3f} "
                         f"[{d[5]}] idx={d[6]}")
                return d

        log.debug("모든 감지된 몬스터가 스킵 목록에 있음")
        return None
```

- [ ] **Step 9: `find_and_track`에서 타겟 몬스터 기록**

`monster_tracker.py:862-868`의:

```python
        # ROI 실패 시 전체 프레임 탐색
        # 추적 중이면 마지막 추적 위치 기준으로 가장 가까운 몬스터 선택 (타겟 고정)
        if bbox is None:
            last_pos = None
            if self.has_target and self.last_bbox is not None:
                last_pos = self._bbox_center_screen(self.last_bbox)
            bbox = self._detect_nearest_available(frame=frame, player_pos=last_pos)
```

다음으로 교체:

```python
        # ROI 실패 시 전체 프레임 탐색
        # 추적 중이면 마지막 추적 위치 기준으로 가장 가까운 몬스터 선택 (타겟 고정)
        if bbox is None:
            last_pos = None
            if self.has_target and self.last_bbox is not None:
                last_pos = self._bbox_center_screen(self.last_bbox)
            det = self._detect_nearest_available(frame=frame, player_pos=last_pos)
            if det is not None:
                bbox = (det[0], det[1], det[2], det[3])
                # 전체 프레임 감지로 새로 잡은 대상 → 타겟 몬스터 갱신
                self.current_monster_idx = det[6]
```

- [ ] **Step 10: `_detect_in_roi`가 타겟 몬스터 템플릿을 쓰도록 교체**

`monster_tracker.py:672`의 (그레이 패스 템플릿 로딩):

```python
        templates = _load_all_active_templates(self.profile_provider, self.template_dir)
```

다음으로 교체:

```python
        # 추적 중이면 타겟 몬스터 폴더만, 아니면 전체 등록 몬스터
        target = self._target_monster()
        roi_template_dir = target.template_dir if target is not None else self.template_dir
        if target is not None:
            templates = _load_templates(roi_template_dir)
        else:
            templates = _load_all_active_templates(self.profile_provider, self.template_dir)
```

`monster_tracker.py:717`의:

```python
            transparent = _load_transparent_templates(self.template_dir)
```

다음으로 교체:

```python
            transparent = _load_transparent_templates(roi_template_dir)
```

`monster_tracker.py:750`의:

```python
        edge_templates = _load_edge_templates(self.template_dir)
```

다음으로 교체:

```python
        edge_templates = _load_edge_templates(roi_template_dir)
```

- [ ] **Step 11: 전체 테스트 + import 회귀 확인**

Run: `python -m pytest tests/ -v`
Expected: 모두 PASS

Run: `python -c "import monster_tracker, macro_engine; print('import ok')"`
Expected: `import ok`

- [ ] **Step 12: 커밋**

```bash
git add monster_tracker.py tests/test_monster_detection.py
git commit -m "feat: MonsterTracker 몬스터별 추적 (current_monster_idx + 타겟 기준 설정/템플릿)"
```

---

## Phase C — 앱 내 템플릿 캡처 (크롭 도구)

> **왜 필요한가:** 외부 도구로 PNG를 잘라 올리는 과정이 번거롭다. 게임 화면을 앱에서 캡처해 드래그로 몬스터를 감싸면 바로 템플릿이 저장되게 한다.

### Task 8: 좌표 변환 + 템플릿 저장 (순수 로직)

**Files:**
- Modify: `template_capture.py`
- Test: `tests/test_template_capture.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_template_capture.py` 끝에 추가:

```python
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
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

Run: `python -m pytest tests/test_template_capture.py -v`
Expected: FAIL — `ImportError: cannot import name 'display_rect_to_image_rect'`

- [ ] **Step 3: 구현 추가**

`template_capture.py` 끝에 추가:

```python
def display_rect_to_image_rect(disp_rect, disp_size, img_size):
    """
    미리보기(축소 표시)에서 그린 사각형을 원본 이미지 좌표로 변환.

    Args:
        disp_rect: (x, y, w, h) 표시 좌표계 선택 영역
        disp_size: (disp_w, disp_h) 실제 표시된 픽스맵 크기
        img_size: (img_w, img_h) 원본 이미지 크기

    Returns:
        (x, y, w, h) 원본 좌표계 (경계로 클램프, 정수).
    """
    dx, dy, dw, dh = disp_rect
    disp_w, disp_h = disp_size
    img_w, img_h = img_size
    if disp_w <= 0 or disp_h <= 0:
        return (0, 0, 0, 0)

    sx = img_w / disp_w
    sy = img_h / disp_h
    x = int(round(dx * sx))
    y = int(round(dy * sy))
    w = int(round(dw * sx))
    h = int(round(dh * sy))

    x = max(0, min(x, img_w))
    y = max(0, min(y, img_h))
    w = max(0, min(w, img_w - x))
    h = max(0, min(h, img_h - y))
    return (x, y, w, h)


def save_template(frame_bgr, img_rect, target_dir, filename):
    """
    프레임에서 img_rect 영역을 잘라 target_dir/filename으로 저장 (한글 경로 안전).

    Raises:
        ValueError: 선택 영역이 비어 있음
        IOError: 인코딩/쓰기 실패
    """
    x, y, w, h = img_rect
    if w <= 0 or h <= 0:
        raise ValueError("선택 영역이 비어 있습니다")

    crop = frame_bgr[y:y + h, x:x + w]
    if crop.size == 0:
        raise ValueError("선택 영역이 비어 있습니다")

    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, filename)

    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        raise IOError(f"이미지 인코딩 실패: {path}")
    with open(path, "wb") as f:
        f.write(buf.tobytes())
    return path
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_template_capture.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add template_capture.py tests/test_template_capture.py
git commit -m "feat: template_capture — 좌표 변환 + 한글 경로 안전 템플릿 저장"
```

---

### Task 9: `CropDialog` / `_CropLabel` 위젯 (GUI)

**Files:**
- Modify: `macro_ui.py` (import 2곳 + `SkillAddDialog` 정의 위, line 134 부근)

> GUI라 수동 검증한다. 좌표 변환은 Task 8에서 단위 테스트됨.

- [ ] **Step 1: import 추가**

`macro_ui.py:29`의:

```python
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize
```

다음으로 교체:

```python
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize, QRect, QPoint
```

`macro_ui.py:22-28`의 QtWidgets import 블록 마지막 줄 `QDialog, QDialogButtonBox,`를:

```python
    QDialog, QDialogButtonBox,
)
```

다음으로 교체:

```python
    QDialog, QDialogButtonBox, QRubberBand,
)
```

- [ ] **Step 2: `_CropLabel` + `CropDialog` 추가**

`macro_ui.py`의 `# 스킬 추가 다이얼로그` 주석 블록(line 134) **바로 위**에 추가:

```python
# ══════════════════════════════════════════════
# 템플릿 캡처 — 크롭 다이얼로그
# ══════════════════════════════════════════════

class _CropLabel(QLabel):
    """드래그로 영역을 선택하는 QLabel. selection에 라벨 좌표계 QRect 보관."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self._origin = None
        self.selection = None  # QRect (라벨 좌표계)

    def mousePressEvent(self, ev):
        self._origin = ev.position().toPoint()
        self._rubber.setGeometry(QRect(self._origin, QSize()))
        self._rubber.show()

    def mouseMoveEvent(self, ev):
        if self._origin is not None:
            self._rubber.setGeometry(
                QRect(self._origin, ev.position().toPoint()).normalized()
            )

    def mouseReleaseEvent(self, ev):
        if self._origin is not None:
            self.selection = QRect(
                self._origin, ev.position().toPoint()
            ).normalized()
            self._origin = None


class CropDialog(QDialog):
    """
    캡처한 게임 프레임을 보여주고 드래그로 몬스터 영역을 선택하게 한다.
    OK 시 result_rect(원본 좌표) + direction을 채운다. 좌표 변환은 template_capture에 위임.
    """

    def __init__(self, frame_bgr, parent=None):
        super().__init__(parent)
        self.setWindowTitle("템플릿 영역 선택 — 드래그로 몬스터를 감싸세요")
        self._frame = frame_bgr
        self._img_h, self._img_w = frame_bgr.shape[:2]
        self.result_rect = None   # (x, y, w, h) 원본 좌표계
        self.direction = "left"

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "게임 화면에서 잡을 몬스터를 마우스로 드래그하세요. "
            "테두리는 여유 없이 몬스터(말+기수)에 딱 맞게."
        ))

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, self._img_w, self._img_h,
                      self._img_w * 3, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        max_w = 1100
        if pix.width() > max_w:
            pix = pix.scaledToWidth(max_w, Qt.TransformationMode.SmoothTransformation)
        self._disp_w, self._disp_h = pix.width(), pix.height()

        self.image_label = _CropLabel()
        self.image_label.setPixmap(pix)
        self.image_label.setFixedSize(self._disp_w, self._disp_h)
        layout.addWidget(self.image_label)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("방향(파일명 접미사):"))
        self.dir_combo = QComboBox()
        self.dir_combo.addItems([
            "left", "right", "top", "bottom",
            "left_top", "left_bottom", "right_top", "right_bottom",
        ])
        dir_row.addWidget(self.dir_combo)
        dir_row.addStretch()
        layout.addLayout(dir_row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        from PyQt6.QtWidgets import QMessageBox
        from template_capture import display_rect_to_image_rect
        sel = self.image_label.selection
        if sel is None or sel.width() < 5 or sel.height() < 5:
            QMessageBox.warning(self, "선택 없음", "몬스터 영역을 드래그로 선택하세요.")
            return
        self.result_rect = display_rect_to_image_rect(
            disp_rect=(sel.x(), sel.y(), sel.width(), sel.height()),
            disp_size=(self._disp_w, self._disp_h),
            img_size=(self._img_w, self._img_h),
        )
        self.direction = self.dir_combo.currentText()
        self.accept()

    def cropped_frame(self):
        """OK 후 호출 — 원본 프레임 반환 (저장은 호출자가 save_template로)."""
        return self._frame
```

- [ ] **Step 3: import 회귀 확인**

Run: `python -c "import macro_ui; print('import ok')"`
Expected: `import ok`

- [ ] **Step 4: 다이얼로그 단독 수동 검증**

프로젝트 루트에 `_tmp_crop_test.py` 저장 후 실행:

```python
import sys, numpy as np
from PyQt6.QtWidgets import QApplication
from macro_ui import CropDialog

app = QApplication(sys.argv)
frame = np.full((600, 800, 3), 60, dtype=np.uint8)
frame[250:350, 350:450] = (40, 90, 160)
dlg = CropDialog(frame)
if dlg.exec():
    print("result_rect:", dlg.result_rect, "direction:", dlg.direction)
else:
    print("취소됨")
```

Run: `python _tmp_crop_test.py`
Expected:
- 창에 회색 배경 + 색 블록
- 색 블록 드래그 시 러버밴드 사각형이 그려짐
- OK 시 콘솔에 `result_rect: (x, y, w, h) direction: left` (x≈350, y≈250 근처)

확인 후: `Remove-Item _tmp_crop_test.py`

- [ ] **Step 5: 커밋**

```bash
git add macro_ui.py
git commit -m "feat: macro_ui — CropDialog/_CropLabel 템플릿 크롭 다이얼로그"
```

---

### Task 10: 몬스터 탭에 "화면에서 캡처" 버튼 연결 (GUI)

**Files:**
- Modify: `macro_ui.py:978-986` (몬스터 탭 버튼 행) + `_on_monster_delete` 위에 메서드 추가

- [ ] **Step 1: 버튼 추가**

`macro_ui.py:979-986`의:

```python
        btn_row = QHBoxLayout()
        btn_add = QPushButton("몬스터 추가")
        btn_add.clicked.connect(self._on_monster_add)
        btn_del = QPushButton("선택 삭제")
        btn_del.clicked.connect(self._on_monster_delete)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        left.addLayout(btn_row)
```

다음으로 교체:

```python
        btn_row = QHBoxLayout()
        btn_add = QPushButton("몬스터 추가")
        btn_add.clicked.connect(self._on_monster_add)
        btn_capture = QPushButton("화면에서 캡처")
        btn_capture.clicked.connect(self._on_monster_capture)
        btn_del = QPushButton("선택 삭제")
        btn_del.clicked.connect(self._on_monster_delete)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_capture)
        btn_row.addWidget(btn_del)
        left.addLayout(btn_row)
```

- [ ] **Step 2: `_on_monster_capture` 메서드 추가**

`macro_ui.py`의 `_on_monster_delete` 메서드(line 1099 부근) **바로 위**에 추가:

```python
    def _on_monster_capture(self):
        """선택된 몬스터에 대해 게임 화면을 캡처 → 크롭 → 템플릿 저장."""
        from PyQt6.QtWidgets import QMessageBox
        from template_capture import save_template

        idx = self._selected_monster_index()
        if idx < 0:
            QMessageBox.information(
                self, "몬스터 선택",
                "먼저 좌측에서 몬스터를 선택하세요. (없으면 '몬스터 추가'로 만든 뒤)"
            )
            return

        monster = self.profile_manager.current.monsters[idx]

        if self.region is None:
            self.region = get_game_region(config.GAME_WINDOW_TITLE)
        if self.region is None:
            QMessageBox.warning(
                self, "게임 창 미발견",
                f"게임 창('{config.GAME_WINDOW_TITLE}')을 찾지 못했습니다."
            )
            return

        frame = capture_screen(region=self.region)
        if frame is None:
            QMessageBox.warning(self, "캡처 실패", "화면 캡처에 실패했습니다.")
            return

        dlg = CropDialog(frame, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.result_rect is None:
            return

        base = f"{monster.name}_{dlg.direction}"
        target_dir = monster.template_dir
        filename = f"{base}.png"
        n = 2
        while os.path.exists(os.path.join(target_dir, filename)):
            filename = f"{base}_{n}.png"
            n += 1

        try:
            path = save_template(dlg.cropped_frame(), dlg.result_rect,
                                 target_dir, filename)
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", str(e))
            return

        clear_template_cache()
        self._append_log("INFO", f"템플릿 캡처 저장: {path}")
        QMessageBox.information(
            self, "저장 완료", f"{filename} 저장됨\n폴더: {target_dir}"
        )
```

- [ ] **Step 3: import 회귀 확인**

Run: `python -c "import macro_ui; print('import ok')"`
Expected: `import ok`

- [ ] **Step 4: 수동 통합 검증 (게임 실행 필요)**

게임을 켠 상태에서 `python macro_ui.py`:
1. "몬스터" 탭 → "몬스터 추가"로 이름 `여포기마병` 입력 + 더미 PNG 1장 선택 → 목록 추가
2. `여포기마병` 선택 → "화면에서 캡처" → 여포기마병을 드래그 → 방향 left → OK
3. "저장 완료" + 로그 경로 출력
4. `Get-ChildItem images/여포기마병/` → 캡처 PNG 확인

- [ ] **Step 5: 커밋**

```bash
git add macro_ui.py
git commit -m "feat: macro_ui — 몬스터 탭 '화면에서 캡처' 버튼"
```

---

## Phase D — 미리보기 / 감지 테스트 / 색상 슬라이더

> **왜 필요한가:** `_capture_preview`가 `detect_wolves`로 기본 `images/`만 감지해 등록 몬스터가 안 보인다. 또 엔진을 켜야만 박스가 보여 임계값 튜닝이 어렵다. 종류별 색상 임계값도 UI에서 조절 가능해야 한다.

### Task 11: 미리보기를 `detect_per_monster` 기반으로 교체 + 감지 테스트 토글

**Files:**
- Modify: `macro_ui.py:34` (import), `macro_ui.py:471-481` (미리보기 그룹), `macro_ui.py:731-759` (`_capture_preview`)

- [ ] **Step 1: import 교체**

`macro_ui.py:34`의:

```python
from monster_tracker import MonsterTracker, detect_wolves, _load_templates, clear_template_cache
```

다음으로 교체:

```python
from monster_tracker import (
    MonsterTracker, detect_per_monster, _load_templates, clear_template_cache,
)
```

- [ ] **Step 2: 미리보기 그룹에 "감지 테스트" 체크박스 추가**

`macro_ui.py:472-479`의:

```python
        # [4] 우측: 게임 화면 미리보기
        preview_group = QGroupBox("게임 화면 미리보기")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel("캡처 대기중...")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setStyleSheet("background: #1a1a1a; border: 1px solid #333;")
        preview_layout.addWidget(self.preview_label)
        top_splitter.addWidget(preview_group)
```

다음으로 교체:

```python
        # [4] 우측: 게임 화면 미리보기
        preview_group = QGroupBox("게임 화면 미리보기")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel("캡처 대기중...")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setStyleSheet("background: #1a1a1a; border: 1px solid #333;")
        preview_layout.addWidget(self.preview_label)

        from PyQt6.QtWidgets import QCheckBox
        self.chk_detect_test = QCheckBox("감지 테스트 (엔진 정지 중에도 감지 박스 표시)")
        preview_layout.addWidget(self.chk_detect_test)
        top_splitter.addWidget(preview_group)
```

- [ ] **Step 3: `_capture_preview`의 감지 오버레이 교체**

`macro_ui.py:742-757`의:

```python
        # 몬스터 감지 결과 오버레이 (엔진이 돌고 있을 때만)
        if self.engine and self.engine.running:
            try:
                wolves = detect_wolves(frame, confidence=config.DETECT_CONFIDENCE)
                for (x, y, w, h, score, name) in wolves:
                    # 감지된 몬스터: 초록 사각형
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.putText(frame, f"{score:.2f}", (x, y - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

                # 현재 타겟 bbox: 빨간 사각형
                if self.engine.tracker.last_bbox:
                    bx, by, bw, bh = self.engine.tracker.last_bbox
                    cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
            except Exception:
                pass
```

다음으로 교체:

```python
        # 몬스터 감지 오버레이 — 엔진 가동 중이거나 '감지 테스트' 체크 시
        engine_running = bool(self.engine and self.engine.running)
        show_detect = engine_running or self.chk_detect_test.isChecked()
        if show_detect:
            try:
                monsters = self.profile_manager.current.monsters
                found = detect_per_monster(frame, monsters) if monsters else []
                for det in found:
                    x, y, w, h, score, name = det[:6]
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.putText(frame, f"{score:.2f}", (x, y - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

                # 현재 타겟 bbox: 빨간 사각형 (엔진 가동 중일 때만)
                if engine_running and self.engine.tracker.last_bbox:
                    bx, by, bw, bh = self.engine.tracker.last_bbox
                    cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
            except Exception:
                pass
```

- [ ] **Step 4: import 회귀 확인**

Run: `python -c "import macro_ui; print('import ok')"`
Expected: `import ok`

- [ ] **Step 5: 수동 검증 (게임 실행 필요)**

`python macro_ui.py`:
1. 여포기마병 등록 상태에서 "감지 테스트" ON
2. 엔진 미시작 상태에서도 미리보기에 여포기마병 위 초록 박스 + 점수
3. 두 종류 이상 등록 시 각각 박스가 뜨는지 확인
4. 감지 임계값 조절이 실시간 반영

- [ ] **Step 6: 커밋**

```bash
git add macro_ui.py
git commit -m "fix: 미리보기를 detect_per_monster 기반으로 교체 + 감지 테스트 토글"
```

---

### Task 12: 몬스터 탭에 색상 임계값 슬라이더 추가

**Files:**
- Modify: `macro_ui.py:988-1011` (상세 패널), `macro_ui.py:1025-1033` (`_on_monster_selected`), `_on_monster_confidence_changed` 아래 핸들러 추가

- [ ] **Step 1: 상세 패널에 색상 슬라이더 추가**

`macro_ui.py:988-1011`의 상세 설정 그룹 블록(현재 `right = QGroupBox("상세 설정")`부터 `l.addWidget(right, 2)`까지)을 다음으로 교체:

```python
        # 우측: 선택된 몬스터 상세 편집
        right = QGroupBox("상세 설정")
        rgrid = QGridLayout(right)
        self.mon_name = QLabel("(선택 없음)")
        self.mon_dir = QLabel("-")
        self.mon_conf = QSlider(Qt.Orientation.Horizontal)
        self.mon_conf.setRange(30, 95)
        self.mon_conf.setSingleStep(5)
        self.mon_conf_label = QLabel("0.55")
        self.mon_conf.valueChanged.connect(
            lambda v: self.mon_conf_label.setText(f"{v/100:.2f}")
        )
        self.mon_conf.sliderReleased.connect(self._on_monster_confidence_changed)

        self.mon_color = QSlider(Qt.Orientation.Horizontal)
        self.mon_color.setRange(0, 90)
        self.mon_color.setSingleStep(5)
        self.mon_color_label = QLabel("0.00 (꺼짐)")
        self.mon_color.valueChanged.connect(self._on_monster_color_label)
        self.mon_color.sliderReleased.connect(self._on_monster_color_changed)

        rgrid.addWidget(QLabel("이름:"), 0, 0)
        rgrid.addWidget(self.mon_name, 0, 1)
        rgrid.addWidget(QLabel("폴더:"), 1, 0)
        rgrid.addWidget(self.mon_dir, 1, 1)
        rgrid.addWidget(QLabel("감지 임계값:"), 2, 0)
        rgrid.addWidget(self.mon_conf, 2, 1)
        rgrid.addWidget(self.mon_conf_label, 2, 2)
        rgrid.addWidget(QLabel("색상 확인:"), 3, 0)
        rgrid.addWidget(self.mon_color, 3, 1)
        rgrid.addWidget(self.mon_color_label, 3, 2)

        l.addLayout(left, 1)
        l.addWidget(right, 2)
```

- [ ] **Step 2: `_on_monster_selected`에서 색상 슬라이더 동기화**

`macro_ui.py:1025-1033`의 `_on_monster_selected` 메서드를 다음으로 교체:

```python
    def _on_monster_selected(self):
        idx = self._selected_monster_index()
        if idx < 0:
            return
        m = self.profile_manager.current.monsters[idx]
        self.mon_name.setText(m.name)
        self.mon_dir.setText(m.template_dir)
        self.mon_conf.setValue(int(m.detect_confidence * 100))
        self.mon_conf_label.setText(f"{m.detect_confidence:.2f}")
        self.mon_color.setValue(int(m.color_confidence * 100))
        self._on_monster_color_label(int(m.color_confidence * 100))
```

- [ ] **Step 3: 색상 핸들러 2개 추가**

`macro_ui.py`의 `_on_monster_confidence_changed` 메서드(line 1109 부근) **바로 아래**에 추가:

```python
    def _on_monster_color_label(self, v: int):
        if v <= 0:
            self.mon_color_label.setText("0.00 (꺼짐)")
        else:
            self.mon_color_label.setText(f"{v/100:.2f}")

    def _on_monster_color_changed(self):
        idx = self._selected_monster_index()
        if idx < 0:
            return
        new_color = self.mon_color.value() / 100
        import dataclasses
        monsters = list(self.profile_manager.current.monsters)
        monsters[idx] = dataclasses.replace(monsters[idx], color_confidence=new_color)
        self.profile_manager.set_monsters(tuple(monsters))
```

- [ ] **Step 4: import 회귀 확인**

Run: `python -c "import macro_ui; print('import ok')"`
Expected: `import ok`

- [ ] **Step 5: 수동 검증**

`python macro_ui.py`:
1. 몬스터 탭 → 몬스터 선택 → "색상 확인" 슬라이더 표시
2. 0 → "0.00 (꺼짐)", 올리면 "0.35" 등
3. 두 종류 등록 시 각각 다른 색상값을 줄 수 있고, 선택 전환 시 값이 따라 바뀜
4. 색상 0.35 + "감지 테스트" ON → 게시판/수레 오탐 박스 감소
5. 프로필 저장 → 재시작 → 종류별 색상값 유지

- [ ] **Step 6: 커밋**

```bash
git add macro_ui.py
git commit -m "feat: macro_ui — 몬스터 탭 색상 확인 임계값 슬라이더 (종류별)"
```

---

## Phase E — 통합 검증 + 템플릿 전략 문서

### Task 13: 여포기마병 템플릿 전략 문서 + end-to-end 검증

**Files:**
- Create: `docs/여포기마병-템플릿-가이드.md`

- [ ] **Step 1: 전략 문서 작성**

Create `docs/여포기마병-템플릿-가이드.md`:

```markdown
# 여러 몬스터 등록 가이드 (여포기마병 포함)

## 기마 몬스터가 까다로운 이유
- "말 + 기수" 2층 구조라 늑대보다 크고, 방향(좌/우/상/하)마다 실루엣이 다르다.
- 말 몸통의 갈색이 수배서 게시판·부서진 수레·흙바닥과 회색조가 비슷해 오탐이 잘 난다.

## 권장 템플릿 전략
1. **앱에서 직접 캡처**: 몬스터 탭 → 몬스터 추가(이름 `여포기마병`) → "화면에서 캡처".
   외부 크롭 불필요. (한글 폴더/파일명 정상 동작.)
2. **딱 맞게 크롭**: 말+기수 전체에 테두리를 맞추고 바닥/배경은 최소화.
3. **방향은 left/top/bottom 위주**: left는 자동으로 right가 생성된다(좌우 반전).
   즉 left, top, bottom 3장이면 좌·우·상·하를 사실상 커버. 부족하면 대각 추가.
4. **네이티브 스케일로 캡처**: 평소 사냥 배율로 두고 캡처.

## 여러 종류를 동시에 잡기
- 몬스터를 종류별로 등록하면 **각자 자기 감지/색상 임계값**으로 감지된다.
  (예: 여포기마병은 색상확인 0.4 + 임계값 0.6, 늑대는 색상확인 0 + 임계값 0.5)
- 추적이 시작되면 매크로는 그 타겟의 종류 설정(추적 임계값·HP 오프셋·색상)을 사용한다.
- 화면에 여러 마리가 있으면 가장 가까운 대상을 먼저 잡고, 처치/타임아웃 시 다음 대상으로 전환.

## 권장 설정값 (몬스터 탭 상세 설정)
- **감지 임계값**: 0.55에서 시작. 오탐↑이면 0.6~0.65, 놓치면 0.5.
- **색상 확인**: 0.30~0.40 권장. 갈색 게시판/수레 오탐이 크게 준다.
  너무 높이면(0.6+) 조명/그림자 변화에 진짜도 걸러질 수 있다.

## 튜닝 절차
1. 종류별로 템플릿 2~3장 캡처(left/top/bottom).
2. "감지 테스트" 체크 → 엔진 정지 상태로 박스 확인.
3. 종류별 감지 임계값 + 색상 확인을 조절해 진짜만 박스가 뜨게.
4. 프로필 메뉴 → "현재 프로필 저장".
5. 게임에서 F5로 실사냥, 로그의 오탐/미감지 빈도로 미세 조정.
```

- [ ] **Step 2: 전체 자동 테스트 통과 확인**

Run: `python -m pytest tests/ -v`
Expected: 모든 테스트 PASS

- [ ] **Step 3: end-to-end 수동 검증 체크리스트 (게임 실행 필요)**

`python macro_ui.py` 실행 후:

1. [ ] 몬스터 추가 → `여포기마병` → 더미 PNG 1장 → 목록 추가
2. [ ] `여포기마병` 선택 → "화면에서 캡처" → left/top/bottom 각 1장 캡처 (`images/여포기마병/`에 3장)
3. [ ] **두 번째 종류**(예: `늑대`)도 등록 → 각자 다른 감지/색상 임계값 설정
4. [ ] "감지 테스트" ON → 미리보기에 두 종류 모두 박스 표시 확인
5. [ ] 여포기마병 색상 확인 0.35 → 게시판/수레 오탐 박스 감소 확인
6. [ ] 프로필 저장 → 재시작 → 종류별 설정 유지 확인
7. [ ] F5 사냥 시작 → 가까운 대상 공격, 처치 후 다음 대상 전환, 로그 "몬스터 감지 ... idx=" 확인
8. [ ] F6 중지

- [ ] **Step 4: 커밋**

```bash
git add docs/여포기마병-템플릿-가이드.md
git commit -m "docs: 여러 몬스터 등록/튜닝 가이드 (여포기마병)"
```

---

## 부록: 설계 노트 / 알려진 한계

- **몬스터별 독립 튜닝 완료**: 감지(`detect_per_monster`)는 종류별 `detect_confidence`/`color_confidence`를 쓰고, 추적은 `current_monster_idx`로 타겟 종류의 `tracking_confidence`/`color_confidence`/`hp_bar_offset_y`/ROI 템플릿을 쓴다.
- **색상 게이트는 전체 프레임 감지에서만 적용**: 추적 중 ROI 재탐색(`_detect_in_roi`)에는 색상 게이트를 적용하지 않는다 — 조명/그림자 변화로 추적 중 타겟을 놓치는 것을 피하기 위함. 추적 임계값(`tracking_confidence`)이 이미 낮게 설정돼 관대하다.
- **종류 간 NMS**: 서로 다른 종류가 같은 위치를 잡으면 높은 점수만 남긴다(`overlap_thresh=0.3`). 겹치는 종류를 등록할 때 한 마리가 한 종류로만 카운트됨.
- **`detect_wolves`/`detect_monsters`는 6-튜플로 보존**: 외부 호환을 위해 유지. 몬스터별 경로는 7-튜플(`detect_per_monster`/`tracker.detect`)을 쓴다.
- **HP바 오프셋**: 기마 몬스터는 키가 커서 종류별 `hp_bar_offset_y`가 다를 수 있다. 현재 UI 미노출 — 사망 판정이 빗나가면 후속 Task로 슬라이더 추가(`MonsterEntry`에 이미 필드 존재).
- **성능**: `detect_per_monster`는 종류 수만큼 `detect_monsters`를 호출한다. 종류가 매우 많으면(>5) 사이클 시간이 늘 수 있다. 필요 시 종류별 템플릿을 한 번에 매칭하도록 통합 최적화는 후속 과제.
```
