# Hunt Profile 기반 매크로 재구성 Phase 1 — 구현 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `config.py`의 사용자 튜닝 가치 있는 값을 `HuntProfile` JSON으로 이전하고, macro_ui에 6 탭 설정 패널을 추가하여 GUI에서 매크로 동작을 직접 설정·저장·전환 가능하게 만든다.

**Architecture:** 7개 frozen dataclass(`HuntProfile`, `MonsterEntry`, `CombatConfig`, `PotionConfig`, `SkillEntry`, `HotkeyConfig`, `LootConfig`) + `ProfileManager`(atomic 통째 교체) + `SkillManager`(N초 간격 자동 발동). `MacroEngine`/`MonsterTracker`는 config import 대신 `profile_manager.current.*` 참조. macro_ui에 QTabWidget으로 6 탭(몬스터/전투/스킬/물약/단축키/프로필) 추가.

**Tech Stack:** Python dataclasses (frozen=True), JSON stdlib, PyQt6 (QTabWidget, QSlider, QSpinBox, QTableWidget, QFileDialog), pytest, threading (GIL atomic 패턴)

**관련 스펙:** `docs/superpowers/specs/2026-05-01-hunt-profile-foundation-design.md`

---

## 파일 구조

| 파일 | 변경 유형 | 역할 |
|------|-----------|------|
| `hunt_profile.py` | 신규 | 7 frozen dataclass + JSON 직렬화 + legacy config 마이그레이션 |
| `profile_manager.py` | 신규 | 단일 인스턴스 패턴 + atomic update 헬퍼들 |
| `skill_manager.py` | 신규 | N초 간격 자동 발동 tick 로직 |
| `tests/test_hunt_profile.py` | 신규 | 라운드트립 + 마이그레이션 정합성 테스트 |
| `tests/test_profile_manager.py` | 신규 | atomic 교체 테스트 |
| `tests/test_skill_manager.py` | 신규 | 시간 mock 기반 tick 테스트 |
| `macro_engine.py` | 수정 | profile_manager 주입 + config import 제거 + skill_manager.tick() 호출 |
| `monster_tracker.py` | 수정 | profile_provider 주입 + monster별 confidence/HP offset 사용 |
| `macro_ui.py` | 대폭 수정 | QTabWidget 구조 + 6 탭 위젯 추가 |
| `config.py` | 수정 | 사용자 튜닝 값에 deprecation 경고 추가 |
| `profiles/default.json` | 자동 생성 | 첫 실행 시 마이그레이션 결과 저장 |

---

### Task 1: hunt_profile.py — 7 frozen dataclass 정의 (TDD)

**Files:**
- Create: `hunt_profile.py`
- Create: `tests/test_hunt_profile.py`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/test_hunt_profile.py`**

```python
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
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/test_hunt_profile.py -v
```

기대: `ImportError: cannot import name 'MonsterEntry' from 'hunt_profile'`

- [ ] **Step 3: `hunt_profile.py` 신규 작성**

```python
"""
HuntProfile — 매크로 동작 설정의 단일 진실 원천.

설계 문서: docs/superpowers/specs/2026-05-01-hunt-profile-foundation-design.md
모든 dataclass는 frozen=True (불변, atomic 교체로 스레드 안전).
"""
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class MonsterEntry:
    """단일 몬스터 종류의 검출 설정."""
    name: str                      # 표시명, 예: "wolf"
    template_dir: str              # 템플릿 폴더, 예: "images/wolf"
    detect_confidence: float       # 0.0~1.0, 전체 프레임 감지 임계값
    tracking_confidence: float     # 0.0~1.0, ROI 재탐색 임계값
    hp_bar_offset_y: int           # bbox 상단 기준 (음수 = 위쪽)


@dataclass(frozen=True)
class CombatConfig:
    """전투 동작 파라미터."""
    attack_interval: float         # 공격 클릭 후 다음 클릭까지 대기 (초)
    detect_miss_max: int           # 연속 N회 감지 실패 시 사망 판정
    target_timeout: float          # 동일 대상 최대 공격 시간 (초)
    click_method: str              # "sendinput" | "directinput" | "mousekeys"


@dataclass(frozen=True)
class PotionConfig:
    """HP/MP 자동 물약 설정. MP는 Phase 1에서는 자리만, 동작은 Phase 3."""
    hp_enabled: bool
    hp_threshold: float            # 0.0~1.0, 이 비율 이하면 사용
    hp_key_scancode: int           # 키 스캔코드
    mp_enabled: bool
    mp_threshold: float
    mp_key_scancode: int
    cooldown: float                # 동일 물약 재사용 대기 (초)


@dataclass(frozen=True)
class SkillEntry:
    """단일 스킬 설정."""
    name: str                      # 표시명, 예: "분노"
    key_scancode: int              # 키 스캔코드
    auto_use_interval: float       # N초 간격 자동 사용. 0이면 수동 (Phase 1: 자동만)
    enabled: bool                  # 활성/비활성


@dataclass(frozen=True)
class HotkeyConfig:
    """매크로 시작/중지 핫키."""
    start: str                     # 예: "F5"
    stop: str                      # 예: "F6"


@dataclass(frozen=True)
class LootConfig:
    """아이템 줍기 설정. 기존 LOOT_* 상수를 모두 포함."""
    enabled: bool
    visual_enabled: bool
    delay_after_kill: float
    snapshot_max_age: float
    diff_threshold: int
    min_blob_area: int
    max_blob_area: int
    max_distance_ratio: float
    max_total_diff_ratio: float
    after_click_delay: float
    press_count: int
    press_interval: float
    key_scancode: int
    corpse_mask_ratio: float
    roi_expand_ratio: float


@dataclass(frozen=True)
class HuntProfile:
    """프로필 전체 — frozen으로 atomic 교체 보장."""
    schema_version: int
    name: str
    monsters: Tuple[MonsterEntry, ...]
    combat: CombatConfig
    potion: PotionConfig
    skills: Tuple[SkillEntry, ...]
    hotkeys: HotkeyConfig
    loot: LootConfig
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

```bash
pytest tests/test_hunt_profile.py -v
```

기대: `9 passed`

- [ ] **Step 5: 커밋**

```bash
git add hunt_profile.py tests/test_hunt_profile.py
git commit -m "feat: hunt_profile.py — 7 frozen dataclass 정의"
```

---

### Task 2: hunt_profile.py — JSON 직렬화 + 라운드트립 (TDD)

**Files:**
- Modify: `hunt_profile.py`
- Modify: `tests/test_hunt_profile.py`

- [ ] **Step 1: 실패하는 테스트 추가 — `tests/test_hunt_profile.py` 끝에**

```python


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
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/test_hunt_profile.py::TestJsonRoundtrip -v
```

기대: `ImportError: cannot import name 'save_profile' from 'hunt_profile'`

- [ ] **Step 3: `hunt_profile.py`에 직렬화 함수 추가 (파일 하단)**

```python


# ══════════════════════════════════════════════
# JSON 직렬화 / 역직렬화
# ══════════════════════════════════════════════

import json
from dataclasses import asdict


SUPPORTED_SCHEMA_VERSIONS = (1,)


def save_profile(profile: HuntProfile, path: str) -> None:
    """HuntProfile을 JSON으로 저장 (사람 친화적 들여쓰기)."""
    data = asdict(profile)  # tuple은 list로 변환됨
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_profile(path: str) -> HuntProfile:
    """JSON에서 HuntProfile 로드. schema_version 검증."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    version = data.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(
            f"지원하지 않는 schema_version={version} "
            f"(지원 버전: {SUPPORTED_SCHEMA_VERSIONS})"
        )

    return HuntProfile(
        schema_version=data["schema_version"],
        name=data["name"],
        monsters=tuple(MonsterEntry(**m) for m in data["monsters"]),
        combat=CombatConfig(**data["combat"]),
        potion=PotionConfig(**data["potion"]),
        skills=tuple(SkillEntry(**s) for s in data["skills"]),
        hotkeys=HotkeyConfig(**data["hotkeys"]),
        loot=LootConfig(**data["loot"]),
    )
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

```bash
pytest tests/test_hunt_profile.py -v
```

기대: 모든 테스트 통과 (Task 1 + Task 2 = 13개)

- [ ] **Step 5: 커밋**

```bash
git add hunt_profile.py tests/test_hunt_profile.py
git commit -m "feat: hunt_profile — JSON 라운드트립 + schema_version 검증"
```

---

### Task 3: hunt_profile.py — legacy config 마이그레이션 (TDD)

**Files:**
- Modify: `hunt_profile.py`
- Modify: `tests/test_hunt_profile.py`

- [ ] **Step 1: 실패하는 테스트 추가 — `tests/test_hunt_profile.py` 끝에**

```python


# ══════════════════════════════════════════════
# Legacy config 마이그레이션
# ══════════════════════════════════════════════

from hunt_profile import migrate_from_legacy_config


class TestLegacyMigration:
    def test_migrate_produces_valid_profile(self):
        profile = migrate_from_legacy_config()
        assert profile.schema_version == 1
        assert profile.name == "default"

    def test_migrate_combat_matches_legacy_constants(self):
        import config
        profile = migrate_from_legacy_config()
        assert profile.combat.attack_interval == config.ATTACK_INTERVAL
        assert profile.combat.detect_miss_max == config.DETECT_MISS_MAX
        assert profile.combat.target_timeout == config.TARGET_TIMEOUT
        assert profile.combat.click_method == config.CLICK_METHOD

    def test_migrate_potion_matches_legacy(self):
        import config
        profile = migrate_from_legacy_config()
        assert profile.potion.hp_enabled == config.POTION_ENABLED
        assert profile.potion.hp_threshold == config.POTION_HP_THRESHOLD
        assert profile.potion.hp_key_scancode == config.POTION_KEY_SCANCODE
        assert profile.potion.cooldown == config.POTION_COOLDOWN

    def test_migrate_loot_matches_legacy(self):
        import config
        profile = migrate_from_legacy_config()
        assert profile.loot.enabled == config.LOOT_ENABLED
        assert profile.loot.visual_enabled == config.LOOT_VISUAL_ENABLED
        assert profile.loot.snapshot_max_age == config.LOOT_SNAPSHOT_MAX_AGE
        assert profile.loot.diff_threshold == config.LOOT_DIFF_THRESHOLD
        assert profile.loot.key_scancode == config.LOOT_KEY_SCANCODE

    def test_migrate_creates_default_wolf_monster(self):
        import config
        profile = migrate_from_legacy_config()
        # 기존 매크로는 늑대 전용 → 마이그레이션 시 wolf 1종 자동 생성
        assert len(profile.monsters) >= 1
        wolf = profile.monsters[0]
        assert wolf.name == "wolf"
        assert wolf.detect_confidence == config.DETECT_CONFIDENCE
        assert wolf.tracking_confidence == config.TRACKING_CONFIDENCE

    def test_migrate_skills_starts_empty(self):
        # 기존 매크로엔 스킬 등록이 없음 → 빈 튜플
        profile = migrate_from_legacy_config()
        assert profile.skills == ()

    def test_migrate_hotkeys_matches_legacy(self):
        import config
        profile = migrate_from_legacy_config()
        assert profile.hotkeys.start == config.START_KEY
        assert profile.hotkeys.stop == config.STOP_KEY
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
pytest tests/test_hunt_profile.py::TestLegacyMigration -v
```

기대: `ImportError: cannot import name 'migrate_from_legacy_config'`

- [ ] **Step 3: `hunt_profile.py`에 마이그레이션 함수 추가 (파일 하단)**

```python


# ══════════════════════════════════════════════
# Legacy config.py → HuntProfile 마이그레이션
# ══════════════════════════════════════════════

def migrate_from_legacy_config() -> HuntProfile:
    """
    config.py의 현재 상수 값들을 읽어 default HuntProfile 생성.
    첫 실행 시 default.json이 없으면 이 함수 결과를 저장한다.
    """
    import config

    # 기존 매크로는 늑대 전용 — 'wolf' 단일 monster entry 생성
    wolf = MonsterEntry(
        name="wolf",
        template_dir="images",  # 기존엔 폴더 분리 없음 → 루트 사용. 사용자가 추후 분리
        detect_confidence=config.DETECT_CONFIDENCE,
        tracking_confidence=config.TRACKING_CONFIDENCE,
        hp_bar_offset_y=config.HP_BAR_OFFSET_Y,
    )

    return HuntProfile(
        schema_version=1,
        name="default",
        monsters=(wolf,),
        combat=CombatConfig(
            attack_interval=config.ATTACK_INTERVAL,
            detect_miss_max=config.DETECT_MISS_MAX,
            target_timeout=config.TARGET_TIMEOUT,
            click_method=config.CLICK_METHOD,
        ),
        potion=PotionConfig(
            hp_enabled=config.POTION_ENABLED,
            hp_threshold=config.POTION_HP_THRESHOLD,
            hp_key_scancode=config.POTION_KEY_SCANCODE,
            mp_enabled=False,                      # Phase 1: MP 동작 X, 자리만
            mp_threshold=0.3,                       # 기본값
            mp_key_scancode=3,                      # 0x03 = "2" 키
            cooldown=config.POTION_COOLDOWN,
        ),
        skills=(),                                  # 빈 튜플로 시작 (사용자가 추가)
        hotkeys=HotkeyConfig(
            start=config.START_KEY,
            stop=config.STOP_KEY,
        ),
        loot=LootConfig(
            enabled=config.LOOT_ENABLED,
            visual_enabled=config.LOOT_VISUAL_ENABLED,
            delay_after_kill=config.LOOT_DELAY_AFTER_KILL,
            snapshot_max_age=config.LOOT_SNAPSHOT_MAX_AGE,
            diff_threshold=config.LOOT_DIFF_THRESHOLD,
            min_blob_area=config.LOOT_MIN_BLOB_AREA,
            max_blob_area=config.LOOT_MAX_BLOB_AREA,
            max_distance_ratio=config.LOOT_MAX_DISTANCE_RATIO,
            max_total_diff_ratio=config.LOOT_MAX_TOTAL_DIFF_RATIO,
            after_click_delay=config.LOOT_AFTER_CLICK_DELAY,
            press_count=config.LOOT_PRESS_COUNT,
            press_interval=config.LOOT_PRESS_INTERVAL,
            key_scancode=config.LOOT_KEY_SCANCODE,
            corpse_mask_ratio=config.LOOT_CORPSE_MASK_RATIO,
            roi_expand_ratio=config.LOOT_ROI_EXPAND_RATIO,
        ),
    )
```

- [ ] **Step 4: 테스트 재실행 — 통과 확인**

```bash
pytest tests/test_hunt_profile.py -v
```

기대: 모든 테스트 통과 (Task 1+2+3 = 20개)

- [ ] **Step 5: 커밋**

```bash
git add hunt_profile.py tests/test_hunt_profile.py
git commit -m "feat: hunt_profile — legacy config 마이그레이션 함수 + 정합성 테스트"
```

---

### Task 4: profile_manager.py — atomic 교체 + update 헬퍼 (TDD)

**Files:**
- Create: `profile_manager.py`
- Create: `tests/test_profile_manager.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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

        assert mgr.current is not original_ref  # 새 객체
        assert mgr.current.combat.attack_interval == 0.30
        assert mgr.current.combat.detect_miss_max == 4  # 다른 필드 보존

    def test_update_potion_replaces_atomically(self):
        p = _make_default_profile()
        mgr = ProfileManager(initial=p)
        mgr.update_potion(hp_threshold=0.7)
        assert mgr.current.potion.hp_threshold == 0.7
        assert mgr.current.potion.hp_enabled is True  # 다른 필드 보존

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
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_profile_manager.py -v
```

기대: `ImportError: cannot import name 'ProfileManager'`

- [ ] **Step 3: `profile_manager.py` 신규 작성**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_profile_manager.py -v
```

기대: `7 passed`

- [ ] **Step 5: 커밋**

```bash
git add profile_manager.py tests/test_profile_manager.py
git commit -m "feat: profile_manager — atomic 통째 교체 + 카테고리별 update 헬퍼"
```

---

### Task 5: skill_manager.py — N초 간격 자동 발동 (TDD)

**Files:**
- Create: `skill_manager.py`
- Create: `tests/test_skill_manager.py`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
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

        sm.tick()                  # fires at t=100
        current_time[0] = 110.0    # +10s, < 30s interval
        sm.tick()

        assert press.call_count == 1

    def test_fires_after_interval_elapsed(self):
        skills = [SkillEntry("buff", 33, 30.0, enabled=True)]
        mgr = ProfileManager(_profile_with_skills(skills))
        press = MagicMock()
        current_time = [100.0]
        sm = SkillManager(mgr, press_key=press, time_fn=lambda: current_time[0])

        sm.tick()                   # fires at t=100
        current_time[0] = 131.0     # +31s, exceeds 30s interval
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

        sm.tick()                   # both fire
        current_time[0] = 111.0
        sm.tick()                   # only 'a' fires (b interval not elapsed)

        assert press.call_count == 3
        # 호출 인자 확인
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
        sm.tick()                   # reset 후 다시 첫 발동처럼 동작

        assert press.call_count == 2
```

- [ ] **Step 2: 실패 확인**

```bash
pytest tests/test_skill_manager.py -v
```

기대: `ImportError: cannot import name 'SkillManager'`

- [ ] **Step 3: `skill_manager.py` 신규 작성**

```python
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
        self._last_use: dict[str, float] = {}  # skill.name → 마지막 발동 시각

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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
pytest tests/test_skill_manager.py -v
```

기대: `7 passed`

- [ ] **Step 5: 커밋**

```bash
git add skill_manager.py tests/test_skill_manager.py
git commit -m "feat: skill_manager — N초 간격 자동 발동 (시간 mock 기반 테스트)"
```

---

### Task 6a: macro_engine.py — ProfileManager + SkillManager `__init__` 주입만

회귀 위험을 줄이기 위해 큰 리팩터를 4개 Task로 분할 (Codex 리뷰 6번):
- **6a**: 생성자 주입만 (기존 동작 그대로 유지)
- **6b**: `_loot_items` 변경
- **6c**: `_check_and_use_potion` 변경
- **6d**: `hunt_loop`에 1회 스냅샷 + skill_manager.tick

**Files:**
- Modify: `macro_engine.py:1-50` (imports + `__init__`)

- [ ] **Step 1: imports 추가 (제거는 아직 안 함 — 호환 유지)**

`macro_engine.py` 상단에 추가:
```python
from profile_manager import ProfileManager
from skill_manager import SkillManager
```

기존 config import는 이 Task에서 **건드리지 않음**. `LOOT_*`, `POTION_*` 등이 아직 그대로 import됨. 6b/6c/6d에서 한 그룹씩 제거.

import 추가:
```python
from profile_manager import ProfileManager
from skill_manager import SkillManager
```

- [ ] **Step 2: `MacroEngine.__init__` 시그니처 변경 — profile_manager + skill_manager 주입만**

이 단계에서는 **`__init__`만 바꾸고 메서드 본문은 손대지 않음**. 기존 동작 그대로 유지 (config 참조도 그대로). 6b/6c/6d에서 본문을 단계적으로 마이그레이션.

기존:
```python
def __init__(self, click_method=CLICK_METHOD, region=None,
             template_dir="images", confidence=DETECT_CONFIDENCE):
    self.click_method = click_method
    ...
```

다음으로 변경:
```python
def __init__(self, profile_manager: ProfileManager, region=None,
             template_dir="images"):
    self.profile_manager = profile_manager
    self.region = region
    self.running = False

    profile = profile_manager.current
    self.click_method = profile.combat.click_method  # 호환용 캐시

    self.tracker = MonsterTracker(
        region=region,
        template_dir=template_dir,
        confidence=profile.monsters[0].detect_confidence if profile.monsters else 0.55,
    )
    self.item_picker = ItemPicker()
    self.skill_manager = SkillManager(
        profile_manager=profile_manager,
        press_key=press_key,
    )
    self._last_activate_time = 0.0
    self._last_region_refresh_time = 0.0
    self._miss_count = 0
    self._last_roam_direction = -1
    self._last_potion_time = 0.0
    self._last_hp_check_time = 0.0
    self.player_hp_ratio = -1.0
    self.player_mp_ratio = -1.0
```

- [ ] **Step 3: 회귀 검증 — 기존 동작 그대로**

```bash
pytest tests/ -v
python -c "from hunt_profile import migrate_from_legacy_config; from profile_manager import ProfileManager; p = ProfileManager(migrate_from_legacy_config()); from macro_engine import MacroEngine; e = MacroEngine(profile_manager=p, region=(0,0,800,600)); print('OK', e.click_method, e.skill_manager is not None)"
```

기대: 모든 테스트 통과, `OK sendinput True`

- [ ] **Step 4: 커밋**

```bash
git add macro_engine.py
git commit -m "refactor: macro_engine.__init__ — profile_manager + skill_manager 주입 (본문 변경 없음)"
```

---

### Task 6b: macro_engine._loot_items — profile.loot로 교체

Codex Major 3 반영: `_loot_items`가 `profile`을 인자로 받아 호출자(hunt_loop)가 사이클당 1회 캡처한 스냅샷을 사용.

**Files:**
- Modify: `macro_engine.py:73-...` (`_loot_items` 메서드)

- [ ] **Step 1: `_loot_items` 시그니처에 `profile` 인자 추가 (호출자는 6d에서 갱신)**

```python
    def _loot_items(self, profile):
        """사망 판정 후 아이템 줍기. profile은 호출자가 1회 캡처한 스냅샷."""
        loot = profile.loot
        if not loot.enabled:
            return

        time.sleep(loot.delay_after_kill + random.uniform(0, 0.05))

        picked = False
        snapshot = self.tracker.combat_snapshot
        if loot.visual_enabled and snapshot is not None and self.region is not None:
            picked = self.item_picker.try_pickup(
                snapshot=snapshot,
                current_region=self.region,
                click_method=profile.combat.click_method,
            )
            if picked:
                log.info("아이템 픽업: 시각 클릭 성공")
                time.sleep(loot.after_click_delay)

        space_count = 1 if picked else loot.press_count
        for i in range(space_count):
            press_key(loot.key_scancode)
            if i < space_count - 1:
                time.sleep(loot.press_interval + random.uniform(0, 0.04))
        if not picked:
            log.info(f"아이템 줍기 (Spacebar 보험 ×{space_count})")
        else:
            log.debug(f"Spacebar 보조 픽업 ×{space_count}")
```

- [ ] **Step 2: 호출자 (hunt_loop)에서 임시로 호환 처리**

`hunt_loop`의 `self._loot_items()` 호출 두 곳을 임시로:
```python
self._loot_items(self.profile_manager.current)
```
로 변경 (6d에서 hunt_loop 본문을 1회 스냅샷 패턴으로 정리).

- [ ] **Step 3: import에서 LOOT_* 제거**

`from config import (...)`에서 다음 7개 제거:
```
LOOT_ENABLED, LOOT_KEY_SCANCODE, LOOT_PRESS_COUNT,
LOOT_PRESS_INTERVAL, LOOT_DELAY_AFTER_KILL,
LOOT_VISUAL_ENABLED, LOOT_AFTER_CLICK_DELAY,
```

- [ ] **Step 4: 회귀 검증**

```bash
pytest tests/ -v
```

기대: 모든 테스트 통과 (loot 동작 변경 없음 — config 값과 default profile 값이 동일)

- [ ] **Step 5: 커밋**

```bash
git add macro_engine.py
git commit -m "refactor: macro_engine._loot_items — profile.loot 인자로 받기"
```

---

### Task 6c: macro_engine._check_and_use_potion — profile.potion로 교체

**Files:**
- Modify: `macro_engine.py` (`_check_and_use_potion` 메서드)

- [ ] **Step 1: `_check_and_use_potion`도 profile 인자로**

```python
    def _check_and_use_potion(self, profile):
        """캐릭터 HP 확인 → 임계값 이하면 물약 사용. profile은 호출자가 캡처한 스냅샷."""
        potion = profile.potion
        if not potion.hp_enabled:
            return

        from config import POTION_CHECK_INTERVAL  # 코드 상수 (UI에서 안 만짐)
        now = time.time()
        if now - self._last_hp_check_time < POTION_CHECK_INTERVAL:
            return
        self._last_hp_check_time = now

        if now - self._last_potion_time < potion.cooldown:
            return

        frame = capture_screen(region=self.region)
        hp_ratio = self._measure_player_hp(frame)
        self.player_hp_ratio = hp_ratio

        mp_ratio = self._measure_player_mp(frame)
        self.player_mp_ratio = mp_ratio

        if hp_ratio < 0:
            log.debug("캐릭터 HP 측정 불가")
            return

        hp_str = f"{hp_ratio:.1%}"
        mp_str = f"{mp_ratio:.1%}" if mp_ratio >= 0 else "측정불가"
        log.debug(f"캐릭터 HP: {hp_str}, MP: {mp_str}")

        if hp_ratio <= potion.hp_threshold:
            press_key(potion.hp_key_scancode)
            self._last_potion_time = now
            log.info(f"물약 사용! (HP: {hp_ratio:.1%}, 임계값: {potion.hp_threshold:.0%})")
```

- [ ] **Step 2: hunt_loop 호출 호환**

`self._check_and_use_potion()` 호출을 임시로:
```python
self._check_and_use_potion(self.profile_manager.current)
```
로 변경.

- [ ] **Step 3: import에서 POTION_* 제거**

`from config import (...)` 블록에서 5개 제거:
```
POTION_ENABLED, POTION_KEY_SCANCODE, POTION_HP_THRESHOLD,
POTION_COOLDOWN, POTION_CHECK_INTERVAL,
```
(`POTION_CHECK_INTERVAL`은 함수 안에서 지역 import로 사용 — 코드 상수)

- [ ] **Step 4: 회귀 검증**

```bash
pytest tests/ -v
python -c "from hunt_profile import migrate_from_legacy_config; from profile_manager import ProfileManager; p = ProfileManager(migrate_from_legacy_config()); from macro_engine import MacroEngine; e = MacroEngine(profile_manager=p, region=(0,0,800,600)); print('OK')"
```

- [ ] **Step 5: 커밋**

```bash
git add macro_engine.py
git commit -m "refactor: macro_engine._check_and_use_potion — profile.potion 인자로 받기"
```

---

### Task 6d: macro_engine.hunt_loop — 사이클당 profile 1회 스냅샷 + skill_manager.tick

Codex Major 3 핵심 반영: 매 사이클 시작에서 `profile = self.profile_manager.current` 한 번만 읽고 그 스냅샷을 모든 헬퍼에 전달. 사이클 도중 UI에서 프로필이 교체돼도 진행 중 사이클은 일관된 값 사용.

**Files:**
- Modify: `macro_engine.py` (`hunt_loop`, `stop`)

- [ ] **Step 1: hunt_loop 본문을 사이클당 1회 스냅샷 패턴으로 재구성**

기존:
```python
        while self.running:
            try:
                self._ensure_foreground()
                self._refresh_region()
                self._check_and_use_potion()
                pos, reason = self.tracker.find_and_track()
                if pos and reason == TRACK_OK:
                    ...
                    delay = max(0.05, random.gauss(ATTACK_INTERVAL, 0.05))
                    time.sleep(delay)
                ...
                elif reason == TRACK_KILLED:
                    ...
                    self._loot_items()
                ...
```

다음으로 변경 (사이클 시작에서 profile atomic 캡처):

```python
        while self.running:
            try:
                # 사이클당 1회 atomic 스냅샷 — 사이클 도중 프로필 교체돼도 일관성 유지
                profile = self.profile_manager.current

                self._ensure_foreground()
                self._refresh_region()

                # 스킬 자동 사용 (등록된 스킬을 N초 간격으로 발동)
                self.skill_manager.tick()

                self._check_and_use_potion(profile)
                pos, reason = self.tracker.find_and_track()

                if pos and reason == TRACK_OK:
                    self._miss_count = 0
                    activate_window()
                    refined = self.tracker.refine_position(original_pos=pos)
                    target = refined if refined else pos
                    click(target[0], target[1], method=profile.combat.click_method)
                    if refined:
                        log.info(f"공격: ({target[0]}, {target[1]}) (보정됨, 원본: {pos})")
                    else:
                        log.info(f"공격: ({target[0]}, {target[1]})")
                    delay = max(0.05, random.gauss(profile.combat.attack_interval, 0.05))
                    time.sleep(delay)

                elif reason == TRACK_MISS_PENDING:
                    time.sleep(0.1)

                elif reason == TRACK_KILLED:
                    self._miss_count = 0
                    log.info("대상 사망 추정 → 아이템 줍기")
                    self._loot_items(profile)

                elif reason == TRACK_ABANDONED_HP:
                    log.info("대상 HP 정체 → 사실상 사망 추정, 아이템 줍기 시도")
                    self._loot_items(profile)

                else:
                    self._miss_count += 1
                    if self._miss_count >= ROAM_AFTER_MISS_COUNT:
                        log.info(f"연속 {self._miss_count}회 미발견 → 랜덤 이동")
                        self._roam_random()
                        self._miss_count = 0
                    else:
                        log.info(f"대상 없음 (사유: {reason}), 재탐색 대기...")
                        time.sleep(DEFAULT_DELAY)

            except Exception as e:
                log.error(f"사냥 루프 예외 발생: {e}")
                time.sleep(1)
```

- [ ] **Step 2: stop() 메서드에 skill_manager 리셋 추가**

```python
    def stop(self):
        self.running = False
        self.tracker.reset()
        self.skill_manager.reset()
        self._miss_count = 0
        self.player_hp_ratio = -1.0
        self.player_mp_ratio = -1.0
        log.info("매크로 중지 요청")
```

- [ ] **Step 3: import에서 ATTACK_INTERVAL, CLICK_METHOD, DETECT_CONFIDENCE 제거**

남은 동적 import 모두 제거. `DEFAULT_DELAY`는 유지 (코드 상수).

- [ ] **Step 4: 전체 테스트 + 회귀 확인**

```bash
pytest tests/ -v
python -c "from hunt_profile import migrate_from_legacy_config; from profile_manager import ProfileManager; p = ProfileManager(migrate_from_legacy_config()); from macro_engine import MacroEngine; e = MacroEngine(profile_manager=p, region=(0,0,800,600)); print('OK', e.click_method)"
```

기대: 모든 테스트 통과, `OK sendinput`

- [ ] **Step 5: 커밋**

```bash
git add macro_engine.py
git commit -m "refactor: macro_engine.hunt_loop — 사이클당 profile 1회 스냅샷 + skill_manager.tick"
```

---

### Task 7: monster_tracker.py — profile_provider 주입

**Files:**
- Modify: `monster_tracker.py`

`MonsterTracker`는 현재 `confidence`를 생성자에서 받고, 다른 detection 임계값들은 `config`에서 import한다. Phase 1에서는 monster별 setting을 사용하기 위해 profile_provider를 주입한다.

단순화를 위해 Phase 1에서는 **confidence만 profile에서 동적 조회**, 나머지는 config 그대로 (per-monster 다른 값을 쓰는 시나리오는 Phase 2에서).

- [ ] **Step 1: `MonsterTracker.__init__`에 profile_provider 인자 추가 (선택적)**

```python
class MonsterTracker:
    def __init__(self, region=None, template_dir="images",
                 confidence=DETECT_CONFIDENCE,
                 profile_provider=None):
        self.region = region
        self.template_dir = template_dir
        self.confidence = confidence  # 폴백용 정적 값 (profile_provider 없을 때)
        self.profile_provider = profile_provider
        ...
```

- [ ] **Step 2: `detect`에서 confidence 우선순위 변경**

`detect_wolves()` 호출 시 confidence 인자에 동적 값 사용:

```python
    def detect(self, frame=None):
        if frame is None:
            frame = capture_screen(region=self.region)
        if frame is None:
            return []

        # profile에 monsters[0]가 있으면 그 confidence 사용, 없으면 정적 값
        confidence = self._current_confidence()
        return detect_wolves(frame, self.template_dir, confidence)

    def _current_confidence(self) -> float:
        """프로필이 있으면 monsters[0].detect_confidence, 없으면 정적값."""
        if self.profile_provider is not None:
            profile = self.profile_provider.current
            if profile.monsters:
                return profile.monsters[0].detect_confidence
        return self.confidence
```

- [ ] **Step 3: `_detect_in_roi`의 tracking_confidence도 동적**

```python
    def _detect_in_roi(self, frame, last_bbox, pad_ratio=1.0, tracking=False):
        ...
        if tracking and self.profile_provider is not None:
            profile = self.profile_provider.current
            if profile.monsters:
                min_confidence = profile.monsters[0].tracking_confidence
            else:
                min_confidence = TRACKING_CONFIDENCE  # 폴백
        else:
            min_confidence = TRACKING_CONFIDENCE if tracking else self.confidence
        ...
```

(전체 메서드 본문은 기존 그대로 유지, 위 3줄만 추가)

- [ ] **Step 4: `_measure_hp_ratio`에서 monster.hp_bar_offset_y 사용 (Codex Major 4 반영)**

기존 코드는 `HP_BAR_OFFSET_Y` 상수를 직접 참조하지만, profile의 monster 항목에 동일 값이 들어 있어 사용 안 하는 상태. 다음으로 변경:

```python
    def _measure_hp_ratio(self, frame):
        if self.last_bbox is None or frame is None:
            return -1.0

        # profile의 monsters[0]에서 hp_bar_offset_y 읽기 (없으면 config 폴백)
        offset_y = self._current_hp_bar_offset_y()

        x, y, w, h = self.last_bbox
        hp_y1 = max(0, y + offset_y)
        hp_y2 = max(0, y + offset_y + HP_BAR_HEIGHT)
        ...  # 나머지 본문 그대로
```

`_current_hp_bar_offset_y()` 헬퍼 메서드 추가:
```python
    def _current_hp_bar_offset_y(self) -> int:
        if self.profile_provider is not None:
            profile = self.profile_provider.current
            if profile.monsters:
                return profile.monsters[0].hp_bar_offset_y
        return HP_BAR_OFFSET_Y
```

- [ ] **Step 5: `_update_combat_snapshot`에서 loot.roi_expand_ratio 사용 (Codex Major 4)**

기존:
```python
snap = build_snapshot(frame, bbox, self.region, LOOT_ROI_EXPAND_RATIO)
```

→
```python
expand_ratio = self._current_roi_expand_ratio()
snap = build_snapshot(frame, bbox, self.region, expand_ratio)
```

`_current_roi_expand_ratio()` 헬퍼 추가:
```python
    def _current_roi_expand_ratio(self) -> float:
        if self.profile_provider is not None:
            return self.profile_provider.current.loot.roi_expand_ratio
        return LOOT_ROI_EXPAND_RATIO
```

- [ ] **Step 6: `MacroEngine.__init__`에서 profile_provider 전달 (Task 6a 후속)**

```python
        self.tracker = MonsterTracker(
            region=region,
            template_dir=template_dir,
            confidence=profile.monsters[0].detect_confidence if profile.monsters else 0.55,
            profile_provider=profile_manager,
        )
```

- [ ] **Step 7: 테스트 회귀 확인**

```bash
pytest tests/ -v
```

기대: 모든 테스트 통과 (default profile의 hp_bar_offset_y, roi_expand_ratio가 config 값과 동일하므로 동작 변경 없음)

- [ ] **Step 8: 커밋**

```bash
git add monster_tracker.py macro_engine.py
git commit -m "refactor: monster_tracker — profile_provider로 confidence/hp_offset/roi_expand 동적 조회"
```

---

### Task 8: macro_ui.py — QTabWidget 골격 + 빈 6 탭

기존 macro_ui는 단일 화면. QTabWidget으로 6 탭 구조 추가. **이 Task에서는 빈 탭만 만들고** 기존 기능(시작/중지/HP/MP 표시)은 상단에 유지.

**Files:**
- Modify: `macro_ui.py` (구조 큰 변경)

- [ ] **Step 1: 신규 모듈 import 추가**

`macro_ui.py` 상단에:

```python
from hunt_profile import migrate_from_legacy_config, load_profile, save_profile
from profile_manager import ProfileManager
import os
```

- [ ] **Step 2: `MacroWindow.__init__`에 ProfileManager 초기화**

`__init__` 안, `self.engine = None` 직전에 추가:

```python
        # 프로필 매니저 초기화 (default.json 자동 마이그레이션)
        self.profile_manager = self._init_profile_manager()
```

`_init_profile_manager()` 메서드 추가:

```python
    def _init_profile_manager(self):
        """
        profiles/default.json 로드. 없으면 legacy config 마이그레이션.
        손상된 JSON 발견 시 .broken 백업 + 경고 다이얼로그 (Codex Critical 2).
        """
        from PyQt6.QtWidgets import QMessageBox
        os.makedirs("profiles", exist_ok=True)
        default_path = "profiles/default.json"

        if os.path.exists(default_path):
            try:
                profile = load_profile(default_path)
                return ProfileManager(profile)
            except Exception as e:
                # 손상된 default.json — 사용자 데이터 보존을 위해 .broken으로 백업
                import datetime
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                broken_path = f"{default_path}.broken_{ts}"
                try:
                    os.rename(default_path, broken_path)
                    backup_msg = f"{broken_path}로 백업했습니다."
                except Exception as rename_err:
                    backup_msg = f"백업 실패: {rename_err}"

                self._append_log("ERROR", f"default.json 손상: {e}. {backup_msg}")
                QMessageBox.warning(
                    self, "프로필 손상",
                    f"profiles/default.json을 읽을 수 없습니다.\n\n"
                    f"오류: {e}\n\n"
                    f"파일을 {os.path.basename(broken_path)}로 백업하고 "
                    f"기본 프로필을 새로 생성합니다.",
                )
                profile = migrate_from_legacy_config()
                save_profile(profile, default_path)
                return ProfileManager(profile)
        else:
            profile = migrate_from_legacy_config()
            save_profile(profile, default_path)
            return ProfileManager(profile)
```

추가 테스트 (Codex Critical 2):

`tests/test_hunt_profile.py`에 손상 JSON 처리 테스트 추가:
```python
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
```

- [ ] **Step 3: 메인 레이아웃에 QTabWidget 추가**

기존 메인 위젯 빌드 코드를 찾아 (`self.setCentralWidget(...)` 부근), 다음 구조로 변경. 핵심: 상단 상태/HP/MP/시작중지 영역은 유지, 하단에 QTabWidget 삽입.

`_build_settings_tabs()` 메서드 신규:

```python
    def _build_settings_tabs(self) -> QTabWidget:
        """6 탭 설정 패널."""
        tabs = QTabWidget()
        tabs.addTab(self._build_monster_tab(), "몬스터")
        tabs.addTab(self._build_combat_tab(), "전투")
        tabs.addTab(self._build_skill_tab(), "스킬")
        tabs.addTab(self._build_potion_tab(), "물약")
        tabs.addTab(self._build_hotkey_tab(), "단축키")
        tabs.addTab(self._build_profile_tab(), "프로필")
        return tabs

    def _build_monster_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("(Task 9에서 구현 — 몬스터 등록/관리)"))
        return w

    def _build_combat_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("(Task 10에서 구현 — 전투 파라미터 슬라이더)"))
        return w

    def _build_skill_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("(Task 11에서 구현 — 스킬 등록)"))
        return w

    def _build_potion_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("(Task 12에서 구현 — HP/MP 임계값 + 키)"))
        return w

    def _build_hotkey_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("(Task 13에서 구현 — 시작/중지 핫키)"))
        return w

    def _build_profile_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(QLabel("(Task 14에서 구현 — 프로필 저장/불러오기)"))
        return w
```

기존 메인 레이아웃에서, 사이드바나 미리보기 영역 옆에 `self._build_settings_tabs()`를 배치. 정확한 위치는 기존 레이아웃 구조에 따라 결정 — `QSplitter`나 `QHBoxLayout` 안에 추가.

- [ ] **Step 4: `_on_start`에서 MacroEngine 생성자 호출 변경**

기존:
```python
        self.engine = MacroEngine(
            click_method=config.CLICK_METHOD,
            region=self.region,
            confidence=config.DETECT_CONFIDENCE,
        )
```

→

```python
        self.engine = MacroEngine(
            profile_manager=self.profile_manager,
            region=self.region,
        )
```

- [ ] **Step 5: macro_ui 실행 가능성 확인**

```bash
python -c "from macro_ui import MacroWindow; print('import OK')"
```

기대: `import OK`

- [ ] **Step 6: 커밋**

```bash
git add macro_ui.py
git commit -m "feat: macro_ui — QTabWidget 골격 + 빈 6 탭 + ProfileManager 초기화"
```

---

### Task 9: 몬스터 탭 — 템플릿 폴더 등록/관리

**Files:**
- Modify: `macro_ui.py` (몬스터 탭 본문)

- [ ] **Step 1: `_build_monster_tab` 본격 구현으로 교체**

```python
    def _build_monster_tab(self) -> QWidget:
        """몬스터 탭 — 등록된 몬스터 리스트 + 추가/삭제/편집."""
        w = QWidget()
        l = QHBoxLayout(w)

        # 좌측: 몬스터 리스트
        left = QVBoxLayout()
        left.addWidget(QLabel("등록된 몬스터:"))
        self.monster_list = QListWidget()
        self.monster_list.itemSelectionChanged.connect(self._on_monster_selected)
        left.addWidget(self.monster_list)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("몬스터 추가")
        btn_add.clicked.connect(self._on_monster_add)
        btn_del = QPushButton("선택 삭제")
        btn_del.clicked.connect(self._on_monster_delete)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        left.addLayout(btn_row)

        # 우측: 선택된 몬스터 상세 편집
        right = QGroupBox("상세 설정")
        rgrid = QGridLayout(right)
        self.mon_name = QLabel("(선택 없음)")
        self.mon_dir = QLabel("-")
        self.mon_conf = QSlider(Qt.Orientation.Horizontal)
        self.mon_conf.setRange(30, 95)  # 0.30~0.95
        self.mon_conf.setSingleStep(5)
        self.mon_conf_label = QLabel("0.55")
        self.mon_conf.valueChanged.connect(
            lambda v: self.mon_conf_label.setText(f"{v/100:.2f}")
        )
        self.mon_conf.sliderReleased.connect(self._on_monster_confidence_changed)

        rgrid.addWidget(QLabel("이름:"), 0, 0)
        rgrid.addWidget(self.mon_name, 0, 1)
        rgrid.addWidget(QLabel("폴더:"), 1, 0)
        rgrid.addWidget(self.mon_dir, 1, 1)
        rgrid.addWidget(QLabel("감지 임계값:"), 2, 0)
        rgrid.addWidget(self.mon_conf, 2, 1)
        rgrid.addWidget(self.mon_conf_label, 2, 2)

        l.addLayout(left, 1)
        l.addWidget(right, 2)

        self._refresh_monster_list()
        return w

    def _refresh_monster_list(self):
        """profile_manager.current.monsters로 리스트 갱신."""
        self.monster_list.clear()
        for m in self.profile_manager.current.monsters:
            self.monster_list.addItem(f"{m.name}  ({m.template_dir})")

    def _selected_monster_index(self) -> int:
        return self.monster_list.currentRow()

    def _on_monster_selected(self):
        idx = self._selected_monster_index()
        if idx < 0:
            return
        m = self.profile_manager.current.monsters[idx]
        self.mon_name.setText(m.name)
        self.mon_dir.setText(m.template_dir)
        self.mon_conf.setValue(int(m.detect_confidence * 100))
        self.mon_conf_label.setText(f"{m.detect_confidence:.2f}")

    def _on_monster_add(self):
        """폴더 다이얼로그로 templates 디렉토리 선택 → 새 몬스터 추가."""
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "몬스터 추가", "이름:")
        if not ok or not name.strip():
            return
        folder = QFileDialog.getExistingDirectory(self, "템플릿 폴더 선택", "images")
        if not folder:
            return
        # 절대 → 상대 경로 변환 시도
        try:
            rel = os.path.relpath(folder).replace("\\", "/")
        except Exception:
            rel = folder
        from hunt_profile import MonsterEntry
        new = MonsterEntry(
            name=name.strip(),
            template_dir=rel,
            detect_confidence=0.55,
            tracking_confidence=0.40,
            hp_bar_offset_y=-20,
        )
        self.profile_manager.set_monsters(
            self.profile_manager.current.monsters + (new,)
        )
        self._refresh_monster_list()
        self._append_log("INFO", f"몬스터 추가: {name}")

    def _on_monster_delete(self):
        idx = self._selected_monster_index()
        if idx < 0:
            return
        monsters = list(self.profile_manager.current.monsters)
        removed = monsters.pop(idx)
        self.profile_manager.set_monsters(tuple(monsters))
        self._refresh_monster_list()
        self._append_log("INFO", f"몬스터 삭제: {removed.name}")

    def _on_monster_confidence_changed(self):
        idx = self._selected_monster_index()
        if idx < 0:
            return
        new_conf = self.mon_conf.value() / 100
        import dataclasses
        monsters = list(self.profile_manager.current.monsters)
        monsters[idx] = dataclasses.replace(monsters[idx], detect_confidence=new_conf)
        self.profile_manager.set_monsters(tuple(monsters))
```

- [ ] **Step 2: 수동 검증**

`python macro_ui.py` 실행 → 몬스터 탭에서:
- 기본 wolf 항목이 보이는지
- 추가 버튼 → 이름 입력 → 폴더 선택 → 리스트에 추가되는지
- 삭제 버튼 → 항목 사라지는지
- 임계값 슬라이더 → 라벨이 즉시 업데이트되는지

- [ ] **Step 3: 커밋**

```bash
git add macro_ui.py
git commit -m "feat: 몬스터 탭 — 등록/삭제/임계값 슬라이더"
```

---

### Task 10: 전투 탭 — 슬라이더 4종

**Files:**
- Modify: `macro_ui.py` (전투 탭 본문)

- [ ] **Step 1: `_build_combat_tab` 본격 구현**

```python
    def _build_combat_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox, QFormLayout, QRadioButton, QButtonGroup

        w = QWidget()
        form = QFormLayout(w)
        combat = self.profile_manager.current.combat

        # attack_interval (DoubleSpinBox)
        self.combat_attack_interval = QDoubleSpinBox()
        self.combat_attack_interval.setRange(0.05, 1.0)
        self.combat_attack_interval.setSingleStep(0.05)
        self.combat_attack_interval.setValue(combat.attack_interval)
        self.combat_attack_interval.valueChanged.connect(
            lambda v: self.profile_manager.update_combat(attack_interval=v)
        )
        form.addRow("공격 간격 (초):", self.combat_attack_interval)

        # detect_miss_max (SpinBox)
        self.combat_miss_max = QSpinBox()
        self.combat_miss_max.setRange(1, 10)
        self.combat_miss_max.setValue(combat.detect_miss_max)
        self.combat_miss_max.valueChanged.connect(
            lambda v: self.profile_manager.update_combat(detect_miss_max=v)
        )
        form.addRow("연속 미감지 사망 판정 (회):", self.combat_miss_max)

        # target_timeout
        self.combat_timeout = QDoubleSpinBox()
        self.combat_timeout.setRange(5.0, 60.0)
        self.combat_timeout.setSingleStep(1.0)
        self.combat_timeout.setValue(combat.target_timeout)
        self.combat_timeout.valueChanged.connect(
            lambda v: self.profile_manager.update_combat(target_timeout=v)
        )
        form.addRow("대상 타임아웃 (초):", self.combat_timeout)

        # click_method (라디오)
        click_group = QGroupBox("클릭 방식")
        click_layout = QVBoxLayout(click_group)
        self.click_method_group = QButtonGroup(self)
        for method in ("sendinput", "directinput", "mousekeys"):
            rb = QRadioButton(method)
            if method == combat.click_method:
                rb.setChecked(True)
            rb.toggled.connect(
                lambda checked, m=method: checked and
                self.profile_manager.update_combat(click_method=m)
            )
            self.click_method_group.addButton(rb)
            click_layout.addWidget(rb)
        form.addRow(click_group)

        return w
```

- [ ] **Step 2: 수동 검증**

UI 실행 → 전투 탭에서 각 위젯 변경 시 profile이 즉시 갱신되는지. 매크로 시작/중지 후 다시 시작했을 때 변경된 값이 반영되는지.

- [ ] **Step 3: 커밋**

```bash
git add macro_ui.py
git commit -m "feat: 전투 탭 — attack_interval / miss_max / timeout / click_method"
```

---

### Task 11: 스킬 탭 — 다중 등록 + 키 캡처

**Files:**
- Modify: `macro_ui.py` (스킬 탭 + 키 캡처 위젯)

- [ ] **Step 1: 키 캡처 위젯 클래스 추가 (파일 상단, MacroWindow 위)**

Codex Major 5 반영: `QWidget` + 내부 `QLineEdit` 조합은 포커스/키이벤트가 부모로 안 와서 불안정. **`QLineEdit`를 직접 상속**하고 modifier-only 키 차단.

```python
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtCore import Qt


# Qt.Key 중 modifier-only (Shift/Ctrl/Alt/Meta 등) — 단독 입력은 무시
_MODIFIER_KEYS = frozenset({
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock,
    Qt.Key.Key_ScrollLock,
})


class KeyCaptureLineEdit(QLineEdit):
    """
    QLineEdit를 상속한 키 캡처 위젯.
    위젯 클릭(또는 포커스) → 안내 텍스트 → 사용자가 키 누르면 nativeScanCode 캡처.
    """
    keyChanged = pyqtSignal(int)  # 새 스캔코드 (nativeScanCode)

    def __init__(self, initial_scancode: int = 0, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self._scan = initial_scancode
        self._capturing = False
        self._update_label()

    def _update_label(self):
        if self._scan == 0:
            self.setText("(클릭 후 키 누르기)")
        else:
            self.setText(f"scan=0x{self._scan:02X}")

    def mousePressEvent(self, event):
        # 위젯 클릭 → 캡처 모드 진입
        self.setText("(키 누르세요...)")
        self._capturing = True
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        # 캡처 도중 포커스 잃으면 모드 해제
        if self._capturing:
            self._capturing = False
            self._update_label()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if not self._capturing:
            super().keyPressEvent(event)
            return

        key = event.key()
        # modifier 단독 입력은 무시 (Shift만 누른 경우 등)
        if key in _MODIFIER_KEYS:
            return

        scan = event.nativeScanCode()
        # nativeScanCode가 0이면 가짜 이벤트 → 무시
        if scan == 0:
            return

        self._scan = scan
        self._capturing = False
        self._update_label()
        self.keyChanged.emit(scan)
        # 캡처 완료 후 포커스 해제 (다음 키는 일반 동작)
        self.clearFocus()

    def scancode(self) -> int:
        return self._scan

    def set_scancode(self, scan: int):
        self._scan = scan
        self._update_label()
```

- [ ] **Step 2: 스킬 탭 본문 구현**

```python
    def _build_skill_tab(self) -> QWidget:
        from PyQt6.QtWidgets import (
            QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
            QDoubleSpinBox, QInputDialog, QLineEdit,
        )
        w = QWidget()
        l = QVBoxLayout(w)

        l.addWidget(QLabel("등록된 스킬 (자동 사용 간격마다 키 발동):"))
        self.skill_table = QTableWidget(0, 4)
        self.skill_table.setHorizontalHeaderLabels(
            ["이름", "키", "자동 사용 간격(초)", "활성"]
        )
        self.skill_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        l.addWidget(self.skill_table)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("스킬 추가")
        btn_add.clicked.connect(self._on_skill_add)
        btn_del = QPushButton("선택 삭제")
        btn_del.clicked.connect(self._on_skill_delete)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        l.addLayout(btn_row)

        self._refresh_skill_table()
        return w

    def _refresh_skill_table(self):
        """profile_manager.current.skills로 테이블 갱신."""
        from PyQt6.QtWidgets import QTableWidgetItem
        self.skill_table.setRowCount(0)
        for s in self.profile_manager.current.skills:
            row = self.skill_table.rowCount()
            self.skill_table.insertRow(row)
            self.skill_table.setItem(row, 0, QTableWidgetItem(s.name))
            self.skill_table.setItem(row, 1, QTableWidgetItem(f"0x{s.key_scancode:02X}"))
            self.skill_table.setItem(row, 2, QTableWidgetItem(f"{s.auto_use_interval:.1f}"))
            chk = QCheckBox()
            chk.setChecked(s.enabled)
            chk.stateChanged.connect(
                lambda state, idx=row: self._on_skill_enabled_changed(idx, state)
            )
            self.skill_table.setCellWidget(row, 3, chk)
        self.skill_table.setRowCount(len(self.profile_manager.current.skills))

    def _on_skill_add(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "스킬 추가", "이름:")
        if not ok or not name.strip():
            return
        interval, ok = QInputDialog.getDouble(
            self, "자동 사용 간격", "초 (0이면 수동):",
            value=30.0, min=0.0, max=600.0, decimals=1
        )
        if not ok:
            return
        # 키 캡처는 다이얼로그 내에서 처리
        scan, ok = QInputDialog.getInt(
            self, "키 스캔코드", "16진수 정수 입력 (예: 33 = 0x21):",
            value=33, min=1, max=255
        )
        if not ok:
            return

        from hunt_profile import SkillEntry
        new = SkillEntry(
            name=name.strip(),
            key_scancode=scan,
            auto_use_interval=interval,
            enabled=True,
        )
        self.profile_manager.set_skills(
            self.profile_manager.current.skills + (new,)
        )
        self._refresh_skill_table()
        self._append_log("INFO", f"스킬 추가: {name} (key=0x{scan:02X})")

    def _on_skill_delete(self):
        row = self.skill_table.currentRow()
        if row < 0:
            return
        skills = list(self.profile_manager.current.skills)
        removed = skills.pop(row)
        self.profile_manager.set_skills(tuple(skills))
        self._refresh_skill_table()
        self._append_log("INFO", f"스킬 삭제: {removed.name}")

    def _on_skill_enabled_changed(self, row: int, state):
        import dataclasses
        skills = list(self.profile_manager.current.skills)
        if row >= len(skills):
            return
        skills[row] = dataclasses.replace(
            skills[row], enabled=(state == Qt.CheckState.Checked.value)
        )
        self.profile_manager.set_skills(tuple(skills))
```

- [ ] **Step 2: 수동 검증**

UI 실행 → 스킬 탭에서 추가/삭제/활성 토글 → 매크로 시작 후 N초마다 로그에 "스킬 사용: ..." 라인 발생 확인.

- [ ] **Step 3: 커밋**

```bash
git add macro_ui.py
git commit -m "feat: 스킬 탭 — 다중 등록 + 활성 토글 + 자동 사용 간격"
```

---

### Task 12: 물약 탭 — HP 임계값 + 키 (MP는 자리만)

**Files:**
- Modify: `macro_ui.py` (물약 탭)

- [ ] **Step 1: `_build_potion_tab` 본격 구현**

```python
    def _build_potion_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout
        w = QWidget()
        l = QVBoxLayout(w)
        potion = self.profile_manager.current.potion

        # HP 섹션
        hp_grp = QGroupBox("HP 자동 물약")
        hp_form = QFormLayout(hp_grp)

        self.potion_hp_enabled = QCheckBox("활성화")
        self.potion_hp_enabled.setChecked(potion.hp_enabled)
        self.potion_hp_enabled.stateChanged.connect(
            lambda s: self.profile_manager.update_potion(
                hp_enabled=(s == Qt.CheckState.Checked.value)
            )
        )
        hp_form.addRow(self.potion_hp_enabled)

        self.potion_hp_threshold = QSlider(Qt.Orientation.Horizontal)
        self.potion_hp_threshold.setRange(10, 95)  # 10%~95%
        self.potion_hp_threshold.setValue(int(potion.hp_threshold * 100))
        self.potion_hp_threshold_label = QLabel(f"{int(potion.hp_threshold*100)}%")
        self.potion_hp_threshold.valueChanged.connect(
            lambda v: self.potion_hp_threshold_label.setText(f"{v}%")
        )
        self.potion_hp_threshold.sliderReleased.connect(
            lambda: self.profile_manager.update_potion(
                hp_threshold=self.potion_hp_threshold.value() / 100
            )
        )
        hp_row = QHBoxLayout()
        hp_row.addWidget(self.potion_hp_threshold)
        hp_row.addWidget(self.potion_hp_threshold_label)
        hp_form.addRow("HP 임계값 (이하면 사용):", hp_row)

        self.potion_hp_key = QSpinBox()
        self.potion_hp_key.setRange(1, 255)
        self.potion_hp_key.setValue(potion.hp_key_scancode)
        self.potion_hp_key.setPrefix("0x")
        self.potion_hp_key.setDisplayIntegerBase(16)
        self.potion_hp_key.valueChanged.connect(
            lambda v: self.profile_manager.update_potion(hp_key_scancode=v)
        )
        hp_form.addRow("키 스캔코드:", self.potion_hp_key)

        l.addWidget(hp_grp)

        # MP 섹션 — 자리만, 비활성
        mp_grp = QGroupBox("MP 자동 물약 (Phase 3에서 활성화)")
        mp_grp.setEnabled(False)
        mp_form = QFormLayout(mp_grp)
        mp_form.addRow(QLabel("(미구현 — UI만 표시)"))
        l.addWidget(mp_grp)

        # 쿨다운
        self.potion_cooldown = QDoubleSpinBox()
        self.potion_cooldown.setRange(1.0, 30.0)
        self.potion_cooldown.setSingleStep(0.5)
        self.potion_cooldown.setValue(potion.cooldown)
        self.potion_cooldown.valueChanged.connect(
            lambda v: self.profile_manager.update_potion(cooldown=v)
        )
        cd_row = QHBoxLayout()
        cd_row.addWidget(QLabel("쿨다운 (초):"))
        cd_row.addWidget(self.potion_cooldown)
        cd_row.addStretch()
        l.addLayout(cd_row)

        l.addStretch()
        return w
```

- [ ] **Step 2: 수동 검증**

물약 탭에서 HP 임계값 슬라이더/키 변경 → 매크로 실행 시 새 임계값 적용. MP 섹션은 회색.

- [ ] **Step 3: 커밋**

```bash
git add macro_ui.py
git commit -m "feat: 물약 탭 — HP 임계값/키 (MP 자리만, Phase 3에서 활성)"
```

---

### Task 13: 단축키 탭 + HotkeyRegistrar (재바인딩)

Codex Critical 1 반영: 핫키는 프로필 필드인데 main.py가 F5/F6 하드코딩 → 변경해도 안 먹힘. **HotkeyRegistrar**를 별도 컴포넌트로 도입해 등록/해제/재바인딩.

**Files:**
- Create: `hotkey_registrar.py`
- Modify: `macro_ui.py` (단축키 탭 + HotkeyRegistrar 사용)
- Modify: `main.py` (config.START_KEY/STOP_KEY → profile.hotkeys)

- [ ] **Step 1: `hotkey_registrar.py` 신규 — 등록/해제 추상화**

```python
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
```

- [ ] **Step 2: `main.py`에서 HotkeyRegistrar 사용**

기존 `main.py`에서 `keyboard.add_hotkey(START_KEY, ...)` 직접 호출 패턴을 다음으로 교체:

```python
# main.py
from hunt_profile import migrate_from_legacy_config
from profile_manager import ProfileManager
from hotkey_registrar import HotkeyRegistrar
from macro_engine import MacroEngine
# ... 기존 import 유지

import os
from hunt_profile import load_profile, save_profile

def main():
    # 프로필 로드
    os.makedirs("profiles", exist_ok=True)
    default_path = "profiles/default.json"
    if os.path.exists(default_path):
        try:
            profile = load_profile(default_path)
        except Exception:
            profile = migrate_from_legacy_config()
            save_profile(profile, default_path)
    else:
        profile = migrate_from_legacy_config()
        save_profile(profile, default_path)
    profile_manager = ProfileManager(profile)

    # 매크로 엔진
    region = get_game_region(GAME_WINDOW_TITLE)
    engine = MacroEngine(profile_manager=profile_manager, region=region)

    # 핫키 등록
    registrar = HotkeyRegistrar()
    registrar.bind(
        start_key=profile_manager.current.hotkeys.start,
        stop_key=profile_manager.current.hotkeys.stop,
        on_start=lambda: threading.Thread(target=engine.hunt_loop, daemon=True).start(),
        on_stop=engine.stop,
    )

    # 메인 스레드 대기
    keyboard.wait("esc")  # 또는 기존 종료 시그널
```

(정확한 main.py 변경 폭은 기존 main.py 구조 따라 조정. 핵심: `kb.add_hotkey(START_KEY, ...)` → `registrar.bind(profile_manager.current.hotkeys.start, ...)`)

- [ ] **Step 3: macro_ui.py에 HotkeyRegistrar 통합**

`MacroWindow.__init__` 안에 추가:
```python
        from hotkey_registrar import HotkeyRegistrar
        self.hotkey_registrar = HotkeyRegistrar()
        self.hotkey_registrar.bind(
            start_key=self.profile_manager.current.hotkeys.start,
            stop_key=self.profile_manager.current.hotkeys.stop,
            on_start=self._start_signal.emit,
            on_stop=self._stop_signal.emit,
        )
```

- [ ] **Step 4: `_build_hotkey_tab` 구현 (재바인딩 포함)**

```python
    def _build_hotkey_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QFormLayout
        w = QWidget()
        form = QFormLayout(w)
        hotkeys = self.profile_manager.current.hotkeys

        info = QLabel(
            "변경 시 즉시 재등록됩니다. (예: F5, F6, F1, Ctrl+Shift+H)"
        )
        form.addRow(info)

        self.hotkey_start = QLineEdit(hotkeys.start)
        self.hotkey_start.editingFinished.connect(self._on_hotkey_changed)
        form.addRow("시작 핫키:", self.hotkey_start)

        self.hotkey_stop = QLineEdit(hotkeys.stop)
        self.hotkey_stop.editingFinished.connect(self._on_hotkey_changed)
        form.addRow("중지 핫키:", self.hotkey_stop)

        return w

    def _on_hotkey_changed(self):
        new_start = self.hotkey_start.text().strip() or "F5"
        new_stop = self.hotkey_stop.text().strip() or "F6"
        self.profile_manager.update_hotkeys(start=new_start, stop=new_stop)
        # 즉시 재바인딩
        try:
            self.hotkey_registrar.rebind(new_start, new_stop)
            self._append_log("INFO", f"핫키 재등록: 시작={new_start}, 중지={new_stop}")
        except Exception as e:
            self._append_log("ERROR", f"핫키 재등록 실패: {e}")
```

- [ ] **Step 5: 수동 검증**

UI 실행 → 단축키 탭에서 시작 키를 F7로 변경 → F7 누르면 매크로 시작 (재시작 없이). F6 → F8 변경도 즉시 반영.

- [ ] **Step 6: 커밋**

```bash
git add hotkey_registrar.py macro_ui.py main.py
git commit -m "feat: 단축키 탭 + HotkeyRegistrar — 즉시 재바인딩 (main.py도 profile 사용)"
```

---

### Task 14: 프로필 탭 — 저장/불러오기/내보내기/가져오기

**Files:**
- Modify: `macro_ui.py` (프로필 탭)

- [ ] **Step 1: `_build_profile_tab` 본격 구현**

```python
    def _build_profile_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QFormLayout
        w = QWidget()
        l = QVBoxLayout(w)

        # 현재 프로필 표시
        self.profile_name_label = QLabel(f"현재: {self.profile_manager.current.name}")
        l.addWidget(self.profile_name_label)

        # 프로필 목록 드롭다운
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("프로필 전환:"))
        self.profile_combo = QComboBox()
        self._refresh_profile_list()
        self.profile_combo.activated.connect(self._on_profile_combo_select)
        row1.addWidget(self.profile_combo)
        l.addLayout(row1)

        # 저장 / 다른 이름으로 저장
        row2 = QHBoxLayout()
        btn_save = QPushButton("현재 프로필 저장")
        btn_save.clicked.connect(self._on_profile_save)
        btn_save_as = QPushButton("다른 이름으로 저장")
        btn_save_as.clicked.connect(self._on_profile_save_as)
        row2.addWidget(btn_save)
        row2.addWidget(btn_save_as)
        l.addLayout(row2)

        # 가져오기 / 내보내기
        row3 = QHBoxLayout()
        btn_import = QPushButton("가져오기 (JSON)")
        btn_import.clicked.connect(self._on_profile_import)
        btn_export = QPushButton("내보내기 (JSON)")
        btn_export.clicked.connect(self._on_profile_export)
        row3.addWidget(btn_import)
        row3.addWidget(btn_export)
        l.addLayout(row3)

        # 공장 초기화
        btn_reset = QPushButton("공장 초기화 (default 재생성)")
        btn_reset.clicked.connect(self._on_profile_reset)
        l.addWidget(btn_reset)

        l.addStretch()
        return w

    def _refresh_profile_list(self):
        import glob
        self.profile_combo.clear()
        files = glob.glob("profiles/*.json")
        for f in files:
            self.profile_combo.addItem(os.path.splitext(os.path.basename(f))[0])

    def _on_profile_combo_select(self):
        name = self.profile_combo.currentText()
        path = f"profiles/{name}.json"
        if not os.path.exists(path):
            return
        try:
            new_profile = load_profile(path)
            self.profile_manager.replace(new_profile)
            self.profile_name_label.setText(f"현재: {name}")
            self._reload_all_tabs()
            self._append_log("INFO", f"프로필 전환: {name}")
        except Exception as e:
            self._append_log("ERROR", f"프로필 로딩 실패: {e}")

    def _on_profile_save(self):
        name = self.profile_manager.current.name
        path = f"profiles/{name}.json"
        save_profile(self.profile_manager.current, path)
        self._append_log("INFO", f"프로필 저장: {path}")

    def _on_profile_save_as(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "다른 이름으로 저장", "프로필 이름:")
        if not ok or not name.strip():
            return
        import dataclasses
        renamed = dataclasses.replace(self.profile_manager.current, name=name.strip())
        self.profile_manager.replace(renamed)
        save_profile(renamed, f"profiles/{name.strip()}.json")
        self._refresh_profile_list()
        self.profile_name_label.setText(f"현재: {name.strip()}")
        self._append_log("INFO", f"프로필 저장: {name.strip()}")

    def _on_profile_import(self):
        path, _ = QFileDialog.getOpenFileName(self, "JSON 가져오기", "", "JSON (*.json)")
        if not path:
            return
        try:
            imported = load_profile(path)
            target = f"profiles/{imported.name}.json"
            save_profile(imported, target)
            self.profile_manager.replace(imported)
            self._refresh_profile_list()
            self.profile_name_label.setText(f"현재: {imported.name}")
            self._reload_all_tabs()
            self._append_log("INFO", f"프로필 가져옴: {imported.name}")
        except Exception as e:
            self._append_log("ERROR", f"가져오기 실패: {e}")

    def _on_profile_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "JSON 내보내기",
            f"{self.profile_manager.current.name}.json",
            "JSON (*.json)"
        )
        if not path:
            return
        save_profile(self.profile_manager.current, path)
        self._append_log("INFO", f"프로필 내보냄: {path}")

    def _on_profile_reset(self):
        from hunt_profile import migrate_from_legacy_config
        default = migrate_from_legacy_config()
        save_profile(default, "profiles/default.json")
        self.profile_manager.replace(default)
        self._refresh_profile_list()
        self.profile_name_label.setText("현재: default")
        self._reload_all_tabs()
        self._append_log("INFO", "default 프로필 재생성")

    def _reload_all_tabs(self):
        """
        프로필 변경 후 모든 탭 위젯의 표시값 갱신.
        Codex Minor 7 반영: QSignalBlocker로 setValue 시 발생하는 valueChanged
        시그널을 차단해 불필요한 profile.update_*() 재호출 방지.
        """
        from PyQt6.QtCore import QSignalBlocker

        # 몬스터 탭 (테이블 재구성이라 시그널 차단 불필요)
        self._refresh_monster_list()

        # 전투 탭 — setValue 호출이 valueChanged 신호를 쏘면 update_combat이
        # 다시 호출되어 race 발생. QSignalBlocker로 묶어서 차단.
        c = self.profile_manager.current.combat
        with QSignalBlocker(self.combat_attack_interval):
            self.combat_attack_interval.setValue(c.attack_interval)
        with QSignalBlocker(self.combat_miss_max):
            self.combat_miss_max.setValue(c.detect_miss_max)
        with QSignalBlocker(self.combat_timeout):
            self.combat_timeout.setValue(c.target_timeout)

        # 스킬 탭 (테이블 재구성)
        self._refresh_skill_table()

        # 물약 탭
        p = self.profile_manager.current.potion
        with QSignalBlocker(self.potion_hp_enabled):
            self.potion_hp_enabled.setChecked(p.hp_enabled)
        with QSignalBlocker(self.potion_hp_threshold):
            self.potion_hp_threshold.setValue(int(p.hp_threshold * 100))
        self.potion_hp_threshold_label.setText(f"{int(p.hp_threshold*100)}%")
        with QSignalBlocker(self.potion_hp_key):
            self.potion_hp_key.setValue(p.hp_key_scancode)
        with QSignalBlocker(self.potion_cooldown):
            self.potion_cooldown.setValue(p.cooldown)

        # 단축키 탭
        h = self.profile_manager.current.hotkeys
        with QSignalBlocker(self.hotkey_start):
            self.hotkey_start.setText(h.start)
        with QSignalBlocker(self.hotkey_stop):
            self.hotkey_stop.setText(h.stop)
```

- [ ] **Step 2: 수동 검증**

- 다른 이름으로 저장 → profiles/ 폴더에 새 파일 생성
- 가져오기 → 외부 JSON 로드 후 모든 탭 갱신
- 공장 초기화 → 기본값 복원

- [ ] **Step 3: 커밋**

```bash
git add macro_ui.py
git commit -m "feat: 프로필 탭 — 저장/불러오기/가져오기/내보내기/공장초기화"
```

---

### Task 15: config.py에 deprecation 경고

**Files:**
- Modify: `config.py`

- [ ] **Step 1: 사용자 튜닝 값들 위에 deprecation 안내 주석 추가**

`config.py`에서 다음 섹션들 위에 주석 한 줄 추가:

```python
# ════════════════════════════════════════════════════════════════════
# DEPRECATION (Phase 1 마이그레이션) — 아래 값들은 profile_manager가
# 사용. config.py 직접 수정은 첫 실행 시 default.json 생성에만 영향.
# 이미 default.json이 있으면 이 값들은 무시됨.
# Phase 2/3 후 완전 제거 예정.
# ════════════════════════════════════════════════════════════════════
```

해당 섹션:
- `ATTACK_INTERVAL`, `DEFAULT_DELAY`, `MIN_CLICK_INTERVAL` 위
- `LOOT_*` 섹션 위
- `POTION_*` 섹션 위
- `START_KEY`, `STOP_KEY` 위

- [ ] **Step 2: 커밋**

```bash
git add config.py
git commit -m "docs: config.py 사용자 튜닝 값들에 Phase 1 deprecation 안내"
```

---

### Task 16: 수동 통합 테스트

**Files:** 없음 (사람이 실행)

- [ ] **Step 1: 매크로 실행**

```bash
python macro_ui.py
```

- [ ] **Step 2: 첫 실행 시 default.json 자동 생성 확인**

```bash
ls profiles/
```

기대: `default.json` 존재. 내용은 기존 config.py 값과 일치.

- [ ] **Step 3: 6 탭 모두 위젯 정상 표시 확인**

각 탭 클릭 → 위젯이 보이고 기본값이 채워졌는지

- [ ] **Step 4: 설정 변경 → 저장 → 재시작 → 값 유지 확인**

전투 탭에서 attack_interval을 0.30으로 변경 → "현재 프로필 저장" → 앱 종료 → 재실행 → 0.30 표시 확인

- [ ] **Step 5: 매크로 시작 → 변경된 값 반영 확인**

attack_interval=0.30으로 변경 후 F5 → 로그에서 공격 간격이 더 길어졌는지

- [ ] **Step 6: 스킬 자동 사용 확인**

스킬 탭에서 `auto_use_interval=5.0`로 등록 → F5 → 로그에 5초마다 "스킬 사용: ..." 라인 발생

- [ ] **Step 7: 프로필 전환 확인**

"다른 이름으로 저장" → "원거리.json" → 파라미터 변경 → 드롭다운에서 default로 전환 → 원래 값 복원 확인

- [ ] **Step 8: 회귀 검증 (기존 동작)**

default 프로필로 사냥 사이클 정상 (몬스터 감지/공격/픽업 모두 작동)

---

### Task 17: 단위 테스트 전체 실행 + 최종 정리

**Files:** 없음

- [ ] **Step 1: 모든 단위 테스트 실행**

```bash
pytest tests/ -v
```

기대: 모든 테스트 통과 (~59개 = 25 기존 + 9 hunt_profile 1 + 4 hunt_profile 2 + 7 hunt_profile 3 + 7 profile_manager + 7 skill_manager)

- [ ] **Step 2: import 검증**

```bash
python -c "from hunt_profile import migrate_from_legacy_config; from profile_manager import ProfileManager; from skill_manager import SkillManager; from macro_engine import MacroEngine; print('all imports OK')"
```

- [ ] **Step 3: git log로 작업 내역 확인**

```bash
git log --oneline 6aaca41..HEAD
```

기대: Task 1~15 대응 커밋 ~20개 (Task 6 분할로 +3, Task 13 HotkeyRegistrar로 +1)

---

## 자체 점검 (스펙 커버리지)

| 스펙 항목 | 구현 Task |
|---|---|
| 7개 frozen dataclass (HuntProfile, MonsterEntry 등) | Task 1 |
| JSON 직렬화 + schema_version 검증 | Task 2 |
| Legacy config → default profile 마이그레이션 | Task 3 |
| ProfileManager atomic 교체 | Task 4 |
| SkillManager N초 간격 자동 발동 | Task 5 |
| MacroEngine.__init__ profile_manager 주입 | Task 6a |
| MacroEngine._loot_items profile.loot 사용 | Task 6b |
| MacroEngine._check_and_use_potion profile.potion 사용 | Task 6c |
| MacroEngine.hunt_loop 사이클당 profile 1회 스냅샷 + skill.tick (Codex Major 3) | Task 6d |
| MonsterTracker profile_provider — confidence/hp_offset/roi_expand (Codex Major 4) | Task 7 |
| QTabWidget 6 탭 골격 + 손상 JSON 백업 (Codex Critical 2) | Task 8 |
| 몬스터 탭 (등록/삭제/임계값) | Task 9 |
| 전투 탭 (attack_interval, miss_max, timeout, click_method) | Task 10 |
| 스킬 탭 (다중 등록 + 키 캡처 + 활성 토글) | Task 11 |
| 물약 탭 (HP 임계값/키, MP 자리만) | Task 12 |
| 스킬 탭 KeyCaptureLineEdit (QLineEdit 상속, modifier 차단 — Codex Major 5) | Task 11 |
| 단축키 탭 + HotkeyRegistrar 즉시 재바인딩 (Codex Critical 1) | Task 13 |
| 프로필 탭 (저장/불러오기/가져오기/내보내기/공장초기화) + QSignalBlocker (Codex Minor 7) | Task 14 |
| config.py deprecation 경고 | Task 15 |
| 수동 통합 테스트 | Task 16 |
| 단위 테스트 회귀 + 최종 검증 | Task 17 |

---

## 변경 이력

- **2026-05-01 v1**: 초안 작성 (17 Task)
- **2026-05-01 v2 (Codex 리뷰 반영)**:
  - **Critical 1**: HotkeyRegistrar 컴포넌트 추가 + main.py 수정 → Task 13에 통합 (시그니처/동작 재바인딩)
  - **Critical 2**: 손상된 default.json은 `.broken_<timestamp>` 백업 + 경고 다이얼로그 → Task 8 확장 + 테스트 2개 추가
  - **Major 3**: Task 6 분할 (6a/6b/6c/6d), `hunt_loop` 사이클당 profile 1회 스냅샷 후 헬퍼에 인자로 전달
  - **Major 4**: monster.hp_bar_offset_y, loot.roi_expand_ratio를 Phase 1에서 실제 와이어링 (이전엔 모델만 있고 사용 안 함) → Task 7 확장
  - **Major 5**: KeyCaptureLineEdit를 QLineEdit 직접 상속으로 재설계 + modifier-only/scan=0 차단 → Task 11 위젯 코드 교체
  - **Major 6**: macro_engine 리팩터를 6a→6b→6c→6d 4 Task로 분할 (회귀 위험 분산)
  - **Minor 7**: `_reload_all_tabs`에 QSignalBlocker 적용 → Task 14 확장
  - 총 Task 수: 17 → 20
