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
