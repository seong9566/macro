"""SkillManager 단위 테스트 (시간 mock 기반)."""
import pytest
from unittest.mock import MagicMock

from hunt_profile import (
    HuntProfile, MonsterEntry, CombatConfig, PotionConfig,
    SkillEntry, HotkeyConfig, LootConfig,
)
from profile_manager import ProfileManager
from skill_manager import SkillManager


def _profile_with_skills(skills):
    return HuntProfile(
        schema_version=1, name="test",
        monsters=(MonsterEntry("wolf", "images/wolf", 0.55, 0.40, -20),),
        combat=CombatConfig(0.15, 4, 15.0, "sendinput"),
        potion=PotionConfig(True, 0.5, 2, False, 0.3, 3, 3.0),
        skills=tuple(skills),
        hotkeys=HotkeyConfig("F5", "F6"),
        loot=LootConfig(True, True, 0.20, 8.0, 30, 30, 2500,
                        1.5, 0.6, 0.3, 2, 0.10, 57, 1.0, 1.0),
    )


class TestSkillManager:
    def test_disabled_skill_never_fires(self):
        skills = [SkillEntry("disabled", 33, 1.0, enabled=False)]
        mgr = ProfileManager(_profile_with_skills(skills))
        press = MagicMock()
        sm = SkillManager(mgr, press_key=press, time_fn=lambda: 100.0)

        sm.tick()
        sm.tick()

        press.assert_not_called()

    def test_zero_interval_skill_never_fires(self):
        skills = [SkillEntry("manual", 33, 0.0, enabled=True)]
        mgr = ProfileManager(_profile_with_skills(skills))
        press = MagicMock()
        sm = SkillManager(mgr, press_key=press, time_fn=lambda: 100.0)

        sm.tick()
        press.assert_not_called()

    def test_first_tick_fires_immediately(self):
        skills = [SkillEntry("buff", 33, 30.0, enabled=True)]
        mgr = ProfileManager(_profile_with_skills(skills))
        press = MagicMock()
        sm = SkillManager(mgr, press_key=press, time_fn=lambda: 100.0)

        sm.tick()

        press.assert_called_once_with(33)

    def test_does_not_fire_again_within_interval(self):
        skills = [SkillEntry("buff", 33, 30.0, enabled=True)]
        mgr = ProfileManager(_profile_with_skills(skills))
        press = MagicMock()

        current_time = [100.0]
        sm = SkillManager(mgr, press_key=press, time_fn=lambda: current_time[0])

        sm.tick()
        current_time[0] = 110.0
        sm.tick()

        assert press.call_count == 1

    def test_fires_after_interval_elapsed(self):
        skills = [SkillEntry("buff", 33, 30.0, enabled=True)]
        mgr = ProfileManager(_profile_with_skills(skills))
        press = MagicMock()
        current_time = [100.0]
        sm = SkillManager(mgr, press_key=press, time_fn=lambda: current_time[0])

        sm.tick()
        current_time[0] = 131.0
        sm.tick()

        assert press.call_count == 2

    def test_multiple_skills_fire_independently(self):
        skills = [
            SkillEntry("a", 33, 10.0, enabled=True),
            SkillEntry("b", 34, 20.0, enabled=True),
        ]
        mgr = ProfileManager(_profile_with_skills(skills))
        press = MagicMock()
        current_time = [100.0]
        sm = SkillManager(mgr, press_key=press, time_fn=lambda: current_time[0])

        sm.tick()
        current_time[0] = 111.0
        sm.tick()

        assert press.call_count == 3
        called_codes = [c.args[0] for c in press.call_args_list]
        assert called_codes == [33, 34, 33]

    def test_reset_clears_history(self):
        skills = [SkillEntry("buff", 33, 30.0, enabled=True)]
        mgr = ProfileManager(_profile_with_skills(skills))
        press = MagicMock()
        current_time = [100.0]
        sm = SkillManager(mgr, press_key=press, time_fn=lambda: current_time[0])

        sm.tick()
        current_time[0] = 105.0
        sm.reset()
        sm.tick()

        assert press.call_count == 2
