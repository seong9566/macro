# Hunt Profile 기반 매크로 재구성 — Phase 1 설계

- **작성일**: 2026-05-01
- **작성자**: Claude (with seong9566)
- **상태**: 초안
- **관련 브랜치**: `feat/transparent-monster-detection`
- **선행 스펙**: `2026-05-01-item-pickup-design.md` (아이템 자동 줍기)

---

## 1. 개요

현재 매크로는 동작 파라미터(공격 간격, 감지 임계값, 물약 키, HP 임계값 등)가 모두 `config.py`에 하드코딩되어 있다. 일반 사용자는 코드 편집 없이는 자신의 환경(키 바인딩, 게임 설정, 캐릭터 클래스)에 맞춰 조정할 수 없다.

본 스펙은 **HuntProfile** 데이터 모델과 **탭형 설정 UI**를 도입하여, 사용자가 매크로 GUI에서 모든 동작을 직접 설정·저장·전환할 수 있게 만든다. 이는 향후 3단계 재구성의 1단계(기반 작업).

### 3단계 재구성 전체 그림

| 단계 | 범위 | 결과 |
|---|---|---|
| **Phase 1 (본 스펙)** | HuntProfile + 탭형 UI + config 이전 | 사용자가 GUI로 모든 동작 설정 |
| **Phase 2** | ML 기반 다중 몬스터 검출 (YOLO) | 템플릿 의존 제거, 다양한 몬스터 |
| **Phase 3** | 전투 전략(근접/원거리) + 다단계 물약 | 클래스별 운영 + 정교한 생존 |

## 2. 목표 / 비목표

### 목표
- `config.py`의 사용자 튜닝 가치가 있는 값을 **HuntProfile JSON**으로 이전
- macro_ui에 **탭형 설정 패널** 추가 (6개 탭)
- 프로필 **저장/불러오기/내보내기/가져오기** 기능
- 기존 동작 100% 회귀 없음 (default.json이 현재 상수 그대로 가짐)
- **스킬 다중 등록 + 단순 자동 사용**(N초 간격) 기능 추가

### 비목표 (Phase 2/3로 이연)
- ML 기반 객체 검출 (Phase 2)
- 원거리 공격 모드, 스킬 로테이션, 조건부 발동 (Phase 3)
- MP 자동 소비 (Phase 3)
- 다단계 HP 임계값 (예: 50%·30%·10%) (Phase 3)
- 프로필 간 자동 전환 / 시간대별 프로필 (향후)

## 3. 핵심 설계

### 3.1 HuntProfile 데이터 모델

`hunt_profile.py` (신규):

```python
@dataclass(frozen=True)
class MonsterEntry:
    name: str                      # 표시명, 예: "wolf"
    template_dir: str              # 템플릿 폴더 (images/wolf 등)
    detect_confidence: float       # 0.0~1.0
    tracking_confidence: float     # ROI 재탐색용
    hp_bar_offset_y: int           # bbox 상단 기준 (음수 = 위)


@dataclass(frozen=True)
class CombatConfig:
    attack_interval: float
    detect_miss_max: int
    target_timeout: float
    click_method: str              # "sendinput" | "directinput" | "mousekeys"


@dataclass(frozen=True)
class PotionConfig:
    hp_enabled: bool
    hp_threshold: float            # 0.0~1.0
    hp_key_scancode: int
    mp_enabled: bool               # Phase 1: 자리만, 동작은 Phase 3
    mp_threshold: float
    mp_key_scancode: int
    cooldown: float                # 동일 물약 재사용 대기


@dataclass(frozen=True)
class SkillEntry:
    name: str                      # 표시명, 예: "분노", "버프"
    key_scancode: int              # 키 스캔코드
    auto_use_interval: float       # 초 단위, 0이면 자동 사용 안 함
    enabled: bool


@dataclass(frozen=True)
class HotkeyConfig:
    start: str                     # 예: "F5"
    stop: str                      # 예: "F6"


@dataclass(frozen=True)
class LootConfig:
    enabled: bool
    visual_enabled: bool
    delay_after_kill: float
    snapshot_max_age: float
    diff_threshold: int
    # ... 기타 LOOT_* 들


@dataclass(frozen=True)
class HuntProfile:
    """프로필 전체 — frozen으로 atomic 교체."""
    schema_version: int
    name: str                      # 프로필 표시명
    monsters: tuple[MonsterEntry, ...]
    combat: CombatConfig
    potion: PotionConfig
    skills: tuple[SkillEntry, ...]
    hotkeys: HotkeyConfig
    loot: LootConfig
```

**왜 frozen + tuple**: combat_snapshot 패턴과 동일. UI 스레드에서 프로필 교체 시 엔진 스레드는 동시 안전하게 읽음. List가 아닌 tuple을 쓴 이유도 동일 (불변성 보장).

### 3.2 프로필 JSON 스키마

`profiles/default.json` (예시):

```json
{
  "schema_version": 1,
  "name": "default",
  "monsters": [
    {
      "name": "wolf",
      "template_dir": "images/wolf",
      "detect_confidence": 0.55,
      "tracking_confidence": 0.40,
      "hp_bar_offset_y": -20
    }
  ],
  "combat": {
    "attack_interval": 0.15,
    "detect_miss_max": 4,
    "target_timeout": 15.0,
    "click_method": "sendinput"
  },
  "potion": {
    "hp_enabled": true,
    "hp_threshold": 0.5,
    "hp_key_scancode": 2,
    "mp_enabled": false,
    "mp_threshold": 0.3,
    "mp_key_scancode": 3,
    "cooldown": 3.0
  },
  "skills": [
    {
      "name": "분노",
      "key_scancode": 33,
      "auto_use_interval": 30.0,
      "enabled": true
    }
  ],
  "hotkeys": {
    "start": "F5",
    "stop": "F6"
  },
  "loot": {
    "enabled": true,
    "visual_enabled": true,
    "delay_after_kill": 0.20,
    "snapshot_max_age": 8.0,
    "diff_threshold": 30,
    "min_blob_area": 30,
    "max_blob_area": 2500,
    "max_distance_ratio": 1.5,
    "max_total_diff_ratio": 0.6,
    "after_click_delay": 0.3,
    "press_count": 2,
    "press_interval": 0.10,
    "key_scancode": 57,
    "corpse_mask_ratio": 1.0,
    "roi_expand_ratio": 1.0
  }
}
```

스캔코드는 정수로 저장 (UI에서 표시할 때 키 라벨로 변환). schema_version으로 향후 마이그레이션 가능.

### 3.3 프로필 저장소

```
profiles/
├── default.json     ← 첫 실행 시 자동 생성 (현재 config.py 값 그대로)
├── 근접_늑대.json   ← 사용자 커스텀
└── 원거리_보스.json
```

위치는 프로젝트 루트의 `profiles/`. 현재 매크로의 다른 폴더(`images/`, `logs/`, `debug_loot/`)와 동일한 패턴.

### 3.4 프로필 라이프사이클

```
[앱 시작]
  └─ ProfileManager.load_default()
       └─ profiles/default.json 없으면? → migrate_from_config()으로 생성
       └─ load → frozen HuntProfile 객체 생성
       └─ ProfileManager.current = profile

[사용자가 UI에서 변경]
  └─ ProfileManager.update_potion(...)  ← 새 frozen 객체 빌드
       └─ ProfileManager.current 통째 교체 (atomic)
       └─ ProfileManager.save_to_disk(path)

[엔진 스레드]
  └─ profile = self.profile_manager.current  ← atomic 읽기
  └─ delay = profile.combat.attack_interval
  ...
```

**핵심**: 엔진 스레드는 `current` 참조를 한 번 읽고 로컬 변수로 사용. UI 스레드가 동시에 교체해도 race-free (CPython GIL + frozen dataclass).

### 3.5 config.py 마이그레이션 전략

이전 단계:
1. `hunt_profile.py`에 `migrate_from_legacy_config()` 함수 추가 — 현재 `config.py` 값들을 읽어 default.json 생성
2. 첫 실행 시 default.json 없으면 자동 호출
3. 코드는 점진적으로 `from config import X` → `engine.profile.X` 로 변경
4. 모든 사용처 변경 후 `config.py`는 *deprecation 경고만* 출력 (Phase 1 종료 시점에 즉시 제거 안 함)
5. Phase 2/3 후 `config.py`에서 동적 값 완전 제거 (정적 상수만 남김)

이전 대상 vs 유지:

| 카테고리 | Phase 1에서 이전 | Phase 1에서 유지 |
|---|---|---|
| 사용자 튜닝 값 | `ATTACK_INTERVAL`, `DETECT_CONFIDENCE`, `LOOT_*`, `POTION_*`, `START_KEY`, `STOP_KEY` 등 | — |
| 코드 상수 | — | `UI_EXCLUDE_TOP/BOTTOM`, `BRIGHTNESS_REJECT_THRESHOLD`, `DETECT_SCALES`, `EDGE_CANNY_LOW/HIGH` 등 (게임 UI 좌표·성능 튜닝) |
| 키 매핑 표 | — | `CLICK_METHODS`, scan code 매핑 |

판단 기준: "사용자가 한 번이라도 만질 만한가?" → 이전. "코드 작성자만 이해 가능한가?" → 유지.

## 4. UI 설계 (탭별)

### 4.1 메인 윈도우 레이아웃

```
┌──────────────────────────────────────────────────┐
│ ☰ 매크로                                  [_][□][X] │
├──────────────────────────────────────────────────┤
│ 상태: 대기 중                  [F5 시작][F6 중지] │
│ HP: ████████░░ 80%  MP: ████░░░░░░ 30%           │
├──────────────────────────────────────────────────┤
│ ┌몬스터┬전투┬스킬┬물약┬단축키┬프로필┐           │
│ └──────┴────┴────┴────┴──────┴──────┘           │
│  (선택된 탭 내용)                                 │
└──────────────────────────────────────────────────┘
```

상단 상태/HP/MP 표시는 현재 macro_ui와 동일. 하단이 6 탭으로 변경.

### 4.2 탭별 내용

**몬스터 탭** (현재 기능 + 그룹화)
- 몬스터 카드 리스트 (각 몬스터 = 하나의 카드)
- 카드 안: 이름, 템플릿 폴더, detect_confidence 슬라이더, HP바 오프셋
- "몬스터 추가" 버튼 → 새 폴더 생성 + 빈 엔트리 추가
- 몬스터 선택 → 해당 폴더의 PNG 미리보기 + "이미지 추가" / "이미지 삭제"

**전투 탭**
- attack_interval (슬라이더 0.05~1.0초)
- detect_miss_max (스피너 1~10)
- target_timeout (스피너 5~60초)
- click_method (라디오 버튼 3개)

**스킬 탭** (신규)
- 스킬 리스트 (테이블 또는 카드)
  - 컬럼: 이름 | 키 | 자동 사용 간격 | 활성화 (체크박스)
- "스킬 추가" 버튼 → 새 행 추가
- 키 캡처: 입력 박스 클릭 후 사용자가 키 누르면 자동 인식 (스캔코드 변환)
- 스킬 행 우클릭 → 삭제

**물약 탭**
- HP 자동 사용
  - 활성화 체크박스
  - 임계값 슬라이더 0~100% (현재 0.5)
  - 키 캡처 박스 (현재 scan 0x02 = "1")
- MP 자동 사용 (Phase 1: UI만, 동작은 Phase 3 — 안내 문구 표시)
  - 같은 구성, 비활성 회색 처리
- 쿨다운 (스피너 1~10초)

**단축키 탭**
- 시작 핫키 (캡처 박스, 기본 F5)
- 중지 핫키 (캡처 박스, 기본 F6)

**프로필 탭**
- 현재 프로필 이름 표시
- "다른 이름으로 저장" 버튼 → 파일 다이얼로그
- 프로필 목록 드롭다운 → 선택 시 즉시 적용
- "내보내기" / "가져오기" 버튼 → JSON 파일 입출력
- "공장 초기화" 버튼 → default.json 새로 생성

### 4.3 변경 적용 타이밍

옵션 A (즉시 반영): UI 위젯 변경 시 `ProfileManager.update_*()` 즉시 호출 → 엔진 다음 사이클부터 적용.
옵션 B (저장 시 반영): "저장" 버튼 누를 때만 적용.

**선택**: A. 사용자 친화적이며, frozen dataclass + atomic 교체로 안전. 단 "저장" 버튼은 디스크 영속화 (메모리 변경과 분리).

## 5. 스킬 자동 사용 메커니즘 (Phase 1 범위)

각 enabled=true 스킬은 `auto_use_interval` 초마다 키를 한 번 누른다.

```python
class SkillManager:
    def __init__(self, profile_provider):
        self.profile_provider = profile_provider
        self._last_use = {}  # skill_name → timestamp

    def tick(self):
        """매크로 사이클마다 호출. 도래한 스킬 발동."""
        profile = self.profile_provider.current
        now = time.time()
        for skill in profile.skills:
            if not skill.enabled or skill.auto_use_interval <= 0:
                continue
            last = self._last_use.get(skill.name, 0)
            if now - last >= skill.auto_use_interval:
                press_key(skill.key_scancode)
                self._last_use[skill.name] = now
                log.info(f"스킬 사용: {skill.name}")
```

`MacroEngine.hunt_loop()`의 매 사이클 시작에 `self.skill_manager.tick()` 호출.

**Phase 1 한계**:
- 단순 N초 주기 사용 (조건부, 콤보, 시너지 등은 Phase 3)
- 스킬은 "캐릭터 또는 자기 자신을 향함" 가정 (위치 클릭 안 함)
- 글로벌 쿨다운 무시

## 6. 데이터 흐름 / 모듈 구조

```
hunt_profile.py (신규)
  ├─ HuntProfile, MonsterEntry, CombatConfig, PotionConfig, SkillEntry, HotkeyConfig, LootConfig (모두 frozen)
  ├─ load_profile(path) → HuntProfile
  ├─ save_profile(profile, path)
  └─ migrate_from_legacy_config() → HuntProfile  (default.json 자동 생성용)

profile_manager.py (신규)
  └─ ProfileManager
       ├─ current: HuntProfile  (단일 atomic 교체점)
       ├─ load(name)
       ├─ save(name)
       ├─ list_profiles() → list[str]
       └─ update_*() 헬퍼들 (UI 위젯이 호출)

skill_manager.py (신규)
  └─ SkillManager
       ├─ tick() → 시간 도래 스킬 발동
       └─ reset() → 정지 시 cooldown 초기화

macro_engine.py (수정)
  ├─ self.profile_manager 보유
  ├─ self.skill_manager 보유
  ├─ hunt_loop()의 모든 config import → self.profile_manager.current.* 참조
  └─ 매 사이클 self.skill_manager.tick() 호출

monster_tracker.py (수정)
  └─ confidence/HP 오프셋 등을 profile에서 받기 (생성자에 profile_provider 주입)

macro_ui.py (대폭 수정)
  ├─ QTabWidget으로 6 탭 구성
  ├─ 각 탭은 별도 위젯 클래스 (MonsterTab, CombatTab, SkillTab, PotionTab, HotkeyTab, ProfileTab)
  └─ 모든 변경이 ProfileManager.update_*() 호출 → atomic 교체

config.py (점진 축소)
  ├─ 사용자 튜닝 값들 → 마이그레이션 후 deprecation 경고
  └─ 코드 상수만 유지
```

## 7. 실패 모드 / 엣지 케이스

| 상황 | 동작 |
|---|---|
| `profiles/default.json` 손상 | JSON 파싱 실패 → 백업으로 이동(`default.json.broken`) → migrate_from_legacy_config()로 재생성 → 사용자에게 경고 다이얼로그 |
| 사용자 추가 프로필이 schema_version 불일치 | 향후 버전 호환 마이그레이션 후크 호출. v1만 있는 현재는 경고 후 default.json 사용. |
| UI에서 잘못된 값 입력 (예: HP 임계값 -1) | 위젯 레벨 입력 검증 (슬라이더 min/max). 부정 입력 차단. |
| 키 캡처 시 modifier 키만 입력 (Shift, Ctrl) | 무시. 일반 키나 F-키만 허용. |
| 스킬 이름 중복 | UI에서 검증 (저장 버튼 비활성화 + 안내). |
| 매크로 실행 중 프로필 변경 | 다음 hunt_loop 사이클부터 새 프로필 적용 (atomic 교체로 인해 원자적). 진행 중 사이클은 이전 값 그대로 (로컬 변수). |

## 8. 테스트 전략

기존 pytest 인프라 활용. 신규 테스트:

- `tests/test_hunt_profile.py`
  - JSON 로드/저장 라운드트립
  - 손상된 JSON 처리
  - schema_version 불일치 처리
  - default 마이그레이션 결과 정합성 (기존 config.py 값과 일치)

- `tests/test_profile_manager.py`
  - atomic 교체 동작
  - update_*() 헬퍼들이 올바른 새 객체 생성
  - 다중 스레드 read-while-write 안전성

- `tests/test_skill_manager.py`
  - 시간 경과에 따른 발동
  - enabled=False 스킬 미발동
  - auto_use_interval=0 스킬 미발동
  - 쿨다운 정확도 (mock 시간 사용)

UI 테스트는 수동 (PyQt6 UI 테스트는 비용 큼). 핵심 로직만 단위 테스트.

## 9. 구현 단계 (개요)

> 상세 분해는 `writing-plans` 스킬에서 다룸. 큰 그림만:

1. `hunt_profile.py`: dataclass + JSON 직렬화 + 마이그레이션 (TDD)
2. `profile_manager.py`: 단일 인스턴스 패턴 + update 헬퍼들 (TDD)
3. `skill_manager.py`: tick 로직 (TDD with mocked time)
4. `macro_engine.py`: profile_manager 주입 + hunt_loop의 config 참조 모두 교체
5. `monster_tracker.py`: 생성자 인자 변경
6. `macro_ui.py`: QTabWidget으로 재구성 + 각 탭 위젯 작성 (단계적 — 한 탭씩)
7. config.py에 deprecation 경고 추가
8. 수동 통합 테스트: profile 변경이 매크로 동작에 즉시 반영되는지
9. 기존 동작 회귀 검증 (default 프로필로 사냥 사이클 정상)

## 10. Phase 2/3 연결점 (참고)

- **Phase 2 (ML 검출)**: `MonsterEntry`에 `model_class_id: int` 필드 추가. `template_dir` 대신 ML 모델 파일 경로 사용.
- **Phase 3 (전투 전략)**: `CombatConfig`에 `attack_strategy: "melee" | "ranged"` 필드 추가. Ranged 모드는 `attack_skill_scancode` 필드 사용 (스킬 등록과 연계 가능).
- **Phase 3 (다단계 물약)**: `PotionConfig`를 `tiers: list[PotionTier]` 형태로 확장. 각 tier에 (threshold, key, cooldown) 묶음.

스키마 변경은 schema_version 증가로 마이그레이션.

## 11. 위험 / 완화

| 위험 | 영향 | 완화 |
|---|---|---|
| macro_ui.py 대폭 변경으로 회귀 | UI 깨짐 | 한 탭씩 단계적 교체. 기존 시작/중지 버튼 우선 유지 |
| 프로필 마이그레이션 미스 → 동작 변경 | 사용자 신뢰 손상 | default.json 생성 후 기존 config.py 값과 1:1 비교 단위 테스트 |
| 스레드 race | 가끔 잘못된 값으로 동작 | frozen + atomic 교체 패턴 (combat_snapshot과 동일, 검증된 패턴) |
| JSON 직렬화/역직렬화 버그 | 프로필 저장 실패 | 라운드트립 단위 테스트로 강제 |
| Phase 1만 끝낸 상태에서 부분 기능 | 사용자 혼란 (MP 탭은 보이는데 동작 안 함) | UI에 "Phase 3에서 활성화" 안내 라벨 표시 |

## 12. 열린 질문

- **프로필 위치**: `profiles/` 프로젝트 루트 vs `~/.macro/profiles/` 사용자 디렉토리. 현재는 프로젝트 루트로 가되, 향후 사용자 분리 필요 시 환경 변수로 전환.
- **키 캡처 UX**: PyQt6의 `keyPressEvent`로 스캔코드 추출 — Windows API 호출 필요할 수 있음. 구현 단계에서 PoC.
- **Hot reload**: 사용자 변경이 즉시 반영(옵션 A) — UI 슬라이더 빈번 조작 시 깜빡임 우려. 100ms debounce 정도면 충분할 듯. 구현 시 결정.
- **import/export 포맷**: JSON만 vs YAML 추가 지원. YAML이 사람 친화적이지만 Python stdlib 아님. JSON 단일로 시작.

## 13. 변경 이력

- 2026-05-01 v1: 초안 작성. 사용자 인터뷰 반영(3단계 분할, ML 검출은 Phase 2로 분리, 프로필 단위 전투 모드, 탭형 UI). 스킬 등록 탭 추가.
