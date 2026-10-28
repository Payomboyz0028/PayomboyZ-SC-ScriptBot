# -*- coding: utf-8 -*-
"""
💎 SC-HUB Midnight Daily Summary & Revenue Digest Engine
Calculates 24-hour financial turnover, department sales, staff leaderboard, and community metrics.
Posts automatically every midnight (00:00 ICT) to: 1563251868501803048.
"""

from __future__ import annotations
import time
import datetime
from typing import Optional, Dict, Any, Tuple
import discord

from config import DAILY_SUMMARY_CHANNEL_ID, COLOR_PRIMARY_GOLD, DEPARTMENTS
from database import db


def get_bangkok_now() -> datetime.datetime:
    """Returns the current datetime in Bangkok / ICT timezone (UTC+7)."""
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))


def build_daily_summary_embed(guild: discord.Guild, data: Dict[str, Any]) -> discord.Embed:
    """Builds a rich executive dashboard embed for the midnight summary."""
    now_ict = get_bangkok_now()
    yesterday_ict = now_ict - datetime.timedelta(days=1)
    date_title = yesterday_ict.strftime("%d/%m/%Y")

    total_rev = data.get("total_revenue", 0.0)
    total_closed = data.get("total_closed", 0)
    paid_orders = data.get("paid_orders", 0)
    active_now = data.get("active_tickets", 0)

    dept_breakdown = data.get("dept_breakdown", {})
    staff_leaderboard = data.get("staff_leaderboard", [])

    joins = data.get("joins_count", 0)
    leaves = data.get("leaves_count", 0)
    verified = data.get("verified_count", 0)

    # 1. Department Breakdown Strings
    dept_lines = []
    for dkey in ("game", "script", "web"):
        dinfo = DEPARTMENTS.get(dkey, {})
        if dkey == "web":
            w1 = dept_breakdown.get("web", {"count": 0, "revenue": 0.0})
            w2 = dept_breakdown.get("website", {"count": 0, "revenue": 0.0})
            dstats = {"count": w1["count"] + w2["count"], "revenue": w1["revenue"] + w2["revenue"]}
        else:
            dstats = dept_breakdown.get(dkey, {"count": 0, "revenue": 0.0})
        dept_lines.append(
            f"{dinfo.get('emoji', '📌')} **{dinfo.get('name', dkey)}:** "
            f"`{dstats['count']:,}` งาน | ยอดขาย: `{dstats['revenue']:,.2f}` ฿"
        )
    dept_str = "\n".join(dept_lines) if dept_lines else "ไม่มีรายการงานในวันนี้"

    # 2. Staff Leaderboard Strings
    leaderboard_lines = []
    medals = ["🥇", "🥈", "🥉", "🏅", "🎖️"]
    for idx, s in enumerate(staff_leaderboard):
        m = medals[idx] if idx < len(medals) else "🔹"
        leaderboard_lines.append(
            f"{m} <@{s['admin_id']}> — ปิด `{s['count']:,}` เคส (ยอดรวม: `{s['revenue']:,.2f}` ฿)"
        )
    staff_str = "\n".join(leaderboard_lines) if leaderboard_lines else "ไม่มีสถิติงานแอดมินในวันนี้"

    embed = discord.Embed(
        title=f"📊 สรุปยอดรายวันรอบเที่ยงคืน • ประจำวันที่ {date_title}",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏰 **เซิร์ฟเวอร์:** `{guild.name}`\n"
            f"⏰ **เวลาปิดยอด:** <t:{int(time.time())}:F>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "💰 **สรุปยอดเงินและออเดอร์รวม (Financial Overview):**\n"
            f"• **ยอดเงินรวมทั้งหมด:** `฿{total_rev:,.2f}` บาท\n"
            f"• **ออเดอร์ชำระเงินแล้ว:** `{paid_orders:,}` รายการ\n"
            f"• **ตั๋วที่ส่งมอบงานสำเร็จ:** `{total_closed:,}` ตั๋ว\n"
            f"• **ตั๋วที่ยังดำเนินการอยู่:** `{active_now:,}` ห้อง\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📂 **ยอดจำหน่ายแยกตามแผนกบริการ (Department Turnover):**\n"
            f"{dept_str}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🏆 **อันดับผลงานทีมงานยอดเยี่ยม (Staff Performance):**\n"
            f"{staff_str}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👥 **ความเคลื่อนไหวสมาชิก (Community Activity):**\n"
            f"• สมาชิกใหม่เข้าร่วม: `+{joins:,}` คน\n"
            f"• ยืนยันตัวตนสำเร็จ (Verified): `+{verified:,}` คน\n"
            f"• สมาชิกออกจากเซิร์ฟเวอร์: `-{leaves:,}` คน\n"
            f"• จำนวนสมาชิกรวมปัจจุบัน: `{guild.member_count:,}` คน\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0xF1C40F  # Premium Gold
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text="💎 SC-HUB MIDNIGHT REVENUE AUDIT • สรุปยอดอัตโนมัติทุกเที่ยงคืน")
    return embed


async def post_daily_summary(
    guild: discord.Guild,
    target_channel: Optional[discord.TextChannel] = None,
    lookback_seconds: int = 86400
) -> Tuple[bool, Optional[discord.Embed], str]:
    """
    Gathers daily metrics for the last lookback_seconds and posts to DAILY_SUMMARY_CHANNEL_ID (1563251868501803048).
    """
    if not guild:
        return False, None, "ไม่พบข้อมูลเซิร์ฟเวอร์"

    now_ts = time.time()
    start_ts = now_ts - lookback_seconds

    # Query metrics from DB
    data = db.get_daily_summary_data(guild.id, start_ts=start_ts, end_ts=now_ts)
    embed = build_daily_summary_embed(guild, data)

    # Resolve target channel
    ch = target_channel
    if not ch:
        ch = guild.get_channel(DAILY_SUMMARY_CHANNEL_ID)
        if not isinstance(ch, discord.TextChannel):
            try:
                ch = await guild.fetch_channel(DAILY_SUMMARY_CHANNEL_ID)
            except Exception:
                ch = None

    if not isinstance(ch, discord.TextChannel):
        return False, embed, f"ไม่สามารถค้นหาห้องสรุปยอด {DAILY_SUMMARY_CHANNEL_ID}"

    try:
        await ch.send(embed=embed)
        return True, embed, f"ส่งสรุปยอดรายวันไปยังห้อง {ch.mention} สำเร็จแล้ว!"
    except Exception as e:
        return False, embed, f"เกิดข้อผิดพลาดในการส่งข้อความ: {e}"
