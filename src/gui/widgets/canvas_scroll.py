def _scrollregion_height(canvas) -> float | None:
    try:
        x1, y1, x2, y2 = map(float, str(canvas.cget("scrollregion")).split())
    except (TypeError, ValueError):
        return None
    return max(0.0, y2 - y1)


def scroll_canvas_units_clamped(canvas, units: int) -> bool:
    if units == 0:
        return False
    try:
        if not canvas.winfo_exists():
            return False
        content_height = _scrollregion_height(canvas)
        if content_height is not None and content_height <= float(canvas.winfo_height()):
            canvas.yview_moveto(0.0)
            return False
        first, last = canvas.yview()
    except Exception:
        return False

    if first <= 0.0 and units < 0:
        canvas.yview_moveto(0.0)
        return False
    if last >= 1.0 and units > 0:
        canvas.yview_moveto(1.0)
        return False

    canvas.yview_scroll(units, "units")
    try:
        first, last = canvas.yview()
        if first < 0.0:
            canvas.yview_moveto(0.0)
        elif last > 1.0:
            canvas.yview_moveto(1.0)
    except Exception:
        pass
    return True
