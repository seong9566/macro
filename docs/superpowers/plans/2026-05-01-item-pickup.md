# 아이템 자동 줍기 (Frame Diff) 구현 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 늑대 사망 직후 ROI 차분으로 드롭 아이템 위치를 검출하여 자동으로 클릭 픽업하는 기능 추가

**Architecture:** `MonsterTracker`가 매 감지 성공 시 `CombatSnapshot`(roi+bbox+region+timestamp 묶음, frozen dataclass)을 갱신한다. `TRACK_KILLED` 시점에 `MacroEngine._loot_items()`가 스냅샷을 atomic 읽기로 가져와 `ItemPicker.try_pickup()`에 넘긴다. ItemPicker는 새 캡처를 떠서 같은 ROI를 잘라낸 뒤 차분→마스킹→블롭 필터링→클릭 순서로 처리한다. 시각 픽업 실패/스킵 시 기존 Spacebar 광역 픽업이 보험 역할.

**Tech Stack:** OpenCV (cv2 — absdiff, threshold, morphology, findContours), numpy, dataclasses (frozen=True), pytest

**관련 스펙:** `docs/superpowers/specs/2026-05-01-item-pickup-design.md`

---

## 파일 구조

| 파일 | 변경 유형 | 역할 |
|------|-----------|------|
| `requirements.txt` | 수정 | pytest 추가 |
| `tests/__init__.py` | 신규 | (빈 파일) |
| `tests/conftest.py` | 신규 | sys.path 설정으로 프로젝트 루트 import 가능 |
| `tests/test_item_picker.py` | 신규 | ItemPicker 순수 함수 단위 테스트 |
| `config.py` | 수정 | `LOOT_*` 시각 픽업 상수 추가 |
| `item_picker.py` | 신규 | `CombatSnapshot` dataclass + `build_snapshot()` + `ItemPicker` 클래스 |
| `monster_tracker.py` | 수정 | `combat_snapshot` 필드 추가, `find_and_track`/`refine_position`/`reset`/`_abandon_target` 갱신 |
| `macro_engine.py` | 수정 | `_loot_items()` 시각+Spacebar 2단계 재구성 |

---

### Task 1: pytest 셋업

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: pytest를 requirements.txt에 추가**

`requirements.txt` 마지막에 한 줄 추가:

```
pytest>=8.0.0
```

- [ ] **Step 2: pytest 설치**

```bash
pip install pytest>=8.0.0
```

기대 출력: `Successfully installed pytest-8.x.x ...`

- [ ] **Step 3: tests 디렉토리 + 초기화 파일 생성**

빈 `tests/__init__.py` 파일 생성 (내용 없음).

- [ ] **Step 4: conftest.py 작성 — 프로젝트 루트를 sys.path에 추가**

`tests/conftest.py`:

```python
"""테스트용 path 설정 — 프로젝트 루트의 모듈을 import 가능하게 함."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 5: pytest 동작 확인 (빈 테스트)**

`tests/test_smoke.py` (임시):

```python
def test_smoke():
    assert 1 + 1 == 2
```

실행:

```bash
pytest tests/test_smoke.py -v
```

기대 출력: `1 passed`

확인 후 `tests/test_smoke.py` 삭제.

- [ ] **Step 6: 커밋**

```bash
git add requirements.txt tests/__init__.py tests/conftest.py
git commit -m "chore: pytest 셋업 — tests/ 디렉토리 + conftest.py"
```

---

### Task 2: config.py에 LOOT_* 시각 픽업 상수 추가

**Files:**
- Modify: `config.py:62-69` (아이템 줍기 설정 섹션 확장)

- [ ] **Step 1: 기존 `LOOT_*` 섹션 아래에 시각 픽업 상수 추가**

`config.py`에서 `LOOT_DELAY_AFTER_KILL = 0.20` 줄 바로 아래(70번 줄 근처)에 다음 블록을 추가:

```python

# ── 시각 기반 픽업 (Frame Diff) ──
LOOT_VISUAL_ENABLED = True              # 차분 기반 픽업 활성화
LOOT_ROI_EXPAND_RATIO = 1.0             # bbox 크기 대비 ROI 확장 비율 (1.0 = 좌우상하 bbox 1개씩)
LOOT_CORPSE_MASK_RATIO = 1.0            # bbox 마스킹 비율 (1.0 = bbox 전체 영역 무시 — 시체 차분 제거)
LOOT_DIFF_THRESHOLD = 30                # 차분 그레이값 임계값 (0~255)
LOOT_MIN_BLOB_AREA = 30                 # 최소 블롭 면적 (px²) — 노이즈 컷
LOOT_MAX_BLOB_AREA = 2500               # 최대 블롭 면적 (px²) — 큰 객체 컷
LOOT_MAX_DISTANCE_RATIO = 1.5           # bbox 중심에서 블롭 중심까지 허용 거리 (× bbox 대각선 길이)
LOOT_MAX_TOTAL_DIFF_RATIO = 0.4         # ROI 픽셀 대비 차분 비율 상한 (초과 시 카메라/캐릭터 이동 판단, 픽업 스킵)
LOOT_SNAPSHOT_MAX_AGE = 0.6             # 베이스라인 최대 허용 나이 (초). 초과 시 시각 픽업 스킵
LOOT_AFTER_CLICK_DELAY = 0.3            # 픽업 클릭 후 대기 (캐릭터 이동/픽업 애니)
LOOT_DEBUG_SAVE = False                 # 차분 디버그 이미지 저장 (튜닝용 — 부담 큼, 평시 False)
LOOT_DEBUG_SAMPLE_RATIO = 0.1           # 디버그 저장 샘플링 비율 (0.1 = 10%만 저장, 1.0 = 전부)
LOOT_DEBUG_DIR = "debug_loot"           # 디버그 이미지 저장 폴더
```

- [ ] **Step 2: import 검증 (실행 안 해도 되지만 확인)**

```bash
python -c "from config import LOOT_VISUAL_ENABLED, LOOT_DIFF_THRESHOLD, LOOT_SNAPSHOT_MAX_AGE; print('OK')"
```

기대 출력: `OK`

- [ ] **Step 3: 커밋**

```bash
git add config.py
git commit -m "feat: config.py에 시각 기반 픽업(LOOT_*) 상수 추가"
```

---

### Task 3: CombatSnapshot dataclass + build_snapshot() (TDD)

**Files:**
- Create: `item_picker.py`
- Create: `tests/test_item_picker.py`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_item_picker.py`**

```python
"""ItemPicker 순수 함수 단위 테스트."""
import dataclasses
import numpy as np
import pytest

from item_picker import CombatSnapshot, build_snapshot, ItemPicker


# ══════════════════════════════════════════════
# CombatSnapshot / build_snapshot
# ══════════════════════════════════════════════

class TestBuildSnapshot:
    def test_normal_case_returns_snapshot_with_correct_roi(self):
        # 200×200 frame, bbox 중심 80~120
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        frame[80:120, 80:120] = 200  # 늑대 영역 마킹
        bbox = (80, 80, 40, 40)
        region = (100, 200, 200, 200)

        snap = build_snapshot(frame, bbox, region, expand_ratio=1.0)

        assert snap is not None
        assert snap.bbox == bbox
        assert snap.region == region
        # ROI = bbox ± bbox 크기 = (40, 40) ~ (160, 160) → 120×120
        assert snap.roi_origin == (40, 40)
        assert snap.roi.shape == (120, 120, 3)

    def test_clamps_roi_at_frame_edge(self):
        # bbox가 프레임 좌상단에 가까워 ROI 일부가 프레임 밖
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        bbox = (10, 10, 20, 20)
        # 이상적 ROI: (-10, -10) ~ (50, 50) → 프레임 경계로 클램핑 → (0, 0) ~ (50, 50)

        snap = build_snapshot(frame, bbox, (0, 0, 100, 100), expand_ratio=1.0)

        assert snap is not None
        assert snap.roi_origin == (0, 0)
        assert snap.roi.shape == (50, 50, 3)

    def test_returns_none_when_bbox_entirely_outside_frame(self):
        frame = np.zeros((50, 50, 3), dtype=np.uint8)
        bbox = (100, 100, 20, 20)  # 프레임 바깥

        snap = build_snapshot(frame, bbox, (0, 0, 50, 50), expand_ratio=1.0)

        assert snap is None

    def test_snapshot_is_frozen(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        snap = build_snapshot(frame, (40, 40, 20, 20), (0, 0, 100, 100), expand_ratio=1.0)

        with pytest.raises(dataclasses.FrozenInstanceError):
            snap.bbox = (0, 0, 10, 10)

    def test_roi_is_independent_copy(self):
        # frame을 수정해도 snapshot.roi는 영향 없어야 함
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        snap = build_snapshot(frame, (40, 40, 20, 20), (0, 0, 100, 100), expand_ratio=1.0)
        original_value = snap.roi[0, 0, 0]

        frame[:] = 255  # 원본 frame 전체를 흰색으로

        # snapshot의 roi는 변경 전 값(0) 유지
        assert snap.roi[0, 0, 0] == original_value
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/test_item_picker.py -v
```

기대: `ImportError: cannot import name 'CombatSnapshot' from 'item_picker'` (모듈 자체가 없음)

- [ ] **Step 3: `item_picker.py` 신규 작성 — dataclass + build_snapshot**

```python
"""
프레임 차분 기반 아이템 자동 줍기.

설계 문서: docs/superpowers/specs/2026-05-01-item-pickup-design.md
"""
import os
import time
import random
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from screen_capture import capture_screen
from clicker import click
from logger import log
from config import (
    LOOT_DIFF_THRESHOLD, LOOT_CORPSE_MASK_RATIO,
    LOOT_MIN_BLOB_AREA, LOOT_MAX_BLOB_AREA,
    LOOT_MAX_DISTANCE_RATIO, LOOT_MAX_TOTAL_DIFF_RATIO,
    LOOT_SNAPSHOT_MAX_AGE,
    LOOT_DEBUG_SAVE, LOOT_DEBUG_SAMPLE_RATIO, LOOT_DEBUG_DIR,
)


# ══════════════════════════════════════════════
# CombatSnapshot — frame/bbox/region/timestamp를 atomic 묶음
# ══════════════════════════════════════════════

@dataclass(frozen=True)
class CombatSnapshot:
    """
    베이스라인 스냅샷 — 같은 캡처에서 잘라낸 ROI + 그 시점의 bbox/region/timestamp.
    frozen=True로 부분 갱신 차단 → 통째 교체만 허용 (스레드 race 회피).
    """
    roi: np.ndarray                              # ROI 슬라이스 복사본 (BGR)
    roi_origin: Tuple[int, int]                  # frame-local ROI 좌상단 (rx, ry)
    bbox: Tuple[int, int, int, int]              # frame-local bbox (x, y, w, h)
    region: Tuple[int, int, int, int]            # 캡처 시점 게임 창 region (스크린)
    timestamp: float                             # time.time() 캡처 시각


def build_snapshot(frame: np.ndarray,
                   bbox: Tuple[int, int, int, int],
                   region: Tuple[int, int, int, int],
                   expand_ratio: float) -> Optional[CombatSnapshot]:
    """
    frame과 bbox로 ROI 잘라 스냅샷 생성.

    bbox 영역을 ±(bbox_w * expand_ratio, bbox_h * expand_ratio)만큼 확장한
    영역을 ROI로 사용. 프레임 경계로 클램핑. ROI 면적 0이면 None.

    Args:
        frame: BGR 프레임 (frame-local 좌표 기준)
        bbox: (x, y, w, h) frame-local
        region: 게임 창 (rx, ry, rw, rh) — 좌표 변환 검증용
        expand_ratio: bbox 크기 대비 ROI 확장 비율

    Returns:
        CombatSnapshot 또는 None (ROI 면적 0)
    """
    bx, by, bw, bh = bbox
    ex_x = int(bw * expand_ratio)
    ex_y = int(bh * expand_ratio)

    rx1 = max(0, bx - ex_x)
    ry1 = max(0, by - ex_y)
    rx2 = min(frame.shape[1], bx + bw + ex_x)
    ry2 = min(frame.shape[0], by + bh + ex_y)

    if rx2 <= rx1 or ry2 <= ry1:
        return None

    roi = frame[ry1:ry2, rx1:rx2].copy()  # 슬라이스 복사 (원본 frame 변경 방지)
    return CombatSnapshot(
        roi=roi,
        roi_origin=(rx1, ry1),
        bbox=bbox,
        region=region,
        timestamp=time.time(),
    )


# ══════════════════════════════════════════════
# ItemPicker — 차분 기반 픽업 로직
# ══════════════════════════════════════════════

class ItemPicker:
    """프레임 차분 기반 아이템 위치 검출 + 클릭."""

    def __init__(self):
        self._debug_save_count = 0
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

```bash
pytest tests/test_item_picker.py -v
```

기대: `5 passed`

- [ ] **Step 5: 커밋**

```bash
git add item_picker.py tests/test_item_picker.py
git commit -m "feat: item_picker.py — CombatSnapshot dataclass + build_snapshot"
```

---

### Task 4: ItemPicker._compute_diff_mask (TDD)

**Files:**
- Modify: `item_picker.py` (ItemPicker 클래스에 메서드 추가)
- Modify: `tests/test_item_picker.py` (테스트 추가)

- [ ] **Step 1: 실패하는 테스트 추가 — `tests/test_item_picker.py` 끝에**

```python


# ══════════════════════════════════════════════
# ItemPicker._compute_diff_mask
# ══════════════════════════════════════════════

class TestComputeDiffMask:
    def test_no_change_returns_empty_mask(self):
        baseline = np.full((50, 50, 3), 100, dtype=np.uint8)
        after = baseline.copy()
        picker = ItemPicker()

        mask = picker._compute_diff_mask(baseline, after, threshold=30)

        assert mask.shape == (50, 50)
        assert mask.dtype == np.uint8
        assert np.count_nonzero(mask) == 0

    def test_detects_above_threshold_change(self):
        baseline = np.full((60, 60, 3), 100, dtype=np.uint8)
        after = baseline.copy()
        # 충분히 큰 영역(20×20)을 변경 — 모폴로지로 깎이는 양 감안
        after[20:40, 20:40] = 200

        picker = ItemPicker()
        mask = picker._compute_diff_mask(baseline, after, threshold=30)

        # 모폴로지 정리 후에도 충분한 픽셀이 남아야 함
        assert np.count_nonzero(mask) > 100

    def test_ignores_below_threshold_noise(self):
        baseline = np.full((50, 50, 3), 100, dtype=np.uint8)
        after = baseline.copy()
        after[10:20, 10:20] = 110  # diff = 10 < threshold 30

        picker = ItemPicker()
        mask = picker._compute_diff_mask(baseline, after, threshold=30)

        assert np.count_nonzero(mask) == 0
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/test_item_picker.py::TestComputeDiffMask -v
```

기대: `AttributeError: 'ItemPicker' object has no attribute '_compute_diff_mask'`

- [ ] **Step 3: `item_picker.py`의 `ItemPicker` 클래스에 메서드 추가**

`ItemPicker.__init__` 아래에 추가:

```python

    def _compute_diff_mask(self, baseline_roi: np.ndarray,
                           after_roi: np.ndarray,
                           threshold: int) -> np.ndarray:
        """
        절대 차분 → 그레이스케일 → 임계값 → 모폴로지(open/close).

        Args:
            baseline_roi: 사망 직전 ROI (BGR)
            after_roi: 사망 직후 ROI (BGR)
            threshold: 그레이값 차이 임계값 (0~255)

        Returns:
            uint8 마스크 (255=차분 있음, 0=없음)
        """
        # 모양이 다르면 작은 쪽에 맞춤 (창 위치 변화 등 엣지)
        if baseline_roi.shape != after_roi.shape:
            h = min(baseline_roi.shape[0], after_roi.shape[0])
            w = min(baseline_roi.shape[1], after_roi.shape[1])
            baseline_roi = baseline_roi[:h, :w]
            after_roi = after_roi[:h, :w]

        diff = cv2.absdiff(baseline_roi, after_roi)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

        # 모폴로지 정리 — 노이즈 제거(open) + 끊긴 영역 합치기(close)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        return mask
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

```bash
pytest tests/test_item_picker.py::TestComputeDiffMask -v
```

기대: `3 passed`

- [ ] **Step 5: 커밋**

```bash
git add item_picker.py tests/test_item_picker.py
git commit -m "feat: ItemPicker._compute_diff_mask — absdiff + threshold + 모폴로지"
```

---

### Task 5: ItemPicker._mask_corpse_area (TDD)

**Files:**
- Modify: `item_picker.py`
- Modify: `tests/test_item_picker.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_item_picker.py` 끝에:

```python


# ══════════════════════════════════════════════
# ItemPicker._mask_corpse_area
# ══════════════════════════════════════════════

class TestMaskCorpseArea:
    def test_zeros_out_full_bbox_area(self):
        diff_mask = np.full((100, 100), 255, dtype=np.uint8)
        bbox_in_roi = (40, 40, 20, 20)  # ROI-local (x, y, w, h)
        picker = ItemPicker()

        result = picker._mask_corpse_area(diff_mask.copy(), bbox_in_roi, ratio=1.0)

        # bbox 영역 (40~60, 40~60)이 0
        assert np.all(result[40:60, 40:60] == 0)
        # bbox 바깥은 그대로 255
        assert np.all(result[:40, :] == 255)
        assert np.all(result[60:, :] == 255)

    def test_partial_ratio_masks_smaller_center_region(self):
        diff_mask = np.full((100, 100), 255, dtype=np.uint8)
        bbox_in_roi = (40, 40, 20, 20)  # 중심 (50, 50)
        picker = ItemPicker()

        # ratio=0.5 → 마스킹 영역 10×10 중심 (50, 50)
        result = picker._mask_corpse_area(diff_mask.copy(), bbox_in_roi, ratio=0.5)

        # 중심 10×10 = (45~55, 45~55)이 0
        assert np.all(result[45:55, 45:55] == 0)
        # bbox 가장자리(예: (41, 41))는 마스킹 안 됨
        assert result[41, 41] == 255

    def test_ratio_zero_does_not_mask(self):
        diff_mask = np.full((100, 100), 255, dtype=np.uint8)
        bbox_in_roi = (40, 40, 20, 20)
        picker = ItemPicker()

        result = picker._mask_corpse_area(diff_mask.copy(), bbox_in_roi, ratio=0.0)

        assert np.all(result == 255)
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/test_item_picker.py::TestMaskCorpseArea -v
```

기대: `AttributeError: ... no attribute '_mask_corpse_area'`

- [ ] **Step 3: `item_picker.py`의 `ItemPicker`에 메서드 추가**

`_compute_diff_mask` 아래에:

```python

    def _mask_corpse_area(self, diff_mask: np.ndarray,
                          bbox_in_roi: Tuple[int, int, int, int],
                          ratio: float) -> np.ndarray:
        """
        bbox 중심으로 (bbox_size × ratio) 영역을 0으로 칠해 시체 차분 제거.

        Args:
            diff_mask: 차분 마스크 (수정됨, in-place)
            bbox_in_roi: ROI-local bbox (x, y, w, h)
            ratio: bbox 크기 대비 마스킹 영역 비율 (0.0~) — 0.0이면 마스킹 안 함

        Returns:
            마스킹된 mask (입력과 동일 객체, in-place 수정)
        """
        if ratio <= 0:
            return diff_mask

        bx, by, bw, bh = bbox_in_roi
        cx = bx + bw // 2
        cy = by + bh // 2
        half_w = int(bw * ratio / 2)
        half_h = int(bh * ratio / 2)

        x1 = max(0, cx - half_w)
        y1 = max(0, cy - half_h)
        x2 = min(diff_mask.shape[1], cx + half_w)
        y2 = min(diff_mask.shape[0], cy + half_h)

        diff_mask[y1:y2, x1:x2] = 0
        return diff_mask
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

```bash
pytest tests/test_item_picker.py::TestMaskCorpseArea -v
```

기대: `3 passed`

- [ ] **Step 5: 커밋**

```bash
git add item_picker.py tests/test_item_picker.py
git commit -m "feat: ItemPicker._mask_corpse_area — 시체 영역 마스킹"
```

---

### Task 6: ItemPicker._is_outlier_diff (TDD)

**Files:**
- Modify: `item_picker.py`
- Modify: `tests/test_item_picker.py`

- [ ] **Step 1: 실패하는 테스트 추가**

```python


# ══════════════════════════════════════════════
# ItemPicker._is_outlier_diff
# ══════════════════════════════════════════════

class TestIsOutlierDiff:
    def test_low_diff_is_not_outlier(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[10:20, 10:20] = 255  # 100 px / 10000 = 1%
        picker = ItemPicker()

        assert picker._is_outlier_diff(mask, threshold_ratio=0.4) is False

    def test_high_diff_is_outlier(self):
        mask = np.full((100, 100), 255, dtype=np.uint8)
        # 90% 채움 (위 10줄만 0)
        mask[:10, :] = 0
        picker = ItemPicker()

        assert picker._is_outlier_diff(mask, threshold_ratio=0.4) is True

    def test_at_threshold_is_outlier(self):
        # 정확히 40% 채움 — 임계값 이상이면 outlier
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[:40, :] = 255  # 40%
        picker = ItemPicker()

        assert picker._is_outlier_diff(mask, threshold_ratio=0.4) is True
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/test_item_picker.py::TestIsOutlierDiff -v
```

기대: `AttributeError`

- [ ] **Step 3: `ItemPicker`에 메서드 추가**

`_mask_corpse_area` 아래에:

```python

    def _is_outlier_diff(self, diff_mask: np.ndarray,
                         threshold_ratio: float) -> bool:
        """
        차분 마스크의 활성 픽셀 비율이 threshold_ratio 이상이면 True.
        카메라/캐릭터 이동 등으로 ROI 전체가 변한 케이스를 거른다.
        """
        total = diff_mask.size
        if total == 0:
            return False
        active = int(np.count_nonzero(diff_mask))
        return active / total >= threshold_ratio
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

```bash
pytest tests/test_item_picker.py::TestIsOutlierDiff -v
```

기대: `3 passed`

- [ ] **Step 5: 커밋**

```bash
git add item_picker.py tests/test_item_picker.py
git commit -m "feat: ItemPicker._is_outlier_diff — 차분 비율 상한 검사"
```

---

### Task 7: ItemPicker._find_item_blob (TDD)

**Files:**
- Modify: `item_picker.py`
- Modify: `tests/test_item_picker.py`

- [ ] **Step 1: 실패하는 테스트 추가**

```python


# ══════════════════════════════════════════════
# ItemPicker._find_item_blob
# ══════════════════════════════════════════════

class TestFindItemBlob:
    def test_finds_single_valid_blob(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[40:55, 40:55] = 255  # 15×15 = 225 px²
        picker = ItemPicker()

        result = picker._find_item_blob(
            mask,
            bbox_center_in_roi=(50, 50),
            bbox_diagonal=20.0,
            min_area=30, max_area=2500,
            max_distance_ratio=1.5,
        )

        assert result is not None
        cx, cy = result
        assert 40 <= cx <= 55
        assert 40 <= cy <= 55

    def test_rejects_too_small_blob(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[50:53, 50:53] = 255  # 9 px² < min 30
        picker = ItemPicker()

        result = picker._find_item_blob(
            mask, (50, 50), 20.0, 30, 2500, 1.5
        )

        assert result is None

    def test_rejects_too_large_blob(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[10:90, 10:90] = 255  # 6400 px² > max 2500
        picker = ItemPicker()

        result = picker._find_item_blob(
            mask, (50, 50), 20.0, 30, 2500, 1.5
        )

        assert result is None

    def test_rejects_blob_too_far_from_bbox_center(self):
        # bbox 중심 (100, 100), 대각선 20, max_distance = 30
        mask = np.zeros((200, 200), dtype=np.uint8)
        mask[10:25, 10:25] = 255  # 중심 ~17, distance ~117 > 30
        picker = ItemPicker()

        result = picker._find_item_blob(
            mask, (100, 100), 20.0, 30, 2500, 1.5
        )

        assert result is None

    def test_picks_largest_blob_when_multiple_valid(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        # 작은 블롭 (10×10 = 100 px²) — 중심 (20, 20)
        mask[15:25, 15:25] = 255
        # 큰 블롭 (20×20 = 400 px²) — 중심 (60, 60)
        mask[50:70, 50:70] = 255

        picker = ItemPicker()
        result = picker._find_item_blob(
            mask, (50, 50), 100.0, 30, 2500, 1.5
        )

        assert result is not None
        cx, cy = result
        # 큰 블롭(중심 60, 60)이 선택되어야 함
        assert 50 <= cx <= 70
        assert 50 <= cy <= 70
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/test_item_picker.py::TestFindItemBlob -v
```

기대: `AttributeError`

- [ ] **Step 3: `ItemPicker`에 메서드 추가**

`_is_outlier_diff` 아래에:

```python

    def _find_item_blob(self, diff_mask: np.ndarray,
                        bbox_center_in_roi: Tuple[int, int],
                        bbox_diagonal: float,
                        min_area: int, max_area: int,
                        max_distance_ratio: float) -> Optional[Tuple[int, int]]:
        """
        차분 마스크에서 크기/위치 필터를 통과하는 블롭 중 가장 큰 것을 선택.

        Args:
            diff_mask: uint8 마스크
            bbox_center_in_roi: ROI-local bbox 중심 (cx, cy)
            bbox_diagonal: bbox 대각선 길이 (px)
            min_area / max_area: 허용 블롭 면적 범위
            max_distance_ratio: bbox 중심에서 블롭까지 허용 거리 (× bbox_diagonal)

        Returns:
            ROI-local 블롭 중심 (cx, cy) 또는 None
        """
        contours, _ = cv2.findContours(diff_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        max_dist = bbox_diagonal * max_distance_ratio
        bcx, bcy = bbox_center_in_roi

        best_area = 0
        best_center = None

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue

            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            dist = ((cx - bcx) ** 2 + (cy - bcy) ** 2) ** 0.5
            if dist > max_dist:
                continue

            if area > best_area:
                best_area = area
                best_center = (cx, cy)

        return best_center
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

```bash
pytest tests/test_item_picker.py::TestFindItemBlob -v
```

기대: `5 passed`

- [ ] **Step 5: 커밋**

```bash
git add item_picker.py tests/test_item_picker.py
git commit -m "feat: ItemPicker._find_item_blob — 크기/위치 필터링 컨투어 선택"
```

---

### Task 8: ItemPicker.try_pickup 통합 메서드

**Files:**
- Modify: `item_picker.py`
- Modify: `tests/test_item_picker.py`

이 단계는 `capture_screen()`/`click()` 부수효과 때문에 monkeypatch로 mock해서 테스트한다.

- [ ] **Step 1: 통합 테스트 추가 — 검증 게이트(스킵 조건)와 정상 흐름**

`tests/test_item_picker.py` 끝에:

```python


# ══════════════════════════════════════════════
# ItemPicker.try_pickup — 통합 (mock 기반)
# ══════════════════════════════════════════════

class TestTryPickup:
    def _make_snapshot(self, age_seconds=0.0, region=(0, 0, 200, 200)):
        """테스트용 스냅샷 — 베이스라인 ROI는 회색."""
        roi = np.full((80, 80, 3), 100, dtype=np.uint8)
        return CombatSnapshot(
            roi=roi,
            roi_origin=(20, 20),
            bbox=(40, 40, 40, 40),  # frame-local
            region=region,
            timestamp=time.time() - age_seconds,
        )

    def test_skips_when_snapshot_too_old(self, monkeypatch):
        snap = self._make_snapshot(age_seconds=5.0)
        click_calls = []
        monkeypatch.setattr("item_picker.click",
                            lambda x, y, method: click_calls.append((x, y)))
        monkeypatch.setattr("item_picker.capture_screen",
                            lambda region: np.zeros((200, 200, 3), dtype=np.uint8))

        picker = ItemPicker()
        picked = picker.try_pickup(snap, current_region=(0, 0, 200, 200), click_method="sendinput")

        assert picked is False
        assert click_calls == []

    def test_skips_when_region_changed(self, monkeypatch):
        snap = self._make_snapshot(region=(0, 0, 200, 200))
        click_calls = []
        monkeypatch.setattr("item_picker.click",
                            lambda x, y, method: click_calls.append((x, y)))
        monkeypatch.setattr("item_picker.capture_screen",
                            lambda region: np.zeros((200, 200, 3), dtype=np.uint8))

        picker = ItemPicker()
        picked = picker.try_pickup(snap, current_region=(50, 50, 200, 200), click_method="sendinput")

        assert picked is False
        assert click_calls == []

    def test_clicks_when_item_appears_in_roi(self, monkeypatch):
        snap = self._make_snapshot()

        # after 프레임 — 베이스라인과 같지만 ROI 한쪽에 "아이템"이 추가됨
        # ROI는 frame[20:100, 20:100]이고 베이스라인 ROI는 회색 (100)
        # after 프레임: ROI 위치에 같은 회색 + 아이템 추가
        after_frame = np.full((200, 200, 3), 100, dtype=np.uint8)
        # 아이템: ROI 좌상단 부근(frame-local 30, 30 ~ 45, 45 = ROI-local 10~25)
        # bbox(frame-local 40~80)에서 떨어진 위치라 마스킹에 안 걸림
        after_frame[30:45, 30:45] = 220

        click_calls = []
        monkeypatch.setattr("item_picker.click",
                            lambda x, y, method: click_calls.append((x, y)))
        monkeypatch.setattr("item_picker.capture_screen",
                            lambda region: after_frame)

        picker = ItemPicker()
        picked = picker.try_pickup(snap, current_region=(0, 0, 200, 200), click_method="sendinput")

        assert picked is True
        assert len(click_calls) == 1
        # 클릭 좌표는 screen 좌표 = region 오프셋 + frame-local
        # region=(0,0,...)이므로 frame-local과 동일
        # 아이템 중심 frame-local ~ (37, 37)
        cx, cy = click_calls[0]
        assert 30 <= cx <= 45
        assert 30 <= cy <= 45

    def test_returns_false_when_no_item_in_diff(self, monkeypatch):
        snap = self._make_snapshot()
        # after = baseline (변화 없음)
        after_frame = np.full((200, 200, 3), 100, dtype=np.uint8)

        click_calls = []
        monkeypatch.setattr("item_picker.click",
                            lambda x, y, method: click_calls.append((x, y)))
        monkeypatch.setattr("item_picker.capture_screen",
                            lambda region: after_frame)

        picker = ItemPicker()
        picked = picker.try_pickup(snap, current_region=(0, 0, 200, 200), click_method="sendinput")

        assert picked is False
        assert click_calls == []
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/test_item_picker.py::TestTryPickup -v
```

기대: `AttributeError: ... no attribute 'try_pickup'`

- [ ] **Step 3: `ItemPicker`에 `try_pickup` + 보조 메서드 추가**

`_find_item_blob` 아래에:

```python

    def _capture_after_roi(self, snapshot: CombatSnapshot) -> Optional[np.ndarray]:
        """
        현재 화면을 캡처해 snapshot.roi_origin/shape에 맞춰 ROI 잘라서 반환.

        Returns:
            ROI BGR 또는 None (캡처 실패 또는 shape 불일치)
        """
        frame = capture_screen(region=snapshot.region)
        if frame is None:
            return None

        rx, ry = snapshot.roi_origin
        rh, rw = snapshot.roi.shape[:2]

        if ry + rh > frame.shape[0] or rx + rw > frame.shape[1]:
            log.debug("after 프레임이 snapshot ROI보다 작음 → 픽업 스킵")
            return None

        return frame[ry:ry + rh, rx:rx + rw]

    def try_pickup(self,
                   snapshot: CombatSnapshot,
                   current_region: Tuple[int, int, int, int],
                   click_method: str) -> bool:
        """
        스냅샷 베이스라인 vs 현재 화면 차분으로 아이템 위치를 찾아 클릭.

        Args:
            snapshot: 사망 직전 베이스라인 스냅샷
            current_region: 현재 게임 창 region (snapshot.region과 비교)
            click_method: clicker.click()용 method 문자열

        Returns:
            True if 아이템 좌표를 클릭했음, False if 스킵 (안전장치/없음)
        """
        # ── 검증 게이트 ──
        age = time.time() - snapshot.timestamp
        if age > LOOT_SNAPSHOT_MAX_AGE:
            log.debug(f"시각 픽업 스킵: 스냅샷 노화 ({age:.2f}s > {LOOT_SNAPSHOT_MAX_AGE}s)")
            return False

        if snapshot.region != current_region:
            log.debug(f"시각 픽업 스킵: region 변경 ({snapshot.region} → {current_region})")
            return False

        # ── after ROI 캡처 ──
        after_roi = self._capture_after_roi(snapshot)
        if after_roi is None:
            log.debug("시각 픽업 스킵: after ROI 캡처 실패")
            return False

        # ── 차분 → 마스크 ──
        diff_mask = self._compute_diff_mask(snapshot.roi, after_roi, LOOT_DIFF_THRESHOLD)

        # ── 이상치 차단 ──
        if self._is_outlier_diff(diff_mask, LOOT_MAX_TOTAL_DIFF_RATIO):
            log.info("시각 픽업 스킵: 차분 비율 과다 (카메라/캐릭터 이동 의심)")
            self._save_debug_image_if_enabled(snapshot, after_roi, diff_mask, click_pos=None,
                                              suffix="outlier")
            return False

        # ── 시체 영역 마스킹 ──
        bx, by, bw, bh = snapshot.bbox
        rx, ry = snapshot.roi_origin
        bbox_in_roi = (bx - rx, by - ry, bw, bh)
        diff_mask = self._mask_corpse_area(diff_mask, bbox_in_roi, LOOT_CORPSE_MASK_RATIO)

        # ── 블롭 검출 ──
        bbox_diagonal = (bw ** 2 + bh ** 2) ** 0.5
        bbox_center_in_roi = (bbox_in_roi[0] + bw // 2, bbox_in_roi[1] + bh // 2)

        click_in_roi = self._find_item_blob(
            diff_mask,
            bbox_center_in_roi,
            bbox_diagonal,
            LOOT_MIN_BLOB_AREA, LOOT_MAX_BLOB_AREA,
            LOOT_MAX_DISTANCE_RATIO,
        )

        if click_in_roi is None:
            log.debug("시각 픽업: 유효 블롭 없음 (드롭 없거나 위치 필터 통과 실패)")
            self._save_debug_image_if_enabled(snapshot, after_roi, diff_mask, click_pos=None,
                                              suffix="no_blob")
            return False

        # ── 클릭 좌표 계산 (ROI-local → frame-local → screen) ──
        cx_roi, cy_roi = click_in_roi
        cx_frame = rx + cx_roi
        cy_frame = ry + cy_roi
        cx_screen = current_region[0] + cx_frame
        cy_screen = current_region[1] + cy_frame

        click(cx_screen, cy_screen, method=click_method)
        log.info(f"시각 픽업 클릭: ({cx_screen}, {cy_screen})")

        self._save_debug_image_if_enabled(snapshot, after_roi, diff_mask,
                                          click_pos=(cx_roi, cy_roi),
                                          suffix="ok")
        return True

    def _save_debug_image_if_enabled(self, snapshot, after_roi, diff_mask,
                                      click_pos, suffix: str):
        """디버그 옵션이 켜졌고 샘플링 통과 시 PNG 저장."""
        if not LOOT_DEBUG_SAVE:
            return
        if random.random() > LOOT_DEBUG_SAMPLE_RATIO:
            return

        try:
            os.makedirs(LOOT_DEBUG_DIR, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            cv2.imwrite(os.path.join(LOOT_DEBUG_DIR, f"{ts}_{suffix}_01_baseline.png"),
                        snapshot.roi)
            cv2.imwrite(os.path.join(LOOT_DEBUG_DIR, f"{ts}_{suffix}_02_after.png"),
                        after_roi)
            cv2.imwrite(os.path.join(LOOT_DEBUG_DIR, f"{ts}_{suffix}_03_diff.png"),
                        diff_mask)
            decision = cv2.cvtColor(diff_mask, cv2.COLOR_GRAY2BGR)
            if click_pos is not None:
                cv2.circle(decision, click_pos, 8, (0, 0, 255), 2)
            cv2.imwrite(os.path.join(LOOT_DEBUG_DIR, f"{ts}_{suffix}_04_decision.png"),
                        decision)
        except Exception as e:
            log.warning(f"디버그 이미지 저장 실패: {e}")
```

- [ ] **Step 4: 전체 테스트 재실행 — 통과 확인**

```bash
pytest tests/test_item_picker.py -v
```

기대: 모든 테스트 통과 (지금까지 추가한 ~20개)

- [ ] **Step 5: 커밋**

```bash
git add item_picker.py tests/test_item_picker.py
git commit -m "feat: ItemPicker.try_pickup — 검증 게이트 + 차분 → 클릭 통합"
```

---

### Task 9: monster_tracker.py에 combat_snapshot 추가

**Files:**
- Modify: `monster_tracker.py:1-22` (import)
- Modify: `monster_tracker.py:294-309` (`MonsterTracker.__init__`)
- Modify: `monster_tracker.py:633-670` (`refine_position`)
- Modify: `monster_tracker.py:671-754` (`find_and_track`)
- Modify: `monster_tracker.py:462-471` (`_abandon_target`)
- Modify: `monster_tracker.py:793-800` (`reset`)

- [ ] **Step 1: import에 ItemPicker 모듈 추가**

`monster_tracker.py` 상단 import 영역에서 기존 `from config import (...)` 블록 위에 추가:

```python
from item_picker import CombatSnapshot, build_snapshot
```

그리고 `from config import (...)` 블록의 import 목록 끝에 다음을 추가 (기존 마지막 줄 `BRIGHTNESS_REJECT_THRESHOLD,` 다음에):

```python
    LOOT_ROI_EXPAND_RATIO,
```

(즉 import 블록의 닫는 `)` 직전에 한 줄 추가)

- [ ] **Step 2: `__init__`에 `combat_snapshot` 필드 추가**

`MonsterTracker.__init__` 마지막 줄(현재 `self._edge_only_count = 0`) 다음에 추가:

```python
        # 시각 기반 픽업용 스냅샷 (frozen dataclass — atomic 통째 교체)
        self.combat_snapshot: Optional[CombatSnapshot] = None
```

`Optional` import도 추가 (파일 상단에서 `from typing import Optional`).

- [ ] **Step 3: 스냅샷 갱신 헬퍼 메서드 추가**

`MonsterTracker` 클래스 안, `_local_to_screen` 위에 추가:

```python
    def _update_combat_snapshot(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]):
        """
        frame과 bbox가 같은 캡처에서 나왔다는 것을 호출자가 보장한 상태에서만 호출.
        스냅샷을 통째 교체 (frozen dataclass라 부분 갱신 불가).
        """
        if self.region is None:
            return
        snap = build_snapshot(frame, bbox, self.region, LOOT_ROI_EXPAND_RATIO)
        if snap is not None:
            self.combat_snapshot = snap
```

`Tuple` import도 추가 (`from typing import Optional, Tuple`).

- [ ] **Step 4: `find_and_track`의 감지 성공 분기에서 스냅샷 갱신**

`monster_tracker.py`에서 다음 블록을 찾는다 (현재 ~744-754줄, "감지 성공 → 미스 카운터 초기화" 부근):

```python
        # 감지 성공 → 미스 카운터 초기화
        self._detect_miss_count = 0
        cx, cy = self._bbox_center_screen(bbox)

        # 첫 감지 시 전투 타이머 시작
        if not self.has_target:
            self.has_target = True
            self.last_bbox = bbox
            self._target_start_time = time.time()
            self._last_hp_check_time = time.time()
            self._last_hp_ratio = -1.0
            self._hp_no_change_count = 0
            log.info(f"몬스터 감지: ({cx},{cy}) bbox={bbox}")
        else:
            self.last_bbox = bbox

        return (cx, cy), TRACK_OK
```

이 블록의 마지막 `return (cx, cy), TRACK_OK` 직전에 한 줄 추가:

```python
        # 같은 캡처(frame)에서 나온 bbox로 스냅샷 갱신 — 시각 픽업 베이스라인
        self._update_combat_snapshot(frame, bbox)

        return (cx, cy), TRACK_OK
```

- [ ] **Step 5: `refine_position`에서 갱신된 bbox로 스냅샷 갱신**

`monster_tracker.py:633-669`의 `refine_position` 메서드를 찾는다. 현재 마지막 부분:

```python
        # last_bbox 갱신
        self.last_bbox = refined_bbox
        log.debug(f"클릭 전 위치 보정: ({cx}, {cy})")
        return (cx, cy)
```

이를 다음으로 교체:

```python
        # last_bbox 갱신 + 같은 캡처/bbox로 스냅샷 동기화
        self.last_bbox = refined_bbox
        self._update_combat_snapshot(frame, refined_bbox)
        log.debug(f"클릭 전 위치 보정: ({cx}, {cy})")
        return (cx, cy)
```

(`frame`은 `refine_position` 내부에서 이미 `frame = capture_screen(...)`으로 캡처된 동일 변수.)

- [ ] **Step 6: `_abandon_target`에서 스냅샷 무효화**

`_abandon_target` 메서드(현재 ~462-470줄)의 마지막 줄(`self._reset_combat_state()`) 다음에 추가:

```python
        self.combat_snapshot = None
```

수정 후 메서드 전체:

```python
    def _abandon_target(self):
        """현재 대상을 포기하고 스킵 목록에 등록."""
        if self.last_bbox is not None:
            cx = self.last_bbox[0] + self.last_bbox[2] // 2
            cy = self.last_bbox[1] + self.last_bbox[3] // 2
            self._skip_positions.append((cx, cy, time.time()))
            log.info(f"대상 포기: ({cx}, {cy}) → 스킵 목록 등록")
        self.has_target = False
        self._reset_combat_state()
        self.combat_snapshot = None
```

- [ ] **Step 7: `reset`에서 스냅샷 무효화**

`reset` 메서드(현재 ~793-800줄):

```python
    def reset(self):
        """감지 상태 초기화."""
        self.has_target = False
        self.last_bbox = None
        self._detect_miss_count = 0
        self._reset_combat_state()
        self._skip_positions.clear()
        log.debug("감지 상태 초기화")
```

`self._skip_positions.clear()` 다음에 한 줄 추가:

```python
        self.combat_snapshot = None
```

- [ ] **Step 8: 모듈 import 검증**

```bash
python -c "from monster_tracker import MonsterTracker; t = MonsterTracker(region=(0,0,100,100)); print('snapshot field:', t.combat_snapshot)"
```

기대 출력: `snapshot field: None`

- [ ] **Step 9: 커밋**

```bash
git add monster_tracker.py
git commit -m "feat: monster_tracker에 combat_snapshot — find_and_track/refine_position에서 atomic 갱신"
```

---

### Task 10: macro_engine.py::_loot_items 재구성

**Files:**
- Modify: `macro_engine.py:1-25` (import 영역)
- Modify: `macro_engine.py:28-49` (`__init__`)
- Modify: `macro_engine.py:73-83` (`_loot_items`)

- [ ] **Step 1: import에 `ItemPicker` 추가**

`macro_engine.py` 상단의 `from clicker import click, press_key` 줄 다음에 추가:

```python
from item_picker import ItemPicker
```

그리고 `from config import (...)` 블록 안에 `LOOT_VISUAL_ENABLED`, `LOOT_AFTER_CLICK_DELAY`를 추가. 즉 기존:

```python
from config import (
    CLICK_METHOD, DEFAULT_DELAY, ATTACK_INTERVAL, DETECT_CONFIDENCE,
    LOOT_ENABLED, LOOT_KEY_SCANCODE, LOOT_PRESS_COUNT,
    LOOT_PRESS_INTERVAL, LOOT_DELAY_AFTER_KILL,
    ...
)
```

에서 `LOOT_DELAY_AFTER_KILL,` 다음에 두 줄 추가:

```python
    LOOT_VISUAL_ENABLED, LOOT_AFTER_CLICK_DELAY,
```

- [ ] **Step 2: `__init__`에 `self.item_picker` 추가**

`MacroEngine.__init__`의 `self.tracker = MonsterTracker(...)` 블록 직후에 추가:

```python
        self.item_picker = ItemPicker()
```

- [ ] **Step 3: `_loot_items()` 메서드 재구성**

기존 메서드(`macro_engine.py:73-83`):

```python
    def _loot_items(self):
        """사망 판정 후 아이템 줍기 (Spacebar × N회)."""
        if not LOOT_ENABLED:
            return

        time.sleep(LOOT_DELAY_AFTER_KILL + random.uniform(0, 0.05))
        for i in range(LOOT_PRESS_COUNT):
            press_key(LOOT_KEY_SCANCODE)
            if i < LOOT_PRESS_COUNT - 1:
                time.sleep(LOOT_PRESS_INTERVAL + random.uniform(0, 0.04))
        log.info(f"아이템 줍기 완료 (Spacebar ×{LOOT_PRESS_COUNT})")
```

이것을 다음으로 통째 교체:

```python
    def _loot_items(self):
        """
        사망 판정 후 아이템 줍기.
            1. 시각 기반 픽업: 스냅샷 차분으로 드롭 위치 검출 → 클릭
            2. Spacebar 보험 픽업: 시각 성공 시 1회, 실패 시 LOOT_PRESS_COUNT회
        """
        if not LOOT_ENABLED:
            return

        time.sleep(LOOT_DELAY_AFTER_KILL + random.uniform(0, 0.05))

        # 1. 시각 기반 픽업 시도 (스냅샷 atomic 읽기 — 한 번만 참조 확보)
        picked = False
        snapshot = self.tracker.combat_snapshot
        if LOOT_VISUAL_ENABLED and snapshot is not None and self.region is not None:
            picked = self.item_picker.try_pickup(
                snapshot=snapshot,
                current_region=self.region,
                click_method=self.click_method,
            )
            if picked:
                log.info("아이템 픽업: 시각 클릭 성공")
                time.sleep(LOOT_AFTER_CLICK_DELAY)

        # 2. Spacebar 보험 — 시각 성공 시 1회 (다중 아이템 보조), 실패 시 LOOT_PRESS_COUNT회
        space_count = 1 if picked else LOOT_PRESS_COUNT
        for i in range(space_count):
            press_key(LOOT_KEY_SCANCODE)
            if i < space_count - 1:
                time.sleep(LOOT_PRESS_INTERVAL + random.uniform(0, 0.04))
        log.debug(f"Spacebar 보험 픽업 ×{space_count} (visual_picked={picked})")
```

- [ ] **Step 4: 모듈 import 검증**

```bash
python -c "from macro_engine import MacroEngine; e = MacroEngine(region=(0,0,800,600)); print('item_picker:', e.item_picker)"
```

기대 출력: `item_picker: <item_picker.ItemPicker object at 0x...>`

- [ ] **Step 5: 단위 테스트 전체 재실행 — 회귀 없음 확인**

```bash
pytest tests/ -v
```

기대: 모든 테스트 통과

- [ ] **Step 6: 커밋**

```bash
git add macro_engine.py
git commit -m "feat: macro_engine._loot_items — 시각 픽업 + Spacebar 보험 2단계"
```

---

### Task 11: 디버그 모드로 수동 통합 테스트

이 단계는 사람이 직접 게임을 띄워 확인. 코드 변경 없음.

**Files:** 없음 (config 토글만)

- [ ] **Step 1: 디버그 모드 켜기**

`config.py`에서:

```python
LOOT_DEBUG_SAVE = True
LOOT_DEBUG_SAMPLE_RATIO = 1.0   # 일단 100% 저장 (디버그 자료 모음)
```

(절대 커밋하지 말 것 — 임시 변경)

- [ ] **Step 2: 게임 띄우고 매크로 실행**

PowerShell 관리자 권한:

```bash
cd "C:\Users\PC\OneDrive\바탕 화면\workspace\macro"
python main.py
```

게임 창 활성 후 F5로 매크로 시작. 늑대 5~10마리 사냥 후 F6으로 중지.

- [ ] **Step 3: `debug_loot/` 디렉토리에서 PNG 4세트 확인**

각 사망 시점마다 4장이 저장됨:
- `*_baseline.png` — 베이스라인 ROI
- `*_after.png` — 사망 직후 ROI
- `*_diff.png` — 차분 마스크
- `*_decision.png` — 최종 결정 (빨간 동그라미 = 클릭 위치)

확인 항목:
- 베이스라인에 늑대가 보이고 after에는 늑대 사라짐 → 정상
- 아이템이 떨어진 케이스에서 diff 마스크에 작은 블롭 표시되는지
- decision PNG의 동그라미가 실제 아이템 위치와 일치하는지

- [ ] **Step 4: `logs/macro_*.log` 확인**

`grep "시각 픽업"` 로그 라인 검토:
- "시각 픽업 스킵: 스냅샷 노화" → `LOOT_SNAPSHOT_MAX_AGE` 상향 검토
- "시각 픽업 스킵: 차분 비율 과다" → 카메라 흔들림 → ROI 축소 또는 임계값 조정
- "시각 픽업: 유효 블롭 없음" → 임계값(`LOOT_DIFF_THRESHOLD`) 또는 크기 필터(`LOOT_MIN_BLOB_AREA`) 조정
- "시각 픽업 클릭: ..." → 정상 동작

- [ ] **Step 5 (선택): 디버그 PNG 일부를 git에 추가하지 않고 보관**

`.gitignore`에 `debug_loot/`이 이미 포함됐는지 확인:

```bash
grep "debug_loot" .gitignore
```

없으면 추가:

```bash
echo "debug_loot/" >> .gitignore
git add .gitignore
git commit -m "chore: .gitignore에 debug_loot/ 추가"
```

- [ ] **Step 6: 결과 메모만 남기고 다음 단계로**

이 Task는 코드 커밋 없음. 관찰 결과(어느 임계값을 어떻게 조정해야 할지)를 다음 Task로 넘김.

---

### Task 12: 임계값 튜닝 + 디버그 옵션 끄기

**Files:**
- Modify: `config.py:LOOT_*` (운영 데이터 기반 조정)

- [ ] **Step 1: Task 11에서 관찰한 결과를 기반으로 다음 우선순위로 조정**

| 증상 | 조정 |
|---|---|
| diff 마스크가 너무 비어 있음 (아이템 안 잡힘) | `LOOT_DIFF_THRESHOLD` ↓ (30→20) |
| diff 마스크가 풀/노이즈로 가득 | `LOOT_DIFF_THRESHOLD` ↑ (30→40) 또는 `LOOT_MIN_BLOB_AREA` ↑ |
| 시체 차분이 너무 많이 잡힘 | `LOOT_CORPSE_MASK_RATIO` ↑ (1.0→1.2) |
| 다른 늑대가 자주 잡힘 | `LOOT_MAX_BLOB_AREA` ↓ 또는 `LOOT_MAX_DISTANCE_RATIO` ↓ (1.5→1.0) |
| 멀리 떨어진 아이템 못 잡음 | `LOOT_ROI_EXPAND_RATIO` ↑ (1.0→1.5) |
| "스냅샷 노화" 로그 자주 | `LOOT_SNAPSHOT_MAX_AGE` ↑ (0.6→1.0) |
| "차분 비율 과다" 자주 (카메라 이동) | `LOOT_MAX_TOTAL_DIFF_RATIO` ↑ (0.4→0.6) 또는 `LOOT_ROI_EXPAND_RATIO` ↓ |

수정할 값들을 `config.py`에 반영.

- [ ] **Step 2: 디버그 옵션 끄기**

`config.py`:

```python
LOOT_DEBUG_SAVE = False
LOOT_DEBUG_SAMPLE_RATIO = 0.1   # 원래 값 복원
```

- [ ] **Step 3: 다시 게임에서 실측 — 5분 사냥**

F5 시작 → 5분 사냥 → F6 정지.

`logs/macro_*.log`에서 다음 비율 확인:
- "시각 픽업 클릭" / "시각 픽업 스킵" 비율
- 시각 픽업 성공률이 50%+ 이면 양호

- [ ] **Step 4: 커밋 (튜닝된 값)**

```bash
git add config.py
git commit -m "tune: LOOT_* 임계값 운영 데이터 기반 조정"
```

---

### Task 13: 최종 검증 + PR 준비

**Files:** 없음

- [ ] **Step 1: 단위 테스트 전체 실행**

```bash
pytest tests/ -v
```

기대: 모두 통과

- [ ] **Step 2: 매크로 5분 안정 운영 확인**

`python main.py` → F5 → 5분 사냥 → F6.

체크리스트:
- 예외/스택트레이스 없음
- 시각 픽업 성공 로그 다수
- F6 정지 시 깔끔하게 종료

- [ ] **Step 3: 로그 통계 확인**

```bash
grep -c "시각 픽업 클릭" logs/macro_$(date +%Y-%m-%d).log
grep -c "시각 픽업 스킵" logs/macro_$(date +%Y-%m-%d).log
grep -c "TRACK_KILLED\|대상 사망" logs/macro_$(date +%Y-%m-%d).log
```

성공률(클릭/사망) 메모.

- [ ] **Step 4: git log로 변경 내역 검토**

```bash
git log --oneline main..HEAD
```

기대: Task 1~12에 대응하는 커밋 ~12개.

- [ ] **Step 5: 작업 마무리**

PR 생성 또는 main 머지는 사용자 결정. (이 Task는 거기까지 가지 않음.)

---

## 자체 점검 (스펙 커버리지)

| 스펙 항목 | 구현 Task |
|---|---|
| `CombatSnapshot` frozen dataclass | Task 3 |
| `build_snapshot()` ROI 슬라이스 복사 | Task 3 |
| `_compute_diff_mask` (absdiff + threshold + 모폴로지) | Task 4 |
| `_mask_corpse_area` (시체 영역 마스킹) | Task 5 |
| `_is_outlier_diff` (차분 비율 상한) | Task 6 |
| `_find_item_blob` (크기/위치 필터) | Task 7 |
| `try_pickup` 검증 게이트 (age/region) | Task 8 |
| 디버그 PNG 저장 (샘플링 포함) | Task 8 |
| `monster_tracker.combat_snapshot` 필드 | Task 9 |
| `find_and_track` 갱신 분기 | Task 9 |
| `refine_position` 갱신 분기 | Task 9 |
| `reset` / `_abandon_target` 무효화 | Task 9 |
| `macro_engine._loot_items` 2단계 재구성 | Task 10 |
| 시각 성공 시 Spacebar 1회 분기 | Task 10 |
| 임계값 튜닝 워크플로 | Task 11~12 |
| 스레드 안전성 (frozen + atomic) | Task 3, 9 (구조적으로 보장) |
