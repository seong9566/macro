"""
HotkeyRegistrar — keyboard 라이브러리 글로벌 핫키 등록/재바인딩 추상화.
프로필 변경 시 기존 핫키 해제 후 새 키로 다시 등록.
"""
from typing import Callable, Optional

import keyboard as kb

from logger import log


class HotkeyRegistrar:
    """글로벌 핫키 등록/해제. rebind()로 새 키로 갱신."""

    def __init__(self):
        self._start_key: Optional[str] = None
        self._stop_key: Optional[str] = None
        self._start_handler: Optional[Callable] = None
        self._stop_handler: Optional[Callable] = None

    def bind(self, start_key: str, stop_key: str,
             on_start: Callable, on_stop: Callable):
        """초기 등록. start_key='F5', stop_key='F6'."""
        self.unbind()
        try:
            kb.add_hotkey(start_key, on_start)
            kb.add_hotkey(stop_key, on_stop)
            self._start_key = start_key
            self._stop_key = stop_key
            self._start_handler = on_start
            self._stop_handler = on_stop
            log.info(f"핫키 등록: 시작={start_key}, 중지={stop_key}")
        except Exception as e:
            log.error(f"핫키 등록 실패: {e}")

    def unbind(self):
        """기존 핫키 해제."""
        if self._start_key:
            try:
                kb.remove_hotkey(self._start_key)
            except Exception:
                pass
        if self._stop_key:
            try:
                kb.remove_hotkey(self._stop_key)
            except Exception:
                pass
        self._start_key = None
        self._stop_key = None

    def rebind(self, start_key: str, stop_key: str):
        """프로필 변경 시 새 키로 재등록 (기존 핸들러 재사용)."""
        if self._start_handler is None or self._stop_handler is None:
            log.warning("rebind 호출 전 bind가 필요합니다")
            return
        self.bind(start_key, stop_key, self._start_handler, self._stop_handler)
