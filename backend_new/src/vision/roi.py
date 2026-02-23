from __future__ import annotations

from typing import List, Tuple


def bbox_center(bbox: Tuple[float, float, float, float]) -> Tuple[int, int]:
    x1, y1, x2, y2 = bbox
    return int((x1 + x2) / 2), int((y1 + y2) / 2)


def point_in_polygon(x: int, y: int, polygon: List[List[int]]) -> bool:
    """Ray casting algorithm."""
    if not polygon or len(polygon) < 3:
        return True

    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside
