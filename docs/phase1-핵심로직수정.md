# Phase 1: 핵심 로직 수정 (HIGH 우선순위)

> **상태: 구현 완료** (Codex CLI 리뷰 반영)
> - 1-4 이미지 피라미드는 Codex 리뷰에 따라 Phase 2로 이관

## 목표
객체 인식 → 클릭의 정확도와 신뢰성을 확보한다.

---

## 1-1. 유령 클릭 제거

**문제:** 사망 판정 대기(3프레임) 동안 이미 사라진 위치를 계속 클릭 → NPC/아이템 오클릭 발생

**현재 코드:** `monster_tracker.py` `find_and_track()` — miss 시 마지막 위치로 `TRACK_OK` 반환

**수정 방안:**
```
감지 실패 시:
  1차: ROI 패딩 2배 확장(pad_ratio=3.0)으로 재탐색
  2차: 확장 ROI에서도 실패 → 즉시 전체 프레임 탐색
  3차: 전체 프레임에서도 실패 → 사망 판정 (TRACK_KILLED)
```

**수정 파일:**
- `monster_tracker.py` — `find_and_track()` 내 miss 처리 로직
- 마지막 위치 클릭 대신 확장 ROI → 전체 탐색 → 사망 판정 3단계

**검증:**
- 몬스터 사망 시 빈 공간 클릭이 0회인지 로그 확인
- 사망 후 즉시 아이템 줍기로 전환되는지 확인

---

## 1-2. 몬스터 HP바 색상 범위 수정

**문제:** `HP_BAR_COLOR_LOWER=(0,100,100)`, `HP_BAR_COLOR_UPPER=(80,255,255)` → H=0~80은 빨강~노랑~초록 전부 매칭 → 배경을 HP바로 오인

**수정 방안:**
```python
# config.py — 몬스터 HP바 전용 색상 (게임 내 실제 색상에 맞게 조정)
MONSTER_HP_COLOR_RANGES = [
    ((0, 100, 100), (10, 255, 255)),     # 빨간색 하위
    ((170, 100, 100), (180, 255, 255)),   # 빨간색 상위
    ((35, 100, 100), (85, 255, 255)),     # 초록색 (HP 많을 때)
]
```

**수정 파일:**
- `config.py` — HP바 색상 범위 분리
- `monster_tracker.py` — `_measure_hp_ratio()` — 다중 범위 OR 마스크 적용

**검증:**
- HP 변화 로그가 실제 게임 상황과 일치하는지 확인
- 살아있는 몬스터를 HP 미변화로 포기하는 경우가 줄었는지 확인

---

## 1-3. ROI 탐색에 소폭 멀티스케일 추가

**문제:** ROI 탐색은 원본 스케일 1개만 사용 → 몬스터 크기 변화 시 ROI 실패 → 느린 전체 탐색으로 전락

**수정 방안:**
```python
# monster_tracker.py — _detect_in_roi() 내부
ROI_SCALES = (0.95, 1.0, 1.05)  # 소폭 3단계

for scale in ROI_SCALES:
    tmpl_scaled = cv2.resize(tmpl_gray, (int(tw*scale), int(th*scale)))
    result = cv2.matchTemplate(roi_gray, tmpl_scaled, cv2.TM_CCOEFF_NORMED)
    ...
```

**수정 파일:**
- `config.py` — `ROI_DETECT_SCALES = (0.95, 1.0, 1.05)` 추가
- `monster_tracker.py` — `_detect_in_roi()` 내부 루프에 스케일 적용

**검증:**
- ROI 재탐색 성공률이 향상되었는지 로그의 "ROI 재탐색 성공" 빈도 확인
- 전체 프레임 탐색 빈도가 줄었는지 확인

---

## 1-4. 전체 프레임 탐색 속도 4배 개선

**문제:** 8템플릿 × 3스케일 = 24회 matchTemplate → 120~360ms

**수정 방안:** 이미지 피라미드 — 프레임을 50% 축소 후 탐색, 좌표를 2배 복원

```python
# monster_tracker.py — detect_wolves() 내부
# 1단계: 축소 프레임에서 후보 탐색
small_frame = cv2.resize(frame_gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
small_tmpl = cv2.resize(tmpl_gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
result = cv2.matchTemplate(small_frame, small_tmpl, cv2.TM_CCOEFF_NORMED)

# 2단계: 후보 위치를 원본 해상도에서 정밀 검증
for candidate in coarse_matches:
    x, y = candidate[0]*2, candidate[1]*2
    roi = frame_gray[y-pad:y+h+pad, x-pad:x+w+pad]
    # 원본 템플릿으로 정밀 매칭
```

**수정 파일:**
- `monster_tracker.py` — `detect_wolves()` 리팩터링
- `config.py` — `PYRAMID_SCALE = 0.5` 추가

**검증:**
- 전체 프레임 탐색 시간을 `time.perf_counter()`로 측정
- 목표: 120~360ms → 30~90ms
- 감지 정확도가 유지되는지 확인 (score 비교)

---

## 예상 결과

| 지표 | 현재 | Phase 1 완료 후 |
|---|---|---|
| 유령 클릭 | 3프레임 (0.45초) | 0프레임 |
| HP 변화 오판 | 빈번 | 최소화 |
| ROI 성공률 | ~60% | ~85% |
| 전체 탐색 속도 | 120~360ms | 30~90ms |
