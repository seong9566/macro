"""HuntProfile dataclass 단위 테스트."""
import dataclasses
import pytest

from hunt_profile import (
    MonsterEntry, CombatConfig, PotionConfig, SkillEntry,
    HotkeyConfig, LootConfig, HuntProfile,
)


class TestDataclasses:
    def test_monster_entry_creates_with_all_fields(self):
        m = MonsterEntry(
            name="wolf",
            template_dir="images/wolf",
            detect_confidence=0.55,
            tracking_confidence=0.40,
            hp_bar_offset_y=-20,
        )
        assert m.name == "wolf"
        assert m.detect_confidence == 0.55

    def test_monster_entry_is_frozen(self):
        m = MonsterEntry("wolf", "images/wolf", 0.55, 0.40, -20)
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.name = "boar"

    def test_combat_config_creates_and_frozen(self):
        c = CombatConfig(
            attack_interval=0.15,
            detect_miss_max=4,
            target_timeout=15.0,
            click_method="sendinput",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.attack_interval = 0.20

    def test_potion_config_creates_and_frozen(self):
        p = PotionConfig(
            hp_enabled=True,
            hp_threshold=0.5,
            hp_key_scancode=2,
            mp_enabled=False,
            mp_threshold=0.3,
            mp_key_scancode=3,
            cooldown=3.0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.hp_threshold = 0.6

    def test_skill_entry_creates_and_frozen(self):
        s = SkillEntry(
            name="분노",
            key_scancode=33,
            auto_use_interval=30.0,
            enabled=True,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.enabled = False

    def test_hotkey_config_creates_and_frozen(self):
        h = HotkeyConfig(start="F5", stop="F6")
        with pytest.raises(dataclasses.FrozenInstanceError):
            h.start = "F7"

    def test_loot_config_creates_and_frozen(self):
        l = LootConfig(
            enabled=True, visual_enabled=True,
            delay_after_kill=0.20, snapshot_max_age=8.0,
            diff_threshold=30, min_blob_area=30, max_blob_area=2500,
            max_distance_ratio=1.5, max_total_diff_ratio=0.6,
            after_click_delay=0.3, press_count=2, press_interval=0.10,
            key_scancode=57, corpse_mask_ratio=1.0, roi_expand_ratio=1.0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            l.enabled = False

    def test_hunt_profile_assembles_all_components(self):
        p = HuntProfile(
            schema_version=1,
            name="default",
            monsters=(MonsterEntry("wolf", "images/wolf", 0.55, 0.40, -20),),
            combat=CombatConfig(0.15, 4, 15.0, "sendinput"),
            potion=PotionConfig(True, 0.5, 2, False, 0.3, 3, 3.0),
            skills=(SkillEntry("분노", 33, 30.0, True),),
            hotkeys=HotkeyConfig("F5", "F6"),
            loot=LootConfig(True, True, 0.20, 8.0, 30, 30, 2500,
                            1.5, 0.6, 0.3, 2, 0.10, 57, 1.0, 1.0),
        )
        assert p.name == "default"
        assert len(p.monsters) == 1
        assert p.monsters[0].name == "wolf"
        assert p.skills[0].name == "분노"

    def test_hunt_profile_is_frozen(self):
        p = HuntProfile(
            schema_version=1, name="default", monsters=(),
            combat=CombatConfig(0.15, 4, 15.0, "sendinput"),
            potion=PotionConfig(True, 0.5, 2, False, 0.3, 3, 3.0),
            skills=(),
            hotkeys=HotkeyConfig("F5", "F6"),
            loot=LootConfig(True, True, 0.20, 8.0, 30, 30, 2500,
                            1.5, 0.6, 0.3, 2, 0.10, 57, 1.0, 1.0),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.name = "other"
