import logging
import os
from datetime import datetime


def setup_logger(name="macro", log_dir="logs", level=logging.DEBUG):
    """
    구조화된 로거를 생성하여 콘솔 + 파일에 동시 출력.

    로그 레벨 가이드:
        DEBUG    - 이미지 매칭 점수, 좌표 계산 상세값
        INFO     - 매크로 시작/중지, 클릭 실행, 이미지 발견
        WARNING  - 이미지 미발견 (timeout), 클릭 방식 fallback
        ERROR    - 템플릿 로딩 실패, 캡처 실패, 예외 발생
        CRITICAL - 게임 창 미감지, 복구 불가능한 오류
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 이미 핸들러가 있으면 중복 추가 방지
    if logger.handlers:
        return logger

    # 로그 포맷
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S"
    )

    # 콘솔 핸들러
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 파일 핸들러 (일자별 로그 파일)
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = logging.FileHandler(
        os.path.join(log_dir, f"macro_{today}.log"),
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


# 모듈 전역 로거 (다른 모듈에서 import하여 사용)
log = setup_logger()
