# Phase 3: 코드 정리 (LOW 우선순위)

## 목표
데드 코드 제거, 미세 최적화, 유지보수성 향상.

---

## 3-1. CSRT 트래커 데드 코드 제거

**문제:** `find_and_track()`이 매번 템플릿 재감지를 사용하므로 CSRT 트래커 코드 ~100줄이 미사용

**제거 대상:**
```
monster_tracker.py:
  - create_tracker() 함수 전체
  - MonsterTracker.start_tracking() 메서드
  - MonsterTracker.update() 메서드
  - MonsterTracker._verify_tracking() 메서드
  - self.tracker 속성
  - self.track_frame_count 속성
  - self.verify_interval 속성
  - self.verify_fail_count 속성
  - self.verify_fail_max 속성
  - self.lost_count 속성
  - self.max_lost 속성
```

**수정 파일:**
- `monster_tracker.py` — 상기 코드 제거
- `self.tracking` → `self.has_target`으로 리네이밍 (의미 명확화)

**효과:** 코드 ~100줄 감소, 유지보수 혼란 제거

---

## 3-2. cv2.resize 다운스케일 시 INTER_AREA 적용

**문제:** 기본 `INTER_LINEAR`은 다운스케일 시 앨리어싱 발생 → 매칭 정확도 미세 저하

**수정 방안:**
```python
# monster_tracker.py — detect_wolves(), _detect_in_roi() 내부
# 기존:
resized = cv2.resize(tmpl_gray, (sw, sh))
# 변경:
interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
resized = cv2.resize(tmpl_gray, (sw, sh), interpolation=interp)
```

**수정 파일:**
- `monster_tracker.py` — `detect_wolves()`, `_detect_in_roi()` 내 resize 호출

**효과:** 축소 매칭 정확도 미세 향상

---

## 3-3. GetSystemMetrics 캐싱

**문제:** `click_sendinput()` 호출마다 `GetSystemMetrics()` 4회 호출 — 값은 모니터 구성 변경 전까지 동일

**수정 방안:**
```python
# clicker.py — 모듈 수준 캐시
_VIRT_X = ctypes.windll.user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
_VIRT_Y = ctypes.windll.user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
_VIRT_W = ctypes.windll.user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
_VIRT_H = ctypes.windll.user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN

def click_sendinput(x, y):
    cx = max(_VIRT_X, min(x, _VIRT_X + _VIRT_W - 1))
    cy = max(_VIRT_Y, min(y, _VIRT_Y + _VIRT_H - 1))
    abs_x = int((cx - _VIRT_X) * 65535 / (_VIRT_W - 1))
    abs_y = int((cy - _VIRT_Y) * 65535 / (_VIRT_H - 1))
    ...
```

**수정 파일:**
- `clicker.py` — 모듈 상단에 캐시 변수, `click_sendinput()` 내부 참조 변경

**효과:** 클릭당 ~0.1ms 절감 (미세하지만 깔끔)

---

## 3-4. 템플릿 캐시 무효화 지원

**문제:** `_template_cache`가 프로그램 수명 동안 갱신 불가 → 개발 중 이미지 교체 시 재시작 필요

**수정 방안:**
```python
# monster_tracker.py
def clear_template_cache():
    """템플릿 캐시 초기화. 이미지 교체 후 호출."""
    global _template_cache
    _template_cache = {}
    log.info("템플릿 캐시 초기화")

# MonsterTracker.reset()에서 호출
def reset(self):
    ...
    clear_template_cache()
```

**수정 파일:**
- `monster_tracker.py` — `clear_template_cache()` 함수 추가, `reset()` 연동

**효과:** 개발 편의성 향상

---

## 3-5. 윈도우 핸들 유효성 검증

**문제:** `_last_hwnd`가 무효 핸들(게임 재시작)인 경우 `SetForegroundWindow` 실패

**수정 방안:**
```python
# window_manager.py — activate_window() 내부
if not user32.IsWindow(target):
    _last_hwnd = None
    log.warning("게임 창 핸들 무효 → 재탐색 필요")
    return False
```

**수정 파일:**
- `window_manager.py` — `activate_window()` 시작부에 `IsWindow` 검증

**효과:** 게임 재시작 후 매크로가 자동으로 새 창을 감지

---

## 3-6. 좌표계 통일 (선택)

**문제:** `find_and_track()`에서 프레임 로컬 좌표를 스크린 절대 좌표로 변환 후, `_detect_nearest_available()`에서 다시 로컬로 변환 — 왕복 변환이 혼란 유발

**수정 방안:**
- 내부 처리는 모두 **프레임 로컬 좌표**로 통일
- 스크린 절대 좌표 변환은 **최종 반환 시점에서만** 수행

**수정 파일:**
- `monster_tracker.py` — `find_and_track()`, `_detect_nearest_available()`

**효과:** 유지보수성 향상, 좌표 관련 버그 예방

---

## 전체 Phase 예상 결과 (Phase 1+2+3 완료 후)

| 지표 | 최초 상태 | 최종 목표 |
|---|---|---|
| 사이클 속도 (ROI 히트) | ~250ms | ~80ms |
| 사이클 속도 (전체 탐색) | ~350~630ms | ~100~180ms |
| 유령 클릭 | 3프레임 | 0프레임 |
| ROI 성공률 | ~60% | ~85% |
| HP 변화 오판 | 빈번 | 최소 |
| 데드 코드 | ~100줄 | 0줄 |
| 캡처 방식 | mss (20~40fps) | dxcam (100+fps) |
| 템플릿 수 | 8장 | 4장 (+자동 반전) |
