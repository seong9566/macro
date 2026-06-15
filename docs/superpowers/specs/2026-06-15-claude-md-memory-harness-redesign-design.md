# CLAUDE.md 메모리 하네스 전면 재설계 — 설계 문서

작성일: 2026-06-15
대상 저장소: 온라인삼국지2 매크로 (`macro`)

## 1. 배경 및 문제

현재 단일 `CLAUDE.md`(48줄)에 개요·빌드·아키텍처·설계 결정·언어 정책이 모두 들어 있다. Claude Code 메모리 모범 사례(https://code.claude.com/docs/en/memory)와 대조하면 다음 문제가 있다.

1. **사실 오류**: `CLAUDE.md`에 "테스트 프레임워크는 아직 없음. 수동 실행으로 검증."이라고 적혀 있으나, 실제로는 pytest 기반 테스트 하네스가 존재한다.
   - `tests/` 패키지(`__init__.py`, `conftest.py`)
   - 테스트 파일 8종: `test_item_picker.py`, `test_hunt_profile.py`, `test_profile_manager.py`, `test_skill_manager.py`, `test_key_display.py`, `test_color_filter.py`, `test_monster_detection.py`, `test_template_capture.py`
   - `requirements.txt`에 `pytest>=8.0.0`
   - `tests/conftest.py`는 프로젝트 루트를 `sys.path`에 추가
2. **명령 불일치**: 빌드/실행 블록이 ```bash``` 펜스인데 내용은 PowerShell 명령이다. 테스트 실행 명령(`python -m pytest`)이 없다.
3. **path-scoped rules 미사용**: 감지/테스트처럼 특정 파일 작업 시에만 필요한 규칙도 항상 컨텍스트에 로드된다.
4. **개인/머신 종속 정보 혼입**: 개인 절대 경로(`cd "C:\Users\PC\..."`)가 팀 공유 `CLAUDE.md`에 포함되어 있다.

## 2. 목표

- 메모리 모범 사례에 맞춰 `CLAUDE.md`를 슬림화하고 사실 오류를 제거한다.
- 토픽별 규칙을 `.claude/rules/`로 분리하고, 감지/테스트 규칙은 path-scoped로 만들어 컨텍스트를 절약한다.
- 개인/머신 종속 항목을 `CLAUDE.local.md`(gitignore)로 분리한다.
- CLAUDE.md 프로젝트 정책(한글 응답/주석/로그)을 유지한다.

비목표(YAGNI): 임포트(`@path`) 도입 — 메모리 문서상 임포트는 컨텍스트를 줄이지 못하므로, 컨텍스트 효율이 더 좋은 `.claude/rules/`를 사용한다. 코드 자체 리팩터링은 범위 밖.

## 3. 목표 파일 구조

```
macro/
├── CLAUDE.md                  ← 슬림화 (개요·아키텍처·빌드·테스트 명령, 목표 <80줄)
├── CLAUDE.local.md            ← 개인/머신 종속 (gitignore 대상, 신규)
├── .gitignore                 ← CLAUDE.local.md 추가
└── .claude/
    └── rules/
        ├── code-style.md      ← paths 없음(항상 로드): 한글 정책·전역 컨벤션
        ├── testing.md         ← paths: ["tests/**", "**/test_*.py"]
        └── detection.md       ← paths: ["monster_tracker.py", "image_finder.py"]
```

## 4. 파일별 상세 명세

### 4.1 CLAUDE.md (루트, 항상 전체 로드)

포함:
- `## 프로젝트 개요` — 현행 유지
- `## 빌드 및 실행`
  - 코드 펜스를 ```powershell```로 변경
  - 설치/실행 명령 유지(`pip install -r requirements.txt`, `python main.py`, `python macro_ui.py`)
  - **테스트 실행 명령 추가**: `python -m pytest`
  - "테스트 프레임워크 없음" 문장 **삭제**(상세는 testing.md로 이관)
  - 개인 절대 경로 `cd "..."` 줄 **삭제**(CLAUDE.local.md로 이관)
- `## 아키텍처` — 트리 + 핵심 실행 흐름 유지
- 언어 정책(`## 언어`)과 세부 설계 결정(`## 핵심 설계 결정`)은 rules로 이관하여 본문에서 제거

제외(이관): 한글 언어 정책 → code-style.md, 감지/클릭 설계 결정 → detection.md, 개인 경로 → CLAUDE.local.md.

### 4.2 .claude/rules/code-style.md (항상 로드, paths 없음)

- 언어 정책: "모든 응답, 주석, 로그 메시지는 한글로 작성"
- 사람 입력 모사 컨벤션: 클릭 좌표 ±2px 랜덤 오프셋, down/up 사이 0.03~0.08초 랜덤 딜레이
- 기타 전역 코딩 컨벤션(필요 시)

### 4.3 .claude/rules/testing.md (path-scoped)

frontmatter:
```yaml
paths:
  - "tests/**"
  - "**/test_*.py"
```

내용:
- 하네스 현황: pytest 기반. `requirements.txt`에 `pytest>=8.0.0`.
- 실행법: `python -m pytest` (저장소 루트에서)
- `tests/conftest.py`가 프로젝트 루트를 `sys.path`에 추가하므로 테스트에서 루트 모듈 직접 import 가능
- 규약:
  - 새 모듈 추가 시 `tests/test_<module>.py` 작성
  - 테스트 파일은 `test_*.py` 명명
  - GUI(PyQt6)/하드웨어 입력(SendInput)/화면 캡처 의존 코드는 모킹하여 단위 테스트
- 후속 권장 항목(문서화만, 이번 구현엔 미포함): 루트에 `pytest.ini` 추가하여 `testpaths = tests` 등 명시

### 4.4 .claude/rules/detection.md (path-scoped)

frontmatter:
```yaml
paths:
  - "monster_tracker.py"
  - "image_finder.py"
```

내용(현 `## 핵심 설계 결정`에서 이관):
- 클릭 방식: 게임이 소프트웨어 클릭 차단 → ctypes `SendInput`(dwExtraInfo=0) 하드웨어 입력 위장 기본. `clicker.py`의 `CLICK_METHODS`로 전환.
- 감지 파이프라인: `detect_wolves()`(멀티스케일 템플릿 매칭 + NMS) → `create_tracker()`(CSRT/KCF) 프레임 추적. 60프레임마다 `_verify_tracking()` 재검증.
- 이중 감지 모듈: `monster_tracker.py`(늑대 전용 템플릿+추적기) vs `image_finder.py`(범용 색상/그레이/ORB). 현재 엔진은 `monster_tracker.py`만 사용.
- 이미지 템플릿: `images/` 방향별 PNG 8장, `_template_cache`로 반복 로딩 방지.

### 4.5 CLAUDE.local.md (신규, gitignore)

- 개인/머신 종속 절대 경로: `cd "C:\Users\PC\OneDrive\바탕 화면\workspace\macro"`
- 향후 개인 샌드박스/테스트 데이터 경로

### 4.6 .gitignore

- `CLAUDE.local.md` 항목 추가(기존 .gitignore 존재 시 항목만 추가, 없으면 신규 생성)

## 5. 적용 모범 사례 체크리스트

- [ ] CLAUDE.md 200줄 미만 유지(목표 80줄 이하)
- [ ] 마크다운 헤더/불릿으로 구조화
- [ ] 구체적·검증 가능한 명령(`python -m pytest` 등)
- [ ] 규칙 충돌/중복 제거(특히 "테스트 없음" 모순 제거)
- [ ] path-scoped rules로 컨텍스트 절약
- [ ] 개인 정보와 팀 공유 정보 분리

## 6. 검증 방법

- 수동: `/memory`로 CLAUDE.md / rules 파일 로드 확인
- 사실 검증: `python -m pytest`가 실제 동작하는지 1회 실행
- 내용 검증: 재배치 후 원본 정보 손실 없음(모든 항목이 새 위치에 존재) 확인

## 7. 범위 밖 (Out of Scope)

- 실제 코드 리팩터링
- `pytest.ini` 실제 추가(문서상 권장만)
- 임포트(`@path`) 도입
