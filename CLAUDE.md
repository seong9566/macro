# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 토픽별 규칙은 `.claude/rules/`에 분리되어 있다: `code-style.md`(한글 정책·전역 컨벤션, 항상 로드),
> `testing.md`(테스트, tests 작업 시), `detection.md`(감지/추적/클릭, 감지 모듈 작업 시).
> 개인/머신 종속 설정은 `CLAUDE.local.md`(git 제외) 참고.

## 프로젝트 개요

온라인삼국지2 전용 매크로 프로그램. 화면 캡처 기반 이미지 인식(템플릿 매칭 + HSV 색상 감지) + 다중 방식 마우스 클릭을 조합하여 게임 내 몬스터 사냥을 자동화한다. Windows 전용.

## 빌드 및 실행

```powershell
# PowerShell 관리자 권한 실행 (작업 경로는 CLAUDE.local.md 참고)

pip install -r requirements.txt
python main.py          # F5=시작, F6=중지
python macro_ui.py      # UI 실행

python -m pytest        # 테스트 실행 (규약은 .claude/rules/testing.md)
```

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
