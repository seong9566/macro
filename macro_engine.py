import time
import random
from monster_tracker import MonsterTracker
from clicker import click
from config import CLICK_METHOD, DEFAULT_DELAY
from logger import log


class MacroEngine:
    def __init__(self, click_method=CLICK_METHOD, region=None,
                 template_dir="images", confidence=0.5):
        self.click_method = click_method
        self.running = False
        self.tracker = MonsterTracker(
            region=region,
            template_dir=template_dir,
            confidence=confidence,
        )

    def hunt_loop(self, delay_after=DEFAULT_DELAY, attack_interval=0.3):
        """
        몬스터 사냥 루프.

        1. 몬스터 감지 → 추적 시작
        2. 추적 중인 대상 클릭 (공격)
        3. 대상 소실 → 자동 재감지
        4. self.running=False까지 무한 반복
        """
        self.running = True
        log.info("사냥 루프 시작")

        while self.running:
            # 몬스터 찾기/추적
            pos = self.tracker.find_and_track()

            if pos:
                # 추적 성공 → 클릭 공격
                click(pos[0], pos[1], method=self.click_method)
                log.debug(f"공격: ({pos[0]}, {pos[1]})")
                time.sleep(attack_interval + random.uniform(0, 0.15))
            else:
                # 몬스터 없음 → 잠시 대기 후 재탐색
                log.debug("대상 없음, 재탐색 대기...")
                time.sleep(delay_after)

        log.info("사냥 루프 종료")

    def stop(self):
        self.running = False
        self.tracker.reset()
        log.info("매크로 중지 요청")
