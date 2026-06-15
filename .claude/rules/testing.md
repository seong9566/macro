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
