"""HP/MP 바 위치 디버그 — 게임 실행 중에 실행하세요."""
import cv2
import numpy as np
from screen_capture import capture_screen
from window_manager import get_game_region

region = get_game_region("온라인삼국지")
print(f"게임 영역: {region}")

frame = capture_screen(region=region)
if frame is None:
    print("캡처 실패")
    exit()

print(f"프레임 크기: {frame.shape}")  # (h, w, ch)

# 1) 전체 좌상단 영역 저장
top_left = frame[0:160, 0:400]
cv2.imwrite("debug_1_top_left.png", top_left)

# 2) 현재 config 좌표로 HP/MP 영역 표시
marked = frame[0:160, 0:400].copy()
# HP (115, 20, 190, 13) — 빨간 사각형
cv2.rectangle(marked, (115, 20), (115+190, 20+13), (0, 0, 255), 2)
cv2.putText(marked, "HP config", (115, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
# MP (115, 42, 190, 10) — 파란 사각형
cv2.rectangle(marked, (115, 42), (115+190, 42+10), (255, 0, 0), 2)
cv2.putText(marked, "MP config", (115, 39), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
cv2.imwrite("debug_2_marked.png", marked)

# 3) 현재 HP 영역의 HSV 분석
bx, by, bw, bh = (115, 20, 190, 13)
hp_roi = frame[by:by+bh, bx:bx+bw]
if hp_roi.size > 0:
    hsv = cv2.cvtColor(hp_roi, cv2.COLOR_BGR2HSV)
    print(f"\n=== HP 영역 (115, 20, 190, 13) ===")
    print(f"  BGR mean: {hp_roi.mean(axis=(0,1))}")
    print(f"  HSV min:  {hsv.min(axis=(0,1))}")
    print(f"  HSV max:  {hsv.max(axis=(0,1))}")
    print(f"  HSV mean: {hsv.mean(axis=(0,1))}")
    cv2.imwrite("debug_3_hp_roi.png", hp_roi)

# 4) 현재 MP 영역의 HSV 분석
bx, by, bw, bh = (115, 42, 190, 10)
mp_roi = frame[by:by+bh, bx:bx+bw]
if mp_roi.size > 0:
    hsv = cv2.cvtColor(mp_roi, cv2.COLOR_BGR2HSV)
    print(f"\n=== MP 영역 (115, 42, 190, 10) ===")
    print(f"  BGR mean: {mp_roi.mean(axis=(0,1))}")
    print(f"  HSV min:  {hsv.min(axis=(0,1))}")
    print(f"  HSV max:  {hsv.max(axis=(0,1))}")
    print(f"  HSV mean: {hsv.mean(axis=(0,1))}")
    cv2.imwrite("debug_4_mp_roi.png", mp_roi)

# 5) 빨간색 픽셀 히트맵 (넓은 영역에서)
wide = frame[0:100, 0:350]
hsv_wide = cv2.cvtColor(wide, cv2.COLOR_BGR2HSV)
mask1 = cv2.inRange(hsv_wide, np.array([0, 100, 100]), np.array([10, 255, 255]))
mask2 = cv2.inRange(hsv_wide, np.array([170, 100, 100]), np.array([180, 255, 255]))
red_mask = cv2.bitwise_or(mask1, mask2)
cv2.imwrite("debug_5_red_mask.png", red_mask)

# 6) 파란색 픽셀 히트맵
mask_b1 = cv2.inRange(hsv_wide, np.array([100, 80, 80]), np.array([130, 255, 255]))
mask_b2 = cv2.inRange(hsv_wide, np.array([130, 80, 80]), np.array([160, 255, 255]))
blue_mask = cv2.bitwise_or(mask_b1, mask_b2)
cv2.imwrite("debug_6_blue_mask.png", blue_mask)

print(f"\n빨간 픽셀 수 (전체 상단): {np.count_nonzero(red_mask)}/{red_mask.size}")
print(f"파란 픽셀 수 (전체 상단): {np.count_nonzero(blue_mask)}/{blue_mask.size}")

print("\n디버그 이미지 6개 저장 완료:")
print("  debug_1_top_left.png    — 좌상단 원본")
print("  debug_2_marked.png      — HP/MP config 사각형 표시")
print("  debug_3_hp_roi.png      — 현재 HP 영역 크롭")
print("  debug_4_mp_roi.png      — 현재 MP 영역 크롭")
print("  debug_5_red_mask.png    — 빨간색 히트맵 (HP 바 위치 확인)")
print("  debug_6_blue_mask.png   — 파란색 히트맵 (MP 바 위치 확인)")
