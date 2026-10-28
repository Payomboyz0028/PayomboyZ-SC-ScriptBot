# -*- coding: utf-8 -*-
"""
💎 SC-HUB Dynamic Welcome Card & Verification Announcement Engine
Renders ultra-high quality anime-cyber welcome banners using Pillow and dispatches
luxury welcome embeds to the dedicated welcome channel (1563251676830236782).
"""

from __future__ import annotations
import io
import time
import os
import aiohttp
import asyncio
from typing import Optional, Tuple
from pathlib import Path
import discord
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import config
from database import db

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "assets" / "welcome_bg_template.jpg"

_RECENTLY_WELCOMED: dict[int, float] = {}


def _get_font(font_path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Safely loads a FreeType font with graceful fallback."""
    if os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    for fb in ("C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(fb):
            try:
                return ImageFont.truetype(fb, size)
            except Exception:
                pass
    return ImageFont.load_default()


async def fetch_avatar_bytes(member: discord.Member | discord.User) -> Optional[bytes]:
    """Downloads member avatar as PNG bytes with error tolerance."""
    try:
        url = str(member.display_avatar.replace(format="png", size=256).url)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as e:
        print(f"[-] [WELCOME] Could not fetch avatar for {member}: {e}")
    return None


def generate_welcome_banner(
    avatar_bytes: Optional[bytes],
    display_name: str,
    username: str,
    member_count: int
) -> io.BytesIO:
    """
    Renders an 8K-styled anime welcome banner featuring:
    - Red blood moon & torii gate aesthetic background
    - Obsidian HUD panel with gold corner-bracket frame
    - High-res antialiased circular avatar with gold border
    - Green verified badge with crisp white checkmark
    - Clean typography (WELCOME, display name, member count, Sentinel subtitle)
    """
    if TEMPLATE_PATH.exists():
        try:
            base_img = Image.open(TEMPLATE_PATH).convert("RGBA")
        except Exception:
            base_img = Image.new("RGBA", (1024, 576), (12, 14, 20, 255))
    else:
        base_img = Image.new("RGBA", (1024, 576), (12, 14, 20, 255))

    w, h = base_img.size
    cx = w // 2
    cy = int(h * 0.44)  # Vertically aligned inside the obsidian frame
    r = 55             # Avatar radius (110px diameter)

    # 1. Circular Avatar Composition
    if avatar_bytes:
        try:
            raw_av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av_resized = raw_av.resize((r * 2, r * 2), Image.Resampling.LANCZOS)
        except Exception:
            av_resized = Image.new("RGBA", (r * 2, r * 2), (40, 50, 75, 255))
    else:
        av_resized = Image.new("RGBA", (r * 2, r * 2), (40, 50, 75, 255))

    # High-quality antialiased circular mask (4x supersampling)
    scale = 4
    mask_large = Image.new("L", (r * 2 * scale, r * 2 * scale), 0)
    draw_mask = ImageDraw.Draw(mask_large)
    draw_mask.ellipse((0, 0, r * 2 * scale - 1, r * 2 * scale - 1), fill=255)
    mask = mask_large.resize((r * 2, r * 2), Image.Resampling.LANCZOS)

    base_img.paste(av_resized, (cx - r, cy - r), mask)

    draw = ImageDraw.Draw(base_img)

    # 2. Golden Ring around Avatar
    ring_color = (241, 196, 15, 255)
    draw.ellipse((cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), outline=ring_color, width=3)

    # 3. Green Verified Badge at bottom-right corner of circle
    bx = cx + int(r * 0.70)
    by = cy + int(r * 0.70)
    br = 15  # Badge radius
    draw.ellipse((bx - br, by - br, bx + br, by + br), fill=(0, 230, 118, 255), outline=(10, 12, 18, 255), width=2)
    # Checkmark inside badge
    check_coords = [(bx - 6, by), (bx - 2, by + 4), (bx + 6, by - 4)]
    draw.line(check_coords, fill=(255, 255, 255, 255), width=3)

    # 4. Typography Loading
    f_welcome = _get_font("C:/Windows/Fonts/arialbd.ttf", 26)
    f_name = _get_font("C:/Windows/Fonts/tahomabd.ttf", 24)       # Full Thai glyph support
    f_sub = _get_font("C:/Windows/Fonts/arialbd.ttf", 15)
    f_footer = _get_font("C:/Windows/Fonts/arial.ttf", 12)

    # 5. Text Placement (Precise HUD Centering)
    # Line 1: W E L C O M E (Gold)
    draw.text((cx, cy + r + 22), "W E L C O M E", fill=(241, 196, 15, 255), font=f_welcome, anchor="mm")

    # Line 2: Display Name (White)
    clean_display = display_name if len(display_name) <= 28 else display_name[:26] + "..."
    draw.text((cx, cy + r + 54), clean_display, fill=(255, 255, 255, 255), font=f_name, anchor="mm")

    # Line 3: Member Count & Username (Mint Cyan)
    clean_user = username if len(username) <= 20 else username[:18] + ".."
    sub_text = f"MEMBER #{member_count:,} • @{clean_user}"
    draw.text((cx, cy + r + 82), sub_text, fill=(0, 245, 212, 255), font=f_sub, anchor="mm")

    # Line 4: Sentinel Subtitle (Subtle Slate Gray)
    footer_text = "PAYOMBØYZ COMMUNITY • OFFICIAL MEMBER • SENTINEL v3.0"
    draw.text((cx, cy + r + 104), footer_text, fill=(136, 146, 176, 255), font=f_footer, anchor="mm")

    # 6. Save to BytesIO
    out_buf = io.BytesIO()
    base_img.convert("RGB").save(out_buf, format="PNG", quality=95)
    out_buf.seek(0)
    return out_buf


async def build_welcome_embed_and_banner(
    guild: discord.Guild,
    member: discord.Member,
    verified_role: Optional[discord.Role] = None,
    member_count: Optional[int] = None
) -> Tuple[str, discord.Embed, discord.File]:
    """
    Builds the complete welcome payload matching the reference visual aesthetic:
    - Text announcement: 🪽 ยินดีต้อนรับคุณ @User เข้าสู่เซิร์ฟเวอร์ PAYOMBØYZ ! 🪽
    - Embed with gold sidebar, author tag, member ID, ASCII decorative box, and timestamps
    - Dynamic welcome banner attachment
    """
    count = member_count or guild.member_count or 1
    now_ts = int(time.time())

    # Resolve verified role
    if not verified_role:
        cfg = db.get_guild_config(guild.id)
        vid = cfg.get("verified_role_id") or config.DEFAULT_VERIFIED_ROLE_ID
        verified_role = guild.get_role(vid)

    role_mention = verified_role.mention if verified_role else "@ยืนยันตัวตนแล้ว"

    # Outer message content
    message_content = f"🪽 **ยินดีต้อนรับคุณ {member.mention} เข้าสู่เซิร์ฟเวอร์ PAYOMBØYZ !** 🪽"

    # Embed Creation
    embed = discord.Embed(
        title=f"» • WELCOME {member.display_name} • «",
        color=config.COLOR_PRIMARY_GOLD
    )

    # Author
    embed.set_author(
        name=f"{member.name} [{member.id}]",
        icon_url=member.display_avatar.url
    )

    # Server Thumbnail (Logo)
    server_icon = guild.icon.url if guild.icon else "https://payomboyzcreative.online/assets/images/logo.png"
    embed.set_thumbnail(url=server_icon)

    # Description (Exact ASCII box layout from reference screenshot)
    desc_lines = [
        "╔═════════════════════════════════════════",
        "║",
        "╠══════════════════════════════╗",
        "║",
        f"• **ยินดีต้อนรับ** ➔ {member.mention}",
        f"({member.name})",
        f"• **ยศที่ได้รับ** ➔ {role_mention}",
        f"• **สมาชิกคนที่** ➔ `#{count:,}`",
        f"• **เวลาที่ยืนยัน** ➔ <t:{now_ts}:F>",
        f"( <t:{now_ts}:R> )",
        "║",
        "╚═════════════════════════════════════════",
        "   ══════════════════════════╝",
        "",
        "👑 **PAYOMBØYZ SENTINEL VERIFICATION PASSED**",
        "เข้าสู่ศูนย์รวม Script Hub, Auto Quest & เครื่องมือระดับพรีเมียม"
    ]
    embed.description = "\n".join(desc_lines)

    # Footer
    embed.set_footer(
        text="PAYOMBOYZ X WELCOME • PAYOMBØYZ COMMUNITY",
        icon_url=server_icon
    )

    # Fetch avatar bytes & render banner
    av_bytes = await fetch_avatar_bytes(member)
    banner_buf = generate_welcome_banner(
        avatar_bytes=av_bytes,
        display_name=member.display_name,
        username=member.name,
        member_count=count
    )

    card_file = discord.File(fp=banner_buf, filename="welcome_card.png")
    embed.set_image(url="attachment://welcome_card.png")

    return message_content, embed, card_file


async def send_welcome_announcement(
    guild: discord.Guild,
    member: discord.Member,
    verified_role: Optional[discord.Role] = None,
    channel_id: Optional[int] = None
) -> bool:
    """
    Sends the welcome announcement embed and card to the target welcome channel.
    Target Channel: 1563251676830236782
    Includes debounce prevention so the same user is not spammed within 60 seconds.
    """
    if not member or not guild:
        return False

    now = time.time()
    last = _RECENTLY_WELCOMED.get(member.id, 0)
    if now - last < 60:
        return False  # Debounced

    _RECENTLY_WELCOMED[member.id] = now

    cfg = db.get_guild_config(guild.id)
    ch_id = channel_id or cfg.get("welcome_channel_id") or getattr(config, "WELCOME_CHANNEL_ID", 1563251676830236782)

    channel = guild.get_channel(ch_id)
    if not isinstance(channel, discord.TextChannel):
        try:
            channel = await guild.fetch_channel(ch_id)
        except Exception as e:
            print(f"[-] [WELCOME] Could not find channel {ch_id}: {e}")
            return False

    if not isinstance(channel, discord.TextChannel):
        return False

    try:
        content, embed, file = await build_welcome_embed_and_banner(
            guild=guild,
            member=member,
            verified_role=verified_role
        )
        await channel.send(content=content, embed=embed, file=file)
        print(f"[+] [WELCOME] Dispatched welcome announcement for {member.name} ({member.id}) to #{channel.name}")
        return True
    except Exception as e:
        print(f"[-] [WELCOME] Failed to send welcome announcement: {e}")
        return False
