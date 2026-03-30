import ctypes
import keyboard
import threading
from macro_engine import MacroEngine
from window_manager import get_game_region
from config import (
    START_KEY, STOP_KEY, CLICK_METHOD,
    GAME_WINDOW_TITLE, AUTO_DETECT_WINDOW, MANUAL_REGION,
    DETECT_CONFIDENCE,
)
from logger import log

# DPI Awareness 설정 (멀티모니터/고DPI 환경 좌표 정합)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

_lock = threading.Lock()
engine = None


def get_region():
    """설정에 따라 게임 창 영역을 가져옴."""
    if AUTO_DETECT_WINDOW:
        region = get_game_region(GAME_WINDOW_TITLE)
        if region is None:
            log.critical(
                f"게임 창을 찾을 수 없습니다: '{GAME_WINDOW_TITLE}'. "
                f"게임이 실행 중인지 확인하세요."
            )
        return region
    return MANUAL_REGION


def start_macro():
    global engine
    with _lock:
        region = get_region()
        if region is None and AUTO_DETECT_WINDOW:
            log.error("매크로 시작 불가: 게임 창 미감지")
            return

        # 기존 엔진이 돌고 있으면 중지
        if engine and engine.running:
            engine.stop()

        engine = MacroEngine(
            click_method=CLICK_METHOD,
            region=region,
            template_dir="images",
            confidence=DETECT_CONFIDENCE,
        )

        log.info(f"매크로 시작! (방식: {CLICK_METHOD}, 영역: {region})")
        thread = threading.Thread(target=engine.hunt_loop, daemon=True)
        thread.start()


def stop_macro():
    global engine
    with _lock:
        if engine:
            engine.stop()
        log.info("매크로 중지!")


# 단축키 등록
keyboard.add_hotkey(START_KEY, start_macro)
keyboard.add_hotkey(STOP_KEY, stop_macro)

log.info(f"[대기중] {START_KEY}=시작 / {STOP_KEY}=중지 / Ctrl+C=종료")
try:
    keyboard.wait()
except KeyboardInterrupt:
    stop_macro()
    log.info("프로그램 종료")
