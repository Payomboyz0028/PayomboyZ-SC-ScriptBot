# -*- coding: utf-8 -*-
"""
💎 SC-HUB Member Join/Leave & Verification Audit Engine
Tracks members entering and leaving the server, specifically verifying whether
the departing or joining member has attained the Verified Member Role (1563251669662171216).
Logs to: 1563251902307901584
"""

from __future__ import annotations
import time
from typing import Optional
import discord

from config import MEMBER_AUDIT_CHANNEL_ID, DEFAULT_VERIFIED_ROLE_ID, COLOR_SUCCESS, COLOR_INFO
from database import db


async def get_audit_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    if not guild:
        return None
    ch = guild.get_channel(MEMBER_AUDIT_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        try:
            ch = await guild.fetch_channel(MEMBER_AUDIT_CHANNEL_ID)
        except Exception:
            ch = None
    return ch if isinstance(ch, discord.TextChannel) else None


async def log_member_join(guild: discord.Guild, member: discord.Member):
    """Logs when a new member joins the guild."""
    channel = await get_audit_channel(guild)
    if not channel:
        return

    # Update database daily counter
    db.increment_audit_stat("joins_count")

    created_ts = int(member.created_at.timestamp())
    now_ts = int(time.time())

    embed = discord.Embed(
        title="📥 สมาชิกใหม่เข้าร่วมเซิร์ฟเวอร์ (Member Joined)",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **สมาชิก:** {member.mention} (`{member.name}`)\n"
            f"🆔 **User ID:** `{member.id}`\n"
            f"📅 **สร้างบัญชีเมื่อ:** <t:{created_ts}:F> (<t:{created_ts}:R>)\n"
            f"⏰ **เข้าร่วมเมื่อ:** <t:{now_ts}:F>\n"
            f"🛡️ **สถานะยืนยันตัวตน:** `⏳ ยังไม่ยืนยันตัวตน (รอทำ Captcha ที่ห้อง #✅・รับยศสมาชิก)`\n"
            f"👥 **จำนวนสมาชิกทั้งหมด:** `{guild.member_count:,}` คน\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x2ECC71  # Green
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="💎 SC-HUB MEMBER AUDIT LOG • ระบบบันทึกคนเข้า-ออก")

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[-] [MEMBER AUDIT] Join log error: {e}")


async def log_member_remove(guild: discord.Guild, member: discord.Member | discord.User):
    """
    Logs when a member leaves or is kicked from the guild.
    Strictly audits whether the member held the Verified Role (1563251669662171216).
    """
    channel = await get_audit_channel(guild)
    if not channel:
        return

    # Update database daily counter
    db.increment_audit_stat("leaves_count")

    now_ts = int(time.time())

    # Check whether they possessed the Verified Role
    cfg = db.get_guild_config(guild.id)
    verified_role_id = cfg.get("verified_role_id") or DEFAULT_VERIFIED_ROLE_ID
    
    is_verified = False
    roles_list = []

    if isinstance(member, discord.Member):
        is_verified = any(r.id == verified_role_id for r in member.roles)
        roles_list = [r.name for r in member.roles if r.name != "@everyone"]

    if is_verified:
        status_text = "✅ **สมาชิกทางการ (ผ่านการยืนยันตัวตนแล้ว)**"
        color = 0xE67E22  # Orange for verified member departure
        verdict = "⚠️ สมาชิกที่มีบทบาท Verified ออกจากเซิร์ฟเวอร์"
    else:
        status_text = "❌ **ยังไม่ผ่านการยืนยันตัวตน (Unverified / บุคคลทั่วไป / บอท)**"
        color = 0x95A5A6  # Grey for unverified
        verdict = "⚪ บุคคลทั่วไปออกจากเซิร์ฟเวอร์โดยยังไม่ได้ยืนยันตัวตน"

    roles_str = ", ".join(f"`{r}`" for r in roles_list[:8]) if roles_list else "ไม่มีบทบาทพิเศษ"

    embed = discord.Embed(
        title="📤 สมาชิกออกจากเซิร์ฟเวอร์ (Member Left)",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **สมาชิก:** `{member.name}` (ID: `{member.id}`)\n"
            f"🏷️ **ผลการตรวจสอบยศ:** {verdict}\n"
            f"🛡️ **สถานะยืนยันตัวตน:** {status_text}\n"
            f"🎖️ **บทบาทที่เคยได้รับ:** {roles_str}\n"
            f"⏰ **เวลาที่ออกจากเซิร์ฟเวอร์:** <t:{now_ts}:F> (<t:{now_ts}:R>)\n"
            f"👥 **จำนวนสมาชิกคงเหลือ:** `{guild.member_count:,}` คน\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=color
    )
    if hasattr(member, "display_avatar") and member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="💎 SC-HUB MEMBER AUDIT LOG • ตรวจสอบสิทธิ์ยศทางการ")

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[-] [MEMBER AUDIT] Leave log error: {e}")


async def log_member_verified(guild: discord.Guild, member: discord.Member, role: Optional[discord.Role] = None):
    """Logs when a member successfully completes Captcha and gets verified."""
    channel = await get_audit_channel(guild)
    if not channel:
        return

    # Update database daily counter
    db.increment_audit_stat("verified_count")

    now_ts = int(time.time())
    role_str = role.mention if role else f"<@&{DEFAULT_VERIFIED_ROLE_ID}>"

    embed = discord.Embed(
        title="🎖️ สมาชิกยืนยันตัวตนสำเร็จ (Member Verified)",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **สมาชิก:** {member.mention} (`{member.name}`)\n"
            f"🆔 **User ID:** `{member.id}`\n"
            f"✅ **บทบาทที่ได้รับ:** {role_str}\n"
            f"🛡️ **ระบบรักษาความปลอดภัย:** `ผ่านการทดสอบ Captcha ป้องกันบอท 100%`\n"
            f"⏰ **เวลายืนยันตัวตน:** <t:{now_ts}:F>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x00A8FF  # Sky Blue / Verified Blue
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="💎 SC-HUB VERIFICATION AUDIT • ยืนยันตัวตนเรียบร้อย")

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[-] [MEMBER AUDIT] Verify log error: {e}")


async def log_role_changes(
    guild: discord.Guild,
    member: discord.Member,
    added_roles: list[discord.Role],
    removed_roles: list[discord.Role]
):
    """
    Logs role changes (excluding verified role and @everyone)
    to ROLE_AUDIT_CHANNEL_ID: 1563251907567419532 (🎭・ประวัติเปลี่ยนยศ).
    """
    if not guild or not member:
        return

    cfg = db.get_guild_config(guild.id)
    ch_id = cfg.get("role_audit_channel_id") or config.ROLE_AUDIT_CHANNEL_ID
    channel = guild.get_channel(ch_id)
    if not isinstance(channel, discord.TextChannel):
        try:
            channel = await guild.fetch_channel(ch_id)
        except Exception:
            channel = None

    if not isinstance(channel, discord.TextChannel):
        return

    verified_id = cfg.get("verified_role_id") or config.DEFAULT_VERIFIED_ROLE_ID

    # Exclude verified role and @everyone
    clean_added = [r for r in added_roles if r.id != verified_id and r != guild.default_role]
    clean_removed = [r for r in removed_roles if r.id != verified_id and r != guild.default_role]

    if not clean_added and not clean_removed:
        return

    now_ts = int(time.time())
    embed = discord.Embed(
        title="🎭 บันทึกประวัติการเปลี่ยนยศ (Role Update Audit)",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **สมาชิก:** {member.mention} (`{member.name}`)\n"
            f"🆔 **User ID:** `{member.id}`\n"
            f"⏰ **เวลาที่เปลี่ยนแปลง:** <t:{now_ts}:F> (<t:{now_ts}:R>)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x9B59B6
    )

    if clean_added:
        added_text = "\n".join(f"🟢 **+** {r.mention} (`{r.name}`)" for r in clean_added)
        embed.add_field(name="📥 ยศที่ได้รับเพิ่ม (Added Roles)", value=added_text, inline=False)

    if clean_removed:
        removed_text = "\n".join(f"🔴 **-** {r.mention} (`{r.name}`)" for r in clean_removed)
        embed.add_field(name="📤 ยศที่ถูกถอดออก (Removed Roles)", value=removed_text, inline=False)

    current_roles = [r.mention for r in member.roles if r != guild.default_role and r.id != verified_id]
    embed.add_field(
        name="🎖️ ยศพิเศษปัจจุบัน",
        value=", ".join(current_roles[:12]) if current_roles else "ไม่มีบทบาทพิเศษ",
        inline=False
    )

    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="💎 SC-HUB ROLE AUDIT • ประวัติการเปลี่ยนยศ (ไม่นับยศ Verify)")

    try:
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[-] [ROLE AUDIT] Log send error: {e}")

