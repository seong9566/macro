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


# ══════════════════════════════════════════════
# Legacy config.py → HuntProfile 마이그레이션
# ══════════════════════════════════════════════

def migrate_from_legacy_config() -> HuntProfile:
    """
    config.py의 현재 상수 값들을 읽어 default HuntProfile 생성.
    첫 실행 시 default.json이 없으면 이 함수 결과를 저장한다.
    """
    import config

    wolf = MonsterEntry(
        name="wolf",
        template_dir="images",
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
            mp_enabled=False,
            mp_threshold=0.3,
            mp_key_scancode=3,
            cooldown=config.POTION_COOLDOWN,
        ),
        skills=(),
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
