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
