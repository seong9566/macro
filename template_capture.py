"""
템플릿 캡처/저장 유틸 — 순수 로직 (GUI 의존성 없음).

- imread_unicode / save_template: Windows 한글 경로 대응 이미지 I/O.
  (cv2.imread/imwrite는 한글 경로에서 조용히 실패하므로 np.fromfile +
   cv2.imdecode / cv2.imencode + open(wb) 조합으로 우회.)
- display_rect_to_image_rect: 미리보기(축소 표시) 좌표를 원본 이미지 좌표로 변환.
"""
import os
import cv2
import numpy as np


def imread_unicode(path, flags=cv2.IMREAD_COLOR):
    """
    한글 등 비ASCII 경로를 안전하게 읽는다.

    Returns:
        numpy.ndarray (BGR) 또는 None (파일 없음/디코드 실패).
    """
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, flags)
    except Exception:
        return None


def display_rect_to_image_rect(disp_rect, disp_size, img_size):
    """
    미리보기(축소 표시)에서 그린 사각형을 원본 이미지 좌표로 변환.

    Args:
        disp_rect: (x, y, w, h) 표시 좌표계 선택 영역
        disp_size: (disp_w, disp_h) 실제 표시된 픽스맵 크기
        img_size: (img_w, img_h) 원본 이미지 크기

    Returns:
        (x, y, w, h) 원본 좌표계 (경계로 클램프, 정수).
    """
    dx, dy, dw, dh = disp_rect
    disp_w, disp_h = disp_size
    img_w, img_h = img_size
    if disp_w <= 0 or disp_h <= 0:
        return (0, 0, 0, 0)

    sx = img_w / disp_w
    sy = img_h / disp_h
    x = int(round(dx * sx))
    y = int(round(dy * sy))
    w = int(round(dw * sx))
    h = int(round(dh * sy))

    x = max(0, min(x, img_w))
    y = max(0, min(y, img_h))
    w = max(0, min(w, img_w - x))
    h = max(0, min(h, img_h - y))
    return (x, y, w, h)


def save_template(frame_bgr, img_rect, target_dir, filename):
    """
    프레임에서 img_rect 영역을 잘라 target_dir/filename으로 저장 (한글 경로 안전).

    Raises:
        ValueError: 선택 영역이 비어 있음
        IOError: 인코딩/쓰기 실패
    """
    x, y, w, h = img_rect
    if w <= 0 or h <= 0:
        raise ValueError("선택 영역이 비어 있습니다")

    crop = frame_bgr[y:y + h, x:x + w]
    if crop.size == 0:
        raise ValueError("선택 영역이 비어 있습니다")

    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, filename)

    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        raise IOError(f"이미지 인코딩 실패: {path}")
    with open(path, "wb") as f:
        f.write(buf.tobytes())
    return path
