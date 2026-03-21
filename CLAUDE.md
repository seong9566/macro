# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

온라인삼국지2 전용 매크로 프로그램. 화면 캡처 기반 이미지 인식 + 다중 방식 마우스 클릭을 조합하여 게임 내 반복 작업을 자동화한다.

**현재 상태:** 기획서(`온삼2_매크로_기획서_v2_1.md`)만 존재. 소스 코드 구현 필요.

## 기술 스택

- Python 3.10+
- opencv-python: 템플릿 매칭 기반 이미지 인식
- pyautogui: 스크린 캡처, 마우스 이동
- pydirectinput: DirectInput 레벨 클릭
- ctypes: Win32 SendInput API 직접 호출 (하드웨어 입력 시뮬레이션)
- keyboard: 핫키 등록, 마우스키 우회용 키보드 입력

## 아키텍처

```
main.py            ─ 진입점. 핫키(F5/F6) 등록, 매크로 스레드 관리
├── config.py      ─ 모든 설정값 (클릭 방식, 딜레이, 창 제목 등)
├── macro_engine.py─ 스택 기반 시퀀스 실행 엔진 (재귀 없이 중첩 루프 처리)
├── image_finder.py─ 화면 캡처 + OpenCV 템플릿 매칭 (캐시 포함)
├── clicker.py     ─ 다중 클릭 방식 통합 인터페이스
├── window_manager.py ─ ctypes로 게임 창 HWND 탐색 및 영역 좌표 반환
└── logger.py      ─ 콘솔+파일 이중 출력 로거 (일자별 로그 파일)
```

## 핵심 설계 결정

- **클릭 방식 우선순위:** directinput → ctypes SendInput(dwExtraInfo=0) → 마우스키(넘패드5) → Interception 드라이버. 게임이 소프트웨어 클릭을 차단하므로 하드웨어 입력 시뮬레이션이 핵심.
- **매크로 엔진:** 재귀 대신 스택 기반으로 루프를 평탄화하여 무한 반복 시 스택 오버플로우 방지.
- **시퀀스 포맷:** JSON-like dict 리스트. `find_click`, `wait`, `loop` 세 가지 액션 지원.
- **이미지 템플릿 캐시:** `_template_cache` 딕셔너리로 동일 이미지 반복 로딩 방지.
- **랜덤 오프셋/딜레이:** 클릭 좌표에 ±2px, 딜레이에 0~0.3초 랜덤 추가.

## 빌드 및 실행

```bash
pip install -r requirements.txt
python main.py          # F5=시작, F6=중지
```

## 언어

- 모든 응답, 주석, 로그 메시지는 **한글**로 작성할 것.
