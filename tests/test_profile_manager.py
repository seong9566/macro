"""ProfileManager 단위 테스트."""
import pytest
from hunt_profile import (
    HuntProfile, MonsterEntry, CombatConfig, PotionConfig,
    SkillEntry, HotkeyConfig, LootConfig,
)
from profile_manager import ProfileManager


def _make_default_profile():
    return HuntProfile(
        schema_version=1, name="default",
        monsters=(MonsterEntry("wolf", "images/wolf", 0.55, 0.40, -20),),
        combat=CombatConfig(0.15, 4, 15.0, "sendinput"),
        potion=PotionConfig(True, 0.5, 2, False, 0.3, 3, 3.0),
        skills=(),
        hotkeys=HotkeyConfig("F5", "F6"),
        loot=LootConfig(True, True, 0.20, 8.0, 30, 30, 2500,
                        1.5, 0.6, 0.3, 2, 0.10, 57, 1.0, 1.0),
    )


class TestProfileManager:
    def test_initial_current_is_provided_profile(self):
        p = _make_default_profile()
        mgr = ProfileManager(initial=p)
        assert mgr.current is p

    def test_update_combat_replaces_atomically(self):
        p = _make_default_profile()
        mgr = ProfileManager(initial=p)
        original_ref = mgr.current

        mgr.update_combat(attack_interval=0.30)

        assert mgr.current is not original_ref
        assert mgr.current.combat.attack_interval == 0.30
        assert mgr.current.combat.detect_miss_max == 4

    def test_update_potion_replaces_atomically(self):
        p = _make_default_profile()
        mgr = ProfileManager(initial=p)
        mgr.update_potion(hp_threshold=0.7)
        assert mgr.current.potion.hp_threshold == 0.7
        assert mgr.current.potion.hp_enabled is True

    def test_set_skills_replaces_tuple(self):
        p = _make_default_profile()
        mgr = ProfileManager(initial=p)
        new_skills = (
            SkillEntry("분노", 33, 30.0, True),
            SkillEntry("버프", 34, 60.0, True),
        )
        mgr.set_skills(new_skills)
        assert mgr.current.skills == new_skills

    def test_set_monsters_replaces_tuple(self):
        p = _make_default_profile()
        mgr = ProfileManager(initial=p)
        new_monsters = (
            MonsterEntry("wolf", "images/wolf", 0.50, 0.35, -18),
            MonsterEntry("boar", "images/boar", 0.60, 0.45, -25),
        )
        mgr.set_monsters(new_monsters)
        assert mgr.current.monsters == new_monsters

    def test_update_hotkeys_replaces(self):
        p = _make_default_profile()
        mgr = ProfileManager(initial=p)
        mgr.update_hotkeys(start="F7", stop="F8")
        assert mgr.current.hotkeys.start == "F7"
        assert mgr.current.hotkeys.stop == "F8"

    def test_replace_swaps_entire_profile(self):
        p1 = _make_default_profile()
        mgr = ProfileManager(initial=p1)
        p2 = _make_default_profile()
        mgr.replace(p2)
        assert mgr.current is p2
