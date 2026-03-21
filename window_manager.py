import ctypes
import ctypes.wintypes as wintypes
from logger import log

# ── win32gui 대신 ctypes로 직접 구현 (의존성 최소화) ──
user32 = ctypes.windll.user32

EnumWindows = user32.EnumWindows
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
IsWindowVisible = user32.IsWindowVisible
GetWindowRect = user32.GetWindowRect

WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
)


def find_game_window(title_keyword):
    """
    창 제목에 keyword가 포함된 윈도우 핸들(HWND)을 반환.

    Args:
        title_keyword: 게임 창 제목에 포함된 문자열

    Returns:
        HWND(int) 또는 None
    """
    result = []

    def callback(hwnd, lparam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                GetWindowTextW(hwnd, buf, length + 1)
                if title_keyword in buf.value:
                    result.append(hwnd)
        return True

    EnumWindows(WNDENUMPROC(callback), 0)

    if result:
        log.info(f"게임 창 발견: HWND={result[0]}")
        return result[0]

    log.critical(f"게임 창 미발견: '{title_keyword}' 포함 윈도우 없음")
    return None


def get_window_region(hwnd):
    """
    윈도우 핸들로부터 (x, y, w, h) 영역을 반환.
    image_finder의 region 파라미터에 직접 전달 가능.

    Returns:
        (x, y, width, height) 또는 None
    """
    if hwnd is None:
        return None

    rect = wintypes.RECT()
    if GetWindowRect(hwnd, ctypes.byref(rect)):
        x = rect.left
        y = rect.top
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        log.debug(f"게임 창 영역: x={x}, y={y}, w={w}, h={h}")
        return (x, y, w, h)

    log.error("GetWindowRect 실패")
    return None


def get_game_region(title_keyword):
    """
    게임 창 제목으로 검색 → 영역 좌표 반환 (편의 함수).

    Returns:
        (x, y, width, height) 또는 None
    """
    hwnd = find_game_window(title_keyword)
    return get_window_region(hwnd)
