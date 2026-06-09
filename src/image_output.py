from PIL import Image, ImageDraw, ImageFont
import os


def _load_font(font_path, size, bold=False):
    """加载字体，bold 时尝试加粗"""
    if font_path and os.path.isfile(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def text_to_image(
    lines: list[str],
    font_path: str | None = None,
    font_size: int = 20,
    padding: int = 20,
    line_spacing: int = 8,
    bg_color: str = "white",
    text_color: str = "black",
):
    font = _load_font(font_path, font_size)

    temp_img = Image.new("RGB", (1, 1))
    try:
        temp_draw = ImageDraw.Draw(temp_img)

        max_width = 0
        total_height = 0
        line_heights = []
        for line in lines:
            bbox = temp_draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            max_width = max(max_width, w)
            line_heights.append(h)
            total_height += h
    finally:
        temp_img.close()

    total_height += line_spacing * (len(lines) - 1)

    img_w = max_width + padding * 2
    img_h = total_height + padding * 2

    img = Image.new("RGB", (img_w, img_h), bg_color)
    draw = ImageDraw.Draw(img)

    y = padding
    for i, line in enumerate(lines):
        draw.text((padding, y), line, font=font, fill=text_color)
        y += line_heights[i] + line_spacing

    return img


def styled_text_to_image(
    blocks: list[dict],
    font_path: str | None = None,
    padding: int = 30,
    bg_color: str = "white",
    text_color: str = "black",
    max_width: int | None = None,
) -> Image.Image:
    """
    将多样式文本块渲染为图片。

    每个 block 是一个 dict，支持的字段：
      - text: 文本内容
      - style: "title" | "subtitle" | "heading" | "body" | "small" | "separator" | "blank"
      - color: 覆盖默认文字颜色（可选）
      - indent: 缩进像素（可选，默认 0）
    """
    # 预定义字体大小
    style_sizes = {
        "title": 28,
        "subtitle": 18,
        "heading": 22,
        "body": 18,
        "small": 15,
        "price_list_row": 15,
        "separator": 0,
        "blank": 0,
    }
    style_spacing_after = {
        "title": 16,
        "subtitle": 12,
        "heading": 10,
        "body": 6,
        "small": 4,
        "price_list_row": 4,
        "separator": 12,
        "blank": 8,
    }

    # 预加载字体
    fonts = {}
    for style, size in style_sizes.items():
        if size > 0:
            fonts[style] = _load_font(font_path, size)

    # 第一遍：计算尺寸
    temp_img = Image.new("RGB", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)

    content_width = 0
    total_height = padding

    for block in blocks:
        style = block.get("style", "body")
        text = block.get("text", "")
        indent = block.get("indent", 0)

        if style == "separator":
            total_height += 8  # 分隔线高度
        elif style == "blank":
            total_height += style_spacing_after["blank"]
        elif style == "price_list_row":
            font = fonts.get(style, fonts["small"])
            columns = block.get("columns", [])
            x = 0
            max_h = 0
            for col in columns:
                text = str(col.get("text", ""))
                width = int(col.get("width", 8))
                col_w = max(width, len(text)) * max(temp_draw.textlength("0", font=font), 1)
                bbox = temp_draw.textbbox((0, 0), text, font=font)
                max_h = max(max_h, bbox[3] - bbox[1])
                x += int(col_w) + 12
            content_width = max(content_width, x + indent)
            total_height += max_h
        else:
            font = fonts.get(style, fonts["body"])
            bbox = temp_draw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            content_width = max(content_width, w + indent)
            total_height += h

        total_height += style_spacing_after.get(style, 6)

    temp_img.close()

    total_height += padding  # 底部 padding

    if max_width and content_width + padding * 2 < max_width:
        img_w = max_width
    else:
        img_w = content_width + padding * 2
    img_h = total_height

    img = Image.new("RGB", (img_w, img_h), bg_color)
    draw = ImageDraw.Draw(img)

    y = padding
    for block in blocks:
        style = block.get("style", "body")
        text = block.get("text", "")
        color = block.get("color", text_color)
        indent = block.get("indent", 0)

        if style == "separator":
            sep_y = y + 4
            draw.line([(padding, sep_y), (img_w - padding, sep_y)], fill="#cccccc", width=2)
            y += 8 + style_spacing_after["separator"]
        elif style == "blank":
            y += style_spacing_after["blank"]
        elif style == "price_list_row":
            font = fonts.get(style, fonts["small"])
            columns = block.get("columns", [])
            x = padding + indent
            max_h = 0
            digit_w = max(draw.textlength("0", font=font), 1)
            for col in columns:
                text = str(col.get("text", ""))
                width = int(col.get("width", 8))
                col_w = int(max(width, len(text)) * digit_w)
                text_w = draw.textlength(text, font=font)
                tx = x + max(col_w - text_w, 0) if col.get("align") == "right" else x
                draw.text((tx, y), text, font=font, fill=color)
                bbox = draw.textbbox((tx, y), text, font=font)
                max_h = max(max_h, bbox[3] - bbox[1])
                x += col_w + 12
            y += max_h + style_spacing_after.get(style, 6)
        else:
            font = fonts.get(style, fonts["body"])
            draw.text((padding + indent, y), text, font=font, fill=color)
            bbox = draw.textbbox((padding + indent, y), text, font=font)
            y += (bbox[3] - bbox[1]) + style_spacing_after.get(style, 6)

    return img


def save_text_image(
    lines: list[str],
    output_path: str,
    **kwargs,
) -> str:
    img = text_to_image(lines, **kwargs)
    img.save(output_path)
    return output_path


def save_styled_image(
    blocks: list[dict],
    output_path: str,
    **kwargs,
) -> str:
    img = styled_text_to_image(blocks, **kwargs)
    img.save(output_path)
    return output_path
