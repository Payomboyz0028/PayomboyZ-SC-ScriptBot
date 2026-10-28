# -*- coding: utf-8 -*-
"""
PAYOMBØYZ Procedural CAPTCHA Engine
Generates stylized distorted visual challenge images matching PAYOMBØYZ Verification aesthetics.
"""

from __future__ import annotations
import io
import math
import random
import string
from typing import Tuple
from PIL import Image, ImageDraw, ImageFont

# Exclude ambiguous characters like O, 0, I, 1, L to provide seamless UX
CAPTCHA_CHARACTERS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

def _find_system_font(size: int = 48) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Attempts to load a bold modern font on Windows/Linux, falling back to default."""
    font_candidates = [
        r"C:\Windows\Fonts\consolab.ttf",   # Consolas Bold
        r"C:\Windows\Fonts\segoeuib.ttf",   # Segoe UI Bold
        r"C:\Windows\Fonts\arialbd.ttf",    # Arial Bold
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    ]
    for font_path in font_candidates:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def generate_captcha_image(length: int = 5) -> Tuple[str, io.BytesIO]:
    """
    Generates a stylized CAPTCHA image with:
    - 5 random characters
    - Dark neon cosmic background (#0B0F19)
    - Cyan/Teal interference lines cutting through the characters
    - Random noise particles
    - Per-character jitter and color variation
    """
    # 1. Generate random code
    code = "".join(random.choices(CAPTCHA_CHARACTERS, k=length))
    
    width, height = 380, 130
    img = Image.new("RGBA", (width, height), (11, 15, 25, 255))
    draw = ImageDraw.Draw(img)

    # 2. Draw subtle border
    draw.rectangle([1, 1, width - 2, height - 2], outline=(30, 50, 80, 255), width=1)

    # 3. Add cosmic background star noise
    for _ in range(120):
        nx = random.randint(2, width - 3)
        ny = random.randint(2, height - 3)
        alpha = random.randint(40, 180)
        color = random.choice([
            (255, 255, 255, alpha),
            (100, 200, 255, alpha),
            (160, 100, 255, alpha)
        ])
        draw.point((nx, ny), fill=color)

    # 4. Render Characters with individual rotation and spacing
    font = _find_system_font(size=46)
    
    char_spacing = (width - 60) // length
    start_x = 30
    base_y = (height // 2) - 30

    for i, char in enumerate(code):
        # Character image canvas for rotation
        char_img = Image.new("RGBA", (70, 70), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)

        # Crisp white with subtle cyan accent
        char_color = random.choice([
            (255, 255, 255, 255),
            (230, 245, 255, 255),
            (210, 235, 255, 255)
        ])
        
        char_draw.text((15, 8), char, fill=char_color, font=font)

        # Random subtle angle rotation (-12 to +12 degrees)
        rot_angle = random.uniform(-12, 12)
        rotated_char = char_img.rotate(rot_angle, expand=True, resample=Image.BICUBIC)

        cx = start_x + (i * char_spacing) + random.randint(-4, 4)
        cy = base_y + random.randint(-4, 4)
        img.paste(rotated_char, (cx, cy), rotated_char)

    # 5. Draw Cyan/Teal Horizontal Distorting Interference Lines
    # Matches the exact style shown in the reference screenshot
    line_y_base = height // 2
    for offset_y in [-18, -6, 8, 20]:
        y = line_y_base + offset_y + random.randint(-2, 2)
        line_color = random.choice([
            (70, 200, 240, 210),   # Cyan
            (100, 220, 255, 220),  # Light cyan
            (50, 160, 220, 190)    # Deep cyan
        ])
        # Draw multi-segment wave line
        points = []
        for x in range(0, width, 20):
            wave_y = y + int(math.sin(x * 0.05) * 3)
            points.append((x, wave_y))
        
        for p_idx in range(len(points) - 1):
            draw.line([points[p_idx], points[p_idx + 1]], fill=line_color, width=random.choice([1, 2]))

    # 6. Save to BytesIO buffer
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return code, buffer
