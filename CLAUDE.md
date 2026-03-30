# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

온라인삼국지2 전용 매크로 프로그램. 화면 캡처 기반 이미지 인식(템플릿 매칭 + HSV 색상 감지) + 다중 방식 마우스 클릭을 조합하여 게임 내 몬스터 사냥을 자동화한다. Windows 전용.

## 빌드 및 실행

```bash
pip install -r requirements.txt
python main.py          # F5=시작, F6=중지
```

테스트 프레임워크는 아직 없음. 수동 실행으로 검증.

## 아키텍처

```
main.py              ─ 진입점. 핫키(F5/F6) 등록, MacroEngine을 데몬 스레드로 실행
├── config.py        ─ 모든 설정 상수 (클릭 방식, 딜레이, 창 제목, 로그 레벨 등)
├── macro_engine.py  ─ 사냥 루프: MonsterTracker로 감지 → clicker로 클릭 → 반복
├── monster_tracker.py ─ 늑대 감지(멀티스케일 템플릿 매칭 + NMS) + OpenCV CSRT 추적기
├── image_finder.py  ─ 범용 이미지 탐색 (HSV 색상, 그레이스케일, ORB 특징점, 멀티스케일)
├── clicker.py       ─ 다중 클릭 방식 통합 (directinput / sendinput / mousekeys)
├── window_manager.py ─ ctypes EnumWindows로 게임 창 HWND 탐색 및 영역 좌표 반환
└── logger.py        ─ 콘솔(INFO)+파일(DEBUG) 이중 출력 로거 (일자별 logs/macro_YYYY-MM-DD.log)
```

**핵심 실행 흐름:** `main.py` → `MacroEngine.hunt_loop()` → `MonsterTracker.find_and_track()` → 감지 시 `clicker.click()` 반복. 추적 중이면 CSRT 트래커로 업데이트만 수행하고, 추적 실패 시 재감지.

## 핵심 설계 결정

- **클릭 방식:** 게임이 소프트웨어 클릭을 차단하므로 ctypes `SendInput`(dwExtraInfo=0)으로 하드웨어 입력 위장이 기본값. `clicker.py`의 `CLICK_METHODS` 딕셔너리로 방식을 전환.
- **몬스터 감지 파이프라인:** `monster_tracker.py`가 `detect_wolves()`(멀티스케일 템플릿 매칭 + NMS)로 감지 후, `create_tracker()`(CSRT/KCF)로 프레임 단위 추적. 60프레임마다 `_verify_tracking()`으로 대상이 여전히 늑대인지 재검증.
- **이중 감지 모듈:** `monster_tracker.py`는 늑대 전용(템플릿 매칭 + 추적기), `image_finder.py`는 범용(색상/그레이/ORB). 현재 매크로 엔진은 `monster_tracker.py`만 사용.
- **이미지 템플릿:** `images/` 폴더에 방향별 늑대 PNG 8장. `_template_cache` 딕셔너리로 반복 로딩 방지.
- **랜덤 오프셋/딜레이:** 클릭 좌표에 ±2px, 클릭 down/up 사이 0.03~0.08초 랜덤으로 사람 입력 모사.

## 언어

- 모든 응답, 주석, 로그 메시지는 **한글**로 작성할 것.
