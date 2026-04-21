# 반투명 몬스터 감지 개선 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 나무 아래로 이동하여 반투명(semi-transparent)해진 몬스터도 감지 및 공격할 수 있도록 감지 파이프라인을 개선한다.

**Architecture:** 기존 그레이스케일 `TM_CCOEFF_NORMED` 매칭은 몬스터가 반투명해지면 픽셀 강도가 배경과 블렌딩되어 score가 급락한다. 이를 해결하기 위해 (1) 에지 기반 템플릿 매칭을 보조 감지기로 추가하고, (2) ROI 추적 중인 대상에 대해 낮은 confidence 임계값을 적용하며, (3) 반투명 상태의 템플릿 변형을 자동 생성하여 매칭 후보를 넓힌다.

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
| `config.py` | 수정 | 에지 매칭 및 반투명 감지 관련 설정 상수 추가 |
| `monster_tracker.py` | 수정 | 에지 기반 보조 감지 + ROI 추적 시 낮은 임계값 + 반투명 템플릿 변형 |

---

### Task 1: ROI 추적 시 낮은 confidence 임계값 적용

**목적:** 이미 추적 중인 대상이 나무 아래로 들어갔을 때, ROI 재탐색의 임계값을 낮춰서 반투명 상태에서도 유지하는 가장 간단한 개선.

**Files:**
- Modify: `config.py:10-16`
- Modify: `monster_tracker.py:430-489` (`_detect_in_roi` 메서드)

- [ ] **Step 1: config.py에 ROI 추적용 낮은 임계값 추가**

```python
# config.py — 이미지 인식 설정 섹션에 추가
TRACKING_CONFIDENCE = 0.40       # 추적 중 ROI 재탐색 임계값 (감지보다 낮게 — 반투명 대응)
```

`DETECT_CONFIDENCE = 0.55` 아래, `VERIFY_CONFIDENCE = 0.45` 아래에 추가.

- [ ] **Step 2: _detect_in_roi에서 추적 중 낮은 임계값 사용**

`monster_tracker.py`의 `_detect_in_roi()` 메서드에 `tracking` 파라미터를 추가:

```python
def _detect_in_roi(self, frame, last_bbox, pad_ratio=1.0, tracking=False):
    """
    마지막 감지 위치 주변 ROI에서만 빠르게 재탐색.

    Args:
        frame: BGR 전체 프레임
        last_bbox: (x, y, w, h) 마지막 감지 영역
        pad_ratio: bbox 크기 대비 패딩 비율
        tracking: True이면 추적 중 낮은 임계값 적용 (반투명 대응)
    """
    # 기존 코드 유지, confidence 결정 부분만 변경:
    min_confidence = TRACKING_CONFIDENCE if tracking else self.confidence
    # ... 이하 self.confidence → min_confidence 로 교체
```

`_detect_in_roi` 내부의 `if max_val >= self.confidence` 부분을 `if max_val >= min_confidence`로 변경.

- [ ] **Step 3: find_and_track에서 ROI 호출 시 tracking=True 전달**

`monster_tracker.py`의 `find_and_track()` 메서드에서 ROI 탐색 호출 부분:

```python
# 기존 (552-554행 근처):
if self.has_target and self.last_bbox is not None:
    roi_bbox = self._detect_in_roi(frame, self.last_bbox,
                                   pad_ratio=TRACKING_ROI_PAD_RATIO)

# 변경:
if self.has_target and self.last_bbox is not None:
    roi_bbox = self._detect_in_roi(frame, self.last_bbox,
                                   pad_ratio=TRACKING_ROI_PAD_RATIO,
                                   tracking=True)
```

- [ ] **Step 4: config.py에 TRACKING_CONFIDENCE import 추가**

`monster_tracker.py` 상단 import에 `TRACKING_CONFIDENCE` 추가:

```python
from config import (
    DETECT_CONFIDENCE, TRACKING_CONFIDENCE,
    TARGET_TIMEOUT, HP_CHECK_INTERVAL, HP_NO_CHANGE_MAX,
    # ... 기존 동일
)
```

- [ ] **Step 5: 수동 테스트 — 나무 아래 몬스터 추적 유지 확인**

```bash
python macro_ui.py
```

몬스터를 추적 중인 상태에서 나무 아래로 이동할 때:
- 기대: ROI 재탐색 score가 0.40 이상이면 추적 유지
- 로그에서 `ROI 재탐색 성공: ... score=0.4x` 확인

- [ ] **Step 6: 커밋**

```bash
git add config.py monster_tracker.py
git commit -m "feat: 추적 중 ROI 재탐색 임계값 분리 — 반투명 몬스터 유지"
```

---

### Task 2: 에지 기반 보조 감지 추가

**목적:** 반투명 몬스터는 픽셀 강도가 변하지만 **윤곽선(에지)**은 상대적으로 보존된다. Canny 에지 추출 후 에지 이미지끼리 매칭하면 반투명 상태에서도 감지율이 올라간다. 기존 그레이스케일 매칭에 실패한 경우에만 에지 매칭을 시도하는 2단계 파이프라인.

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
```

- [ ] **Step 2: monster_tracker.py에 에지 템플릿 캐시 추가**

`_template_cache`와 별도로 에지 템플릿을 캐싱:

```python
_edge_template_cache = {}  # {path: [(fpath, edge_img), ...]}


def _load_edge_templates(template_dir):
    """템플릿의 Canny 에지 버전을 로딩/캐시."""
    if template_dir in _edge_template_cache:
        return _edge_template_cache[template_dir]

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
    EDGE_CANNY_LOW, EDGE_CANNY_HIGH,
)
```

- [ ] **Step 4: _detect_in_roi에 에지 매칭 폴백 추가**

`_detect_in_roi()` 메서드 끝부분에, 그레이스케일 매칭 실패 시 에지 매칭 시도:

```python
def _detect_in_roi(self, frame, last_bbox, pad_ratio=1.0, tracking=False):
    # ... 기존 ROI 잘라내기 코드 동일 ...

    # 그레이스케일 ROI
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    # === 1단계: 기존 그레이스케일 매칭 ===
    min_confidence = TRACKING_CONFIDENCE if tracking else self.confidence
    templates = _load_templates(self.template_dir)
    best_score = 0
    best_result = None

    for fpath, tmpl_color, tmpl_gray in templates:
        th, tw = tmpl_gray.shape[:2]
        for scale in ROI_DETECT_SCALES:
            sh = max(1, int(th * scale))
            sw = max(1, int(tw * scale))
            if sh > roi_gray.shape[0] or sw > roi_gray.shape[1]:
                continue
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            tmpl_resized = cv2.resize(tmpl_gray, (sw, sh), interpolation=interp)
            result = cv2.matchTemplate(roi_gray, tmpl_resized, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val >= min_confidence and max_val > best_score:
                best_score = max_val
                best_result = (roi_x1 + max_loc[0], roi_y1 + max_loc[1], sw, sh)

    if best_result:
        log.debug(f"ROI 재탐색 성공: ({best_result[0]},{best_result[1]}) score={best_score:.3f}")
        return best_result

    # === 2단계: 에지 매칭 폴백 (반투명 대응) ===
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
        log.debug(f"ROI 에지 매칭 성공: ({best_edge_result[0]},{best_edge_result[1]}) score={best_edge_score:.3f}")
        return best_edge_result

    return None
```

- [ ] **Step 5: 수동 테스트**

```bash
python macro_ui.py
```

몬스터가 나무 아래로 들어갈 때:
- 기대: 그레이 매칭 실패 시 "ROI 에지 매칭 성공" 로그가 출력되며 추적 유지
- 확인: 로그에서 `ROI 에지 매칭 성공` 메시지가 나오는지

- [ ] **Step 6: 커밋**

```bash
git add config.py monster_tracker.py
git commit -m "feat: 에지 기반 보조 감지 추가 — 반투명 몬스터 폴백 매칭"
```

---

### Task 3: 반투명 템플릿 변형 자동 생성

**목적:** 게임의 반투명 렌더링을 시뮬레이션하여 alpha-blended 템플릿 변형을 자동 생성한다. 원본 템플릿을 평균 배경색과 여러 alpha 비율로 블렌딩하여, 반투명 상태의 몬스터와 직접 매칭할 수 있는 추가 템플릿을 확보한다.

**Files:**
- Modify: `config.py`
- Modify: `monster_tracker.py`

- [ ] **Step 1: config.py에 반투명 변형 설정 추가**

```python
# ══════════════════════════════════════════════
# 반투명 템플릿 변형 설정
# ══════════════════════════════════════════════
TRANSPARENT_VARIANTS_ENABLED = True  # 반투명 템플릿 자동 생성
TRANSPARENT_ALPHA_LEVELS = (0.5, 0.7)  # 블렌딩 비율 (1.0=원본, 0.5=50% 투명)
TRANSPARENT_BG_COLOR = (60, 80, 40)    # 블렌딩 대상 배경색 (BGR, 나무/풀 계열 녹색)
```

- [ ] **Step 2: monster_tracker.py import에 설정 추가**

```python
from config import (
    # ... 기존 ...
    TRANSPARENT_VARIANTS_ENABLED, TRANSPARENT_ALPHA_LEVELS, TRANSPARENT_BG_COLOR,
)
```

- [ ] **Step 3: _load_templates에 반투명 변형 생성 로직 추가**

`_load_templates()` 함수의 `_template_cache[template_dir] = templates` 직전에:

```python
    # 반투명 변형 자동 생성
    if TRANSPARENT_VARIANTS_ENABLED:
        bg = np.array(TRANSPARENT_BG_COLOR, dtype=np.float32)
        variants = []
        for fpath, tmpl_color, tmpl_gray in templates:
            for alpha in TRANSPARENT_ALPHA_LEVELS:
                blended_color = cv2.addWeighted(
                    tmpl_color, alpha,
                    np.full_like(tmpl_color, bg, dtype=np.uint8), 1.0 - alpha,
                    0
                )
                blended_gray = cv2.cvtColor(blended_color, cv2.COLOR_BGR2GRAY)
                variant_name = f"{os.path.basename(fpath)}@a{alpha:.1f}"
                variants.append((variant_name, blended_color, blended_gray))
        templates.extend(variants)
        log.debug(f"반투명 변형 {len(variants)}개 생성 (alpha: {TRANSPARENT_ALPHA_LEVELS})")
```

주의: `variants`의 첫 번째 요소가 `fpath` 대신 `variant_name`(문자열)이므로, 기존 `os.path.basename(fpath)` 호출 부분과 호환됨 (basename은 `/`가 없으면 원본 반환).

- [ ] **Step 4: 로딩 완료 로그 메시지 갱신**

```python
    log.info(f"몬스터 템플릿 {len(templates)}개 로딩 완료 (자동 반전 + 반투명 변형 포함)")
```

- [ ] **Step 5: 수동 테스트**

```bash
python macro_ui.py
```

시작 시 로그 확인:
- 기대: `몬스터 템플릿 24개 로딩 완료` (원본 8 + 반투명 변형 8×2=16)
- 나무 아래 몬스터 감지: 반투명 변형 템플릿과 매칭되어 score 향상

- [ ] **Step 6: 성능 영향 확인**

템플릿 수가 8→24개로 3배 증가하므로 전체 프레임 감지 시간 확인:
- 기존: ~30ms → 예상: ~90ms
- 감지 주기(`SEARCH_INTERVAL=0.5초`)보다 충분히 빠른지 확인
- 느리면 `TRANSPARENT_ALPHA_LEVELS`를 `(0.6,)` 하나로 줄여서 16개로 조정

- [ ] **Step 7: 커밋**

```bash
git add config.py monster_tracker.py
git commit -m "feat: 반투명 템플릿 변형 자동 생성 — 나무 아래 몬스터 감지율 향상"
```

---

### Task 4: 감지 실패 시 사망 판정 유예 횟수 조정

**목적:** 에지 매칭과 반투명 변형이 추가되었으므로, 그래도 감지 실패가 발생하면 이전보다 더 빠르게 사망 판정을 내려도 된다. 하지만 반투명 상태 진입/이탈 과도기에 1~2프레임 놓칠 수 있으므로 유예 횟수를 약간 늘린다.

**Files:**
- Modify: `config.py`
- Modify: `monster_tracker.py:244`

- [ ] **Step 1: config.py에 감지 실패 유예 횟수를 설정으로 분리**

```python
# 전투 판정 설정 섹션에 추가
DETECT_MISS_MAX = 4              # 연속 N회 감지 실패 시 사망 판정 (기존 3 → 4로 증가)
```

- [ ] **Step 2: monster_tracker.py에서 하드코딩 제거**

```python
# import에 추가
from config import (
    # ... 기존 ...
    DETECT_MISS_MAX,
)

# MonsterTracker.__init__에서:
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

1. **Task 1 (ROI 임계값 분리)** — 가장 간단하고 즉각적인 효과. 5분 내 완료 가능.
2. **Task 4 (유예 횟수 조정)** — Task 1과 함께 적용하면 반투명 상태 진입 시 추적 유지력 향상.
3. **Task 2 (에지 매칭)** — 그레이 매칭 실패 시 폴백. Task 1로도 부족할 때 핵심 역할.
4. **Task 3 (반투명 변형)** — 최초 감지(전체 프레임 탐색) 시에도 반투명 몬스터를 찾을 수 있게 함.

## 리스크

- **오탐 증가:** 임계값을 낮추면 배경 패턴이 몬스터로 오인될 가능성 증가 → ROI 영역에서만 낮은 임계값 적용하여 위험 최소화 (이미 추적 중인 대상 근처에서만)
- **성능 저하:** 템플릿 수 3배 증가 + 에지 연산 추가 → ROI 탐색은 작은 영역이라 영향 미미. 전체 프레임 탐색은 주기(0.5초)가 충분히 여유 있음
- **배경색 하드코딩:** `TRANSPARENT_BG_COLOR`가 실제 나무 배경과 다르면 효과 감소 → config에서 조정 가능하게 설정화
