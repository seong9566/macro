import ctypes
import keyboard
import os
import threading
from macro_engine import MacroEngine
from window_manager import get_game_region
from hunt_profile import migrate_from_legacy_config, load_profile, save_profile
from profile_manager import ProfileManager
from hotkey_registrar import HotkeyRegistrar
from config import (
    GAME_WINDOW_TITLE, AUTO_DETECT_WINDOW, MANUAL_REGION,
)
from logger import log

# DPI Awareness 설정 (멀티모니터/고DPI 환경 좌표 정합)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()


def _check_admin():
    """관리자 권한 실행 여부 확인. SendInput이 게임에 전달되려면 필수."""
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        is_admin = False
    if not is_admin:
        log.warning(
            "⚠ 관리자 권한 없이 실행 중! "
            "게임에 클릭이 전달되지 않을 수 있습니다. "
            "cmd/터미널을 '관리자 권한으로 실행' 후 다시 시도하세요."
        )
    else:
        log.info("관리자 권한 확인 완료")
    return is_admin


def _load_or_migrate_profile() -> ProfileManager:
    """profiles/default.json 로드 또는 legacy config 마이그레이션."""
    os.makedirs("profiles", exist_ok=True)
    path = "profiles/default.json"
    if os.path.exists(path):
        try:
            return ProfileManager(load_profile(path))
        except Exception as e:
            log.error(f"프로필 로딩 실패 → 마이그레이션 후 백업: {e}")
            try:
                os.rename(path, f"{path}.broken")
            except Exception:
                pass
    profile = migrate_from_legacy_config()
    save_profile(profile, path)
    return ProfileManager(profile)


_lock = threading.Lock()
engine = None
profile_manager = _load_or_migrate_profile()


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

        if engine and engine.running:
            engine.stop()

        engine = MacroEngine(
            profile_manager=profile_manager,
            region=region,
            template_dir="images",
        )

        log.info(f"매크로 시작! (영역: {region})")
        thread = threading.Thread(target=engine.hunt_loop, daemon=True)
        thread.start()


def stop_macro():
    global engine
    with _lock:
        if engine:
            engine.stop()
        log.info("매크로 중지!")


# 관리자 권한 확인
_check_admin()

# 핫키 등록 (프로필에서 키 읽음 — 동적 재바인딩 가능)
hotkey_registrar = HotkeyRegistrar()
hk = profile_manager.current.hotkeys
hotkey_registrar.bind(
    start_key=hk.start,
    stop_key=hk.stop,
    on_start=start_macro,
    on_stop=stop_macro,
)

log.info(f"[대기중] {hk.start}=시작 / {hk.stop}=중지 / Ctrl+C=종료")
try:
    keyboard.wait()
except KeyboardInterrupt:
    stop_macro()
    hotkey_registrar.unbind()
    log.info("프로그램 종료")
