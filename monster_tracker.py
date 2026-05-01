import cv2
import numpy as np
import os
import glob
import time
from typing import Optional, Tuple

from item_picker import CombatSnapshot, build_snapshot
from config import (
    DETECT_CONFIDENCE, TRACKING_CONFIDENCE,
    TARGET_TIMEOUT, HP_CHECK_INTERVAL, HP_NO_CHANGE_MAX,
    HP_BAR_OFFSET_Y, HP_BAR_HEIGHT,
    HP_BAR_COLOR_LOWER1, HP_BAR_COLOR_UPPER1,
    HP_BAR_COLOR_LOWER2, HP_BAR_COLOR_UPPER2,
    UI_EXCLUDE_TOP, UI_EXCLUDE_BOTTOM,
    PRECLICK_REFINE_ENABLED, PRECLICK_ROI_PAD_RATIO, TRACKING_ROI_PAD_RATIO,
    REFINE_MAX_DISTANCE, DETECT_SCALES, ROI_DETECT_SCALES,
    DETECT_MISS_MAX,
    EDGE_DETECT_ENABLED, EDGE_DETECT_CONFIDENCE,
    EDGE_CANNY_LOW, EDGE_CANNY_HIGH, EDGE_ONLY_MAX_COUNT,
    TRANSPARENT_VARIANTS_ENABLED, TRANSPARENT_ALPHA_LEVELS, TRANSPARENT_BG_COLORS,
    BRIGHTNESS_REJECT_THRESHOLD,
    LOOT_ROI_EXPAND_RATIO,
)
from screen_capture import capture_screen
from logger import log

# ══════════════════════════════════════════════
# 추적 종료 사유
# ══════════════════════════════════════════════
TRACK_OK = "ok"                      # 추적 중 (정상)
TRACK_KILLED = "killed"              # 대상 소실 → 사망 추정
TRACK_MISS_PENDING = "miss_pending"  # 감지 실패 대기 중 (클릭 중단, 줍기 안 함)
TRACK_ABANDONED_TIMEOUT = "timeout"  # 타임아웃으로 포기
TRACK_ABANDONED_HP = "hp_stuck"      # HP 미변화로 포기
TRACK_NOT_FOUND = "not_found"        # 감지 실패


# ══════════════════════════════════════════════
# 템플릿 캐시
# ══════════════════════════════════════════════

_template_cache = {}  # {path: [(fpath, color, gray), ...]}


def clear_template_cache():
    """템플릿 캐시 초기화. 이미지 교체 후 호출."""
    global _template_cache, _edge_template_cache, _transparent_template_cache
    _template_cache = {}
    _edge_template_cache = {}
    _transparent_template_cache = {}
    log.info("템플릿 캐시 초기화")


def _load_templates(template_dir):
    """
    템플릿 폴더에서 모든 이미지를 컬러+그레이스케일로 로딩 (캐시 활용).
    left 계열 템플릿은 좌우 반전하여 right 버전을 자동 생성.
    top/bottom은 상하 시점이 달라 반전하지 않음.
    """
    if template_dir in _template_cache:
        return _template_cache[template_dir]

    templates = []
    if not os.path.isdir(template_dir):
        log.error(f"템플릿 폴더 없음: {template_dir}")
        return templates

    loaded_names = set()
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
        for fpath in glob.glob(os.path.join(template_dir, ext)):
            basename = os.path.basename(fpath)

            # right 계열은 left에서 자동 생성하므로 스킵
            if "right" in basename.lower():
                left_name = basename.lower().replace("right", "left")
                left_path = os.path.join(template_dir, left_name)
                if os.path.exists(left_path):
                    log.debug(f"템플릿 스킵 (자동 반전 사용): {basename}")
                    continue

            tmpl_color = cv2.imread(fpath)
            if tmpl_color is None:
                continue
            tmpl_gray = cv2.cvtColor(tmpl_color, cv2.COLOR_BGR2GRAY)
            templates.append((fpath, tmpl_color, tmpl_gray))
            loaded_names.add(basename)
            log.debug(f"템플릿 로딩: {basename} ({tmpl_color.shape})")

            # left 계열 → right 자동 생성 (좌우 반전)
            if "left" in basename.lower():
                flipped_color = cv2.flip(tmpl_color, 1)
                flipped_gray = cv2.flip(tmpl_gray, 1)
                flip_name = basename.replace("left", "right")
                flip_path = fpath.replace("left", "right")
                templates.append((flip_path, flipped_color, flipped_gray))
                log.debug(f"템플릿 자동 반전: {basename} → {flip_name}")

    _template_cache[template_dir] = templates
    log.info(f"몬스터 템플릿 {len(templates)}개 로딩 완료 (자동 반전 포함)")
    return templates


_transparent_template_cache = {}  # {path: [(name, color, gray), ...]}


def _load_transparent_templates(template_dir):
    """원본 템플릿의 반투명 변형을 생성/캐시 (ROI 전용). 다중 배경색 × 다중 alpha."""
    if template_dir in _transparent_template_cache:
        return _transparent_template_cache[template_dir]

    if not TRANSPARENT_VARIANTS_ENABLED:
        _transparent_template_cache[template_dir] = []
        return []

    templates = _load_templates(template_dir)
    variants = []

    for bg_color in TRANSPARENT_BG_COLORS:
        bg = np.array(bg_color, dtype=np.uint8)
        for fpath, tmpl_color, tmpl_gray in templates:
            for alpha in TRANSPARENT_ALPHA_LEVELS:
                blended_color = cv2.addWeighted(
                    tmpl_color, alpha,
                    np.full_like(tmpl_color, bg), 1.0 - alpha,
                    0
                )
                blended_gray = cv2.cvtColor(blended_color, cv2.COLOR_BGR2GRAY)
                variant_name = f"{os.path.basename(fpath)}@a{alpha:.1f}bg{bg_color[1]}"
                variants.append((variant_name, blended_color, blended_gray))

    _transparent_template_cache[template_dir] = variants
    log.debug(f"반투명 변형 {len(variants)}개 생성 (alpha: {TRANSPARENT_ALPHA_LEVELS}, 배경: {len(TRANSPARENT_BG_COLORS)}종)")
    return variants


_edge_template_cache = {}  # {path: [(fpath, edge_img), ...]}


def _load_edge_templates(template_dir):
    """원본 템플릿의 Canny 에지 버전을 로딩/캐시."""
    if template_dir in _edge_template_cache:
        return _edge_template_cache[template_dir]

    templates = _load_templates(template_dir)
    edge_templates = []
    for fpath, tmpl_color, tmpl_gray in templates:
        edge = cv2.Canny(tmpl_gray, EDGE_CANNY_LOW, EDGE_CANNY_HIGH)
        edge_templates.append((fpath, edge))

    _edge_template_cache[template_dir] = edge_templates
    log.debug(f"에지 템플릿 {len(edge_templates)}개 생성")
    return edge_templates


# ══════════════════════════════════════════════
# 멀티스케일 템플릿 매칭 (늑대 전용)
# ══════════════════════════════════════════════

def detect_wolves(frame, template_dir="images", confidence=0.55,
                  scales=None):
    """
    늑대 템플릿 이미지만을 사용하여 화면에서 늑대를 감지.
    멀티스케일 + NMS로 정확도를 높임.

    Args:
        frame: BGR 이미지 (캡처된 화면)
        template_dir: 늑대 템플릿 이미지 폴더
        confidence: 매칭 임계값
        scales: 탐색할 스케일 목록

    Returns:
        [(x, y, w, h, score, template_name), ...] NMS 적용된 결과
    """
    if scales is None:
        scales = DETECT_SCALES

    templates = _load_templates(template_dir)
    if not templates:
        return []

    # 그레이스케일 변환 1회 (컬러 대비 ~3배 빠름)
    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    candidates = []

    for fpath, tmpl_color, tmpl_gray in templates:
        tmpl_name = os.path.basename(fpath)
        th, tw = tmpl_gray.shape[:2]

        for scale in scales:
            sh = int(th * scale)
            sw = int(tw * scale)
            if sh < 10 or sw < 10:
                continue
            if sh > frame_gray.shape[0] or sw > frame_gray.shape[1]:
                continue

            # 그레이스케일 매칭 — 채널 1개로 ~3배 빠름
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            resized = cv2.resize(tmpl_gray, (sw, sh), interpolation=interp)
            result = cv2.matchTemplate(frame_gray, resized, cv2.TM_CCOEFF_NORMED)

            # confidence 이상인 모든 위치 찾기
            locations = np.where(result >= confidence)

            for pt_y, pt_x in zip(*locations):
                score = result[pt_y, pt_x]
                candidates.append((int(pt_x), int(pt_y), sw, sh, float(score), tmpl_name))

    # UI 영역 제외 필터링
    frame_h = frame.shape[0]
    filtered = []
    for c in candidates:
        cy = c[1] + c[3] // 2  # bbox 중심 y
        if cy < UI_EXCLUDE_TOP:
            continue  # 상단 UI 영역
        if cy > frame_h - UI_EXCLUDE_BOTTOM:
            continue  # 하단 UI 영역
        # 밝기 필터 — 감지 영역이 지나치게 밝으면 배경 오탐으로 제거
        roi = frame_gray[c[1]:c[1] + c[3], c[0]:c[0] + c[2]]
        if roi.size > 0 and np.mean(roi) > BRIGHTNESS_REJECT_THRESHOLD:
            continue
        filtered.append(c)
    candidates = filtered

    # NMS 적용
    if not candidates:
        return []

    bboxes = [(c[0], c[1], c[2], c[3]) for c in candidates]
    scores = [c[4] for c in candidates]
    names = [c[5] for c in candidates]

    picked = _nms_with_scores(bboxes, scores, overlap_thresh=0.3)

    results = []
    for i in picked:
        x, y, w, h = bboxes[i]
        results.append((x, y, w, h, scores[i], names[i]))

    if results:
        log.debug(f"늑대 감지: {len(results)}마리")
        for r in results:
            log.debug(f"  → ({r[0]},{r[1]}) {r[2]}x{r[3]} score={r[4]:.3f} [{r[5]}]")

    return results


def _nms_with_scores(bboxes, scores, overlap_thresh=0.3):
    """점수 기반 NMS. 높은 점수 우선 유지."""
    if not bboxes:
        return []

    boxes = np.array(bboxes, dtype=np.float32)
    sc = np.array(scores, dtype=np.float32)

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 0] + boxes[:, 2]
    y2 = boxes[:, 1] + boxes[:, 3]
    areas = boxes[:, 2] * boxes[:, 3]

    idxs = np.argsort(sc)[::-1]  # 점수 높은 순
    picked = []

    while len(idxs) > 0:
        i = idxs[0]
        picked.append(i)

        xx1 = np.maximum(x1[i], x1[idxs[1:]])
        yy1 = np.maximum(y1[i], y1[idxs[1:]])
        xx2 = np.minimum(x2[i], x2[idxs[1:]])
        yy2 = np.minimum(y2[i], y2[idxs[1:]])

        inter_w = np.maximum(0, xx2 - xx1)
        inter_h = np.maximum(0, yy2 - yy1)
        inter_area = inter_w * inter_h
        union = areas[i] + areas[idxs[1:]] - inter_area
        overlap = inter_area / union  # 표준 IoU

        remove = np.where(overlap > overlap_thresh)[0]
        idxs = np.delete(idxs, np.concatenate(([0], remove + 1)))

    return picked


class MonsterTracker:
    """
    늑대 전용 감지 클래스.

    동작 흐름:
        1. detect_wolves() → 늑대 템플릿 매칭으로 감지
        2. find_and_track() → 매 프레임 재감지 + ROI 우선 탐색
        3. 감지 실패 연속 N회 → 사망 판정
    """

    def __init__(self, region=None, template_dir="images", confidence=DETECT_CONFIDENCE):
        self.region = region
        self.template_dir = template_dir
        self.confidence = confidence
        self.has_target = False              # 현재 타겟이 있는지 여부
        self.last_bbox = None
        # 전투 판정 상태
        self._target_start_time = 0.0       # 현재 대상 추적 시작 시각
        self._last_hp_check_time = 0.0      # 마지막 HP 체크 시각
        self._last_hp_ratio = -1.0          # 마지막 HP 비율 (-1=미측정)
        self._hp_no_change_count = 0        # HP 변화 없음 연속 횟수
        self._skip_positions = []           # 타임아웃된 대상 위치 (일시 제외)
        self._detect_miss_count = 0         # 연속 감지 실패 횟수 (사망 판정용)
        self._detect_miss_max = DETECT_MISS_MAX
        self._last_detect_was_edge = False   # 마지막 감지가 에지 전용이었는지
        self._edge_only_count = 0            # 에지 전용 연속 감지 횟수
        # 시각 기반 픽업용 스냅샷 (frozen dataclass — atomic 통째 교체)
        self.combat_snapshot: Optional[CombatSnapshot] = None

    # ══════════════════════════════════════════════
    # 좌표 변환 헬퍼 (내부: 프레임 로컬, 외부: 스크린 절대)
    # ══════════════════════════════════════════════

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

    def _local_to_screen(self, x, y):
        """프레임 로컬 좌표 → 스크린 절대 좌표."""
        if self.region:
            return x + self.region[0], y + self.region[1]
        return x, y

    def _bbox_center_screen(self, bbox):
        """bbox 중심을 스크린 절대 좌표로 반환."""
        cx = bbox[0] + bbox[2] // 2
        cy = bbox[1] + bbox[3] // 2
        return self._local_to_screen(cx, cy)

    def detect(self, frame=None):
        """
        화면에서 몬스터를 감지하여 바운딩 박스 리스트 반환.

        Args:
            frame: BGR 이미지. None이면 새로 캡처.

        Returns:
            [(x, y, w, h, score, name), ...] 또는 빈 리스트
        """
        if frame is None:
            frame = capture_screen(region=self.region)
        if frame is None:
            return []

        return detect_wolves(frame, self.template_dir, self.confidence)

    def detect_nearest(self, frame=None, player_pos=None):
        """
        몬스터를 감지하고 가장 가까운 것의 바운딩 박스 반환.

        Returns:
            (x, y, w, h) 또는 None
        """
        wolves = self.detect(frame=frame)
        if not wolves:
            return None

        # 플레이어 위치 기준
        if player_pos is None:
            if self.region:
                px = self.region[2] // 2
                py = self.region[3] // 2
            else:
                px, py = 960, 540  # 기본 FHD 중앙
        else:
            px, py = player_pos
            if self.region:
                px -= self.region[0]
                py -= self.region[1]

        # 거리 기준 정렬
        def dist(wolf):
            cx = wolf[0] + wolf[2] // 2
            cy = wolf[1] + wolf[3] // 2
            return (cx - px) ** 2 + (cy - py) ** 2

        wolves.sort(key=dist)
        w = wolves[0]
        log.info(f"가장 가까운 늑대: ({w[0]},{w[1]}) score={w[4]:.3f} [{w[5]}]")
        return (w[0], w[1], w[2], w[3])


    def _measure_hp_ratio(self, frame):
        """
        추적 중인 대상의 HP바 비율(0.0~1.0)을 측정.
        bbox 상단 위쪽 영역에서 HP바 색상 픽셀 비율로 추정.

        Returns:
            float (0.0~1.0) 또는 -1.0 (측정 불가)
        """
        if self.last_bbox is None or frame is None:
            return -1.0

        x, y, w, h = self.last_bbox
        # HP바 영역: bbox 상단 위쪽
        hp_y1 = max(0, y + HP_BAR_OFFSET_Y)
        hp_y2 = max(0, y + HP_BAR_OFFSET_Y + HP_BAR_HEIGHT)
        hp_x1 = max(0, x)
        hp_x2 = min(frame.shape[1], x + w)

        if hp_y1 >= hp_y2 or hp_x1 >= hp_x2:
            return -1.0

        roi = frame[hp_y1:hp_y2, hp_x1:hp_x2]
        if roi.size == 0:
            return -1.0

        # HSV 변환 후 HP바 색상 범위 마스크 (빨간색 2구간 OR)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, np.array(HP_BAR_COLOR_LOWER1), np.array(HP_BAR_COLOR_UPPER1))
        mask2 = cv2.inRange(hsv, np.array(HP_BAR_COLOR_LOWER2), np.array(HP_BAR_COLOR_UPPER2))
        mask = cv2.bitwise_or(mask1, mask2)
        total_pixels = roi.shape[0] * roi.shape[1]
        if total_pixels == 0:
            return -1.0

        ratio = np.count_nonzero(mask) / total_pixels
        return ratio

    def _check_target_alive(self, frame):
        """
        현재 대상이 아직 유효한지 판정 (타임아웃 + HP바 변화).

        Returns:
            TRACK_OK=계속 공격, TRACK_ABANDONED_TIMEOUT/TRACK_ABANDONED_HP=포기 사유
        """
        now = time.time()

        # 1. 타임아웃 체크
        elapsed = now - self._target_start_time
        if elapsed > TARGET_TIMEOUT:
            log.warning(f"타겟 타임아웃 ({elapsed:.1f}초 경과) → 타겟 전환")
            return TRACK_ABANDONED_TIMEOUT

        # 2. HP바 변화 체크 (주기적)
        if now - self._last_hp_check_time >= HP_CHECK_INTERVAL:
            self._last_hp_check_time = now
            hp_ratio = self._measure_hp_ratio(frame)

            if hp_ratio < 0:
                # HP바 측정 불가 — 타임아웃에만 의존
                return TRACK_OK

            if self._last_hp_ratio >= 0:
                delta = self._last_hp_ratio - hp_ratio
                if abs(delta) < 0.02:
                    # HP 변화 거의 없음
                    self._hp_no_change_count += 1
                    log.debug(
                        f"HP 변화 없음 ({self._hp_no_change_count}/{HP_NO_CHANGE_MAX})"
                        f" ratio={hp_ratio:.2f}"
                    )
                    if self._hp_no_change_count >= HP_NO_CHANGE_MAX:
                        log.warning("HP 변화 없음 지속 → 타겟 전환")
                        return TRACK_ABANDONED_HP
                else:
                    # HP 감소 확인 → 공격 유효
                    self._hp_no_change_count = 0
                    log.debug(f"HP 변화 감지: {self._last_hp_ratio:.2f} → {hp_ratio:.2f}")

            self._last_hp_ratio = hp_ratio

        return TRACK_OK

    def _abandon_target(self):
        """현재 대상을 포기하고 스킵 목록에 등록."""
        if self.last_bbox is not None:
            cx = self.last_bbox[0] + self.last_bbox[2] // 2
            cy = self.last_bbox[1] + self.last_bbox[3] // 2
            self._skip_positions.append((cx, cy, time.time()))
            log.info(f"대상 포기: ({cx}, {cy}) → 스킵 목록 등록")
        self.has_target = False
        self._reset_combat_state()
        # 의도적으로 combat_snapshot 보존 — HP-stuck abandon이 사실상 사망인 경우가 많아 픽업 베이스라인으로 사용
        # 다음 진짜 감지 성공 시 자연 갱신됨

    def _reset_combat_state(self):
        """전투 판정 상태 초기화."""
        self._target_start_time = 0.0
        self._last_hp_check_time = 0.0
        self._last_hp_ratio = -1.0
        self._hp_no_change_count = 0
        self._edge_only_count = 0
        self._last_detect_was_edge = False

    def _is_skipped(self, bbox):
        """해당 위치가 최근 스킵된 대상인지 확인 (30초간 유지)."""
        now = time.time()
        # 만료된 항목 정리
        self._skip_positions = [
            (sx, sy, t) for sx, sy, t in self._skip_positions
            if now - t < 30.0
        ]
        cx = bbox[0] + bbox[2] // 2
        cy = bbox[1] + bbox[3] // 2
        for sx, sy, _ in self._skip_positions:
            dist = ((cx - sx) ** 2 + (cy - sy) ** 2) ** 0.5
            if dist < 50:  # 50px 이내면 같은 대상으로 간주
                return True
        return False

    def _detect_in_roi(self, frame, last_bbox, pad_ratio=1.0, tracking=False):
        """
        마지막 감지 위치 주변 ROI에서만 빠르게 재탐색.
        그레이스케일 매칭으로 전체 프레임 대비 ~3-8ms로 완료.

        Args:
            frame: BGR 전체 프레임
            last_bbox: (x, y, w, h) 마지막 감지 영역
            pad_ratio: bbox 크기 대비 패딩 비율 (1.0 = bbox 크기만큼 확장)

        Returns:
            (x, y, w, h) 또는 None
        """
        x, y, w, h = last_bbox
        pad_x = int(w * pad_ratio)
        pad_y = int(h * pad_ratio)

        roi_x1 = max(0, x - pad_x)
        roi_y1 = max(0, y - pad_y)
        roi_x2 = min(frame.shape[1], x + w + pad_x)
        roi_y2 = min(frame.shape[0], y + h + pad_y)

        roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]
        if roi.size == 0:
            return None

        # 그레이스케일 ROI (속도 3배 향상)
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        templates = _load_templates(self.template_dir)
        best_score = 0
        best_result = None
        min_confidence = TRACKING_CONFIDENCE if tracking else self.confidence

        for fpath, tmpl_color, tmpl_gray in templates:
            th, tw = tmpl_gray.shape[:2]

            for scale in ROI_DETECT_SCALES:
                sh = max(1, int(th * scale))
                sw = max(1, int(tw * scale))

                # ROI보다 큰 템플릿은 스킵 (강제 축소와 멀티스케일 분리)
                if sh > roi_gray.shape[0] or sw > roi_gray.shape[1]:
                    continue

                # 다운스케일 INTER_AREA, 업스케일 INTER_LINEAR
                interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                tmpl_resized = cv2.resize(tmpl_gray, (sw, sh), interpolation=interp)

                result = cv2.matchTemplate(roi_gray, tmpl_resized, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)

                if max_val >= min_confidence and max_val > best_score:
                    best_score = max_val
                    # ROI 좌표 → 프레임 좌표로 변환
                    best_result = (roi_x1 + max_loc[0], roi_y1 + max_loc[1], sw, sh)

        if best_result:
            # 밝기 필터 — 감지 영역이 지나치게 밝으면 배경 오탐으로 제거
            bx, by, bw, bh = best_result
            check_roi = roi_gray[by - roi_y1:by - roi_y1 + bh, bx - roi_x1:bx - roi_x1 + bw]
            if check_roi.size > 0 and np.mean(check_roi) > BRIGHTNESS_REJECT_THRESHOLD:
                log.debug(f"ROI 밝기 필터 제거 [그레이]: mean={np.mean(check_roi):.0f} > {BRIGHTNESS_REJECT_THRESHOLD}")
                best_result = None
                best_score = 0
            else:
                self._last_detect_was_edge = False
                log.debug(f"ROI 재탐색 성공 [그레이]: ({best_result[0]},{best_result[1]}) score={best_score:.3f}")
                return best_result

        # === 반투명 변형 폴백 (원본 실패 + 추적 중일 때만) ===
        if tracking and TRANSPARENT_VARIANTS_ENABLED:
            transparent = _load_transparent_templates(self.template_dir)
            for fpath, tmpl_color, tmpl_gray in transparent:
                th, tw = tmpl_gray.shape[:2]
                for scale in ROI_DETECT_SCALES:
                    sh = max(1, int(th * scale))
                    sw = max(1, int(tw * scale))
                    if sh > roi_gray.shape[0] or sw > roi_gray.shape[1]:
                        continue
                    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                    tmpl_resized = cv2.resize(tmpl_gray, (sw, sh), interpolation=interp)
                    result = cv2.matchTemplate(roi_gray, tmpl_resized, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    if max_val >= min_confidence and max_val > best_score:
                        best_score = max_val
                        best_result = (roi_x1 + max_loc[0], roi_y1 + max_loc[1], sw, sh)

            if best_result:
                bx, by, bw, bh = best_result
                check_roi = roi_gray[by - roi_y1:by - roi_y1 + bh, bx - roi_x1:bx - roi_x1 + bw]
                if check_roi.size > 0 and np.mean(check_roi) > BRIGHTNESS_REJECT_THRESHOLD:
                    log.debug(f"ROI 밝기 필터 제거 [반투명]: mean={np.mean(check_roi):.0f} > {BRIGHTNESS_REJECT_THRESHOLD}")
                    best_result = None
                    best_score = 0
                else:
                    self._last_detect_was_edge = False
                    log.debug(f"ROI 재탐색 성공 [반투명]: ({best_result[0]},{best_result[1]}) score={best_score:.3f}")
                    return best_result

        # === 에지 매칭 폴백 (그레이+반투명 실패 + 추적 중일 때만) ===
        if not EDGE_DETECT_ENABLED or not tracking:
            return None

        roi_edge = cv2.Canny(roi_gray, EDGE_CANNY_LOW, EDGE_CANNY_HIGH)
        edge_templates = _load_edge_templates(self.template_dir)
        best_edge_score = 0
        best_edge_result = None

        for fpath, tmpl_edge in edge_templates:
            th, tw = tmpl_edge.shape[:2]
            for scale in ROI_DETECT_SCALES:
                sh = max(1, int(th * scale))
                sw = max(1, int(tw * scale))
                if sh > roi_edge.shape[0] or sw > roi_edge.shape[1]:
                    continue
                interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                tmpl_resized = cv2.resize(tmpl_edge, (sw, sh), interpolation=interp)
                result = cv2.matchTemplate(roi_edge, tmpl_resized, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                if max_val >= EDGE_DETECT_CONFIDENCE and max_val > best_edge_score:
                    best_edge_score = max_val
                    best_edge_result = (roi_x1 + max_loc[0], roi_y1 + max_loc[1], sw, sh)

        if best_edge_result:
            bx, by, bw, bh = best_edge_result
            check_roi = roi_gray[by - roi_y1:by - roi_y1 + bh, bx - roi_x1:bx - roi_x1 + bw]
            if check_roi.size > 0 and np.mean(check_roi) > BRIGHTNESS_REJECT_THRESHOLD:
                log.debug(f"ROI 밝기 필터 제거 [에지]: mean={np.mean(check_roi):.0f} > {BRIGHTNESS_REJECT_THRESHOLD}")
                return None
            self._last_detect_was_edge = True
            log.debug(f"ROI 재탐색 성공 [에지]: ({best_edge_result[0]},{best_edge_result[1]}) score={best_edge_score:.3f}")
            return best_edge_result

        return None

    def refine_position(self, original_pos=None):
        """
        클릭 직전 호출. 마지막 감지 위치 주변 ROI만 빠르게 재캡처+매칭하여
        몬스터의 현재 위치를 반환. (~5-15ms)

        Args:
            original_pos: (x, y) 원본 감지 좌표. 거리 제한 검증에 사용.

        Returns:
            (center_x, center_y) 또는 None (재감지 실패 또는 거리 초과 시)
        """
        if not PRECLICK_REFINE_ENABLED or self.last_bbox is None:
            return None

        frame = capture_screen(region=self.region)
        if frame is None:
            return None

        refined_bbox = self._detect_in_roi(frame, self.last_bbox,
                                           pad_ratio=PRECLICK_ROI_PAD_RATIO,
                                           tracking=True)
        if refined_bbox is None:
            return None

        cx, cy = self._bbox_center_screen(refined_bbox)

        # 거리 제한: 원본 좌표에서 너무 멀면 오탐으로 판단하여 무시
        if original_pos is not None:
            dist = ((cx - original_pos[0]) ** 2 + (cy - original_pos[1]) ** 2) ** 0.5
            if dist > REFINE_MAX_DISTANCE:
                log.debug(f"보정 거리 초과 ({dist:.0f}px > {REFINE_MAX_DISTANCE}px) → 원본 좌표 유지")
                return None

        # last_bbox 갱신 + 같은 캡처/bbox로 스냅샷 동기화
        self.last_bbox = refined_bbox
        self._update_combat_snapshot(frame, refined_bbox)
        log.debug(f"클릭 전 위치 보정: ({cx}, {cy})")
        return (cx, cy)

    def find_and_track(self):
        """
        매 프레임 템플릿 재감지 방식으로 몬스터를 찾아 중심 좌표 반환.
        CSRT 추적기 드리프트 문제를 회피하기 위해 매번 재감지.
        타임아웃/HP 미변화 시 자동으로 타겟 전환.

        Returns:
            ((center_x, center_y), reason) — reason은 TRACK_* 상수
            (None, reason) — 감지 실패 시
        """
        # 프레임 1회 캡처
        frame = capture_screen(region=self.region)
        if frame is None:
            return None, TRACK_NOT_FOUND

        # 타겟 생존 판정 (공격 중인 경우)
        if self.has_target:
            alive_reason = self._check_target_alive(frame)
            if alive_reason != TRACK_OK:
                self._abandon_target()
                return None, alive_reason

        # 추적 중이면 ROI 우선 탐색 (빠름, ~5-15ms)
        bbox = None
        if self.has_target and self.last_bbox is not None:
            roi_bbox = self._detect_in_roi(frame, self.last_bbox,
                                           pad_ratio=TRACKING_ROI_PAD_RATIO,
                                           tracking=True)
            # 스킵 목록에 없는 경우에만 사용
            if roi_bbox is not None and not self._is_skipped(roi_bbox):
                bbox = roi_bbox

        # 에지 전용 연속 감지 안전장치
        if bbox is not None and self._last_detect_was_edge:
            self._edge_only_count += 1
            if self._edge_only_count >= EDGE_ONLY_MAX_COUNT:
                log.warning(f"에지 전용 연속 {self._edge_only_count}회 → 신뢰도 낮음, 추적 해제")
                self._abandon_target()
                return None, TRACK_NOT_FOUND
        elif bbox is not None:
            self._edge_only_count = 0

        # ROI 실패 시 전체 프레임 탐색
        # 추적 중이면 마지막 추적 위치 기준으로 가장 가까운 몬스터 선택 (타겟 고정)
        if bbox is None:
            last_pos = None
            if self.has_target and self.last_bbox is not None:
                last_pos = self._bbox_center_screen(self.last_bbox)
            bbox = self._detect_nearest_available(frame=frame, player_pos=last_pos)

        if bbox is None:
            if self.has_target:
                self._detect_miss_count += 1
                log.debug(f"감지 실패 ({self._detect_miss_count}/{self._detect_miss_max})")
                if self._detect_miss_count >= self._detect_miss_max:
                    # 연속 N회 감지 실패 → 사망 확정
                    log.info(f"대상 소실 (연속 {self._detect_miss_count}회 미감지) → 사망 추정")
                    self.has_target = False
                    self._detect_miss_count = 0
                    self._reset_combat_state()
                    # 의도적으로 combat_snapshot 보존 — 픽업 베이스라인으로 사용 후 다음 감지 시 자연 갱신
                    return None, TRACK_KILLED
                else:
                    # 아직 사망 확정 아님 → 클릭 중단하고 대기 (유령 클릭 방지)
                    log.debug(f"감지 대기 중 ({self._detect_miss_count}/{self._detect_miss_max})")
                    return None, TRACK_MISS_PENDING
            return None, TRACK_NOT_FOUND

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

        # 같은 캡처(frame)에서 나온 bbox로 스냅샷 갱신 — 시각 픽업 베이스라인
        self._update_combat_snapshot(frame, bbox)

        return (cx, cy), TRACK_OK

    def _detect_nearest_available(self, frame=None, player_pos=None):
        """
        스킵 목록에 없는 가장 가까운 몬스터를 반환.

        Returns:
            (x, y, w, h) 또는 None
        """
        wolves = self.detect(frame=frame)
        if not wolves:
            return None

        # 플레이어 위치 기준
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

        # 거리 기준 정렬
        wolves.sort(key=lambda w: (w[0] + w[2] // 2 - px) ** 2 + (w[1] + w[3] // 2 - py) ** 2)

        # 스킵되지 않은 첫 대상 반환
        for w in wolves:
            bbox = (w[0], w[1], w[2], w[3])
            if not self._is_skipped(bbox):
                log.info(f"가장 가까운 몬스터: ({w[0]},{w[1]}) score={w[4]:.3f} [{w[5]}]")
                return bbox

        log.debug("모든 감지된 몬스터가 스킵 목록에 있음")
        return None

    def reset(self):
        """감지 상태 초기화."""
        self.has_target = False
        self.last_bbox = None
        self._detect_miss_count = 0
        self._reset_combat_state()
        self._skip_positions.clear()
        self.combat_snapshot = None
        log.debug("감지 상태 초기화")
