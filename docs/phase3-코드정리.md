# Phase 3: 코드 정리 (LOW 우선순위)

> **상태: Codex 리뷰 반영하여 계획 수정 완료**
> - 3-2 (INTER_AREA) 제거 — Phase 1에서 이미 반영됨
> - 3-3 (GetSystemMetrics 캐싱) 보류 — 모니터 핫플러그 위험
> - 3-5 확장 — hwnd + region 재획득까지 묶음

## 목표
데드 코드 제거, 유지보수성 향상, 런타임 안정성 강화.

---

## 3-1. 윈도우 핸들 검증 + 창/region 자동 재획득 (최우선)

**문제:** `_last_hwnd`가 무효 핸들(게임 재시작)이면 `SetForegroundWindow` 실패. 또한 `main.py`가 시작 시 1회만 region을 잡고, `MacroEngine`이 그 좌표를 계속 사용 → 창 이동/크기 변경 시 좌표 stale.

**수정 방안:**
```python
# window_manager.py — activate_window() 확장
def activate_window(hwnd=None):
    target = hwnd or _last_hwnd
    if target is None or not user32.IsWindow(target):
        _last_hwnd = None
        log.warning("게임 창 핸들 무효 → 재탐색")
        return False
    ...

# macro_engine.py — hunt_loop() 내 주기적 region 재획득
def _refresh_region(self):
    """주기적으로 게임 창 위치/크기 재확인."""
    new_region = get_game_region(GAME_WINDOW_TITLE)
    if new_region and new_region != self.region:
        self.region = new_region
        self.tracker.region = new_region
        log.info(f"게임 창 영역 갱신: {new_region}")
```

**수정 파일:**
- `window_manager.py` — `IsWindow` 검증 + 재탐색
- `macro_engine.py` — 30초마다 `_refresh_region()` 호출
- `config.py` — `REGION_REFRESH_INTERVAL = 30.0` 추가

---

## 3-2. CSRT 트래커 데드코드 제거

**문제:** `find_and_track()`이 매번 템플릿 재감지 사용. CSRT 관련 ~100줄 미사용. 외부 참조 없음 확인됨 (Codex 전역 검색).

**제거 대상:**
- `create_tracker()` 함수
- `MonsterTracker.start_tracking()`, `.update()`, `._verify_tracking()`
- `self.tracker`, `self.track_frame_count`, `self.verify_interval`
- `self.verify_fail_count`, `self.verify_fail_max`
- `self.lost_count`, `self.max_lost`

**추가:** `self.tracking` → `self.has_target` 리네이밍 (의미 명확화)

**주의:** `CLAUDE.md`의 CSRT 관련 설명도 함께 업데이트

---

## 3-3. 좌표계 통일

**문제:** `find_and_track()`에서 프레임 로컬→스크린 절대 변환 후, `_detect_nearest_available()`에서 다시 로컬로 변환. 왕복 변환이 유지보수 시 버그 유발.

**수정 방안:** 공통 헬퍼 함수로 변환 일원화
```python
# monster_tracker.py에 추가
def _local_to_screen(self, x, y):
    """프레임 로컬 좌표 → 스크린 절대 좌표."""
    if self.region:
        return x + self.region[0], y + self.region[1]
    return x, y

def _bbox_center_screen(self, bbox):
    """bbox의 중심을 스크린 절대 좌표로 반환."""
    cx = bbox[0] + bbox[2] // 2
    cy = bbox[1] + bbox[3] // 2
    return self._local_to_screen(cx, cy)
```

**적용 대상:** `find_and_track`, `_detect_nearest_available`, `refine_position`, `_is_skipped`

---

## 3-4. 템플릿 캐시 무효화 지원

**문제:** `_template_cache`가 프로그램 수명 동안 갱신 불가.

**수정 방안:** 명시적 `clear_template_cache()` 함수 추가 (reset에 자동 연동하지 않음)
```python
def clear_template_cache():
    global _template_cache
    _template_cache = {}
    log.info("템플릿 캐시 초기화")
```

---

## 보류/제거 항목

| 항목 | 상태 | 사유 |
|---|---|---|
| ~~3-2 원본: INTER_AREA~~ | **제거** | Phase 1에서 이미 적용 완료 |
| ~~3-3 원본: GetSystemMetrics 캐싱~~ | **보류** | 모니터 핫플러그 시 stale 위험, 이득 미미 |

---

## 수정된 우선순위

| 순서 | 항목 | 효과 |
|---|---|---|
| 1 | hwnd 검증 + region 재획득 | 게임 재시작/창 이동 시 자동 복구 |
| 2 | CSRT 데드코드 제거 | ~100줄 삭제, 상태 단순화 |
| 3 | 좌표계 통일 | 유지보수성, 버그 예방 |
| 4 | 캐시 무효화 | 개발 편의성 |
