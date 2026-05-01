"""
ProfileManager — HuntProfile 단일 인스턴스 + atomic 통째 교체.

스레드 안전성 모델:
- 읽기(reader): self.current 참조 1회 읽기는 GIL atomic. 엔진 스레드는
  사이클당 1회 읽고 로컬 변수로 사용 (frozen dataclass라 일관성 보장).
- 쓰기(writer): update_*() 헬퍼는 read-modify-write 패턴이므로 호출자는
  단일 스레드(예: PyQt6 UI 스레드)여야 함. 두 writer가 동시 호출하면
  마지막 쓴 사람만 보존되는 lost-update가 발생할 수 있음. 멀티 writer가
  필요해지면 threading.Lock 추가 필요.
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
