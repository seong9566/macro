# 반투명 몬스터 감지 개선 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 나무 아래로 이동하여 반투명(semi-transparent)해진 몬스터도 감지 및 공격할 수 있도록 감지 파이프라인을 개선한다.

**Architecture:** 기존 그레이스케일 `TM_CCOEFF_NORMED` 매칭은 몬스터가 반투명해지면 픽셀 강도가 배경과 블렌딩되어 score가 급락한다. 이를 해결하기 위해 (1) ROI 추적 중인 대상에 대해 낮은 confidence 임계값을 적용하고, (2) 에지 기반 템플릿 매칭을 보조 감지기로 추가하며, (3) 반투명 상태의 템플릿 변형을 ROI 전용으로 자동 생성하여 매칭 후보를 넓힌다.

**Tech Stack:** OpenCV (Canny edge, matchTemplate), NumPy, 기존 monster_tracker.py

---

## 문제 분석

현재 파이프라인의 한계:
- `detect_wolves()` → 그레이스케일 `TM_CCOEFF_NORMED` 사용
- 몬스터가 나무 아래로 들어가면 게임이 alpha blending으로 반투명 렌더링
- 픽셀 강도가 배경과 섞여 원본 템플릿과의 매칭 score가 `DETECT_CONFIDENCE(0.55)` 이하로 떨어짐
- 결과: 추적 중 감지 실패 → 사망 오판 → 타겟 해제

## 파일 구조

| 파일 | 변경 유형 | 역할 |
|------|----------|------|
| `config.py` | 수정 | 기존 `VERIFY_CONFIDENCE` 제거, 에지 매칭·반투명·유예 설정 추가 |
| `monster_tracker.py` | 수정 | ROI 낮은 임계값 + 에지 폴백 + 반투명 변형(ROI 전용) + 에지 연속 안전장치 |

---

### Task 1: ROI 추적 시 낮은 confidence 임계값 적용

**목적:** 이미 추적 중인 대상이 나무 아래로 들어갔을 때, ROI 재탐색의 임계값을 낮춰서 반투명 상태에서도 유지하는 가장 간단한 개선.

**Files:**
- Modify: `config.py:10-12`
- Modify: `monster_tracker.py:430-489` (`_detect_in_roi` 메서드)
- Modify: `monster_tracker.py:491-526` (`refine_position` 메서드)

- [ ] **Step 1: config.py에서 VERIFY_CONFIDENCE를 TRACKING_CONFIDENCE로 대체**

기존 `VERIFY_CONFIDENCE = 0.45`는 코드에서 사용되지 않으므로 제거하고, 역할을 명확히 한 `TRACKING_CONFIDENCE`로 대체:

```python
# config.py — 이미지 인식 설정 섹션
DETECT_CONFIDENCE = 0.55     # 몬스터 감지 임계값 (0.0 ~ 1.0)
TRACKING_CONFIDENCE = 0.40   # 추적 중 ROI 재탐색 임계값 (감지보다 낮게 — 반투명 대응)
SEARCH_INTERVAL = 0.5        # 이미지 탐색 주기 (초)
```

`VERIFY_CONFIDENCE = 0.45` 라인은 삭제.

- [ ] **Step 2: _detect_in_roi에서 추적 중 낮은 임계값 사용**

`monster_tracker.py`의 `_detect_in_roi()` 메서드 시그니처에 `tracking` 파라미터 추가, 내부 confidence 판정만 변경:

```python
def _detect_in_roi(self, frame, last_bbox, pad_ratio=1.0, tracking=False):
```

메서드 내부의 `if max_val >= self.confidence` 한 줄을 다음으로 교체:

```python
    min_confidence = TRACKING_CONFIDENCE if tracking else self.confidence
    # ...
    if max_val >= min_confidence and max_val > best_score:
```

**주의:** 메서드의 나머지 로직(ROI 잘라내기, 스케일 루프, 반환)은 변경하지 않음.

- [ ] **Step 3: find_and_track에서 ROI 호출 시 tracking=True 전달**

`monster_tracker.py`의 `find_and_track()` 메서드 (552-554행 근처):

```python
# 변경:
if self.has_target and self.last_bbox is not None:
    roi_bbox = self._detect_in_roi(frame, self.last_bbox,
                                   pad_ratio=TRACKING_ROI_PAD_RATIO,
                                   tracking=True)
```

- [ ] **Step 4: refine_position에서도 tracking=True 전달**

`refine_position()` (509-510행)도 추적 중인 대상에 대해 호출되므로 일관성 있게 적용:

```python
# 변경:
refined_bbox = self._detect_in_roi(frame, self.last_bbox,
                                   pad_ratio=PRECLICK_ROI_PAD_RATIO,
                                   tracking=True)
```

- [ ] **Step 5: config.py에 TRACKING_CONFIDENCE import 추가**

`monster_tracker.py` 상단 import에서 `DETECT_CONFIDENCE` 옆에 `TRACKING_CONFIDENCE` 추가:

```python
from config import (
    DETECT_CONFIDENCE, TRACKING_CONFIDENCE,
    TARGET_TIMEOUT, HP_CHECK_INTERVAL, HP_NO_CHANGE_MAX,
    # ... 기존 동일
)
```

- [ ] **Step 6: 로그에 감지 경로 태그 추가**

`_detect_in_roi`의 성공 로그에 경로 식별 태그 추가 (이후 Task 2에서 에지 태그도 추가):

```python
if best_result:
    log.debug(f"ROI 재탐색 성공 [그레이]: ({best_result[0]},{best_result[1]}) score={best_score:.3f}")
```

- [ ] **Step 7: 수동 테스트 — 나무 아래 몬스터 추적 유지 확인**

```bash
python macro_ui.py
```

몬스터를 추적 중인 상태에서 나무 아래로 이동할 때:
- 기대: ROI 재탐색 score가 0.40 이상이면 추적 유지
- 로그에서 `ROI 재탐색 성공 [그레이]: ... score=0.4x` 확인

- [ ] **Step 8: 커밋**

```bash
git add config.py monster_tracker.py
git commit -m "feat: 추적 중 ROI 재탐색 임계값 분리 — 반투명 몬스터 유지"
```

---

### Task 2: 에지 기반 보조 감지 추가

**목적:** 반투명 몬스터는 픽셀 강도가 변하지만 **윤곽선(에지)**은 상대적으로 보존된다. Canny 에지 추출 후 에지 이미지끼리 매칭하면 반투명 상태에서도 감지율이 올라간다. 기존 그레이스케일 매칭에 실패한 경우에만 에지 매칭을 시도하는 2단계 파이프라인.

**주의:** 이 Task는 `_detect_in_roi` 메서드 전체를 재작성하지 않는다. Task 1에서 변경한 코드 끝(`return None` 직전)에 에지 폴백 블록만 삽입한다.

**Files:**
- Modify: `config.py`
- Modify: `monster_tracker.py`

- [ ] **Step 1: config.py에 에지 감지 설정 추가**

```python
# ══════════════════════════════════════════════
# 에지 기반 보조 감지 설정 (반투명 몬스터 대응)
# ══════════════════════════════════════════════
EDGE_DETECT_ENABLED = True           # 에지 매칭 보조 감지 활성화
EDGE_DETECT_CONFIDENCE = 0.35        # 에지 매칭 임계값 (그레이보다 낮게)
EDGE_CANNY_LOW = 50                  # Canny 에지 하한 임계값
EDGE_CANNY_HIGH = 150                # Canny 에지 상한 임계값
EDGE_ONLY_MAX_COUNT = 5              # 에지 전용 연속 감지 최대 허용 횟수 (초과 시 추적 해제)
```

- [ ] **Step 2: monster_tracker.py에 에지 템플릿 캐시 추가**

`_template_cache` 선언부 아래에 에지 템플릿 캐시 추가:

```python
_edge_template_cache = {}  # {path: [(fpath, edge_img), ...]}


def _load_edge_templates(template_dir):
    """원본 템플릿(반투명 변형 제외)의 Canny 에지 버전을 로딩/캐시."""
    if template_dir in _edge_template_cache:
        return _edge_template_cache[template_dir]

    # 원본 템플릿만 사용 (반투명 변형의 에지는 불필요)
    templates = _load_templates(template_dir)
    edge_templates = []
    for fpath, tmpl_color, tmpl_gray in templates:
        edge = cv2.Canny(tmpl_gray, EDGE_CANNY_LOW, EDGE_CANNY_HIGH)
        edge_templates.append((fpath, edge))

    _edge_template_cache[template_dir] = edge_templates
    log.debug(f"에지 템플릿 {len(edge_templates)}개 생성")
    return edge_templates
```

`clear_template_cache()`에 `_edge_template_cache` 초기화도 추가:

```python
def clear_template_cache():
    global _template_cache, _edge_template_cache
    _template_cache = {}
    _edge_template_cache = {}
    log.info("템플릿 캐시 초기화")
```

- [ ] **Step 3: config.py 에지 설정 import 추가**

`monster_tracker.py` 상단 import에 추가:

```python
from config import (
    # ... 기존 동일 ...
    EDGE_DETECT_ENABLED, EDGE_DETECT_CONFIDENCE,
    EDGE_CANNY_LOW, EDGE_CANNY_HIGH, EDGE_ONLY_MAX_COUNT,
)
```

- [ ] **Step 4: _detect_in_roi 끝에 에지 폴백 블록만 삽입**

`_detect_in_roi()` 메서드에서 기존 그레이 매칭 성공 시 `return best_result` 이후, 최종 `return None` 직전에 에지 폴백 블록을 삽입:

```python
    # (기존 그레이 매칭 성공 시 여기서 return됨)
    if best_result:
        log.debug(f"ROI 재탐색 성공 [그레이]: ({best_result[0]},{best_result[1]}) score={best_score:.3f}")
        return best_result

    # === 에지 매칭 폴백 (그레이 실패 + 추적 중일 때만) ===
    if not EDGE_DETECT_ENABLED or not tracking:
        return None

    roi_edge = cv2.Canny(roi_gray, EDGE_CANNY_LOW, EDGE_CANNY_HIGH)
    edge_templates = _load_edge_templates(self.template_dir)
    best_edge_score = 0
    best_edge_result = None

    for fpath, tmpl_edge in edge_templates:
        th, tw = tmpl_edge.shape[:2]
        for scale in ROI_DETECT_SCALES:
            sh = max(1, int(th * scale))
            sw = max(1, int(tw * scale))
            if sh > roi_edge.shape[0] or sw > roi_edge.shape[1]:
                continue
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            tmpl_resized = cv2.resize(tmpl_edge, (sw, sh), interpolation=interp)
            result = cv2.matchTemplate(roi_edge, tmpl_resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= EDGE_DETECT_CONFIDENCE and max_val > best_edge_score:
                best_edge_score = max_val
                best_edge_result = (roi_x1 + max_loc[0], roi_y1 + max_loc[1], sw, sh)

    if best_edge_result:
        log.debug(f"ROI 재탐색 성공 [에지]: ({best_edge_result[0]},{best_edge_result[1]}) score={best_edge_score:.3f}")
        return best_edge_result

    return None
```

- [ ] **Step 5: 에지 전용 연속 감지 안전장치 추가**

몬스터 사망 후 에지 매칭이 다른 오브젝트(드롭 아이템 등)에 걸려 사망 판정이 안 되는 상황을 방지.

`MonsterTracker.__init__`에 카운터 추가:

```python
self._edge_only_count = 0            # 에지 전용 연속 감지 횟수
```

`_detect_in_roi`의 반환값으로는 에지 여부를 전달할 수 없으므로, 반환 시 인스턴스 플래그를 설정:

```python
# _detect_in_roi 내부, 에지 성공 시:
if best_edge_result:
    self._last_detect_was_edge = True
    log.debug(f"ROI 재탐색 성공 [에지]: ...")
    return best_edge_result

# 그레이 성공 시:
if best_result:
    self._last_detect_was_edge = False
    log.debug(f"ROI 재탐색 성공 [그레이]: ...")
    return best_result
```

`MonsterTracker.__init__`에 플래그 추가:

```python
self._last_detect_was_edge = False
self._edge_only_count = 0
```

`find_and_track()`에서 ROI 감지 성공 후 에지 안전장치 체크:

```python
# ROI 감지 성공 후 (bbox != None 이후):
if self._last_detect_was_edge:
    self._edge_only_count += 1
    if self._edge_only_count >= EDGE_ONLY_MAX_COUNT:
        log.warning(f"에지 전용 연속 {self._edge_only_count}회 → 신뢰도 낮음, 추적 해제")
        self._abandon_target()
        return None, TRACK_NOT_FOUND
else:
    self._edge_only_count = 0  # 그레이 매칭 성공 시 리셋
```

`_reset_combat_state()`에 리셋 추가:

```python
def _reset_combat_state(self):
    # ... 기존 ...
    self._edge_only_count = 0
    self._last_detect_was_edge = False
```

- [ ] **Step 6: 수동 테스트**

```bash
python macro_ui.py
```

몬스터가 나무 아래로 들어갈 때:
- 기대: 그레이 매칭 실패 시 `ROI 재탐색 성공 [에지]` 로그가 출력되며 추적 유지
- 기대: 에지 전용이 5회 연속되면 `에지 전용 연속 5회 → 신뢰도 낮음, 추적 해제` 로그와 함께 타겟 해제

- [ ] **Step 7: 커밋**

```bash
git add config.py monster_tracker.py
git commit -m "feat: 에지 기반 보조 감지 + 연속 에지 안전장치 추가"
```

---

### Task 3: 반투명 템플릿 변형 자동 생성 (ROI 전용)

**전제 조건:** Task 1+2 구현 후 실제 반투명 상태의 스크린샷을 2~3장 캡처하여, 원본 템플릿과의 score를 측정한다. Task 1+2만으로 충분히 감지되면 이 Task는 건너뛴다.

**목적:** 게임의 반투명 렌더링을 시뮬레이션하여 alpha-blended 템플릿 변형을 자동 생성한다. **성능 보호를 위해 ROI 재탐색(`_detect_in_roi`)에서만 사용하고, 전체 프레임 탐색(`detect_wolves`)에서는 원본 템플릿만 사용한다.**

**Files:**
- Modify: `config.py`
- Modify: `monster_tracker.py`

- [ ] **Step 1: 사전 검증 — 반투명 상태 score 측정**

매크로 UI를 실행하여 몬스터가 나무 아래에 있을 때의 실제 score를 로그에서 확인:
- Task 1의 `TRACKING_CONFIDENCE=0.40`으로 감지되는지?
- Task 2의 에지 폴백으로 감지되는지?
- 둘 다 실패하는 경우에만 이 Task 진행

- [ ] **Step 2: config.py에 반투명 변형 설정 추가**

```python
# ══════════════════════════════════════════════
# 반투명 템플릿 변형 설정 (ROI 전용)
# ══════════════════════════════════════════════
TRANSPARENT_VARIANTS_ENABLED = True  # 반투명 템플릿 자동 생성
TRANSPARENT_ALPHA_LEVELS = (0.5, 0.7)  # 블렌딩 비율 (1.0=원본, 0.5=50% 투명)
TRANSPARENT_BG_COLOR = (60, 80, 40)    # 블렌딩 대상 배경색 (BGR, 나무/풀 계열 녹색)
```

- [ ] **Step 3: monster_tracker.py에 ROI 전용 반투명 템플릿 로더 추가**

`_load_templates()`는 변경하지 않는다. 대신 별도 함수를 만들어 ROI에서만 사용:

```python
_transparent_template_cache = {}  # {path: [(name, color, gray), ...]}


def _load_transparent_templates(template_dir):
    """원본 템플릿의 반투명 변형을 생성/캐시 (ROI 전용)."""
    if template_dir in _transparent_template_cache:
        return _transparent_template_cache[template_dir]

    if not TRANSPARENT_VARIANTS_ENABLED:
        _transparent_template_cache[template_dir] = []
        return []

    templates = _load_templates(template_dir)
    bg = np.array(TRANSPARENT_BG_COLOR, dtype=np.uint8)
    variants = []

    for fpath, tmpl_color, tmpl_gray in templates:
        for alpha in TRANSPARENT_ALPHA_LEVELS:
            blended_color = cv2.addWeighted(
                tmpl_color, alpha,
                np.full_like(tmpl_color, bg), 1.0 - alpha,
                0
            )
            blended_gray = cv2.cvtColor(blended_color, cv2.COLOR_BGR2GRAY)
            variant_name = f"{os.path.basename(fpath)}@a{alpha:.1f}"
            variants.append((variant_name, blended_color, blended_gray))

    _transparent_template_cache[template_dir] = variants
    log.debug(f"반투명 변형 {len(variants)}개 생성 (alpha: {TRANSPARENT_ALPHA_LEVELS})")
    return variants
```

`clear_template_cache()`에도 초기화 추가:

```python
def clear_template_cache():
    global _template_cache, _edge_template_cache, _transparent_template_cache
    _template_cache = {}
    _edge_template_cache = {}
    _transparent_template_cache = {}
    log.info("템플릿 캐시 초기화")
```

- [ ] **Step 4: config.py import 추가**

```python
from config import (
    # ... 기존 ...
    TRANSPARENT_VARIANTS_ENABLED, TRANSPARENT_ALPHA_LEVELS, TRANSPARENT_BG_COLOR,
)
```

- [ ] **Step 5: _detect_in_roi에서 반투명 변형 템플릿도 매칭**

`_detect_in_roi`의 1단계 그레이 매칭 루프에서, 원본 템플릿 루프 이후 반투명 변형도 같은 방식으로 매칭:

```python
    # === 1단계: 그레이스케일 매칭 (원본 + 반투명 변형) ===
    min_confidence = TRACKING_CONFIDENCE if tracking else self.confidence
    templates = _load_templates(self.template_dir)

    # 추적 중이면 반투명 변형도 후보에 추가
    if tracking and TRANSPARENT_VARIANTS_ENABLED:
        transparent = _load_transparent_templates(self.template_dir)
        all_templates = list(templates) + list(transparent)
    else:
        all_templates = templates

    best_score = 0
    best_result = None

    for fpath, tmpl_color, tmpl_gray in all_templates:
        # ... 기존 매칭 루프 동일 ...
```

이렇게 하면 `detect_wolves()`(전체 프레임)에는 영향 없이 ROI 추적 시에만 반투명 변형을 사용.

- [ ] **Step 6: 수동 테스트**

```bash
python macro_ui.py
```

시작 시 로그 확인:
- 기대: `반투명 변형 16개 생성` (8 원본 × 2 alpha)
- 전체 프레임 탐색: 원본 8개만 사용 (성능 유지)
- ROI 추적: 원본 8 + 변형 16 = 24개 사용 (반투명 대응)

- [ ] **Step 7: 커밋**

```bash
git add config.py monster_tracker.py
git commit -m "feat: 반투명 템플릿 변형 ROI 전용 생성 — 전체 프레임 성능 보호"
```

---

### Task 4: 감지 실패 시 사망 판정 유예 횟수 설정화

**목적:** 하드코딩된 감지 실패 유예 횟수를 config로 분리하고, 반투명 과도기(나무 진입/이탈)에서 1~2프레임 놓치는 것을 허용하도록 3→4회로 증가.

**Files:**
- Modify: `config.py`
- Modify: `monster_tracker.py:244`

- [ ] **Step 1: config.py에 감지 실패 유예 횟수 설정 추가**

```python
# 전투 판정 설정 섹션에 추가
DETECT_MISS_MAX = 4              # 연속 N회 감지 실패 시 사망 판정 (기존 3 → 4로 증가)
```

- [ ] **Step 2: monster_tracker.py에서 하드코딩 제거**

import에 추가:

```python
from config import (
    # ... 기존 ...
    DETECT_MISS_MAX,
)
```

`MonsterTracker.__init__`에서:

```python
# 기존:
self._detect_miss_max = 3
# 변경:
self._detect_miss_max = DETECT_MISS_MAX
```

- [ ] **Step 3: 커밋**

```bash
git add config.py monster_tracker.py
git commit -m "feat: 감지 실패 유예 횟수 설정화 — 반투명 과도기 대응"
```

---

## 구현 우선순위

1. **Task 1 (ROI 임계값 분리 + VERIFY_CONFIDENCE 정리)** — 가장 간단하고 즉각적인 효과.
2. **Task 4 (유예 횟수 설정화)** — Task 1과 함께 적용하면 반투명 상태 진입 시 추적 유지력 향상.
3. **Task 2 (에지 매칭 + 안전장치)** — 그레이 매칭 실패 시 폴백. 에지 전용 연속 카운터로 오탐 방지.
4. **Task 3 (반투명 변형, ROI 전용)** — Task 1+2 실측 후 필요 시에만 진행. 전체 프레임 탐색 성능에 영향 없음.

## 리스크

- **오탐 증가:** 임계값을 낮추면 배경 패턴이 몬스터로 오인될 가능성 증가 → ROI 영역에서만 낮은 임계값 적용하여 위험 최소화
- **에지 매칭 오탐:** `EDGE_DETECT_CONFIDENCE=0.35`는 낮은 편 → 에지 전용 연속 5회 초과 시 추적 해제하는 안전장치로 방지
- **성능 저하:** 반투명 변형은 ROI 전용으로 분리하여 전체 프레임 탐색(8 템플릿)은 기존과 동일. ROI는 작은 영역이라 24개 템플릿도 ~15ms 내 완료
- **배경색 하드코딩:** `TRANSPARENT_BG_COLOR`가 실제 나무 배경과 다르면 효과 감소 → config에서 조정 가능. Task 3 전 사전 검증 단계로 실효성 확인
