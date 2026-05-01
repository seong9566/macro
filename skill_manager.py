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

            # 첫 발동(이력 없음) 또는 간격 도래 시 발동
            # `last == 0.0` 마법 상수 대신 명시적 키 존재 검사 (review 권고)
            if skill.name not in self._last_use:
                fire = True
            else:
                fire = (now - self._last_use[skill.name]) >= skill.auto_use_interval

            if fire:
                self._press_key(skill.key_scancode)
                self._last_use[skill.name] = now
                log.info(f"스킬 사용: {skill.name} (key=0x{skill.key_scancode:02X})")

        # 프로필에서 제거된 스킬의 이력 정리 (메모리 누수 방지 + 동명 재추가 시 신선한 시작)
        active_names = {s.name for s in profile.skills}
        self._last_use = {k: v for k, v in self._last_use.items() if k in active_names}

    def reset(self) -> None:
        """발동 이력 초기화 (매크로 정지/재시작 시 호출)."""
        self._last_use.clear()
