# CLAUDE.md 메모리 하네스 전면 재설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 단일 `CLAUDE.md`를 메모리 모범 사례에 맞춰 슬림화하고, 사실 오류(테스트 하네스 "없음")를 제거하며, 토픽별 규칙을 `.claude/rules/`로 분리하고 개인 정보를 `CLAUDE.local.md`로 옮긴다.

**Architecture:** 루트 `CLAUDE.md`에는 개요·아키텍처·빌드·테스트 명령만 남기고, 한글 정책은 `.claude/rules/code-style.md`(항상 로드), 테스트/감지 규칙은 path-scoped rules로 분리한다. 개인 절대 경로는 gitignore된 `CLAUDE.local.md`로 이관한다. 정보 손실 없이 재배치하는 것이 핵심.

**Tech Stack:** Markdown, YAML frontmatter, Claude Code 메모리 시스템(.claude/rules/), git.

참조 spec: `docs/superpowers/specs/2026-06-15-claude-md-memory-harness-redesign-design.md`

---

## File Structure

- Create: `.claude/rules/code-style.md` — 한글 정책 + 전역 컨벤션 (항상 로드)
- Create: `.claude/rules/testing.md` — 테스트 실행/규약 (path-scoped: tests)
- Create: `.claude/rules/detection.md` — 감지·추적·클릭 설계 결정 (path-scoped: 감지 모듈)
- Create: `CLAUDE.local.md` — 개인/머신 종속 경로 (gitignore)
- Modify: `CLAUDE.md` — 슬림화, 빌드 펜스 정정, 테스트 명령 추가, 이관 항목 제거
- Modify: `.gitignore` — `CLAUDE.local.md` 추가

---

## Task 1: 한글/전역 컨벤션 rules 파일 생성

**Files:**
- Create: `.claude/rules/code-style.md`

- [ ] **Step 1: code-style.md 작성**

`.claude/rules/code-style.md` 파일을 아래 내용으로 생성한다 (paths frontmatter 없음 → 항상 로드):

```markdown
# 코드 스타일 / 전역 컨벤션

## 언어 정책
- 모든 응답, 주석, 로그 메시지는 **한글**로 작성할 것.

## 사람 입력 모사
- 클릭 좌표에 ±2px 랜덤 오프셋을 적용한다.
- 클릭 down/up 사이에 0.03~0.08초 랜덤 딜레이를 넣어 사람 입력을 모사한다.
```

- [ ] **Step 2: 파일 생성 확인**

Run: `ls .claude/rules/code-style.md`
Expected: 경로가 출력됨(파일 존재)

- [ ] **Step 3: 커밋**

```bash
git add .claude/rules/code-style.md
git commit -m "docs: code-style rules — 한글 정책/입력 모사 분리"
```

---

## Task 2: 테스트 rules 파일 생성 (path-scoped)

**Files:**
- Create: `.claude/rules/testing.md`

- [ ] **Step 1: testing.md 작성**

`.claude/rules/testing.md` 파일을 아래 내용으로 생성한다:

```markdown
---
paths:
  - "tests/**"
  - "**/test_*.py"
---

# 테스트 규약

## 현황
- pytest 기반 테스트 하네스가 존재한다. `requirements.txt`에 `pytest>=8.0.0` 포함.
- `tests/` 는 패키지(`__init__.py`)이며 `tests/conftest.py`가 프로젝트 루트를
  `sys.path`에 추가하므로, 테스트에서 루트 모듈을 직접 import 할 수 있다.

## 실행
- 저장소 루트에서: `python -m pytest`
- 단일 파일: `python -m pytest tests/test_color_filter.py -v`

## 규약
- 새 모듈을 추가하면 `tests/test_<module>.py` 를 작성한다.
- 테스트 파일은 `test_*.py` 로 명명한다.
- GUI(PyQt6) / 하드웨어 입력(SendInput) / 화면 캡처에 의존하는 코드는
  모킹하여 단위 테스트한다.

## 후속 권장 (미적용)
- 루트에 `pytest.ini` 를 추가해 `testpaths = tests` 등을 명시하면 좋다.
```

- [ ] **Step 2: 파일 생성 확인**

Run: `ls .claude/rules/testing.md`
Expected: 경로가 출력됨

- [ ] **Step 3: 테스트가 실제로 동작하는지 검증**

Run: `python -m pytest -q`
Expected: 테스트가 수집·실행됨 (전부 통과가 이상적이나, 최소한 "collected N items"가 보이고 import 에러가 없어야 함). 실패가 있으면 그 내용을 기록하되 본 plan 범위(문서)에서는 수정하지 않는다.

- [ ] **Step 4: 커밋**

```bash
git add .claude/rules/testing.md
git commit -m "docs: testing rules — pytest 하네스 현황/실행/규약 (path-scoped)"
```

---

## Task 3: 감지/추적 rules 파일 생성 (path-scoped)

**Files:**
- Create: `.claude/rules/detection.md`

- [ ] **Step 1: detection.md 작성**

`.claude/rules/detection.md` 파일을 아래 내용으로 생성한다:

```markdown
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
```

- [ ] **Step 2: 파일 생성 확인**

Run: `ls .claude/rules/detection.md`
Expected: 경로가 출력됨

- [ ] **Step 3: 커밋**

```bash
git add .claude/rules/detection.md
git commit -m "docs: detection rules — 감지/추적/클릭 설계 결정 (path-scoped)"
```

---

## Task 4: CLAUDE.local.md 생성 + .gitignore 등록

**Files:**
- Create: `CLAUDE.local.md`
- Modify: `.gitignore`

- [ ] **Step 1: .gitignore에 CLAUDE.local.md 추가**

`.gitignore`의 `# Claude Code` 섹션을 다음과 같이 수정한다.

기존:
```
# Claude Code
.claude/settings.local.json
```

변경 후:
```
# Claude Code
.claude/settings.local.json
CLAUDE.local.md
```

- [ ] **Step 2: CLAUDE.local.md 작성**

`CLAUDE.local.md` 파일을 아래 내용으로 생성한다:

```markdown
# 개인 / 머신 종속 설정 (git 추적 제외)

## 작업 디렉터리
- `cd "C:\Users\PC\OneDrive\바탕 화면\workspace\macro"`

## 개인 메모
- (개인 샌드박스 경로, 테스트 데이터 등은 여기에 추가)
```

- [ ] **Step 3: gitignore 동작 확인**

Run: `git check-ignore CLAUDE.local.md`
Expected: `CLAUDE.local.md` 가 출력됨(무시 대상으로 인식). 출력이 없으면 .gitignore 항목을 점검한다.

- [ ] **Step 4: 커밋 (.gitignore만 — CLAUDE.local.md는 추적 안 됨)**

```bash
git add .gitignore
git commit -m "chore: CLAUDE.local.md gitignore 등록"
```

---

## Task 5: CLAUDE.md 슬림화

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: CLAUDE.md 전체를 아래 내용으로 교체**

이관된 항목(언어 정책, 핵심 설계 결정, 개인 경로, "테스트 없음" 문장)을 제거하고, 빌드 펜스를 `powershell`로 정정하며 테스트 명령을 추가한다. 최종 내용:

````markdown
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
````

- [ ] **Step 2: 정보 손실 없음 확인**

다음을 눈으로 확인한다 (모두 새 위치에 존재해야 함):
- 한글 언어 정책 → `.claude/rules/code-style.md`
- 랜덤 오프셋/딜레이 → `.claude/rules/code-style.md`
- 클릭 방식 / 감지 파이프라인 / 이중 감지 모듈 / 이미지 템플릿 → `.claude/rules/detection.md`
- 테스트 실행/규약 → `.claude/rules/testing.md` 및 CLAUDE.md의 `python -m pytest`
- 개인 경로 `cd "..."` → `CLAUDE.local.md`

Run: `grep -n "테스트 프레임워크는 아직 없음" CLAUDE.md`
Expected: 출력 없음(문장이 제거됨)

Run: `grep -n "C:\\\\Users\\\\PC" CLAUDE.md`
Expected: 출력 없음(개인 경로가 제거됨)

- [ ] **Step 3: 줄 수 확인**

Run: `wc -l CLAUDE.md`
Expected: 80줄 미만

- [ ] **Step 4: 커밋**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md 슬림화 — rules 분리/테스트 명령 추가/펜스 정정"
```

---

## Task 6: 최종 검증

**Files:** (없음 — 검증만)

- [ ] **Step 1: 새 구조 파일 전부 존재 확인**

Run: `ls CLAUDE.md CLAUDE.local.md .claude/rules/code-style.md .claude/rules/testing.md .claude/rules/detection.md`
Expected: 5개 경로 모두 출력

- [ ] **Step 2: git 상태 확인 — CLAUDE.local.md는 추적되지 않아야 함**

Run: `git status --porcelain`
Expected: `CLAUDE.local.md`가 목록에 없음(무시됨). 다른 변경은 모두 커밋되어 깨끗해야 함.

- [ ] **Step 3: 세션에서 로드 확인 (수동)**

Claude Code 세션에서 `/memory`를 실행해 `CLAUDE.md`와 `.claude/rules/*.md`가 로드되는지 확인한다. path-scoped인 testing/detection은 해당 파일을 열 때 로드된다.
