import cv2
import numpy as np
import pyautogui
import os
import glob
from logger import log

# ══════════════════════════════════════════════
# 화면 캡처
# ══════════════════════════════════════════════

def capture_screen(region=None):
    """화면을 캡처하여 OpenCV BGR 배열로 반환."""
    try:
        screenshot = pyautogui.screenshot(region=region)
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    except Exception as e:
        log.error(f"화면 캡처 실패: {e}")
        return None


# ══════════════════════════════════════════════
# 템플릿 캐시
# ══════════════════════════════════════════════

_template_cache = {}  # {path: grayscale_template}


def _load_templates(template_dir):
    """템플릿 폴더에서 모든 이미지를 그레이스케일로 로딩 (캐시 활용)."""
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
            templates.append((fpath, tmpl_gray))
            log.debug(f"템플릿 로딩: {os.path.basename(fpath)} ({tmpl_gray.shape})")

    _template_cache[template_dir] = templates
    log.info(f"늑대 템플릿 {len(templates)}개 로딩 완료")
    return templates


# ══════════════════════════════════════════════
# 멀티스케일 템플릿 매칭 (늑대 전용)
# ══════════════════════════════════════════════

def detect_wolves(frame, template_dir="images", confidence=0.55,
                  scales=(0.8, 0.9, 1.0, 1.1, 1.2)):
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
    templates = _load_templates(template_dir)
    if not templates:
        return []

    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    candidates = []

    for fpath, tmpl_gray in templates:
        tmpl_name = os.path.basename(fpath)
        th, tw = tmpl_gray.shape[:2]

        for scale in scales:
            sh = int(th * scale)
            sw = int(tw * scale)
            if sh < 10 or sw < 10:
                continue
            if sh > frame_gray.shape[0] or sw > frame_gray.shape[1]:
                continue

            resized = cv2.resize(tmpl_gray, (sw, sh))
            result = cv2.matchTemplate(frame_gray, resized, cv2.TM_CCOEFF_NORMED)

            # confidence 이상인 모든 위치 찾기
            locations = np.where(result >= confidence)

            for pt_y, pt_x in zip(*locations):
                score = result[pt_y, pt_x]
                candidates.append((int(pt_x), int(pt_y), sw, sh, float(score), tmpl_name))

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
        overlap = inter_area / np.minimum(areas[i], areas[idxs[1:]])

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

    def __init__(self, region=None, template_dir="images", confidence=0.55):
        self.region = region
        self.template_dir = template_dir
        self.confidence = confidence
        self.tracker = None
        self.tracking = False
        self.last_bbox = None
        self.lost_count = 0
        self.max_lost = 10
        self.track_frame_count = 0
        self.verify_interval = 60  # N프레임마다 템플릿 재검증 (여유롭게)
        self.verify_fail_count = 0
        self.verify_fail_max = 5  # 연속 검증 실패 N회 시 추적 해제

    def detect(self):
        """
        화면에서 늑대만 감지하여 바운딩 박스 리스트 반환.
        템플릿 매칭 전용 — 늑대 이미지에 매칭되는 것만 반환.

        Returns:
            [(x, y, w, h, score, name), ...] 또는 빈 리스트
        """
        frame = capture_screen(region=self.region)
        if frame is None:
            return []

        return detect_wolves(frame, self.template_dir, self.confidence)

    def detect_nearest(self, player_pos=None):
        """
        늑대를 감지하고 가장 가까운 것의 바운딩 박스 반환.

        Returns:
            (x, y, w, h) 또는 None
        """
        wolves = self.detect()
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

        # ROI 영역에서 늑대 템플릿 매칭 시도
        templates = _load_templates(self.template_dir)
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        for fpath, tmpl_gray in templates:
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

            if max_val >= self.confidence * 0.5:  # 검증은 기준을 크게 낮춤 (추적 중 변형 감안)
                log.debug(f"추적 대상 검증 성공: score={max_val:.3f}")
                return True

        log.debug("추적 대상 검증 실패 (1회)")
        return False

    def start_tracking(self, bbox):
        """특정 바운딩 박스에 대한 추적 시작."""
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

    def update(self):
        """
        추적 업데이트. 현재 늑대의 스크린 절대 좌표 반환.

        Returns:
            (center_x, center_y) 또는 None (추적 실패 시)
        """
        if not self.tracking or self.tracker is None:
            return None

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

    def find_and_track(self):
        """
        늑대 감지 → 가장 가까운 대상 추적 → 중심 좌표 반환.
        이미 추적 중이면 업데이트만 수행.

        Returns:
            (center_x, center_y) 또는 None
        """
        # 이미 추적 중이면 업데이트
        if self.tracking and self.tracker is not None:
            pos = self.update()
            if pos:
                return pos
            # update에서 tracker가 None이 됐을 수 있으므로 리셋
            self.tracking = False
            self.tracker = None

        # 새로 감지
        bbox = self.detect_nearest()
        if bbox is None:
            log.debug("늑대 미발견")
            return None

        # 추적 시작
        if not self.start_tracking(bbox):
            return None

        cx = bbox[0] + bbox[2] // 2
        cy = bbox[1] + bbox[3] // 2
        if self.region:
            cx += self.region[0]
            cy += self.region[1]

        return (cx, cy)

    def reset(self):
        """추적 상태 초기화."""
        self.tracker = None
        self.tracking = False
        self.last_bbox = None
        self.lost_count = 0
        self.track_frame_count = 0
        self.verify_fail_count = 0
        log.debug("트래커 초기화")
