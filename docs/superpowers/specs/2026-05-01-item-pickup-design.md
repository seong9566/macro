# 아이템 자동 줍기 설계 (Frame Diff 기반)

- **작성일**: 2026-05-01
- **작성자**: Claude (with seong9566)
- **상태**: 초안 (브레인스토밍 완료, 리뷰 대기)
- **관련 브랜치**: `feat/transparent-monster-detection`

---

## 1. 개요

현재 매크로는 몬스터 사망 판정 후 **그 자리에서 Spacebar만 2회 누르는** 방식으로 아이템을 줍는다 (`macro_engine.py::_loot_items`). 이는 캐릭터가 아이템에 인접해 있을 때만 동작하며, 드롭 위치가 캐릭터에서 떨어진 경우(이번 게임처럼 ±수십 픽셀 오프셋이 있는 경우) **줍지 못하고 사냥 사이클로 넘어간다**.

본 설계는 사망 판정 직후 **드롭된 아이템을 시각적으로 검출하여 그 좌표로 클릭**(`온라인삼국지2`의 클릭형 픽업)하여 자동 회수하는 기능을 추가한다.

## 2. 목표 / 비목표

### 목표
- 늑대 사망 직후 드롭된 아이템 위치를 자동으로 찾아 클릭한다
- 드롭이 없을 때(미드롭, 일격 미사살 후 분리 등)는 **클릭/대기 시간을 낭비하지 않는다**
- **아이템 종류와 무관**하게 동작한다 (게임/몬스터마다 별도 템플릿 등록 불필요)
- 기존 사냥 루프의 1초 이내 추가 지연만 발생

### 비목표 (이번 스펙 범위 밖)
- 아이템 필터링(특정 아이템만 줍기, 등급 분류) — 이후 스펙에서 다룸
- 인벤토리 가득 참 감지 — 별도 기능
- 멀티 아이템 동시 픽업 최적화 — v1은 아이템 1개 픽업 후 다음 사냥
- 다른 몬스터(늑대 외) 지원 — 현재 매크로 자체가 늑대 전용이므로 동일 범위 유지

## 3. 핵심 설계: Frame Diff (방식 D)

### 3.1 작동 원리

1. **베이스라인 캡처**: 마지막 공격 직전 프레임을 저장 (몬스터가 살아있는 상태)
2. **사망 판정**: 기존 `TRACK_KILLED` 시그널 사용 (변경 없음)
3. **사후 캡처**: 사망 판정 직후 새 프레임 캡처 (시체 + 가능하면 아이템)
4. **차분**: 베이스라인 ROI vs 사후 ROI 절대 차분 → 임계값 → 모폴로지 정리
5. **블롭 필터링**: 크기/위치 기준으로 "아이템스러운" 블롭만 추림
6. **클릭**: 가장 유력한 블롭 중심으로 1회 클릭 (없으면 스킵)
7. **폴백**: 기존 Spacebar 광역 픽업도 한 번 실행 (캐릭터 발 밑 드롭 보험)

### 3.2 ROI 및 마스킹 전략

차분 영역을 좁게 설정하는 게 오탐 방지의 핵심.

```
ROI = bbox 중심 기준 ±(bbox_w * LOOT_ROI_EXPAND_RATIO, bbox_h * LOOT_ROI_EXPAND_RATIO) 확장 영역
      (LOOT_ROI_EXPAND_RATIO=1.0 → bbox 크기의 3×3 = 9배 면적, ~150×150px 수준)
```

차분 결과에서 다음을 제외/필터:
- **시체 잔존 영역 마스킹**: bbox 안쪽은 시체가 사라지면서 큰 차분이 생기므로, 결과 mask에서 bbox 영역을 0으로 채워 무시. 마스킹 범위는 `LOOT_CORPSE_MASK_RATIO`(=1.0, bbox 전체)로 시작. 운영 후 0.7~1.2 범위에서 튜닝.
- **블롭 크기 필터**: `MIN_BLOB_AREA <= area <= MAX_BLOB_AREA` (기본 30~2500 px²)
- **위치 필터**: 블롭 중심이 bbox 중심에서 너무 멀면(`> LOOT_MAX_DISTANCE_RATIO × bbox 대각선`) 제외
- **이상치 차단**: 차분 픽셀 비율이 ROI 전체의 `LOOT_MAX_TOTAL_DIFF_RATIO` 초과 시 카메라/캐릭터 이동 의심 → 픽업 스킵

### 3.3 데이터 흐름 — 스냅샷 기반 설계

베이스라인은 **단일 원자적 스냅샷**으로 관리한다 (frame, bbox, region, timestamp가 같은 캡처에서 짝지어진 묶음). 이렇게 해야 다음 위험을 모두 피한다:
- `refine_position()`이 별도 캡처에서 bbox를 갱신할 때 frame ↔ bbox 짝 불일치
- 게임 창 이동/리사이즈로 region이 바뀌었는데 옛 region 기준 좌표가 남는 문제
- 사망 판정까지 시간 누적(`DETECT_MISS_MAX × 사이클`)으로 베이스라인이 너무 묵는 문제
- 엔진 스레드와 정지 스레드 사이의 부분 갱신 race

#### 스냅샷 자료구조

```python
@dataclass(frozen=True)
class CombatSnapshot:
    roi: np.ndarray              # 베이스라인 ROI (frame 전체가 아닌 잘라낸 부분만 — 메모리 절약)
    roi_origin: tuple[int, int]  # frame-local 기준 ROI 좌상단 (rx_local, ry_local)
    bbox: tuple[int, int, int, int]  # frame-local bbox (x, y, w, h)
    region: tuple[int, int, int, int]  # 캡처 시점의 게임 창 region (스크린)
    timestamp: float             # time.time() 캡처 시각
```

스냅샷은 frozen dataclass — **부분 갱신 불가, 항상 통째로 교체** (Python 참조 할당이 원자적이므로 락 없이도 race-free).

#### 흐름

```
[기존 사냥 루프]
MacroEngine.hunt_loop()
  └─ tracker.find_and_track() → (pos, TRACK_OK)
      └─ click(target) ── 클릭 직전 refine_position() 호출
            └─ refine_position() 내부에서 새 캡처 → bbox 갱신 →
               그 동일한 캡처/bbox/region/now()으로 self.combat_snapshot 갱신
               (즉 스냅샷은 refine_position 결과와 동기화. ROI만 잘라 저장)

tracker.find_and_track() → (None, TRACK_KILLED)
  └─ snapshot = self.tracker.combat_snapshot   # 스냅샷 atomic 읽기 (1회)
  └─ if snapshot is None: skip visual pickup, Spacebar만
  └─ if (now - snapshot.timestamp) > LOOT_SNAPSHOT_MAX_AGE: skip (너무 묵음)
  └─ if snapshot.region != self.region: skip (창 이동/리사이즈)
  └─ ItemPicker.try_pickup(snapshot, click_method=self.click_method)
        ├─ capture_screen(snapshot.region) → after 프레임 (region 일치 검증)
        ├─ after_roi = after[snapshot.roi_origin: + snapshot.roi.shape] 잘라내기
        ├─ _diff_and_find_blob(snapshot.roi, after_roi, snapshot.bbox) → click_pos | None
        ├─ if click_pos: click(click_pos)  (snapshot.region 기준 screen 좌표 변환)
        └─ return picked: bool

  └─ if not picked: press_key(SPACEBAR) × LOOT_PRESS_COUNT  (보험)
  └─ if picked: press_key(SPACEBAR) × 1  (다중 아이템 보조)
  └─ 다음 사냥으로 진행
```

#### 스냅샷 갱신 시점 — 핵심
- **스냅샷 갱신은 클릭 직전 `refine_position()` 호출 직후**에 수행 (가장 최신/정확한 bbox와 같은 캡처를 한 묶음으로 저장)
- `find_and_track()` 내부의 일반 감지 성공 시에도 갱신 (refine 안 한 경우 대비)
- 갱신 시 `roi`는 `frame[roi_y:roi_y+H, roi_x:roi_x+W].copy()`로 **ROI만 슬라이스 복사** (full frame copy 비용 회피)
- After 프레임은 `try_pickup()` 내부에서 새로 캡처

## 4. 컴포넌트 변경

### 4.1 신규 모듈: `item_picker.py`

```python
from dataclasses import dataclass
from typing import Optional
import numpy as np

@dataclass(frozen=True)
class CombatSnapshot:
    """베이스라인 스냅샷 — frame, bbox, region, time을 동일 캡처에서 묶음."""
    roi: np.ndarray                          # ROI 슬라이스 복사본 (BGR)
    roi_origin: tuple[int, int]              # frame-local ROI 좌상단 (rx, ry)
    bbox: tuple[int, int, int, int]          # frame-local bbox (x, y, w, h)
    region: tuple[int, int, int, int]        # 캡처 시점 게임 창 region
    timestamp: float                         # time.time()


def build_snapshot(frame, bbox, region, expand_ratio: float) -> Optional[CombatSnapshot]:
    """frame과 bbox에서 ROI를 잘라 스냅샷 생성. 경계 체크 실패 시 None."""
    ...


class ItemPicker:
    """프레임 차분 기반 아이템 위치 검출 + 클릭."""

    def try_pickup(self, snapshot: CombatSnapshot, current_region, click_method) -> bool:
        """
        Args:
            snapshot: 사망 직전 베이스라인 스냅샷
            current_region: 현재 게임 창 region (snapshot.region과 비교용)
            click_method: clicker.click()용 문자열

        Returns:
            True if 아이템 후보 클릭, False if 스킵 (없거나 안전장치 작동)

        스냅샷 유효성 검사:
            - snapshot.region == current_region (창 이동 검증)
            - now - snapshot.timestamp <= LOOT_SNAPSHOT_MAX_AGE
        실패 시 즉시 False 반환.
        """
        ...

    def _capture_after_roi(self, snapshot) -> Optional[np.ndarray]:
        """현재 화면을 캡처해 snapshot.roi_origin/shape에 맞춰 ROI만 잘라 반환."""
        ...

    def _compute_diff_mask(self, baseline_roi, after_roi) -> np.ndarray:
        """절대 차분 → 그레이스케일 → LOOT_DIFF_THRESHOLD → 모폴로지(open/close)."""
        ...

    def _mask_corpse_area(self, diff_mask, bbox_in_roi, ratio: float) -> np.ndarray:
        """bbox 영역(× ratio)을 마스크에서 0으로 칠해 시체 차분 제거."""
        ...

    def _find_item_blob(self, diff_mask, bbox_center_in_roi, max_dist) -> Optional[tuple[int, int]]:
        """크기·위치 필터 통과 컨투어 중 가장 큰/가까운 것 → ROI-local (cx, cy)."""
        ...

    def _is_outlier_diff(self, diff_mask) -> bool:
        """차분 픽셀 비율이 LOOT_MAX_TOTAL_DIFF_RATIO 초과면 True (카메라/캐릭터 이동 등)."""
        ...

    def _save_debug_image(self, snapshot, after_roi, diff_mask, click_pos):
        """LOOT_DEBUG_SAVE=True일 때만 호출. 4장 PNG 저장."""
        ...
```

설계 포인트:
- **ROI만 저장**: full frame `.copy()` 비용 회피 (~150×150px 사이즈로 메모리/시간 절약)
- **frozen dataclass**: 부분 갱신 불가 → 스레드 race-free (Python 참조 할당은 atomic)
- **유효성 게이트 3단**: snapshot 존재 / age 한도 / region 일치 — 하나라도 실패하면 즉시 스킵

### 4.2 수정: `monster_tracker.py`

- `MonsterTracker.__init__`에 `self.combat_snapshot: CombatSnapshot | None = None` 추가
- 스냅샷 갱신은 **반드시 frame과 bbox가 같은 캡처에서 나온 시점**에서만 수행:
  1. `find_and_track()`에서 일반 감지 성공 후 (frame=현재 캡처, bbox=방금 감지한 bbox)
  2. `refine_position()` 내부에서 새 캡처로 bbox를 갱신한 직후 (frame=refine 캡처, bbox=refine bbox)
  - 두 곳 모두 `self.combat_snapshot = build_snapshot(frame, bbox, self.region, LOOT_ROI_EXPAND_RATIO)`로 통째 교체
- 갱신 시 `frame` 전체가 아닌 ROI만 슬라이스 복사 (`build_snapshot` 내부에서 처리) → 사이클당 비용은 ~150×150×3 byte 복사 = 무시 가능
- `reset()`에서 `self.combat_snapshot = None`
- `_abandon_target()`에서도 스냅샷 무효화 (이전 대상 잔재 방지)
- 외부에서 `tracker.combat_snapshot`을 **단일 atomic 읽기로 1회만** 접근 (참조 카피 후 사용 → 락 불필요)

### 4.3 수정: `macro_engine.py`

- `__init__`에 `self.item_picker = ItemPicker()` 추가
- `_loot_items()`를 다음과 같이 재구성:
  ```python
  def _loot_items(self):
      if not LOOT_ENABLED:
          return

      time.sleep(LOOT_DELAY_AFTER_KILL + random.uniform(0, 0.05))

      # 1. 시각 기반 픽업 시도 (스냅샷 atomic 읽기)
      picked = False
      snapshot = self.tracker.combat_snapshot  # 한 번만 읽음 → 이후 일관성 보장
      if LOOT_VISUAL_ENABLED and snapshot is not None and self.region is not None:
          picked = self.item_picker.try_pickup(
              snapshot=snapshot,
              current_region=self.region,
              click_method=self.click_method,
          )
          if picked:
              log.info("아이템 픽업: 차분 기반 클릭 성공")
              time.sleep(LOOT_AFTER_CLICK_DELAY)

      # 2. Spacebar 보험 — 시각 픽업이 실패/스킵일 때 더 적극적으로,
      #    성공 시는 다중 아이템 보조용으로 1회만
      space_count = 1 if picked else LOOT_PRESS_COUNT
      for i in range(space_count):
          press_key(LOOT_KEY_SCANCODE)
          if i < space_count - 1:
              time.sleep(LOOT_PRESS_INTERVAL + random.uniform(0, 0.04))
      log.debug(f"Spacebar 보험 픽업 ×{space_count} (visual_picked={picked})")
  ```
- 사이클 비용 절감: 시각 픽업 성공 시 Spacebar 1회로 줄여 ~100ms 절약

### 4.4 수정: `config.py`

```python
# ══════════════════════════════════════════════
# 아이템 시각 기반 줍기 (Frame Diff)
# ══════════════════════════════════════════════
LOOT_VISUAL_ENABLED = True              # 차분 기반 픽업 활성화
LOOT_ROI_EXPAND_RATIO = 1.0             # bbox 크기 대비 ROI 확장 비율 (1.0=좌우상하 bbox 1개씩)
LOOT_CORPSE_MASK_RATIO = 1.0            # bbox 마스킹 비율 (1.0=bbox 전체 영역 무시 — 시체 차분 제거)
LOOT_DIFF_THRESHOLD = 30                # 차분 그레이값 임계값 (0~255)
LOOT_MIN_BLOB_AREA = 30                 # 최소 블롭 면적 (px²) — 노이즈 컷
LOOT_MAX_BLOB_AREA = 2500               # 최대 블롭 면적 (px²) — 큰 객체 컷
LOOT_MAX_DISTANCE_RATIO = 1.5           # bbox 중심에서 블롭 중심까지 허용 거리 (×bbox 대각선 길이)
LOOT_MAX_TOTAL_DIFF_RATIO = 0.4         # ROI 픽셀 대비 차분 비율 상한 (초과 시 카메라/캐릭터 이동 판단, 픽업 스킵)
LOOT_SNAPSHOT_MAX_AGE = 0.6             # 베이스라인 최대 허용 나이 (초). 초과 시 시각 픽업 스킵
LOOT_AFTER_CLICK_DELAY = 0.3            # 픽업 클릭 후 대기 (캐릭터 이동/픽업 애니)
LOOT_DEBUG_SAVE = False                 # 차분 디버그 이미지 저장 (튜닝용 — 부담 큼, 평시 False)
LOOT_DEBUG_SAMPLE_RATIO = 0.1           # 디버그 저장 샘플링 비율 (0.1=10%만 저장, 1.0=전부)
LOOT_DEBUG_DIR = "debug_loot"
```

기존 `LOOT_PRESS_COUNT=2`는 그대로 유지 (시각 픽업 실패 시 보험 역할 + 다중 아이템 대응). 운영 데이터 보고 1로 줄일지 결정.

## 5. 실패 모드 처리

| 상황 | 동작 |
|---|---|
| 드롭 없음 | 차분에서 유효 블롭 없음 → 시각 클릭 안 함 → Spacebar `LOOT_PRESS_COUNT`회. 추가 지연 ~50ms. |
| 일격 미사살 (몬스터가 안 죽음) | `TRACK_KILLED`가 안 나오므로 본 코드 미진입. 기존 추적 로직 유지. |
| 스냅샷 없음 (즉시 미감지로 사망 등 엣지) | `combat_snapshot is None` → 시각 픽업 스킵, Spacebar만. |
| 스냅샷 노화 (`age > LOOT_SNAPSHOT_MAX_AGE`) | 시각 픽업 스킵, Spacebar만. 사망 사이클이 비정상적으로 길어진 케이스. |
| 게임 창 이동/리사이즈 (`snapshot.region != current_region`) | 좌표 매핑 불일치 위험 → 시각 픽업 스킵, Spacebar만. |
| 차분에 다른 몬스터 진입 | 큰 블롭(`> MAX_BLOB_AREA`) → 필터 제외. 통과 시 위치 필터(`MAX_DISTANCE_RATIO`)로 추가 제외. |
| 캐릭터/카메라 이동으로 ROI 전체가 크게 변함 | 차분 픽셀이 ROI의 `LOOT_MAX_TOTAL_DIFF_RATIO` 초과 → "이상치"로 판단, 픽업 스킵. |
| 잘못된 위치 클릭 (오탐) | 캐릭터가 잠깐 이상한 곳으로 이동만 하고 사냥 재개. 누적 손해 작음. |
| 정지 핫키(F6) 도중 픽업 시도 | `combat_snapshot`은 immutable frozen dataclass — `_loot_items()` 시작 시 1회 atomic 읽기 후 로컬 변수 사용. `reset()`이 동시 호출되어도 이미 잡은 참조에 영향 없음. |

### 5.1 스레드 안전성

- 매크로는 main 스레드(핫키)와 daemon 스레드(`hunt_loop`)가 동시 동작
- `MonsterTracker.combat_snapshot`은 **frozen dataclass + 통째 교체 패턴** — Python의 참조 할당이 GIL 보장 하에 atomic이므로 락 불필요
- `reset()`이 `combat_snapshot = None`으로 바꾸기 전에 다른 스레드가 이미 참조를 잡았다면, 그 스레드는 **이전 스냅샷의 일관된 상태**(roi/bbox/region/timestamp 모두 동일 캡처)를 그대로 사용 → race-free
- `frame.copy()`로 ROI를 슬라이스 복사하므로 원본 frame이 GC되어도 스냅샷은 안전

## 5.2 성능 / 사이클 시간

| 단계 | 추가 비용 | 비고 |
|---|---|---|
| 매 사이클: 스냅샷 갱신 (ROI 슬라이스 복사) | < 1ms | ~150×150×3 byte numpy 슬라이스. 무시 가능. |
| 사망 시: after 캡처 | ~10~30ms | 기존 capture_screen과 동일. |
| 사망 시: ROI 차분 + 모폴로지 + 컨투어 | ~5~10ms | 작은 ROI라 부담 적음. |
| 사망 시: 클릭 1회 + delay | ~300ms | `LOOT_AFTER_CLICK_DELAY` 등. |
| 사망 시: Spacebar 1~2회 | ~100~200ms | 시각 성공 시 1회로 단축. |
| 사망 시: 디버그 PNG 저장 (옵션) | ~30~50ms × 4장 | `LOOT_DEBUG_SAVE`로만 활성, `LOOT_DEBUG_SAMPLE_RATIO`로 샘플링. |

총 사망당 추가 시간 ≈ **400~600ms** (디버그 끄고). 기존 `_loot_items` 대비 +200~400ms. 사용자 목표 "1초 이내" 만족.

## 6. 디버깅 / 검증

테스트 프레임워크가 없으므로 **수동 확인** 위주.

### 6.1 디버그 이미지 저장
- `LOOT_DEBUG_SAVE=True`로 켜면 사망 판정마다 다음 4장을 `debug_loot/{timestamp}_*.png`로 저장:
  - `01_baseline_roi.png` — 차분 입력 1
  - `02_after_roi.png` — 차분 입력 2
  - `03_diff_mask.png` — 임계값 마스크 (시체 마스킹 적용 후)
  - `04_decision.png` — 후보 블롭 + 클릭 좌표 시각화
- 운영 중 오탐/미감지 발생 시 해당 PNG로 임계값 튜닝

### 6.2 수동 검증 시나리오
1. 늑대 1마리 사냥 → 아이템 드롭 → 픽업 성공 확인 (인벤토리 변화)
2. 늑대 1마리 사냥 → 아이템 미드롭 (드롭율 게임 따라) → 클릭 안 하고 사냥 진행 확인
3. 일격 미사살 → 추적 계속 진행 확인 (픽업 코드 미진입)
4. 늑대 무리 한가운데서 사냥 → 다른 늑대가 ROI를 침범 → 오탐 없는지 확인
5. 캐릭터가 이동 중인 상태에서 사망 판정 → 캐릭터 자체의 차분이 ROI에 들어와 오탐 가능성 → 결과 관찰

### 6.3 튜닝 파라미터 우선순위
1. `LOOT_DIFF_THRESHOLD` (가장 영향 큼) — 너무 낮으면 노이즈, 너무 높으면 미감지
2. `LOOT_MIN_BLOB_AREA` — 풀/그림자 노이즈가 통과하면 상향
3. `LOOT_MAX_BLOB_AREA` — 다른 몬스터가 자주 잡히면 하향
4. `LOOT_ROI_EXPAND_RATIO` — 드롭 위치가 더 멀리도 나오면 상향

## 7. 구현 단계 (개요)

> 상세 단계 분해는 `writing-plans` 스킬에서 다룸. 여기는 큰 그림만.

1. `item_picker.py` 신규 작성: `CombatSnapshot` dataclass + `build_snapshot()` + `ItemPicker` 클래스
2. `config.py`에 `LOOT_*` 상수 추가 (시각 픽업 + 안전장치)
3. `monster_tracker.py`:
   - `combat_snapshot` 필드 추가
   - `find_and_track()` 감지 성공 분기에서 스냅샷 갱신
   - `refine_position()` 갱신 분기에서도 스냅샷 갱신 (frame/bbox 짝 일치 보장)
   - `reset()` / `_abandon_target()`에서 `combat_snapshot = None`
4. `macro_engine.py::_loot_items()` 재구성: 스냅샷 atomic 읽기 → 시각 픽업 시도 → Spacebar 보험
5. 디버그 옵션 켜고(`LOOT_DEBUG_SAVE=True`) 수동 테스트 → PNG 수집
6. 임계값 튜닝 우선순위: `LOOT_DIFF_THRESHOLD` → `LOOT_MIN_BLOB_AREA` → `LOOT_CORPSE_MASK_RATIO` → `LOOT_ROI_EXPAND_RATIO`
7. 디버그 옵션 끄고 안정 운영 확인

## 8. 향후 확장 (참고)

- **호버 검증 추가 (방식 E)**: 차분 후보 좌표에 마우스 잠깐 옮기고 툴팁 패턴 검출 → 진짜 아이템인지 검증. 정확도↑, 사이클 시간↑.
- **아이템 필터**: 호버 시 표시되는 이름 텍스트 OCR로 특정 아이템만 줍기.
- **인벤토리 가득 감지**: 인벤토리 UI에 흰 슬롯 0개일 때 픽업 자동 비활성화.
- **다른 몬스터 지원**: 현재 매크로의 늑대 전용 구조와 분리해 generic 사냥 모드 지원 시 본 픽업 로직 그대로 재사용 가능.

## 9. 열린 질문 (운영 후 결정)

- **`LOOT_DELAY_AFTER_KILL`(0.20초) 적절성**: 너무 짧으면 아이템이 아직 화면에 안 떴을 수 있음. 0.3~0.5초로 상향 검토.
- **`LOOT_SNAPSHOT_MAX_AGE`(0.6초) 적절성**: 사이클 시간(50~100ms × `DETECT_MISS_MAX=4` ≈ 200~400ms)을 충분히 커버하나, 게임 환경에 따라 조정 필요.
- **시체 마스크 비율(`LOOT_CORPSE_MASK_RATIO=1.0`)**: 늑대가 bbox를 다 채우지 않을 때 가장자리 차분이 잡힘. 운영 보고 1.0~1.2 사이 조정.
- **연속 사냥 시 캐릭터 위치 누적 변화**: 픽업 클릭 → 캐릭터 이동 → 다음 사냥 시작 시 캐릭터 위치가 변함. 다음 사망 시점의 차분 ROI에 영향 줄 수 있는지 모니터링.

## 10. 변경 이력

- **2026-05-01 v1**: 초안 작성
- **2026-05-01 v2 (Codex 리뷰 반영)**:
  - **Critical**: `frame`과 `last_bbox` 짝 불일치 위험 → `CombatSnapshot` frozen dataclass로 묶어 atomic 갱신
  - **Major**: 게임 창 region 변화 감지 → 스냅샷에 region 포함, 클릭 시 검증
  - **Major**: 베이스라인 노화 → `LOOT_SNAPSHOT_MAX_AGE` 추가, age 체크 시 스킵
  - **Major**: 스레드 race → frozen dataclass + 통째 교체로 락 없이 안전 (5.1절 신규)
  - **Major**: 성능 — full frame copy 회피, ROI만 슬라이스 복사. 디버그 PNG는 샘플링(`LOOT_DEBUG_SAMPLE_RATIO`)
  - **Minor**: config 상수와 본문 수치 일치, Spacebar 횟수 — 시각 성공 시 1회 / 실패 시 `LOOT_PRESS_COUNT`로 분기
