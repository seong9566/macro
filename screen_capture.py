"""
공통 화면 캡처 레이어.

dxcam(Desktop Duplication API) 우선 사용, 실패 시 mss로 자동 폴백.
monster_tracker.py와 image_finder.py가 이 모듈을 공유하여
캡처 방식을 일원화한다.
"""
import cv2
import numpy as np
from logger import log

# ══════════════════════════════════════════════
# dxcam 초기화 (실패 시 None → mss 폴백)
# ══════════════════════════════════════════════
_dxcam_camera = None
_use_dxcam = False

_screen_width = 1920
_screen_height = 1080

try:
    import ctypes
    _screen_width = ctypes.windll.user32.GetSystemMetrics(0)   # SM_CXSCREEN
    _screen_height = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
except Exception:
    pass

try:
    import dxcam as _dxcam_mod
    _dxcam_camera = _dxcam_mod.create(output_color="BGR")
    _use_dxcam = True
    log.info(f"dxcam 초기화 성공 (device: {_dxcam_mod.device_info()}, 화면: {_screen_width}x{_screen_height})")
except Exception as e:
    log.warning(f"dxcam 초기화 실패 → mss 폴백 사용: {e}")
    _use_dxcam = False

# ══════════════════════════════════════════════
# mss 폴백 (스레드별 인스턴스)
# ══════════════════════════════════════════════
import threading
import mss

_thread_local = threading.local()


def _get_mss():
    """스레드별 mss 인스턴스 반환 (스레드 안전)."""
    if not hasattr(_thread_local, "sct"):
        _thread_local.sct = mss.mss()
    return _thread_local.sct


# ══════════════════════════════════════════════
# 통합 캡처 인터페이스
# ══════════════════════════════════════════════

def capture_screen(region=None, grayscale=False):
    """
    화면을 캡처하여 OpenCV 배열로 반환.

    dxcam이 사용 가능하면 Desktop Duplication API(100+ FPS)를 사용하고,
    실패 시 mss(GDI BitBlt, 20~40 FPS)로 자동 폴백.

    Args:
        region: (x, y, w, h) 캡처 영역. None이면 전체 화면.
        grayscale: True이면 GRAY 1채널로 직접 반환 (탐지 전용, 2단계 변환 제거).
                   False이면 BGR 3채널 반환 (HP바 측정 등 색상 필요한 경우).

    Returns:
        numpy.ndarray (BGR 또는 GRAY) 또는 None (캡처 실패 시)
    """
    if _use_dxcam:
        return _capture_dxcam(region, grayscale)
    return _capture_mss(region, grayscale)


def _capture_dxcam(region, grayscale):
    """dxcam으로 캡처. region은 (x, y, w, h) → (left, top, right, bottom) 변환."""
    try:
        if region:
            x, y, w, h = region
            # 좌표 클램핑 (화면 범위 내로 제한)
            left = max(0, x)
            top = max(0, y)
            right = min(left + w, _screen_width)
            bottom = min(top + h, _screen_height)
            if right <= left or bottom <= top:
                return _capture_mss(region, grayscale)
            dxcam_region = (left, top, right, bottom)
            frame = _dxcam_camera.grab(region=dxcam_region)
        else:
            frame = _dxcam_camera.grab()

        if frame is None:
            return _capture_mss(region, grayscale)

        if grayscale:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame
    except Exception as e:
        log.debug(f"dxcam 캡처 실패 → mss 폴백: {e}")
        return _capture_mss(region, grayscale)


def _capture_mss(region, grayscale):
    """mss(GDI BitBlt)로 캡처."""
    try:
        sct = _get_mss()
        if region:
            monitor = {"left": region[0], "top": region[1],
                       "width": region[2], "height": region[3]}
        else:
            monitor = sct.monitors[0]
        screenshot = sct.grab(monitor)
        img = np.array(screenshot)

        if grayscale:
            return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except Exception as e:
        log.error(f"화면 캡처 실패: {e}")
        return None
