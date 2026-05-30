"""
색상 확인 필터 — 그레이스케일 템플릿 매칭의 오탐을 HSV 색상 히스토그램
상관도로 제거한다. detect_monsters가 NMS 뒤에 적용.

threshold <= 0 이면 비활성(모든 후보 통과).
"""
import cv2
import numpy as np

_H_BINS = 50
_S_BINS = 60
_RANGES = [0, 180, 0, 256]
_CHANNELS = [0, 1]


def color_match_score(roi_bgr, template_bgr):
    """
    두 BGR 이미지의 HSV(H-S) 히스토그램 상관도를 반환.

    Returns:
        float — cv2.HISTCMP_CORREL 결과 (-1.0~1.0). 높을수록 색 분포 유사.
        둘 중 하나라도 비어 있으면 -1.0.
    """
    if roi_bgr is None or template_bgr is None:
        return -1.0
    if roi_bgr.size == 0 or template_bgr.size == 0:
        return -1.0

    hsv_roi = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    hsv_tmpl = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2HSV)

    hist_roi = cv2.calcHist([hsv_roi], _CHANNELS, None, [_H_BINS, _S_BINS], _RANGES)
    hist_tmpl = cv2.calcHist([hsv_tmpl], _CHANNELS, None, [_H_BINS, _S_BINS], _RANGES)
    cv2.normalize(hist_roi, hist_roi, 0, 1, cv2.NORM_MINMAX)
    cv2.normalize(hist_tmpl, hist_tmpl, 0, 1, cv2.NORM_MINMAX)

    return float(cv2.compareHist(hist_roi, hist_tmpl, cv2.HISTCMP_CORREL))


def filter_by_color(frame_bgr, results, name_to_color, threshold):
    """
    감지 결과를 색상 상관도로 필터링.

    Args:
        frame_bgr: 전체 BGR 프레임
        results: [(x, y, w, h, score, name), ...]
        name_to_color: {template_name: BGR 템플릿 이미지}
        threshold: 색상 상관도 임계값. <= 0 이면 비활성(원본 그대로 반환).

    Returns:
        필터링된 results (입력과 동일 형식)
    """
    if threshold <= 0:
        return results

    kept = []
    for item in results:
        x, y, w, h, score, name = item[:6]
        tmpl_color = name_to_color.get(name)
        if tmpl_color is None:
            kept.append(item)
            continue
        roi = frame_bgr[max(0, y):y + h, max(0, x):x + w]
        if color_match_score(roi, tmpl_color) >= threshold:
            kept.append(item)
    return kept
