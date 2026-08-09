"""生成应用图标：assets/icon.ico（多尺寸）与 assets/icon.png（256px）。

用 PySide6 的 QSvgRenderer 将 assets/icon.svg 栅格化为各尺寸 PNG，
再用 Pillow 合成 Windows 多尺寸 ICO。依赖均为项目已有依赖，可直接运行：

    .\\.venv\\Scripts\\python.exe scripts\\generate_icon.py
"""
import os
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / "assets" / "icon.svg"
ICO_PATH = ROOT / "assets" / "icon.ico"
PNG_PATH = ROOT / "assets" / "icon.png"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _render_image(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def _to_png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(buffer.data())


def main() -> int:
    if not SVG_PATH.is_file():
        print(f"[ERROR] missing source SVG: {SVG_PATH}")
        return 1

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        print(f"[ERROR] invalid SVG: {SVG_PATH}")
        return 1

    frames = [
        Image.open(BytesIO(_to_png_bytes(_render_image(renderer, size)))).convert("RGBA")
        for size in ICO_SIZES
    ]
    frames[-1].save(
        ICO_PATH,
        format="ICO",
        append_images=frames[:-1],
    )
    frames[-1].save(PNG_PATH, format="PNG")

    with Image.open(ICO_PATH) as ico:
        print(f"[OK] {ICO_PATH} sizes={ico.info['sizes']}")
    print(f"[OK] {PNG_PATH} ({PNG_PATH.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
