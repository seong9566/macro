"""ItemPicker 순수 함수 단위 테스트."""
import dataclasses
import time
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
