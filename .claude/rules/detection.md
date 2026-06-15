---
paths:
  - "monster_tracker.py"
  - "image_finder.py"
---

# 몬스터 감지 / 추적 / 클릭 설계 결정

## 클릭 방식
- 게임이 소프트웨어 클릭을 차단하므로 ctypes `SendInput`(dwExtraInfo=0)으로
  하드웨어 입력을 위장하는 것이 기본값이다.
- `clicker.py`의 `CLICK_METHODS` 딕셔너리로 방식(directinput / sendinput / mousekeys)을 전환한다.

## 감지 파이프라인
- `monster_tracker.py`가 `detect_wolves()`(멀티스케일 템플릿 매칭 + NMS)로 감지 후,
  `create_tracker()`(CSRT/KCF)로 프레임 단위 추적한다.
- 60프레임마다 `_verify_tracking()`으로 대상이 여전히 늑대인지 재검증한다.

## 이중 감지 모듈
- `monster_tracker.py`: 늑대 전용(템플릿 매칭 + 추적기).
- `image_finder.py`: 범용(HSV 색상 / 그레이스케일 / ORB 특징점 / 멀티스케일).
- 현재 매크로 엔진은 `monster_tracker.py`만 사용한다.

## 이미지 템플릿
- `images/` 폴더에 방향별 늑대 PNG 8장.
- `_template_cache` 딕셔너리로 반복 로딩을 방지한다.
