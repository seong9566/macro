"""테스트용 path 설정 — 프로젝트 루트의 모듈을 import 가능하게 함."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
