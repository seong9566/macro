import cv2
import numpy as np
import mss
import os
import glob
import time
from config import (
    DETECT_CONFIDENCE, VERIFY_CONFIDENCE,
    TARGET_TIMEOUT, HP_CHECK_INTERVAL, HP_NO_CHANGE_MAX,
    HP_BAR_OFFSET_Y, HP_BAR_HEIGHT, HP_BAR_COLOR_LOWER, HP_BAR_COLOR_UPPER,
    UI_EXCLUDE_TOP, UI_EXCLUDE_BOTTOM,
    PRECLICK_REFINE_ENABLED, PRECLICK_ROI_PAD_RATIO, TRACKING_ROI_PAD_RATIO,
    REFINE_MAX_DISTANCE, DETECT_SCALES,
)
from logger import log

# ══════════════════════════════════════════════
# 화면 캡처 (mss 기반 — pyautogui 대비 3~6배 빠름)
# ══════════════════════════════════════════════

# ══════════════════════════════════════════════
# 추적 종료 사유
# ══════════════════════════════════════════════
TRACK_OK = "ok"                      # 추적 중 (정상)
TRACK_KILLED = "killed"              # 대상 소실 → 사망 추정
TRACK_ABANDONED_TIMEOUT = "timeout"  # 타임아웃으로 포기
TRACK_ABANDONED_HP = "hp_stuck"      # HP 미변화로 포기
TRACK_NOT_FOUND = "not_found"        # 감지 실패

import threading

_thread_local = threading.local()


def _get_sct():
    """스레드별 mss 인스턴스 반환 (스레드 안전)."""
    if not hasattr(_thread_local, "sct"):
        _thread_local.sct = mss.mss()
    return _thread_local.sct


def capture_screen(region=None):
    """화면을 캡처하여 OpenCV BGR 배열로 반환."""
    try:
        sct = _get_sct()
        if region:
            monitor = {"left": region[0], "top": region[1],
                       "width": region[2], "height": region[3]}
        else:
            monitor = sct.monitors[0]  # 전체 화면
        screenshot = sct.grab(monitor)
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)
    except Exception as e:
        log.error(f"화면 캡처 실패: {e}")
        return None


# ══════════════════════════════════════════════
# 템플릿 캐시
# ══════════════════════════════════════════════

_template_cache = {}  # {path: (color_template, gray_template)}


def _load_templates(template_dir):
    """템플릿 폴더에서 모든 이미지를 컬러+그레이스케일로 로딩 (캐시 활용)."""
    if template_dir in _template_cache:
        return _template_cache[template_dir]

    templates = []
    if not os.path.isdir(template_dir):
        log.error(f"템플릿 폴더 없음: {template_dir}")
        return templates

    for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
        for fpath in glob.glob(os.path.join(template_dir, ext)):
            tmpl_color = cv2.imread(fpath)
            if tmpl_color is None:
                continue
            tmpl_gray = cv2.cvtColor(tmpl_color, cv2.COLOR_BGR2GRAY)
            templates.append((fpath, tmpl_color, tmpl_gray))
            log.debug(f"템플릿 로딩: {os.path.basename(fpath)} ({tmpl_color.shape})")

    _template_cache[template_dir] = templates
    log.info(f"몬스터 템플릿 {len(templates)}개 로딩 완료")
    return templates


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
            resized = cv2.resize(tmpl_gray, (sw, sh))
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


# ══════════════════════════════════════════════
# OpenCV Tracker
# ══════════════════════════════════════════════

def create_tracker():
    """OpenCV 트래커 생성. CSRT가 가장 정확함."""
    if hasattr(cv2, 'legacy') and hasattr(cv2.legacy, 'TrackerCSRT_create'):
        return cv2.legacy.TrackerCSRT_create()
    if hasattr(cv2, 'TrackerCSRT_create'):
        return cv2.TrackerCSRT_create()
    if hasattr(cv2, 'legacy') and hasattr(cv2.legacy, 'TrackerKCF_create'):
        return cv2.legacy.TrackerKCF_create()
    if hasattr(cv2, 'TrackerKCF_create'):
        return cv2.TrackerKCF_create()
    raise RuntimeError("OpenCV Tracker를 사용할 수 없습니다. opencv-contrib-python을 설치하세요.")


class MonsterTracker:
    """
    늑대 전용 감지 + 추적 클래스.

    동작 흐름:
        1. detect_wolves() → 늑대 템플릿 매칭으로만 감지
        2. start_tracking() → CSRT 트래커로 추적 시작
        3. update() → 프레임마다 위치 업데이트
        4. 추적 실패 또는 주기적 검증 → 재감지
    """

    def __init__(self, region=None, template_dir="images", confidence=DETECT_CONFIDENCE):
        self.region = region
        self.template_dir = template_dir
        self.confidence = confidence
        self.verify_confidence = VERIFY_CONFIDENCE
        self.tracker = None
        self.tracking = False
        self.last_bbox = None
        self.lost_count = 0
        self.max_lost = 10
        self.track_frame_count = 0
        self.verify_interval = 25  # N프레임마다 템플릿 재검증
        self.verify_fail_count = 0
        self.verify_fail_max = 3  # 연속 검증 실패 N회 시 추적 해제
        # 전투 판정 상태
        self._target_start_time = 0.0       # 현재 대상 추적 시작 시각
        self._last_hp_check_time = 0.0      # 마지막 HP 체크 시각
        self._last_hp_ratio = -1.0          # 마지막 HP 비율 (-1=미측정)
        self._hp_no_change_count = 0        # HP 변화 없음 연속 횟수
        self._skip_positions = []           # 타임아웃된 대상 위치 (일시 제외)
        self._detect_miss_count = 0         # 연속 감지 실패 횟수 (사망 판정용)
        self._detect_miss_max = 3           # 연속 N회 실패 시 사망 판정

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

    def _verify_tracking(self):
        """추적 중인 대상이 여전히 늑대인지 템플릿 매칭으로 검증."""
        if self.last_bbox is None:
            return False

        frame = capture_screen(region=self.region)
        if frame is None:
            return False

        x, y, w, h = self.last_bbox
        # 바운딩 박스 주변을 약간 확장하여 검증
        pad = 10
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(frame.shape[1], x + w + pad)
        y2 = min(frame.shape[0], y + h + pad)
        roi = frame[y1:y2, x1:x2]

        if roi.size == 0:
            return False

        # ROI 영역에서 그레이스케일 템플릿 매칭 시도
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        templates = _load_templates(self.template_dir)

        for fpath, tmpl_color, tmpl_gray in templates:
            # ROI보다 큰 템플릿은 스킵
            if tmpl_gray.shape[0] > roi_gray.shape[0] or tmpl_gray.shape[1] > roi_gray.shape[1]:
                # 축소해서 시도
                scale = min(roi_gray.shape[0] / tmpl_gray.shape[0],
                            roi_gray.shape[1] / tmpl_gray.shape[1]) * 0.9
                if scale < 0.3:
                    continue
                sh = int(tmpl_gray.shape[0] * scale)
                sw = int(tmpl_gray.shape[1] * scale)
                tmpl_resized = cv2.resize(tmpl_gray, (sw, sh))
            else:
                tmpl_resized = tmpl_gray

            if tmpl_resized.shape[0] > roi_gray.shape[0] or tmpl_resized.shape[1] > roi_gray.shape[1]:
                continue

            result = cv2.matchTemplate(roi_gray, tmpl_resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)

            if max_val >= self.verify_confidence:  # 별도 검증 임계값 사용
                log.debug(f"추적 대상 검증 성공: score={max_val:.3f}")
                return True

        log.debug("추적 대상 검증 실패 (1회)")
        return False

    def start_tracking(self, bbox, frame=None):
        """특정 바운딩 박스에 대한 추적 시작."""
        if frame is None:
            frame = capture_screen(region=self.region)
        if frame is None:
            return False

        self.tracker = create_tracker()
        self.tracker.init(frame, tuple(bbox))
        self.tracking = True
        self.last_bbox = bbox
        self.lost_count = 0
        self.track_frame_count = 0
        cx = bbox[0] + bbox[2] // 2
        cy = bbox[1] + bbox[3] // 2
        log.info(f"늑대 추적 시작: bbox={bbox}, 중심=({cx}, {cy})")
        return True

    def update(self, frame=None):
        """
        추적 업데이트. 현재 몬스터의 스크린 절대 좌표 반환.

        Args:
            frame: BGR 이미지. None이면 새로 캡처.

        Returns:
            (center_x, center_y) 또는 None (추적 실패 시)
        """
        if not self.tracking or self.tracker is None:
            return None

        if frame is None:
            frame = capture_screen(region=self.region)
        if frame is None:
            return None

        success, bbox = self.tracker.update(frame)

        if success:
            self.lost_count = 0
            self.track_frame_count += 1
            x, y, w, h = [int(v) for v in bbox]
            self.last_bbox = (x, y, w, h)

            # 주기적으로 늑대인지 검증
            if self.track_frame_count % self.verify_interval == 0:
                if self._verify_tracking():
                    self.verify_fail_count = 0
                else:
                    self.verify_fail_count += 1
                    log.debug(f"검증 실패 누적: {self.verify_fail_count}/{self.verify_fail_max}")
                    if self.verify_fail_count >= self.verify_fail_max:
                        log.warning("추적 대상이 늑대가 아님 → 추적 해제")
                        self.tracking = False
                        self.tracker = None
                        return None

            cx = x + w // 2
            cy = y + h // 2

            # region 오프셋 보정
            if self.region:
                cx += self.region[0]
                cy += self.region[1]

            log.debug(f"추적 중: ({cx}, {cy})")
            return (cx, cy)
        else:
            self.lost_count += 1
            log.debug(f"추적 실패 ({self.lost_count}/{self.max_lost})")

            if self.lost_count >= self.max_lost:
                self.tracking = False
                self.tracker = None
                log.warning("추적 대상 소실 → 재감지 필요")

            return None

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

        # HSV 변환 후 HP바 색상 범위 마스크
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array(HP_BAR_COLOR_LOWER), np.array(HP_BAR_COLOR_UPPER))
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
        self.tracking = False
        self.tracker = None
        self._reset_combat_state()

    def _reset_combat_state(self):
        """전투 판정 상태 초기화."""
        self._target_start_time = 0.0
        self._last_hp_check_time = 0.0
        self._last_hp_ratio = -1.0
        self._hp_no_change_count = 0

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

    def _detect_in_roi(self, frame, last_bbox, pad_ratio=1.0):
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

        for fpath, tmpl_color, tmpl_gray in templates:
            # ROI보다 큰 템플릿은 축소하여 시도
            if tmpl_gray.shape[0] > roi_gray.shape[0] or tmpl_gray.shape[1] > roi_gray.shape[1]:
                scale = min(roi_gray.shape[0] / tmpl_gray.shape[0],
                            roi_gray.shape[1] / tmpl_gray.shape[1]) * 0.9
                if scale < 0.3:
                    continue
                tmpl_resized = cv2.resize(tmpl_gray,
                                          (int(tmpl_gray.shape[1] * scale),
                                           int(tmpl_gray.shape[0] * scale)))
            else:
                tmpl_resized = tmpl_gray

            if tmpl_resized.shape[0] > roi_gray.shape[0] or tmpl_resized.shape[1] > roi_gray.shape[1]:
                continue

            result = cv2.matchTemplate(roi_gray, tmpl_resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val >= self.confidence and max_val > best_score:
                best_score = max_val
                tw, th = tmpl_resized.shape[1], tmpl_resized.shape[0]
                # ROI 좌표 → 프레임 좌표로 변환
                best_result = (roi_x1 + max_loc[0], roi_y1 + max_loc[1], tw, th)

        if best_result:
            log.debug(f"ROI 재탐색 성공: ({best_result[0]},{best_result[1]}) score={best_score:.3f}")

        return best_result

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
                                           pad_ratio=PRECLICK_ROI_PAD_RATIO)
        if refined_bbox is None:
            return None

        cx = refined_bbox[0] + refined_bbox[2] // 2
        cy = refined_bbox[1] + refined_bbox[3] // 2

        # region 오프셋 보정
        if self.region:
            cx += self.region[0]
            cy += self.region[1]

        # 거리 제한: 원본 좌표에서 너무 멀면 오탐으로 판단하여 무시
        if original_pos is not None:
            dist = ((cx - original_pos[0]) ** 2 + (cy - original_pos[1]) ** 2) ** 0.5
            if dist > REFINE_MAX_DISTANCE:
                log.debug(f"보정 거리 초과 ({dist:.0f}px > {REFINE_MAX_DISTANCE}px) → 원본 좌표 유지")
                return None

        # last_bbox 갱신
        self.last_bbox = refined_bbox
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
        if self.tracking:
            alive_reason = self._check_target_alive(frame)
            if alive_reason != TRACK_OK:
                self._abandon_target()
                return None, alive_reason

        # 추적 중이면 ROI 우선 탐색 (빠름, ~5-15ms)
        bbox = None
        if self.tracking and self.last_bbox is not None:
            roi_bbox = self._detect_in_roi(frame, self.last_bbox,
                                           pad_ratio=TRACKING_ROI_PAD_RATIO)
            # 스킵 목록에 없는 경우에만 사용
            if roi_bbox is not None and not self._is_skipped(roi_bbox):
                bbox = roi_bbox

        # ROI 실패 시 전체 프레임 탐색
        # 추적 중이면 마지막 추적 위치 기준으로 가장 가까운 몬스터 선택 (타겟 고정)
        if bbox is None:
            last_pos = None
            if self.tracking and self.last_bbox is not None:
                lx = self.last_bbox[0] + self.last_bbox[2] // 2
                ly = self.last_bbox[1] + self.last_bbox[3] // 2
                if self.region:
                    lx += self.region[0]
                    ly += self.region[1]
                last_pos = (lx, ly)
            bbox = self._detect_nearest_available(frame=frame, player_pos=last_pos)

        if bbox is None:
            if self.tracking:
                self._detect_miss_count += 1
                log.debug(f"감지 실패 ({self._detect_miss_count}/{self._detect_miss_max})")
                if self._detect_miss_count >= self._detect_miss_max:
                    # 연속 N회 감지 실패 → 사망 추정
                    log.info(f"대상 소실 (연속 {self._detect_miss_count}회 미감지) → 사망 추정")
                    self.tracking = False
                    self._detect_miss_count = 0
                    self._reset_combat_state()
                    return None, TRACK_KILLED
                else:
                    # 아직 사망 확정 아님 → 마지막 알려진 위치로 계속 공격
                    if self.last_bbox is not None:
                        cx = self.last_bbox[0] + self.last_bbox[2] // 2
                        cy = self.last_bbox[1] + self.last_bbox[3] // 2
                        if self.region:
                            cx += self.region[0]
                            cy += self.region[1]
                        log.debug(f"마지막 위치로 계속 공격: ({cx},{cy})")
                        return (cx, cy), TRACK_OK
                    return None, TRACK_NOT_FOUND
            return None, TRACK_NOT_FOUND

        # 감지 성공 → 미스 카운터 초기화
        self._detect_miss_count = 0

        cx = bbox[0] + bbox[2] // 2
        cy = bbox[1] + bbox[3] // 2
        if self.region:
            cx += self.region[0]
            cy += self.region[1]

        # 첫 감지 시 전투 타이머 시작
        if not self.tracking:
            self.tracking = True
            self.last_bbox = bbox
            self._target_start_time = time.time()
            self._last_hp_check_time = time.time()
            self._last_hp_ratio = -1.0
            self._hp_no_change_count = 0
            log.info(f"몬스터 감지: ({cx},{cy}) bbox={bbox}")
        else:
            self.last_bbox = bbox

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
        """추적 상태 초기화."""
        self.tracker = None
        self.tracking = False
        self.last_bbox = None
        self.lost_count = 0
        self.track_frame_count = 0
        self.verify_fail_count = 0
        self._detect_miss_count = 0
        self._reset_combat_state()
        self._skip_positions.clear()
        log.debug("트래커 초기화")
