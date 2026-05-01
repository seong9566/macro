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


# ══════════════════════════════════════════════
# JSON 라운드트립
# ══════════════════════════════════════════════

import json
import tempfile
from pathlib import Path

from hunt_profile import save_profile, load_profile


class TestJsonRoundtrip:
    def _sample_profile(self):
        return HuntProfile(
            schema_version=1,
            name="test",
            monsters=(
                MonsterEntry("wolf", "images/wolf", 0.55, 0.40, -20),
                MonsterEntry("boar", "images/boar", 0.60, 0.45, -25),
            ),
            combat=CombatConfig(0.15, 4, 15.0, "sendinput"),
            potion=PotionConfig(True, 0.5, 2, False, 0.3, 3, 3.0),
            skills=(SkillEntry("분노", 33, 30.0, True),),
            hotkeys=HotkeyConfig("F5", "F6"),
            loot=LootConfig(True, True, 0.20, 8.0, 30, 30, 2500,
                            1.5, 0.6, 0.3, 2, 0.10, 57, 1.0, 1.0),
        )

    def test_save_and_load_roundtrip_preserves_all_fields(self, tmp_path):
        original = self._sample_profile()
        path = tmp_path / "test.json"

        save_profile(original, str(path))
        loaded = load_profile(str(path))

        assert loaded == original  # frozen dataclass equality

    def test_save_writes_human_readable_json(self, tmp_path):
        profile = self._sample_profile()
        path = tmp_path / "test.json"
        save_profile(profile, str(path))

        text = path.read_text(encoding="utf-8")
        # indent=2 적용되어야 함 — 줄바꿈/공백 존재
        assert "\n  " in text
        # 기본 필드 존재
        data = json.loads(text)
        assert data["schema_version"] == 1
        assert data["name"] == "test"
        assert len(data["monsters"]) == 2
        assert len(data["skills"]) == 1

    def test_load_handles_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            load_profile(str(path))

    def test_load_rejects_unknown_schema_version(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({
            "schema_version": 999,
            "name": "bad",
            "monsters": [], "combat": {"attack_interval": 0.15, "detect_miss_max": 4,
                                        "target_timeout": 15.0, "click_method": "sendinput"},
            "potion": {"hp_enabled": True, "hp_threshold": 0.5, "hp_key_scancode": 2,
                       "mp_enabled": False, "mp_threshold": 0.3, "mp_key_scancode": 3, "cooldown": 3.0},
            "skills": [], "hotkeys": {"start": "F5", "stop": "F6"},
            "loot": {"enabled": True, "visual_enabled": True, "delay_after_kill": 0.2,
                     "snapshot_max_age": 8.0, "diff_threshold": 30, "min_blob_area": 30,
                     "max_blob_area": 2500, "max_distance_ratio": 1.5,
                     "max_total_diff_ratio": 0.6, "after_click_delay": 0.3,
                     "press_count": 2, "press_interval": 0.10, "key_scancode": 57,
                     "corpse_mask_ratio": 1.0, "roi_expand_ratio": 1.0},
        }), encoding="utf-8")

        with pytest.raises(ValueError, match="schema_version"):
            load_profile(str(path))


# Codex Critical 2 — 손상 JSON 처리
class TestCorruptedJsonHandling:
    def test_load_raises_on_corrupted_json(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{ this is not valid json", encoding="utf-8")
        with pytest.raises(Exception):  # JSONDecodeError 또는 KeyError
            load_profile(str(path))

    def test_load_raises_on_truncated_json(self, tmp_path):
        path = tmp_path / "trunc.json"
        path.write_text('{"schema_version": 1, "name": "x"', encoding="utf-8")  # 닫힘 없음
        with pytest.raises(Exception):
            load_profile(str(path))
