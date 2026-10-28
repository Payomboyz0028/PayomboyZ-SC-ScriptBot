# -*- coding: utf-8 -*-
"""
💎 SC-HUB Financial Auditor & Receipt Dispatcher
Handles logging and dispatching of verified bank slips and TrueMoney vouchers
to Channel: 1563251864256909444 (#✅・ตรวจสอบสำเร็จ).
"""

from __future__ import annotations
import time
from typing import Optional
import discord

import config
from database import db


async def post_verified_slip_receipt(
    guild: discord.Guild,
    channel: discord.TextChannel | discord.abc.GuildChannel,
    customer: discord.Member | discord.User,
    amount: float,
    slip_ref: str,
    payment_method: str = "โอนผ่านธนาคาร (Bank Slip)",
    admin: Optional[discord.Member | discord.User] = None,
    department_name: str = "บริการทั่วไป"
):
    """
    Dispatches a verified transaction receipt to VERIFIED_SLIP_CHANNEL_ID (1563251864256909444).
    """
    if not guild:
        return

    cfg = db.get_guild_config(guild.id)
    receipt_ch_id = cfg.get("verified_slip_channel_id") or config.VERIFIED_SLIP_CHANNEL_ID
    target_ch = guild.get_channel(receipt_ch_id)
    if not isinstance(target_ch, discord.TextChannel):
        try:
            target_ch = await guild.fetch_channel(receipt_ch_id)
        except Exception:
            target_ch = None

    if not isinstance(target_ch, discord.TextChannel):
        return

    admin_str = admin.mention if admin else "ระบบอัตโนมัติ"
    now_ts = int(time.time())

    embed = discord.Embed(
        title="✅ บันทึกรายการชำระเงินสำเร็จ (Verified Payment Receipt)",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **ผู้ชำระเงิน:** {customer.mention} (`{customer.id}`)\n"
            f"💰 **ยอดเงินทำรายการ:** `{amount:,.2f}` บาท\n"
            f"💳 **ช่องทางการชำระ:** `{payment_method}`\n"
            f"🧾 **รหัสอ้างอิงสลิป/ซอง:** `{slip_ref}`\n"
            f"📍 **ห้องตั๋วงาน:** {channel.mention} (`{channel.name}`)\n"
            f"📂 **แผนกงาน:** `{department_name}`\n"
            f"🛡️ **ผู้ดูแลรับงาน:** {admin_str}\n"
            f"⏰ **เวลาบันทึกรายการ:** <t:{now_ts}:F> (<t:{now_ts}:R>)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🛡️ *รายการนี้ผ่านการตรวจสอบความถูกต้องและลงบันทึกใน Slip Ledger เรียบร้อยแล้ว*"
        ),
        color=config.COLOR_SUCCESS
    )
    if hasattr(customer, "display_avatar") and customer.display_avatar:
        embed.set_thumbnail(url=customer.display_avatar.url)
    embed.set_footer(text="💎 SC-HUB FINANCIAL AUDIT • ตรวจสอบสลิปและซองทรูสำเร็จ")

    try:
        await target_ch.send(embed=embed)
    except Exception as e:
        print(f"[-] [VERIFIED SLIP AUDIT] Receipt send error: {e}")
