"""
SkillManager — 등록된 스킬을 auto_use_interval에 맞춰 주기적 발동.

Phase 1 범위: 단순 N초 간격. 조건부/콤보/로테이션은 Phase 3.
"""
import time as _time
from typing import Callable

from logger import log


class SkillManager:
    """ProfileManager의 스킬 목록을 관찰하며 시간 도래 스킬을 발동."""

    def __init__(self, profile_manager,
                 press_key: Callable[[int], None],
                 time_fn: Callable[[], float] = _time.time):
        self._profile_manager = profile_manager
        self._press_key = press_key
        self._time_fn = time_fn
        self._last_use: dict[str, float] = {}

    def tick(self) -> None:
        """매크로 사이클마다 호출. 도래한 스킬을 발동."""
        profile = self._profile_manager.current
        now = self._time_fn()

        for skill in profile.skills:
            if not skill.enabled:
                continue
            if skill.auto_use_interval <= 0:
                continue

            last = self._last_use.get(skill.name, 0.0)
            if last == 0.0 or (now - last) >= skill.auto_use_interval:
                self._press_key(skill.key_scancode)
                self._last_use[skill.name] = now
                log.info(f"스킬 사용: {skill.name} (key=0x{skill.key_scancode:02X})")

    def reset(self) -> None:
        """발동 이력 초기화 (매크로 정지/재시작 시 호출)."""
        self._last_use.clear()
