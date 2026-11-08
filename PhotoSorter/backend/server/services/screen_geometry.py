"""Perspective-independent pixel geometry of four ordered screen corners.

Expected order: top-left, top-right, bottom-right, bottom-left around
the visible quadrilateral; convexity checks also reject crossed segments.
Coordinates are EXIF-oriented original pixels, not UI-scaled coordinates.
"""
from __future__ import annotations
import math

def validate(corners: list[dict], band_width_px: float, width: int, height: int) -> list[dict]:
    if len(corners) != 4:
        raise ValueError("Укажите ровно четыре угла экрана")
    points = []
    for point in corners:
        x, y = float(point["x"]), float(point["y"])
        if not math.isfinite(x) or not math.isfinite(y) or not (0 <= x <= width and 0 <= y <= height):
            raise ValueError("Углы экрана должны находиться внутри исходного изображения")
        points.append((x, y))
    cross = []
    for i in range(4):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % 4]
        x3, y3 = points[(i + 2) % 4]
        if math.hypot(x2 - x1, y2 - y1) < 2:
            raise ValueError("Соседние точки экрана слишком близко")
        cross.append((x2-x1)*(y3-y2) - (y2-y1)*(x3-x2))
    if not (all(v > 0 for v in cross) or all(v < 0 for v in cross)):
        raise ValueError("Контур должен быть выпуклым и не пересекаться")
    area = abs(sum(points[i][0]*points[(i+1)%4][1] -
                   points[(i+1)%4][0]*points[i][1] for i in range(4))) / 2
    if area < max(32, width * height * 0.000001):
        raise ValueError("Площадь экрана слишком мала")
    if not math.isfinite(band_width_px) or not (1 <= band_width_px <= min(width,height)*0.25):
        raise ValueError("Недопустимая толщина полосы поиска")
    return [{"x":x,"y":y} for x,y in points]
