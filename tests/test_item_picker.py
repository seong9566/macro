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
