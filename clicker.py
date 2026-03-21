import time
import random
import ctypes
from ctypes import wintypes
from logger import log

# ══════════════════════════════════════════════
# Win32 INPUT 구조체 (올바른 Union 구조)
# ══════════════════════════════════════════════

MOUSEEVENTF_MOVE       = 0x0001
MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOUSEEVENTF_ABSOLUTE   = 0x8000

INPUT_MOUSE    = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          wintypes.LONG),
        ("dy",          wintypes.LONG),
        ("mouseData",   wintypes.DWORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),   # ULONG_PTR (정수형)
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",         wintypes.WORD),
        ("wScan",       wintypes.WORD),
        ("dwFlags",     wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg",    wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    """Win32 INPUT 구조체의 Union 부분 (mi / ki / hi)"""
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    """Win32 INPUT 구조체 — Union을 올바르게 포함."""
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


def _send_mouse_input(flags, abs_x=0, abs_y=0):
    """SendInput으로 마우스 이벤트 1건 전송 (내부 헬퍼)."""
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi.dx = abs_x
    inp.union.mi.dy = abs_y
    inp.union.mi.mouseData = 0
    inp.union.mi.dwFlags = flags
    inp.union.mi.time = 0
    inp.union.mi.dwExtraInfo = 0  # 하드웨어 입력처럼 0

    sent = ctypes.windll.user32.SendInput(
        1, ctypes.byref(inp), ctypes.sizeof(INPUT)
    )
    if sent != 1:
        log.warning(f"SendInput 실패: flags=0x{flags:04X}")


# ══════════════════════════════════════════════
# 클릭 방식별 구현
# ══════════════════════════════════════════════

# ── 방식 1: pydirectinput ──
def click_directinput(x, y):
    import pydirectinput
    pydirectinput.moveTo(x, y)
    time.sleep(0.05)
    pydirectinput.click()
    log.debug(f"[directinput] 클릭: ({x}, {y})")


# ── 방식 2: ctypes SendInput (하드웨어 위장) ──
def click_sendinput(x, y):
    """ctypes SendInput으로 하드웨어 수준 클릭."""
    screen_w = ctypes.windll.user32.GetSystemMetrics(0)
    screen_h = ctypes.windll.user32.GetSystemMetrics(1)
    abs_x = int(x * 65535 / screen_w)
    abs_y = int(y * 65535 / screen_h)

    # 이동
    _send_mouse_input(
        MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
        abs_x, abs_y
    )
    time.sleep(0.05)

    # 다운
    _send_mouse_input(
        MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE,
        abs_x, abs_y
    )
    time.sleep(random.uniform(0.03, 0.08))

    # 업
    _send_mouse_input(
        MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE,
        abs_x, abs_y
    )
    log.debug(f"[sendinput] 클릭: ({x}, {y}) → abs({abs_x}, {abs_y})")


# ── 방식 3: 마우스키 (넘패드 5) ──
def click_mousekeys(x, y):
    """마우스키 기능으로 클릭 (사전에 마우스키 활성화 필요)."""
    import pyautogui
    import keyboard as kb

    pyautogui.moveTo(x, y)
    time.sleep(0.05)
    kb.press_and_release('num 5')
    log.debug(f"[mousekeys] 클릭: ({x}, {y})")


# ══════════════════════════════════════════════
# 통합 클릭 인터페이스
# ══════════════════════════════════════════════

CLICK_METHODS = {
    "directinput": click_directinput,
    "sendinput":   click_sendinput,
    "mousekeys":   click_mousekeys,
}


def click(x, y, method="sendinput"):
    """
    설정된 방식으로 클릭 실행.

    Args:
        x, y: 클릭 좌표 (스크린 절대 좌표)
        method: "directinput" | "sendinput" | "mousekeys"

    Raises:
        ValueError: 지원하지 않는 method
    """
    if method not in CLICK_METHODS:
        raise ValueError(
            f"지원하지 않는 클릭 방식: '{method}'. "
            f"사용 가능: {list(CLICK_METHODS.keys())}"
        )

    # 사람처럼 보이게 약간의 랜덤 오프셋
    offset_x = random.randint(-2, 2)
    offset_y = random.randint(-2, 2)
