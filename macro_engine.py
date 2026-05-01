import time
import random
import math
import cv2
import numpy as np
from monster_tracker import MonsterTracker, TRACK_OK, TRACK_KILLED, TRACK_MISS_PENDING
from screen_capture import capture_screen
from clicker import click, press_key
from item_picker import ItemPicker
from window_manager import activate_window, get_game_region
from config import (
    CLICK_METHOD, DEFAULT_DELAY, ATTACK_INTERVAL, DETECT_CONFIDENCE,
    LOOT_ENABLED, LOOT_KEY_SCANCODE, LOOT_PRESS_COUNT,
    LOOT_PRESS_INTERVAL, LOOT_DELAY_AFTER_KILL,
    LOOT_VISUAL_ENABLED, LOOT_AFTER_CLICK_DELAY,
    ACTIVATE_WINDOW_ON_START, REACTIVATE_INTERVAL, REGION_REFRESH_INTERVAL,
    GAME_WINDOW_TITLE,
    ROAM_ENABLED, ROAM_AFTER_MISS_COUNT, ROAM_CLICK_DISTANCE,
    ROAM_MOVE_DELAY, ROAM_DIRECTION_COUNT,
    POTION_ENABLED, POTION_KEY_SCANCODE, POTION_HP_THRESHOLD,
    POTION_COOLDOWN, POTION_CHECK_INTERVAL,
    PLAYER_HP_BAR_REGION, PLAYER_HP_COLOR_LOWER, PLAYER_HP_COLOR_UPPER,
    PLAYER_HP_COLOR_LOWER2, PLAYER_HP_COLOR_UPPER2,
    PLAYER_MP_BAR_REGION, PLAYER_MP_COLOR_LOWER, PLAYER_MP_COLOR_UPPER,
    PLAYER_MP_COLOR_LOWER2, PLAYER_MP_COLOR_UPPER2,
)
from logger import log


class MacroEngine:
    def __init__(self, click_method=CLICK_METHOD, region=None,
                 template_dir="images", confidence=DETECT_CONFIDENCE):
        self.click_method = click_method
        self.region = region
        self.running = False
        self.tracker = MonsterTracker(
            region=region,
            template_dir=template_dir,
            confidence=confidence,
        )
        self.item_picker = ItemPicker()
        self._last_activate_time = 0.0
        self._last_region_refresh_time = 0.0
        # 랜덤 이동 상태
        self._miss_count = 0                # 연속 미발견 횟수
        self._last_roam_direction = -1      # 마지막 이동 방향 인덱스
        # 자동 물약 상태
        self._last_potion_time = 0.0        # 마지막 물약 사용 시각
        self._last_hp_check_time = 0.0      # 마지막 HP 확인 시각
        # HP/MP 비율 (UI 동기화용 — 0.0~1.0, -1.0=측정 불가)
        self.player_hp_ratio = -1.0
        self.player_mp_ratio = -1.0

    def _ensure_foreground(self):
        """게임 창이 포그라운드인지 주기적으로 확인 및 전환."""
        now = time.time()
        if now - self._last_activate_time >= REACTIVATE_INTERVAL:
            activate_window()
            self._last_activate_time = now

    def _refresh_region(self):
        """주기적으로 게임 창 위치/크기 재확인. 창 이동/재시작 시 자동 복구."""
        now = time.time()
        if now - self._last_region_refresh_time < REGION_REFRESH_INTERVAL:
            return
        self._last_region_refresh_time = now

        new_region = get_game_region(GAME_WINDOW_TITLE)
        if new_region is None:
            return
        if new_region != self.region:
            self.region = new_region
            self.tracker.region = new_region
            log.info(f"게임 창 영역 갱신: {new_region}")

    def _loot_items(self):
        """
        사망 판정 후 아이템 줍기.
            1. 시각 기반 픽업: 스냅샷 차분으로 드롭 위치 검출 → 클릭
            2. Spacebar 보험 픽업: 시각 성공 시 1회, 실패 시 LOOT_PRESS_COUNT회
        """
        if not LOOT_ENABLED:
            return

        time.sleep(LOOT_DELAY_AFTER_KILL + random.uniform(0, 0.05))

        # 1. 시각 기반 픽업 시도 (스냅샷 atomic 읽기 — 한 번만 참조 확보)
        picked = False
        snapshot = self.tracker.combat_snapshot
        if LOOT_VISUAL_ENABLED and snapshot is not None and self.region is not None:
            picked = self.item_picker.try_pickup(
                snapshot=snapshot,
                current_region=self.region,
                click_method=self.click_method,
            )
            if picked:
                log.info("아이템 픽업: 시각 클릭 성공")
                time.sleep(LOOT_AFTER_CLICK_DELAY)

        # 2. Spacebar 보험 — 시각 성공 시 1회 (다중 아이템 보조), 실패 시 LOOT_PRESS_COUNT회
        space_count = 1 if picked else LOOT_PRESS_COUNT
        for i in range(space_count):
            press_key(LOOT_KEY_SCANCODE)
            if i < space_count - 1:
                time.sleep(LOOT_PRESS_INTERVAL + random.uniform(0, 0.04))
        log.debug(f"Spacebar 보험 픽업 ×{space_count} (visual_picked={picked})")

    # ══════════════════════════════════════════════
    # 랜덤 이동 (몬스터 미발견 시)
    # ══════════════════════════════════════════════

    def _roam_random(self):
        """
        몬스터를 찾지 못했을 때 랜덤 방향으로 이동.
        8방향 중 이전 방향을 제외하고 랜덤 선택하여 한쪽으로만 이동하는 문제 방지.
        """
        if not ROAM_ENABLED:
            return

        if not self.region:
            log.warning("이동 불가: 게임 영역 미설정")
            return

        # 게임 화면 중앙 (스크린 절대 좌표)
        center_x = self.region[0] + self.region[2] // 2
        center_y = self.region[1] + self.region[3] // 2

        # 8방향 중 이전 방향 제외하고 랜덤 선택
        directions = list(range(ROAM_DIRECTION_COUNT))
        if self._last_roam_direction >= 0 and len(directions) > 1:
            directions.remove(self._last_roam_direction)
        direction = random.choice(directions)
        self._last_roam_direction = direction

        # 방향별 각도 (0=우, 1=우상, 2=상, ... 7=우하)
        angle = direction * (2 * math.pi / ROAM_DIRECTION_COUNT)
        # 거리에 약간의 랜덤 추가
        dist = ROAM_CLICK_DISTANCE + random.randint(-30, 30)
        target_x = int(center_x + dist * math.cos(angle))
        target_y = int(center_y - dist * math.sin(angle))  # 화면 Y축은 아래가 +

        # 게임 영역 내로 클램핑
        min_x = self.region[0] + 20
        max_x = self.region[0] + self.region[2] - 20
        min_y = self.region[1] + 20
        max_y = self.region[1] + self.region[3] - 20
        target_x = max(min_x, min(target_x, max_x))
        target_y = max(min_y, min(target_y, max_y))

        direction_names = ["→", "↗", "↑", "↖", "←", "↙", "↓", "↘"]
        dir_name = direction_names[direction] if direction < len(direction_names) else "?"

        activate_window()
        click(target_x, target_y, method=self.click_method)
        log.info(f"랜덤 이동: {dir_name} ({target_x}, {target_y})")
        time.sleep(ROAM_MOVE_DELAY + random.uniform(0, 0.3))

    # ══════════════════════════════════════════════
    # 자동 물약 (캐릭터 HP 감시)
    # ══════════════════════════════════════════════

    def _measure_player_hp(self, frame=None):
        """
        캐릭터 HP바의 HP 비율(0.0~1.0)을 측정.
        게임 화면 좌상단의 HP바 영역에서 빨간색 픽셀 비율로 추정.

        Args:
            frame: 캡처된 프레임 (None이면 내부에서 캡처)

        Returns:
            float (0.0~1.0) 또는 -1.0 (측정 불가)
        """
        if frame is None:
            frame = capture_screen(region=self.region)
        if frame is None:
            return -1.0

        bx, by, bw, bh = PLAYER_HP_BAR_REGION
        # 프레임 범위 체크
        if by + bh > frame.shape[0] or bx + bw > frame.shape[1]:
            return -1.0

        roi = frame[by:by + bh, bx:bx + bw]
        if roi.size == 0:
            return -1.0

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # 빨간색은 HSV에서 H=0~10 과 H=170~180 두 범위에 걸쳐 있음
        mask1 = cv2.inRange(hsv,
                            np.array(PLAYER_HP_COLOR_LOWER),
                            np.array(PLAYER_HP_COLOR_UPPER))
        mask2 = cv2.inRange(hsv,
                            np.array(PLAYER_HP_COLOR_LOWER2),
                            np.array(PLAYER_HP_COLOR_UPPER2))
        mask = cv2.bitwise_or(mask1, mask2)

        total_pixels = roi.shape[0] * roi.shape[1]
        if total_pixels == 0:
            return -1.0

        ratio = np.count_nonzero(mask) / total_pixels
        return ratio

    def _measure_player_mp(self, frame=None):
        """
        캐릭터 MP바의 MP 비율(0.0~1.0)을 측정.
        게임 화면의 MP바 영역에서 파란색 픽셀 비율로 추정.

        Args:
            frame: 캡처된 프레임 (None이면 내부에서 캡처)

        Returns:
            float (0.0~1.0) 또는 -1.0 (측정 불가)
        """
        if frame is None:
            frame = capture_screen(region=self.region)
        if frame is None:
            return -1.0

        bx, by, bw, bh = PLAYER_MP_BAR_REGION
        if by + bh > frame.shape[0] or bx + bw > frame.shape[1]:
            return -1.0

        roi = frame[by:by + bh, bx:bx + bw]
        if roi.size == 0:
            return -1.0

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # 파란색~보라색 2구간 매칭 (그라데이션 대응)
        mask1 = cv2.inRange(hsv,
                            np.array(PLAYER_MP_COLOR_LOWER),
                            np.array(PLAYER_MP_COLOR_UPPER))
        mask2 = cv2.inRange(hsv,
                            np.array(PLAYER_MP_COLOR_LOWER2),
                            np.array(PLAYER_MP_COLOR_UPPER2))
        mask = cv2.bitwise_or(mask1, mask2)

        total_pixels = roi.shape[0] * roi.shape[1]
        if total_pixels == 0:
            return -1.0

        ratio = np.count_nonzero(mask) / total_pixels
        return ratio

    def _check_and_use_potion(self):
        """
        캐릭터 HP를 확인하고 낮으면 물약 사용.
        쿨다운 시간 내에는 재사용하지 않음.
        """
        if not POTION_ENABLED:
            return

        now = time.time()

        # 확인 주기 체크
        if now - self._last_hp_check_time < POTION_CHECK_INTERVAL:
            return
        self._last_hp_check_time = now

        # 쿨다운 체크
        if now - self._last_potion_time < POTION_COOLDOWN:
            return

        frame = capture_screen(region=self.region)

        hp_ratio = self._measure_player_hp(frame)
        self.player_hp_ratio = hp_ratio

        mp_ratio = self._measure_player_mp(frame)
        self.player_mp_ratio = mp_ratio

        if hp_ratio < 0:
            log.debug("캐릭터 HP 측정 불가")
            return

        hp_str = f"{hp_ratio:.1%}"
        mp_str = f"{mp_ratio:.1%}" if mp_ratio >= 0 else "측정불가"
        log.debug(f"캐릭터 HP: {hp_str}, MP: {mp_str}")

        if hp_ratio <= POTION_HP_THRESHOLD:
            press_key(POTION_KEY_SCANCODE)
            self._last_potion_time = now
            log.info(f"물약 사용! (HP: {hp_ratio:.1%}, 임계값: {POTION_HP_THRESHOLD:.0%})")

    # ══════════════════════════════════════════════
    # 메인 사냥 루프
    # ══════════════════════════════════════════════

    def hunt_loop(self):
        """
        몬스터 사냥 루프.

        1. 게임 창 포그라운드 전환 (SendInput이 게임에 전달되도록)
        2. 캐릭터 HP 확인 → 낮으면 물약 사용
        3. 몬스터 감지 → 추적 시작
        4. 추적 중인 대상 클릭 (공격) — 빠른 반복
        5. 대상 소실(사망) → 아이템 줍기 → 다음 대상
        6. 연속 미발견 시 → 랜덤 방향 이동
        7. self.running=False까지 무한 반복
        """
        self.running = True
        log.info("사냥 루프 시작")

        # 최초 포그라운드 전환
        if ACTIVATE_WINDOW_ON_START:
            activate_window()
            self._last_activate_time = time.time()
            time.sleep(0.2)  # 포커스 전환 대기

        while self.running:
            try:
                # 주기적 포그라운드 확인 + 창 영역 갱신
                self._ensure_foreground()
                self._refresh_region()

                # 캐릭터 HP 확인 → 물약 자동 사용
                self._check_and_use_potion()

                pos, reason = self.tracker.find_and_track()

                if pos and reason == TRACK_OK:
                    self._miss_count = 0  # 발견 시 미발견 카운터 초기화
                    # 클릭 직전: 게임 창 포그라운드 확보 (UI가 위에 있으면 클릭이 UI에 감)
                    activate_window()
                    # 클릭 직전 ROI 재감지로 위치 보정 (~10ms)
                    refined = self.tracker.refine_position(original_pos=pos)
                    target = refined if refined else pos
                    click(target[0], target[1], method=self.click_method)
                    if refined:
                        log.info(f"공격: ({target[0]}, {target[1]}) (보정됨, 원본: {pos})")
                    else:
                        log.info(f"공격: ({target[0]}, {target[1]})")
                    # 가우시안 분포 딜레이 (균등분포보다 자연스러움)
                    delay = max(0.05, random.gauss(ATTACK_INTERVAL, 0.05))
                    time.sleep(delay)

                elif reason == TRACK_MISS_PENDING:
                    # 감지 대기 중 — 클릭 중단, 줍기 안 함, 짧게 대기 후 재탐색
                    time.sleep(0.1)

                elif reason == TRACK_KILLED:
                    self._miss_count = 0
                    # 대상 사망 → 아이템 줍기
                    log.info("대상 사망 추정 → 아이템 줍기")
                    self._loot_items()

                else:
                    # 미발견 또는 포기
                    self._miss_count += 1
                    if self._miss_count >= ROAM_AFTER_MISS_COUNT:
                        # 연속 미발견 → 랜덤 이동으로 몬스터 탐색
                        log.info(f"연속 {self._miss_count}회 미발견 → 랜덤 이동")
                        self._roam_random()
                        self._miss_count = 0
                    else:
                        log.info(f"대상 없음 (사유: {reason}), 재탐색 대기...")
                        time.sleep(DEFAULT_DELAY)

            except Exception as e:
                log.error(f"사냥 루프 예외 발생: {e}")
                time.sleep(1)

        log.info("사냥 루프 종료")

    def stop(self):
        self.running = False
        self.tracker.reset()
        self._miss_count = 0
        self.player_hp_ratio = -1.0
        self.player_mp_ratio = -1.0
        log.info("매크로 중지 요청")
