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
