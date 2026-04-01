# 몬스터 이동 보정 개선 계획 v2

> Codex CLI + Architect 리뷰 반영. 원본 A+D → **B+D로 변경**.

## 문제 재정의

원본 계획의 진단 "감지-클릭 간 50-200ms 지연"은 불완전함.

**실제 전체 루프 지연 분석:**
```
find_and_track()     ~55-205ms  (캡처 5ms + 감지 50-200ms)
click()              ~80-130ms  (moveTo 50ms + down/up 30-80ms)
attack_interval      ~300-450ms (0.3s + random 0-0.15s)
────────────────────────────────
총 루프 사이클        ~435-785ms
```

**진짜 병목:** `attack_interval` 300-450ms가 전체 지연의 60% 이상 차지.
속도 예측으로 감지 시간(50-200ms)만 보정해도 attack_interval 동안의 이동은 보정 불가.

## 최종 추천: B + D

### 선택 근거

| 기준 | B+D | A+D (기각) |
|------|-----|-----------|
| attack_interval 보정 | O (클릭 직전 재감지) | X (감지 시점만 보정) |
| 첫 감지 시 동작 | O (재감지는 이력 불필요) | X (속도=0, 보정 없음) |
| 방향 전환 대응 | O (실측 기반) | X (관성 기반 오예측) |
| 타겟 전환 시 오염 | 없음 | 이전 몬스터 속도 오염 위험 |
| 기존 코드 재활용 | `_verify_tracking()` 활용 | 신규 구현 필요 |
| 추가 비용 | 캡처 1회 ~5ms | 거의 없음 |

## 구현 단계

### 1단계: 파이프라인 최적화 (D)

**1-1. 스케일 축소**

`monster_tracker.py:92` 수정:
```python
# 변경 전
scales=(0.8, 0.9, 1.0, 1.1, 1.2)  # 5개

# 변경 후
scales=(0.9, 1.0, 1.1)  # 3개 — 매칭 횟수 40→24 (40% 감소)
```

**1-2. 추적 중 ROI 우선 탐색**

`find_and_track()`에서 `self.tracking=True`일 때 `last_bbox` 주변만 먼저 탐색:
```python
def _detect_in_roi(self, frame, last_bbox, pad_ratio=1.0):
    """
    마지막 감지 위치 주변 ROI에서만 빠르게 재탐색.
    전체 프레임 대비 ~5-15ms로 완료.

    Args:
        frame: BGR 전체 프레임
        last_bbox: (x, y, w, h) 마지막 감지 영역
        pad_ratio: bbox 크기 대비 패딩 비율 (1.0 = bbox 크기만큼 확장)

    Returns:
        (x, y, w, h) 또는 None
    """
    x, y, w, h = last_bbox
    pad_x = int(w * pad_ratio)
    pad_y = int(h * pad_ratio)

    roi_x1 = max(0, x - pad_x)
    roi_y1 = max(0, y - pad_y)
    roi_x2 = min(frame.shape[1], x + w + pad_x)
    roi_y2 = min(frame.shape[0], y + h + pad_y)

    roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]
    if roi.size == 0:
        return None

    templates = _load_templates(self.template_dir)
    best_score = 0
    best_result = None

    for fpath, tmpl_color, tmpl_gray in templates:
        # 단일 스케일(1.0)만 사용 — ROI에서는 스케일 변동 적음
        if tmpl_color.shape[0] > roi.shape[0] or tmpl_color.shape[1] > roi.shape[1]:
            scale = min(roi.shape[0] / tmpl_color.shape[0],
                        roi.shape[1] / tmpl_color.shape[1]) * 0.9
            if scale < 0.3:
                continue
            tmpl_resized = cv2.resize(tmpl_color,
                                      (int(tmpl_color.shape[1] * scale),
                                       int(tmpl_color.shape[0] * scale)))
        else:
            tmpl_resized = tmpl_color

        if tmpl_resized.shape[0] > roi.shape[0] or tmpl_resized.shape[1] > roi.shape[1]:
            continue

        result = cv2.matchTemplate(roi, tmpl_resized, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= self.confidence and max_val > best_score:
            best_score = max_val
            tw, th = tmpl_resized.shape[1], tmpl_resized.shape[0]
            # ROI 좌표 → 프레임 좌표로 변환
            best_result = (roi_x1 + max_loc[0], roi_y1 + max_loc[1], tw, th)

    return best_result
```

`find_and_track()` 수정:
```python
def find_and_track(self):
    frame = capture_screen(region=self.region)
    if frame is None:
        return None, TRACK_NOT_FOUND

    # 타겟 생존 판정
    if self.tracking:
        alive_reason = self._check_target_alive(frame)
        if alive_reason != TRACK_OK:
            self._abandon_target()
            return None, alive_reason

    # 추적 중이면 ROI 우선 탐색 (빠름)
    bbox = None
    if self.tracking and self.last_bbox is not None:
        bbox = self._detect_in_roi(frame, self.last_bbox, pad_ratio=1.0)
        if bbox:
            log.debug(f"ROI 재탐색 성공: ({bbox[0]},{bbox[1]})")

    # ROI 실패 시 전체 프레임 탐색 (기존 로직)
    if bbox is None:
        bbox = self._detect_nearest_available(frame=frame)

    # ... 이하 기존 로직 동일 ...
```

### 2단계: 클릭 직전 ROI 재감지 (B) — 핵심 개선

**새 메서드: `refine_position()`**

`monster_tracker.py`에 추가:
```python
def refine_position(self):
    """
    클릭 직전 호출. 마지막 감지 위치 주변 ROI만 빠르게 재캡처+매칭하여
    몬스터의 현재 위치를 반환. (~5-15ms)

    Returns:
        (center_x, center_y) 또는 None (재감지 실패 시)
    """
    if self.last_bbox is None:
        return None

    frame = capture_screen(region=self.region)
    if frame is None:
        return None

    refined_bbox = self._detect_in_roi(frame, self.last_bbox, pad_ratio=1.5)
    if refined_bbox is None:
        return None

    cx = refined_bbox[0] + refined_bbox[2] // 2
    cy = refined_bbox[1] + refined_bbox[3] // 2

    # region 오프셋 보정
    if self.region:
        cx += self.region[0]
        cy += self.region[1]

    # last_bbox 갱신
    self.last_bbox = refined_bbox
    log.debug(f"위치 보정: ({cx}, {cy})")
    return (cx, cy)
```

**`macro_engine.py` 수정:**
```python
if pos and reason == TRACK_OK:
    # 클릭 직전 위치 보정 (~10ms)
    refined = self.tracker.refine_position()
    target = refined if refined else pos
    click(target[0], target[1], method=self.click_method)
    log.info(f"공격: ({target[0]}, {target[1]})"
             + (f" (보정됨, 원본: {pos})" if refined else ""))
    time.sleep(attack_interval + random.uniform(0, 0.15))
```

### 3단계: config.py 설정 추가

```python
# ══════════════════════════════════════════════
# 이동 보정 설정
# ══════════════════════════════════════════════
PRECLICK_REFINE_ENABLED = True    # 클릭 직전 ROI 재감지 활성화
PRECLICK_ROI_PAD_RATIO = 1.5     # ROI 패딩 비율 (bbox 크기 대비)
TRACKING_ROI_PAD_RATIO = 1.0     # 추적 중 ROI 우선 탐색 패딩 비율
```

## 수정 대상 파일

| 파일 | 변경 내용 |
|------|----------|
| `monster_tracker.py` | `_detect_in_roi()`, `refine_position()` 추가. `find_and_track()` ROI 우선 탐색. `detect_wolves()` 기본 스케일 축소 |
| `macro_engine.py` | `click()` 직전 `refine_position()` 호출 추가 |
| `config.py` | `PRECLICK_*`, `TRACKING_ROI_*` 설정 추가 |

## Fallback 전략

| 상황 | 동작 |
|------|------|
| ROI 재감지 성공 | 보정된 좌표로 클릭 |
| ROI 재감지 실패 (ROI 이탈) | 원래 감지 좌표로 클릭 (기존과 동일) |
| ROI 우선 탐색 실패 | 전체 프레임 재감지 (기존과 동일) |

## 향후 확장 (필요 시)

- 속도 예측(A)은 ROI 중심을 이동 방향으로 편향시키는 보조 용도로만 추가
- `attack_interval`을 줄이거나 대기 중 추적 유지하는 구조로 개선
- 클릭 랜덤 오프셋(±2px)을 공격 시에만 비활성화하는 옵션 추가
