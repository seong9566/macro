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
