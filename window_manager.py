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
GetClientRect = user32.GetClientRect
ClientToScreen = user32.ClientToScreen
SetForegroundWindow = user32.SetForegroundWindow
ShowWindow = user32.ShowWindow
BringWindowToTop = user32.BringWindowToTop
GetForegroundWindow = user32.GetForegroundWindow

SW_RESTORE = 9

WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
)

# 마지막으로 찾은 게임 창 핸들 (포그라운드 전환용)
_last_hwnd = None


def find_game_window(title_keyword):
    """
    창 제목에 keyword가 포함된 윈도우 핸들(HWND)을 반환.

    Args:
        title_keyword: 게임 창 제목에 포함된 문자열

    Returns:
        HWND(int) 또는 None
    """
    global _last_hwnd
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
        _last_hwnd = result[0]
        log.info(f"게임 창 발견: HWND={result[0]}")
        return result[0]

    log.critical(f"게임 창 미발견: '{title_keyword}' 포함 윈도우 없음")
    return None


def activate_window(hwnd=None):
    """
    게임 창을 포그라운드로 전환.
    SendInput이 게임에 전달되려면 게임 창이 활성화 상태여야 함.

    Args:
        hwnd: 윈도우 핸들. None이면 마지막으로 찾은 게임 창 사용.

    Returns:
        True: 성공, False: 실패
    """
    target = hwnd or _last_hwnd
    if target is None:
        log.warning("포그라운드 전환 실패: HWND 없음")
        return False

    # 이미 포그라운드면 스킵
    if GetForegroundWindow() == target:
        return True

    # ALT 키 트릭: Windows 포커스 도용 방지 정책 우회
    # ALT를 SendInput으로 보내면 포그라운드 전환 권한 획득
    from clicker import _send_key_input, KEYEVENTF_KEYUP
    _send_key_input(0x38)  # ALT down (스캔코드)
    _send_key_input(0x38, KEYEVENTF_KEYUP)  # ALT up

    ShowWindow(target, SW_RESTORE)
    SetForegroundWindow(target)
    log.debug(f"게임 창 포그라운드 전환: HWND={target}")
    return True


def get_client_region(hwnd):
    """
    윈도우 핸들로부터 클라이언트 영역(타이틀바/테두리 제외)의
    스크린 절대 좌표 (x, y, w, h)를 반환.

    GetWindowRect는 DWM 투명 테두리를 포함해 좌표가 ~8px 틀어짐.
    GetClientRect + ClientToScreen으로 실제 게임 렌더링 영역만 정확히 획득.

    Returns:
        (x, y, width, height) 또는 None
    """
    if hwnd is None:
        return None

    # 클라이언트 영역 크기
    client_rect = wintypes.RECT()
    if not GetClientRect(hwnd, ctypes.byref(client_rect)):
        log.error("GetClientRect 실패")
        return None

    # 클라이언트 좌상단의 스크린 절대 좌표
    pt = wintypes.POINT(0, 0)
    ClientToScreen(hwnd, ctypes.byref(pt))

    x = pt.x
    y = pt.y
    w = client_rect.right - client_rect.left
    h = client_rect.bottom - client_rect.top
    log.debug(f"게임 클라이언트 영역: x={x}, y={y}, w={w}, h={h}")
    return (x, y, w, h)


def get_window_region(hwnd):
    """
    윈도우 핸들로부터 (x, y, w, h) 영역을 반환.
    클라이언트 영역(게임 렌더링 영역)만 반환하여 좌표 정확도 보장.

    Returns:
        (x, y, width, height) 또는 None
    """
    return get_client_region(hwnd)


def get_game_region(title_keyword):
    """
    게임 창 제목으로 검색 → 클라이언트 영역 좌표 반환 (편의 함수).

    Returns:
        (x, y, width, height) 또는 None
    """
    hwnd = find_game_window(title_keyword)
    return get_window_region(hwnd)
