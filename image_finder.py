import cv2
import numpy as np
import time
import os
import glob
from screen_capture import capture_screen
from logger import log

# ── 템플릿 캐시 (동일 이미지 반복 로딩 방지) ──
_template_cache = {}

# ── ORB 특징점 매칭용 ──
_orb = cv2.ORB_create(nfeatures=500)
_bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
_keypoint_cache = {}  # {path: (keypoints, descriptors)}


def _load_template(template_path):
    """
    템플릿 이미지를 로딩하고 캐시에 저장.
    파일이 없거나 손상되면 예외를 발생시킴.
    """
    if template_path in _template_cache:
        return _template_cache[template_path]

    if not os.path.exists(template_path):
        log.error(f"템플릿 파일 없음: {template_path}")
        raise FileNotFoundError(f"템플릿 파일을 찾을 수 없습니다: {template_path}")

    template = cv2.imread(template_path)
    if template is None:
        log.error(f"템플릿 로딩 실패 (손상된 이미지?): {template_path}")
        raise ValueError(f"이미지를 읽을 수 없습니다: {template_path}")

    _template_cache[template_path] = template
    log.debug(f"템플릿 로딩 완료: {template_path} ({template.shape})")
    return template


def _load_templates(template_path):
    """
    단일 파일 또는 폴더 경로를 받아 템플릿 목록을 반환.
    폴더일 경우 내부의 모든 png/jpg 파일을 로딩.
    """
    if os.path.isdir(template_path):
        templates = []
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
            for f in glob.glob(os.path.join(template_path, ext)):
                templates.append((f, _load_template(f)))
        if not templates:
            log.error(f"폴더에 이미지 없음: {template_path}")
            raise FileNotFoundError(f"폴더에 이미지 파일이 없습니다: {template_path}")
        return templates
    else:
        return [(template_path, _load_template(template_path))]


# ══════════════════════════════════════════════
# HSV 색상 기반 감지 (방향 무관)
# ══════════════════════════════════════════════

def _find_by_color(screen, region=None,
                   hsv_lower=(0, 0, 180), hsv_upper=(180, 50, 255),
                   min_area=800, max_area=15000):
    """
    HSV 색상 범위로 대상을 감지하여 중심 좌표 목록을 반환.
    흰색 늑대: 채도 낮고(S < 50) 밝기 높은(V > 180) 영역.

    Args:
        screen: BGR 이미지
        region: 원본 화면 기준 오프셋 (x, y, w, h)
        hsv_lower: HSV 하한값 (H, S, V)
        hsv_upper: HSV 상한값 (H, S, V)
        min_area: 최소 덩어리 크기 (너무 작은 노이즈 제거)
        max_area: 최대 덩어리 크기 (UI 요소 등 제거)

    Returns:
        [(center_x, center_y, area), ...] 면적 큰 순 정렬, 또는 빈 리스트
    """
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(hsv_lower), np.array(hsv_upper))

    # 노이즈 제거: 열림(open) → 닫힘(close)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    results = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if min_area <= area <= max_area:
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            # region 오프셋 보정
            if region:
                cx += region[0]
                cy += region[1]

            results.append((cx, cy, area))

    # 면적 큰 순 정렬 (더 확실한 대상 우선)
    results.sort(key=lambda r: r[2], reverse=True)

    if results:
        log.debug(f"[color] 감지된 대상: {len(results)}개")
    return results


def find_monster_by_color(region=None, player_pos=None,
                          hsv_lower=(0, 0, 180), hsv_upper=(180, 50, 255),
                          min_area=800, max_area=15000):
    """
    색상 기반으로 몬스터를 찾아 가장 가까운 대상의 좌표를 반환.

    Args:
        region: 게임 창 영역 (x, y, w, h)
        player_pos: 플레이어 위치 (x, y) - None이면 화면 중앙 기준
        hsv_lower/hsv_upper: HSV 색상 범위
        min_area/max_area: 덩어리 크기 필터

    Returns:
        (center_x, center_y) 또는 None
    """
    screen = capture_screen(region=region)
    if screen is None:
        return None

    targets = _find_by_color(screen, region,
                             hsv_lower, hsv_upper,
                             min_area, max_area)

    if not targets:
        return None

    # 플레이어 위치 기준 가장 가까운 대상 선택
    if player_pos is None:
        if region:
            px = region[0] + region[2] // 2
            py = region[1] + region[3] // 2
        else:
            # 전체 화면 중앙
            px = screen.shape[1] // 2
            py = screen.shape[0] // 2
    else:
        px, py = player_pos

    # 거리 기준 정렬
    targets.sort(key=lambda t: (t[0] - px) ** 2 + (t[1] - py) ** 2)

    cx, cy, area = targets[0]
    log.info(f"몬스터 감지 [color]: ({cx}, {cy}) [area={area}]")
    return (cx, cy)


# ══════════════════════════════════════════════
# 템플릿 매칭 (기존 방식)
# ══════════════════════════════════════════════

def _template_match_gray(screen, template, confidence):
    """그레이스케일 템플릿 매칭 (색상 변화에 강함)."""
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    tmpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    if (tmpl_gray.shape[0] > screen_gray.shape[0] or
            tmpl_gray.shape[1] > screen_gray.shape[1]):
        return None, 0.0

    result = cv2.matchTemplate(screen_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    return max_loc, max_val


def _template_match_multiscale(screen, template, confidence,
                                scale_range=(0.7, 1.3), scale_step=0.1):
    """다중 스케일 템플릿 매칭 (크기 변화 대응)."""
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    tmpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    best_val = 0.0
    best_loc = None
    best_scale = 1.0

    scales = np.arange(scale_range[0], scale_range[1] + scale_step, scale_step)
    for scale in scales:
        h = int(tmpl_gray.shape[0] * scale)
        w = int(tmpl_gray.shape[1] * scale)
        if h < 10 or w < 10:
            continue
        if h > screen_gray.shape[0] or w > screen_gray.shape[1]:
            continue

        resized = cv2.resize(tmpl_gray, (w, h))
        result = cv2.matchTemplate(screen_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_scale = scale

    if best_val >= confidence and best_loc is not None:
        h = int(tmpl_gray.shape[0] * best_scale)
        w = int(tmpl_gray.shape[1] * best_scale)
        center_x = best_loc[0] + w // 2
        center_y = best_loc[1] + h // 2
        return (center_x, center_y), best_val, best_scale

    return None, best_val, best_scale


def _orb_match(screen, template_path, template, min_matches=10):
    """ORB 특징점 기반 매칭 (형태 변화에 강함)."""
    if template_path not in _keypoint_cache:
        tmpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        kp, des = _orb.detectAndCompute(tmpl_gray, None)
        if des is None:
            return None
        _keypoint_cache[template_path] = (kp, des)

    kp_tmpl, des_tmpl = _keypoint_cache[template_path]

    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    kp_screen, des_screen = _orb.detectAndCompute(screen_gray, None)
    if des_screen is None:
        return None

    matches = _bf.match(des_tmpl, des_screen)
    matches = sorted(matches, key=lambda m: m.distance)

    good_matches = [m for m in matches if m.distance < 60]

    if len(good_matches) >= min_matches:
        pts = np.array([kp_screen[m.trainIdx].pt for m in good_matches])
        center_x = int(np.mean(pts[:, 0]))
        center_y = int(np.mean(pts[:, 1]))
        log.debug(
            f"[ORB] 특징점 매칭 성공: {len(good_matches)}개 "
            f"→ ({center_x}, {center_y})"
        )
        return (center_x, center_y)

    return None


def find_image(template_path, confidence=0.8, region=None, method="auto"):
    """
    화면에서 템플릿 이미지를 찾아 중심 좌표를 반환.

    Args:
        template_path: 찾을 이미지 경로 (파일 또는 폴더)
        confidence: 매칭 임계값 (0.0 ~ 1.0)
        region: 탐색 영역 (x, y, w, h) - None이면 전체 화면
        method: 매칭 방식
            "color"      - HSV 색상 기반 감지 (방향 무관, 가장 빠름)
            "auto"       - 색상 → 그레이스케일 → ORB 순서로 시도
            "gray"       - 그레이스케일 템플릿 매칭만
            "multiscale" - 다중 스케일 매칭만
            "orb"        - ORB 특징점 매칭만

    Returns:
        (center_x, center_y) 또는 None
    """
    # ── 색상 기반 감지 우선 ──
    if method in ("auto", "color"):
        pos = find_monster_by_color(region=region)
        if pos:
            return pos
        if method == "color":
            return None

    # ── 템플릿 매칭 폴백 ──
    screen = capture_screen(region=region)
    if screen is None:
        return None

    templates = _load_templates(template_path)

    for tmpl_path, template in templates:
        result = _find_single(screen, tmpl_path, template, confidence, region, method)
        if result:
            return result

    return None


def _find_single(screen, tmpl_path, template, confidence, region, method):
    """단일 템플릿에 대한 매칭 수행."""
    basename = os.path.basename(tmpl_path)

    # ── 그레이스케일 매칭 ──
    if method in ("auto", "gray"):
        loc, score = _template_match_gray(screen, template, confidence)
        log.debug(f"[gray] {basename} → score={score:.3f} (threshold={confidence})")

        if score >= confidence and loc is not None:
            h, w = template.shape[:2]
            center_x = loc[0] + w // 2
            center_y = loc[1] + h // 2
            if region:
                center_x += region[0]
                center_y += region[1]
            log.info(f"이미지 발견 [gray]: {basename} → ({center_x}, {center_y}) [score={score:.3f}]")
            return (center_x, center_y)

        if method == "gray":
            return None

    # ── ORB 특징점 매칭 ──
    if method in ("auto", "orb"):
        pos = _orb_match(screen, tmpl_path, template)
        if pos is not None:
            cx, cy = pos
            if region:
                cx += region[0]
                cy += region[1]
            log.info(f"이미지 발견 [ORB]: {basename} → ({cx}, {cy})")
            return (cx, cy)

    return None


def wait_for_image(template_path, timeout=10, interval=0.5, **kwargs):
    """
    이미지가 나타날 때까지 대기.
    timeout 초 내에 못 찾으면 None 반환.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            pos = find_image(template_path, **kwargs)
            if pos:
                return pos
        except (FileNotFoundError, ValueError):
            return None
        time.sleep(interval)

    log.warning(
        f"이미지 대기 timeout ({timeout}초): "
        f"{os.path.basename(template_path)}"
    )
    return None
