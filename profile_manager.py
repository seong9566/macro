"""
ProfileManager — HuntProfile 단일 인스턴스 + atomic 통째 교체.

스레드 안전성: frozen dataclass + Python 참조 할당의 GIL atomicity.
엔진 스레드는 self.current 참조를 한 번 읽고 로컬 변수로 사용.
UI 스레드는 update_*() 헬퍼로 새 객체 생성 후 통째 교체.
"""
import dataclasses
from typing import Tuple

from hunt_profile import (
    HuntProfile, MonsterEntry, CombatConfig, PotionConfig,
    SkillEntry, HotkeyConfig, LootConfig,
)


class ProfileManager:
    """단일 활성 프로필 보관소. atomic 통째 교체로 race-free."""

    def __init__(self, initial: HuntProfile):
        self.current: HuntProfile = initial

    def replace(self, new_profile: HuntProfile) -> None:
        """전체 프로필 교체."""
        self.current = new_profile

    def update_combat(self, **changes) -> None:
        """CombatConfig의 일부 필드만 변경. 나머지는 보존."""
        new_combat = dataclasses.replace(self.current.combat, **changes)
        self.current = dataclasses.replace(self.current, combat=new_combat)

    def update_potion(self, **changes) -> None:
        """PotionConfig 부분 변경."""
        new_potion = dataclasses.replace(self.current.potion, **changes)
        self.current = dataclasses.replace(self.current, potion=new_potion)

    def update_loot(self, **changes) -> None:
        """LootConfig 부분 변경."""
        new_loot = dataclasses.replace(self.current.loot, **changes)
        self.current = dataclasses.replace(self.current, loot=new_loot)

    def update_hotkeys(self, **changes) -> None:
        """HotkeyConfig 부분 변경."""
        new_hotkeys = dataclasses.replace(self.current.hotkeys, **changes)
        self.current = dataclasses.replace(self.current, hotkeys=new_hotkeys)

    def set_monsters(self, monsters: Tuple[MonsterEntry, ...]) -> None:
        """몬스터 목록 통째 교체."""
        self.current = dataclasses.replace(self.current, monsters=tuple(monsters))

    def set_skills(self, skills: Tuple[SkillEntry, ...]) -> None:
        """스킬 목록 통째 교체."""
        self.current = dataclasses.replace(self.current, skills=tuple(skills))
