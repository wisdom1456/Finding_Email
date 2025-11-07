from __future__ import annotations

import cv2
import numpy as np


def correct_rotation(image: np.ndarray, osd_data: dict) -> np.ndarray:
    """Corrects the rotation of an image based on OSD data."""
    angle = osd_data["rotate"]
    if angle != 0:
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, -angle, 1.0)
        # Use a white border to avoid black edges
        image = cv2.warpAffine(
            image,
            M,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )
    return image
