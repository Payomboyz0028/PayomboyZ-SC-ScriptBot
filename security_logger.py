# -*- coding: utf-8 -*-
"""
💎 SC-HUB Security, Fraud Prevention & Anomaly Alert Engine
Dispatches real-time incident reports to the designated security channel (1563251866517770250).
"""

from __future__ import annotations
import time
from typing import Optional, List, Tuple, Any, Dict
import discord

from config import ANOMALY_LOG_CHANNEL_ID, COLOR_DANGER


async def log_security_anomaly(
    guild: discord.Guild,
    title: str,
    description: str,
    incident_type: str = "SECURITY_ALERT",
    severity: str = "HIGH",  # LOW, MEDIUM, HIGH, CRITICAL, URGENT
    user: Optional[discord.Member | discord.User] = None,
    channel: Optional[discord.abc.GuildChannel] = None,
    fields: Optional[List[Tuple[str, str, bool]]] = None,
    evidence: Optional[str] = None
) -> bool:
    """
    Sends a high-visibility security alert embed to ANOMALY_LOG_CHANNEL_ID (1563251866517770250).
    """
    if not guild:
        return False

    anomaly_channel = guild.get_channel(ANOMALY_LOG_CHANNEL_ID)
    if not isinstance(anomaly_channel, discord.TextChannel):
        try:
            anomaly_channel = await guild.fetch_channel(ANOMALY_LOG_CHANNEL_ID)
        except Exception:
            anomaly_channel = None

    if not anomaly_channel:
        print(f"[-] [SECURITY ALERT] Failed to resolve anomaly channel {ANOMALY_LOG_CHANNEL_ID}")
        return False

    severity_emojis = {
        "LOW": "🟡 LOW",
        "MEDIUM": "🟠 MEDIUM",
        "HIGH": "🔴 HIGH",
        "CRITICAL": "🔥 CRITICAL",
        "URGENT": "🚨 URGENT"
    }
    sev_badge = severity_emojis.get(severity.upper(), f"⚠️ {severity.upper()}")

    embed = discord.Embed(
        title=f"🚨 [รายการผิดปรกติ] {title}",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ **ระบบตรวจจับ:** `SC-HUB Anti-Fraud & Sentinel Guard`\n"
            f"🏷️ **ประเภทเหตุการณ์:** `{incident_type}`\n"
            f"⚠️ **ระดับความรุนแรง:** **{sev_badge}**\n"
            f"⏰ **เวลาที่เกิดเหตุ:** <t:{int(time.time())}:F> (<t:{int(time.time())}:R>)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{description}"
        ),
        color=0xFF0033  # Red Danger
    )

    if user:
        embed.add_field(
            name="👤 ผู้ใช้งานที่เกี่ยวข้อง",
            value=f"{user.mention} (`{user.name}` | ID: `{user.id}`)",
            inline=True
        )

    if channel:
        embed.add_field(
            name="📍 ห้องที่เกิดเหตุ",
            value=f"{channel.mention} (`{channel.name}` | ID: `{channel.id}`)",
            inline=True
        )

    if fields:
        for name, val, inl in fields:
            embed.add_field(name=name, value=val, inline=inl)

    if evidence:
        embed.add_field(name="🔍 หลักฐาน / Technical Payload", value=f"```{evidence[:1000]}```", inline=False)

    embed.set_footer(text="💎 SC-HUB SENTINEL SECURITY ENGINE • 24/7 ACTIVE SURVEILLANCE")

    try:
        await anomaly_channel.send(embed=embed)
        return True
    except Exception as e:
        print(f"[-] [SECURITY ALERT] Failed to send to {anomaly_channel.id}: {e}")
        return False
