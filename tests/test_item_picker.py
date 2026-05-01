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
