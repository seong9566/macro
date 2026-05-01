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

        # ── 블롭 검출 (kwargs로 호출 — 6-param positional은 가독성 떨어짐) ──
        bbox_diagonal = (bw ** 2 + bh ** 2) ** 0.5
        bbox_center_in_roi = (bbox_in_roi[0] + bw // 2, bbox_in_roi[1] + bh // 2)

        click_in_roi = self._find_item_blob(
            diff_mask=diff_mask,
            bbox_center_in_roi=bbox_center_in_roi,
            bbox_diagonal=bbox_diagonal,
            min_area=LOOT_MIN_BLOB_AREA,
            max_area=LOOT_MAX_BLOB_AREA,
            max_distance_ratio=LOOT_MAX_DISTANCE_RATIO,
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
