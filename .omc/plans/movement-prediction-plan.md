# 몬스터 이동 보정 개선 계획

## 문제 정의

현재 `find_and_track()` → `click()` 사이에 몬스터 이동을 보정하는 로직이 없음.
- `capture_screen()` + `detect_wolves()` (멀티스케일 템플릿 매칭 5스케일 × 8템플릿) = 약 50~200ms 소요
- 이 시간 동안 몬스터가 이동하면 클릭이 빗나감

## 현재 코드 흐름 (문제점)

```
find_and_track():
  frame = capture_screen()        # ~5ms
  detect_wolves(frame)            # ~50-200ms (멀티스케일 매칭)
  return (cx, cy)                 # 이미 과거 위치

hunt_loop():
  pos = find_and_track()          # 과거 위치 반환
  click(pos)                      # 몬스터는 이미 이동했음
  sleep(0.3 + random)             # 다음 반복까지 대기
```

## 후보 방식 비교

### 방식 A: 속도 벡터 기반 선행 예측 (Velocity Lead Prediction)

**원리:** 연속 프레임에서 몬스터 위치 변화를 추적하여 이동 속도(vx, vy)를 계산하고, 클릭 시점에 `predicted_pos = detected_pos + velocity * processing_delay`로 보정.

**장점:**
- 등속 이동 몬스터에 매우 효과적
- 추가 캡처 불필요 (기존 데이터 활용)
- 연산 비용 거의 없음

**단점:**
- 방향 전환 시 오예측 (관성 기반이므로)
- 최소 2프레임 이상 위치 이력 필요 (첫 감지 시 사용 불가)
- 속도 추정이 부정확하면 오히려 더 빗나감

**구현 복잡도:** 낮음

### 방식 B: ROI 기반 클릭 직전 재감지 (Pre-Click ROI Re-detection)

**원리:** 전체 프레임 감지 후, 클릭 직전에 마지막 감지 위치 주변 ROI만 빠르게 재캡처+매칭하여 현재 위치로 갱신.

**장점:**
- 실제 현재 위치를 사용 (예측이 아닌 관측)
- ROI가 작으므로 매칭 속도 매우 빠름 (~5-15ms)
- 방향 전환에도 강건

**단점:**
- 추가 캡처 1회 (mss grab ~3-5ms)
- 몬스터가 ROI를 벗어나면 실패
- 여전히 미세한 지연 존재

**구현 복잡도:** 중간

### 방식 C: 하이브리드 (속도 예측 + ROI 검증)

**원리:** 속도 벡터로 예측 위치를 계산하고, 그 예측 위치 중심의 ROI에서 재감지하여 검증/보정.

**장점:**
- 속도 예측으로 ROI 중심을 이동 방향으로 이동시켜 ROI 이탈 방지
- 재감지로 최종 위치 정확도 보장
- 두 방식의 장점 결합

**단점:**
- 구현 복잡도 높음
- 두 시스템 모두 유지보수 필요
- 이 프로젝트 규모에 과도할 수 있음

**구현 복잡도:** 높음

### 방식 D: 파이프라인 최적화 (지연 시간 최소화)

**원리:** 템플릿 매칭 자체를 빠르게 만들어 감지-클릭 간 지연을 최소화.
- 스케일 수 축소 (5 → 3)
- 이전 감지 위치 주변 우선 탐색
- 그레이스케일 전용 매칭 (컬러 대신)

**장점:**
- 코드 변경 최소
- 부작용 없음

**단점:**
- 감지 정확도 저하 가능
- 근본적 해결이 아님 (지연이 줄어도 0은 아님)

**구현 복잡도:** 낮음

## 추천: 방식 A + D 조합

**이유:**
1. 이 게임의 몬스터는 대부분 등속 직선 이동 (랜덤 방향 전환은 저빈도)
2. 속도 예측은 연산 비용이 거의 없고, 기존 `find_and_track()` 루프에 자연스럽게 통합
3. 파이프라인 최적화로 지연 자체를 줄이면 예측 오차도 줄어듦
4. ROI 재감지(방식 B)는 fallback으로 나중에 추가 가능

## 상세 구현 계획

### 1단계: MonsterTracker에 위치 이력 + 속도 추정 추가

```python
# monster_tracker.py에 추가할 상태
self._position_history = []       # [(cx, cy, timestamp), ...]
self._velocity = (0.0, 0.0)      # (vx, vy) px/sec
self._max_history = 5             # EMA 계산용 최근 N개

def _update_velocity(self, cx, cy):
    """위치 이력을 갱신하고 EMA 기반 속도 벡터를 계산."""
    now = time.time()
    self._position_history.append((cx, cy, now))

    # 최근 N개만 유지
    if len(self._position_history) > self._max_history:
        self._position_history = self._position_history[-self._max_history:]

    # 최소 2개 이상 있어야 속도 계산 가능
    if len(self._position_history) < 2:
        self._velocity = (0.0, 0.0)
        return

    # EMA 방식: 최근 측정에 더 높은 가중치
    vx_sum, vy_sum, weight_sum = 0.0, 0.0, 0.0
    for i in range(1, len(self._position_history)):
        prev = self._position_history[i - 1]
        curr = self._position_history[i]
        dt = curr[2] - prev[2]
        if dt <= 0:
            continue
        weight = i  # 최근일수록 높은 가중치
        vx_sum += (curr[0] - prev[0]) / dt * weight
        vy_sum += (curr[1] - prev[1]) / dt * weight
        weight_sum += weight

    if weight_sum > 0:
        self._velocity = (vx_sum / weight_sum, vy_sum / weight_sum)
```

### 2단계: find_and_track()에서 예측 좌표 반환

```python
def find_and_track(self):
    t_start = time.time()
    frame = capture_screen(region=self.region)
    # ... 기존 감지 로직 ...

    # 감지된 원본 좌표
    cx, cy = bbox 중심 계산

    # 속도 갱신
    self._update_velocity(cx, cy)

    # 처리 시간 측정
    processing_time = time.time() - t_start

    # 선행 보정: 처리 시간만큼 앞으로 예측
    vx, vy = self._velocity
    pred_cx = cx + vx * processing_time
    pred_cy = cy + vy * processing_time

    # 화면 경계 클램프
    pred_cx = max(0, min(pred_cx, screen_width))
    pred_cy = max(0, min(pred_cy, screen_height))

    return (int(pred_cx), int(pred_cy)), TRACK_OK
```

### 3단계: config.py에 관련 설정 추가

```python
# 이동 예측 설정
PREDICTION_ENABLED = True         # 이동 예측 활성화
PREDICTION_HISTORY_SIZE = 5       # 속도 계산용 위치 이력 수
PREDICTION_MAX_OFFSET = 50        # 최대 보정 거리 (px). 과도한 보정 방지
```

### 4단계: 파이프라인 최적화 (선택)

- `detect_wolves()` 스케일을 `(0.85, 1.0, 1.15)` 3단계로 축소
- 추적 중일 때는 마지막 감지 위치 주변 ROI만 우선 탐색

## 수정 대상 파일

| 파일 | 변경 내용 |
|------|----------|
| `monster_tracker.py` | 위치 이력, 속도 추정, 예측 좌표 계산 추가 |
| `config.py` | `PREDICTION_*` 설정 상수 추가 |
| `macro_engine.py` | 변경 없음 (인터페이스 동일) |

## 리스크

1. **과도한 보정**: 속도 추정 오차가 크면 오히려 더 빗나감 → `PREDICTION_MAX_OFFSET`으로 제한
2. **정지 몬스터**: 속도 = 0이면 보정 없음 → 기존과 동일하게 동작
3. **급격한 방향 전환**: EMA 특성상 반응 지연 → 짧은 이력(5개)으로 최소화
