# Phase 2: 사이클 속도 최적화 (MEDIUM 우선순위)

## 목표
한 사이클(감지→클릭)의 총 소요시간을 250ms 이하로 단축한다.

---

## 2-1. 캡처 1회로 통합 (불필요한 이중 캡처 제거)

**문제:** `find_and_track()`에서 캡처 1회 + `refine_position()`에서 캡처 1회 = 매 사이클 2회 캡처 (+10~20ms)

**수정 방안:**
```python
# monster_tracker.py
def find_and_track(self):
    frame = capture_screen(region=self.region)
    self._last_frame = frame  # 캐싱
    ...

def refine_position(self, original_pos=None, frame=None):
    if frame is None:
        frame = self._last_frame or capture_screen(region=self.region)
    ...
```

```python
# macro_engine.py
refined = self.tracker.refine_position(original_pos=pos)
# refine_position 내부에서 self._last_frame 재사용
```

**수정 파일:**
- `monster_tracker.py` — `find_and_track()`, `refine_position()`
- 시그니처 변경 없음 (하위 호환)

**절감:** 10~20ms/사이클

---

## 2-2. BGRA→GRAY 직접 변환 (이중 변환 제거)

**문제:** `capture_screen()`에서 BGRA→BGR 변환 후, `detect_wolves()`에서 다시 BGR→GRAY 변환

**수정 방안:**
```python
# monster_tracker.py — capture_screen() 수정
def capture_screen(region=None, grayscale=False):
    ...
    img = np.array(screenshot)
    if grayscale:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
```

```python
# detect_wolves() 내부
frame_gray = capture_screen(region=region, grayscale=True)
# 기존: frame = capture → frame_gray = cvtColor(frame, BGR2GRAY)
# 변경: frame_gray = capture(grayscale=True)  ← 1단계로 줄임
```

**주의:** HP바 측정 등 BGR 프레임이 필요한 곳은 기존 방식 유지

**수정 파일:**
- `monster_tracker.py` — `capture_screen()`, `detect_wolves()`, `_detect_in_roi()`

**절감:** 1~3ms/사이클

---

## 2-3. 좌우 반전으로 템플릿 절반 (8장 → 4장)

**문제:** 8방향 템플릿 × 3스케일 = 24회 matchTemplate

**수정 방안:** 좌/우 대칭 쌍을 `cv2.flip()`으로 처리

```
원본 4장만 유지:
  monster_left.png      → cv2.flip() → monster_right.png
  monster_left_top.png  → cv2.flip() → monster_right_top.png
  monster_left_bottom.png → cv2.flip() → monster_right_bottom.png
  monster_top.png       → (반전 없음, 상하 대칭이면 bottom과 합칠 수도)
```

```python
# _load_templates() 수정
for fpath in glob.glob(...):
    tmpl = cv2.imread(fpath)
    tmpl_gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)
    templates.append((fpath, tmpl, tmpl_gray))
    
    # 좌우 반전 버전 자동 생성
    if "left" in os.path.basename(fpath):
        flipped = cv2.flip(tmpl, 1)  # 좌우 반전
        flipped_gray = cv2.flip(tmpl_gray, 1)
        flip_name = fpath.replace("left", "right")
        templates.append((flip_name, flipped, flipped_gray))
```

**수정 파일:**
- `monster_tracker.py` — `_load_templates()`
- `images/` — right 계열 4장 제거 가능 (또는 그대로 두고 로딩 시 자동 판단)

**절감:** matchTemplate 횟수 24회 → 12~15회 (40~50% 감소)

---

## 2-4. dxcam 화면 캡처 전환

**문제:** mss는 GDI BitBlt 기반으로 20~40 FPS 한계

**수정 방안:** dxcam (Desktop Duplication API) 사용으로 100+ FPS

```bash
pip install dxcam
```

```python
# monster_tracker.py — capture_screen() 교체
import dxcam

_camera = None

def _get_camera():
    global _camera
    if _camera is None:
        _camera = dxcam.create(output_color="BGR")
        _camera.start(target_fps=60, video_mode=True)
    return _camera

def capture_screen(region=None, grayscale=False):
    camera = _get_camera()
    if region:
        left, top, w, h = region
        frame = camera.get_latest_frame()
        if frame is None:
            return None
        # dxcam은 전체 화면 캡처 → region crop
        cropped = frame[top:top+h, left:left+w]
    else:
        cropped = camera.get_latest_frame()
    
    if cropped is None:
        return None
    if grayscale:
        return cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    return cropped
```

**주의사항:**
- dxcam은 Windows 전용 (현재 프로젝트도 Windows 전용이므로 OK)
- GPU 드라이버 필요 (대부분 게임 PC에 이미 설치됨)
- mss를 폴백으로 유지 (dxcam 초기화 실패 시)

**수정 파일:**
- `monster_tracker.py` — `capture_screen()` 교체
- `image_finder.py` — 동일 함수가 있으므로 통합 또는 동기화
- `requirements.txt` — `dxcam` 추가

**절감:** 캡처 10~20ms → 2~5ms

---

## 예상 결과

| 지표 | Phase 1 완료 후 | Phase 2 완료 후 |
|---|---|---|
| 캡처 속도 | 10~20ms | 2~5ms (dxcam) |
| 이중 캡처 | 2회/사이클 | 1회/사이클 |
| 색상 변환 | BGRA→BGR→GRAY | BGRA→GRAY (직접) |
| 템플릿 매칭 횟수 | 24회 | 12~15회 |
| **총 사이클 (ROI 히트)** | **~200ms** | **~80~130ms** |
| **총 사이클 (전체 탐색)** | **~150~250ms** | **~100~180ms** |
