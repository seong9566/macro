import time
import random
from monster_tracker import MonsterTracker, TRACK_OK, TRACK_KILLED
from clicker import click, press_key
from config import (
    CLICK_METHOD, DEFAULT_DELAY, DETECT_CONFIDENCE,
    LOOT_ENABLED, LOOT_KEY_SCANCODE, LOOT_PRESS_COUNT,
    LOOT_PRESS_INTERVAL, LOOT_DELAY_AFTER_KILL,
)
from logger import log


class MacroEngine:
    def __init__(self, click_method=CLICK_METHOD, region=None,
                 template_dir="images", confidence=DETECT_CONFIDENCE):
        self.click_method = click_method
        self.running = False
        self.tracker = MonsterTracker(
            region=region,
            template_dir=template_dir,
            confidence=confidence,
        )

    def _loot_items(self):
        """사망 판정 후 아이템 줍기 (Spacebar × N회)."""
        if not LOOT_ENABLED:
            return

        time.sleep(LOOT_DELAY_AFTER_KILL + random.uniform(0, 0.05))
        for i in range(LOOT_PRESS_COUNT):
            press_key(LOOT_KEY_SCANCODE)
            if i < LOOT_PRESS_COUNT - 1:
                time.sleep(LOOT_PRESS_INTERVAL + random.uniform(0, 0.04))
        log.info(f"아이템 줍기 완료 (Spacebar ×{LOOT_PRESS_COUNT})")

    def hunt_loop(self, delay_after=DEFAULT_DELAY, attack_interval=0.3):
        """
        몬스터 사냥 루프.

        1. 몬스터 감지 → 추적 시작
        2. 추적 중인 대상 클릭 (공격)
        3. 대상 소실(사망) → 아이템 줍기 → 다음 대상
        4. 타임아웃/HP정체(포기) → 줍기 없이 다음 대상
        5. self.running=False까지 무한 반복
        """
        self.running = True
        log.info("사냥 루프 시작")

        while self.running:
            try:
                pos, reason = self.tracker.find_and_track()

                if pos and reason == TRACK_OK:
                    # 추적 성공 → 클릭 공격
                    click(pos[0], pos[1], method=self.click_method)
                    log.info(f"공격: ({pos[0]}, {pos[1]})")
                    time.sleep(attack_interval + random.uniform(0, 0.15))

                elif reason == TRACK_KILLED:
                    # 대상 사망 → 아이템 줍기
                    log.info("대상 사망 추정 → 아이템 줍기")
                    self._loot_items()

                else:
                    # 미발견 또는 포기 → 잠시 대기 후 재탐색
                    log.info(f"대상 없음 (사유: {reason}), 재탐색 대기...")
                    time.sleep(delay_after)

            except Exception as e:
                log.error(f"사냥 루프 예외 발생: {e}")
                time.sleep(1)

        log.info("사냥 루프 종료")

    def stop(self):
        self.running = False
        self.tracker.reset()
        log.info("매크로 중지 요청")
