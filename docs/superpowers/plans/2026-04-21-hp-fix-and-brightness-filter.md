# HP/MP 좌표 보정 + 흰색 배경 오탐 수정 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) HP/MP 바 좌표를 실제 게임 화면에 맞게 보정하여 정확한 비율 표시, (2) 흰색 배경(폭포/안개) 오탐 완전 차단

**Architecture:** HP/MP는 캡처된 프레임에서 디버그 이미지를 저장하여 정확한 좌표를 확인 후 config 보정. 흰색 배경 오탐은 기존 `BRIGHTNESS_REJECT_THRESHOLD=200` 값을 낮추고, ROI 재탐색(`_detect_in_roi`)에도 밝기 필터를 추가하여 추적 중 오탐까지 차단.

**Tech Stack:** OpenCV, numpy

---

## 파일 구조

| 파일 | 변경 유형 | 역할 |
|------|-----------|------|
| `config.py` | 수정 | HP/MP 바 좌표 보정, BRIGHTNESS_REJECT_THRESHOLD 하향 |
| `monster_tracker.py` | 수정 | `_detect_in_roi()`에 밝기 필터 추가 |

---

### Task 1: HP/MP 바 좌표 디버그 및 보정

**Files:**
- Modify: `config.py:114-128` (HP/MP 바 영역 설정)

- [ ] **Step 1: 디버그 스크립트로 실제 HP/MP 바 위치 확인**

프로젝트 루트에서 다음 Python 스크립트를 실행하여 HP/MP 바 영역을 시각적으로 확인한다:

```python
import cv2
import numpy as np
from screen_capture import capture_screen
from window_manager import get_game_region

region = get_game_region("온라인삼국지")
frame = capture_screen(region=region)
if frame is not None:
    # 좌상단 넓은 영역 저장 (x=0~350, y=0~150)
    debug_roi = frame[0:150, 0:350]
    cv2.imwrite("debug_hp_mp_area.png", debug_roi)

    # 현재 config 값으로 HP/MP 영역 표시
    hp = frame.copy()
    cv2.rectangle(hp, (70, 48), (70+150, 48+8), (0, 0, 255), 2)  # HP: 빨간 사각형
    cv2.rectangle(hp, (70, 65), (70+150, 65+8), (255, 0, 0), 2)  # MP: 파란 사각형
    debug_marked = hp[0:150, 0:350]
    cv2.imwrite("debug_hp_mp_marked.png", debug_marked)

    print(f"게임 영역: {region}")
    print("debug_hp_mp_area.png 와 debug_hp_mp_marked.png 저장 완료")
    print("빨간 사각형 = 현재 HP 영역, 파란 사각형 = 현재 MP 영역")
```

저장된 이미지를 확인하여 실제 HP/MP 바와 사각형이 정확히 겹치는지 확인한다.

게임 스크린샷 분석 기준:
- HP바 (빨간색): "2853 / 3219" 텍스트가 있는 빨간 바 → 약 y=45~55 영역, x=85~280
- MP바 (파란색): "16 / 737" 텍스트가 있는 파란/보라 바 → 약 y=65~75 영역, x=85~280

- [ ] **Step 2: config.py HP/MP 좌표 보정**

`config.py`에서 HP/MP 바 영역을 디버그 결과에 맞게 수정한다.

기존:
```python
PLAYER_HP_BAR_REGION = (70, 48, 150, 8)
```

변경 (스크린샷 분석 기반 — 디버그 결과로 미세 조정 필요):
```python
PLAYER_HP_BAR_REGION = (85, 45, 195, 10)
```

기존:
```python
PLAYER_MP_BAR_REGION = (70, 65, 150, 8)
```

변경:
```python
PLAYER_MP_BAR_REGION = (85, 65, 195, 10)
```

주요 변경점:
- x 시작점: 70 → 85 (캐릭터 초상화 원형 아이콘 오른쪽으로 이동)
- 너비: 150 → 195 (바 전체 길이에 맞춤)
- 높이: 8 → 10 (바 높이를 넉넉히 잡아 픽셀 수 확보)

- [ ] **Step 3: 커밋**

```bash
git add config.py
git commit -m "fix: HP/MP 바 좌표 보정 — 실제 게임 바 위치에 맞춤"
```

---

### Task 2: 흰색 배경 오탐 차단 강화

**Files:**
- Modify: `config.py:44` (BRIGHTNESS_REJECT_THRESHOLD)
- Modify: `monster_tracker.py:497-620` (`_detect_in_roi` 메서드)

현재 문제:
1. `BRIGHTNESS_REJECT_THRESHOLD = 200`이 너무 높아 밝은 배경을 통과시킴
2. `detect_wolves()` (전체 프레임 탐색)에만 밝기 필터가 있고, `_detect_in_roi()` (ROI 추적)에는 없음 → 추적 중 흰색 배경으로 타겟이 이동하면 오탐 지속

- [ ] **Step 1: BRIGHTNESS_REJECT_THRESHOLD 하향**

`config.py`에서 밝기 임계값을 낮춘다.

기존:
```python
BRIGHTNESS_REJECT_THRESHOLD = 200   # 0~255 (흰색 안개/하늘 배경 제거용)
```

변경:
```python
BRIGHTNESS_REJECT_THRESHOLD = 170   # 0~255 (흰색 안개/폭포/하늘 배경 제거용, 기존 200에서 하향)
```

200은 거의 흰색만 걸러내지만, 170은 밝은 회색(안개/폭포 배경)도 필터링한다.
몬스터(흰 늑대)의 평균 밝기는 보통 140~160 범위이므로 170이면 몬스터는 통과한다.

- [ ] **Step 2: `_detect_in_roi()`에 밝기 필터 추가**

`monster_tracker.py`의 `_detect_in_roi()` 메서드에서, 그레이스케일 매칭 결과(`best_result`)를 반환하기 전에 밝기 검사를 추가한다.

기존 (554~557번 줄):
```python
        if best_result:
            self._last_detect_was_edge = False
            log.debug(f"ROI 재탐색 성공 [그레이]: ({best_result[0]},{best_result[1]}) score={best_score:.3f}")
            return best_result
```

변경:
```python
        if best_result:
            # 밝기 필터 — 감지 영역이 지나치게 밝으면 배경 오탐으로 제거
            bx, by, bw, bh = best_result
            check_roi = roi_gray[by - roi_y1:by - roi_y1 + bh, bx - roi_x1:bx - roi_x1 + bw]
            if check_roi.size > 0 and np.mean(check_roi) > BRIGHTNESS_REJECT_THRESHOLD:
                log.debug(f"ROI 밝기 필터 제거 [그레이]: mean={np.mean(check_roi):.0f} > {BRIGHTNESS_REJECT_THRESHOLD}")
                best_result = None
                best_score = 0
            else:
                self._last_detect_was_edge = False
                log.debug(f"ROI 재탐색 성공 [그레이]: ({best_result[0]},{best_result[1]}) score={best_score:.3f}")
                return best_result
```

동일하게 반투명 변형 폴백 결과(577~580번 줄)에도 밝기 필터를 추가한다:

기존:
```python
            if best_result:
                self._last_detect_was_edge = False
                log.debug(f"ROI 재탐색 성공 [반투명]: ({best_result[0]},{best_result[1]}) score={best_score:.3f}")
                return best_result
```

변경:
```python
            if best_result:
                bx, by, bw, bh = best_result
                check_roi = roi_gray[by - roi_y1:by - roi_y1 + bh, bx - roi_x1:bx - roi_x1 + bw]
                if check_roi.size > 0 and np.mean(check_roi) > BRIGHTNESS_REJECT_THRESHOLD:
                    log.debug(f"ROI 밝기 필터 제거 [반투명]: mean={np.mean(check_roi):.0f} > {BRIGHTNESS_REJECT_THRESHOLD}")
                    best_result = None
                    best_score = 0
                else:
                    self._last_detect_was_edge = False
                    log.debug(f"ROI 재탐색 성공 [반투명]: ({best_result[0]},{best_result[1]}) score={best_score:.3f}")
                    return best_result
```

동일하게 에지 매칭 폴백 결과(606~609번 줄)에도 밝기 필터를 추가한다. 에지 이미지(`roi_edge`)가 아닌 원본 `roi_gray`에서 밝기를 측정해야 한다 (에지 이미지의 평균값은 밝기와 무관):

기존:
```python
        if best_edge_result:
            self._last_detect_was_edge = True
            log.debug(f"ROI 재탐색 성공 [에지]: ({best_edge_result[0]},{best_edge_result[1]}) score={best_edge_score:.3f}")
            return best_edge_result
```

변경:
```python
        if best_edge_result:
            bx, by, bw, bh = best_edge_result
            check_roi = roi_gray[by - roi_y1:by - roi_y1 + bh, bx - roi_x1:bx - roi_x1 + bw]
            if check_roi.size > 0 and np.mean(check_roi) > BRIGHTNESS_REJECT_THRESHOLD:
                log.debug(f"ROI 밝기 필터 제거 [에지]: mean={np.mean(check_roi):.0f} > {BRIGHTNESS_REJECT_THRESHOLD}")
                return None
            self._last_detect_was_edge = True
            log.debug(f"ROI 재탐색 성공 [에지]: ({best_edge_result[0]},{best_edge_result[1]}) score={best_edge_score:.3f}")
            return best_edge_result
```

- [ ] **Step 3: 커밋**

```bash
git add config.py monster_tracker.py
git commit -m "fix: 흰색 배경 오탐 차단 강화 — 임계값 하향 + ROI 밝기 필터 추가 (그레이/반투명/에지 3단계)"
```

---

## 참고 사항

### 밝기 임계값 선택 근거
- 흰 늑대 몬스터: 그레이스케일 평균 밝기 약 140~160
- 안개/폭포 배경: 그레이스케일 평균 밝기 약 200~240
- 임계값 170: 몬스터(통과) ↔ 배경(차단) 경계로 적절
- 너무 낮추면 밝은 조명 아래 몬스터도 필터링될 수 있으므로 170이 안전 마진

### HP/MP 좌표는 게임 해상도에 의존
게임 창 크기가 변경되면 HP/MP 바 좌표도 달라진다. 설정 탭의 슬라이더로 실시간 조정 가능.
