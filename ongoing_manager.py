# -*- coding: utf-8 -*-
"""
💎 SC-HUB Live Ongoing Work & Order Tracker Engine
Maintains real-time ongoing work cards and progress updates in department-specific channels:
- 🎮 เติมเกมส์: 1563251830677315666
- 🌐 เว็บไซต์: 1563251842232615052
- 📜 สคริปต์: 1563251853477552259
"""

from __future__ import annotations
import time
import asyncio
from typing import Optional, Dict, Any, List
import discord
from discord import ui

from config import DEPARTMENTS, ONGOING_CHANNELS, DEFAULT_ONGOING_BOARD_MSG_IDS, COLOR_SUCCESS, COLOR_PRIMARY_GOLD
from database import db
from views.process_view import STAGES


def resolve_ongoing_channel_id(category_key: str) -> Optional[int]:
    """Resolves the designated ongoing work channel for a department."""
    dept = DEPARTMENTS.get(category_key, {})
    return dept.get("ongoing_channel_id") or ONGOING_CHANNELS.get(category_key)


def build_ongoing_card_embed(
    ticket_data: Dict[str, Any],
    is_completed: bool = False,
    close_reason: str = ""
) -> discord.Embed:
    """Builds a real-time progress card for the department's ongoing work channel."""
    ticket_num = ticket_data.get("ticket_num", 0)
    category_key = ticket_data.get("category_key", "game")
    dept = DEPARTMENTS.get(category_key, {"name": category_key, "emoji": "📌"})
    
    stage_key = ticket_data.get("process_stage", "queued")
    stage = STAGES.get(stage_key, STAGES["queued"])
    
    customer_id = ticket_data.get("customer_id", 0)
    admin_id = ticket_data.get("claimed_admin_id", 0)
    paid_status = ticket_data.get("paid_status", 0)
    amount = ticket_data.get("amount", 0.0)
    slip_ref = ticket_data.get("slip_ref", "")
    created_at = ticket_data.get("created_at", time.time())
    channel_id = ticket_data.get("channel_id", 0)

    if is_completed:
        title = f"✅ [ปิดงานสำเร็จ] SC-HUB #{ticket_num:04d} • {dept.get('emoji', '')} {dept.get('name', category_key)}"
        color = COLOR_SUCCESS
        status_line = f"🎉 **สถานะล่าสุด:** `เสร็จสิ้นสมบูรณ์ 100%` (ปิดตั๋วเรียบร้อยแล้ว)\n📝 **หมายเหตุ:** *{close_reason or 'ส่งมอบสินค้าครบถ้วน'}*"
    else:
        title = f"🔄 [กำลังดำเนินงาน] SC-HUB #{ticket_num:04d} • {dept.get('emoji', '')} {dept.get('name', category_key)}"
        color = 0x00A8FF if stage_key != "final_stage" else 0xF1C40F
        status_line = (
            f"📊 **ความคืบหน้า:** `{stage['progress_bar']}` ({stage['label']})\n"
            f"🏷️ **ขั้นตอน:** `{stage['step_badge']}`\n"
            f"📝 **คำอธิบาย:** *{stage['desc']}*"
        )

    pay_status_str = f"✅ ชำระแล้ว `{amount:,.2f}` บาท (สลิป: `{slip_ref or 'บันทึกแล้ว'}`)" if paid_status else "⏳ รอแจ้งชำระเงิน"

    embed = discord.Embed(
        title=title,
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **ลูกค้า:** <@{customer_id}>\n"
            f"🛡️ **แอดมินผู้รับผิดชอบ:** <@{admin_id}>\n"
            f"📍 **ห้องตั๋วงาน:** <#{channel_id}>\n"
            f"💳 **การชำระเงิน:** {pay_status_str}\n"
            f"⏰ **เวลาเปิดตั๋ว:** <t:{int(created_at)}:F> (<t:{int(created_at)}:R>)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{status_line}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=color
    )
    embed.set_footer(text=f"💎 SC-HUB LIVE ORDER TRACKER • แผนก {dept.get('name', category_key)}")
    return embed


class OngoingCardView(ui.View):
    """Persistent View for ongoing work cards with strict role/admin authorization."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="🎫 ไปยังห้องตั๋วส่วนตัว",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="dispatch:ongoing:jump_ticket"
    )
    async def btn_jump_ticket(self, interaction: discord.Interaction, button: ui.Button):
        # 1. Fetch ticket by ongoing message ID
        msg_id = interaction.message.id if interaction.message else 0
        tdata = db.get_ticket_by_ongoing_message(msg_id)
        if not tdata:
            await interaction.response.send_message(
                "❌ ไม่พบข้อมูลตั๋วงานนี้ หรือตั๋วงานนี้ถูกปิดและเคลียร์งานไปแล้ว",
                ephemeral=True
            )
            return

        claimed_admin_id = tdata.get("claimed_admin_id")
        customer_id = tdata.get("customer_id")
        channel_id = tdata.get("channel_id")
        user_id = interaction.user.id

        is_claimed_admin = (user_id == claimed_admin_id)
        is_customer = (user_id == customer_id)
        is_owner = (interaction.guild and user_id == interaction.guild.owner_id)
        
        if not is_owner and interaction.guild and isinstance(interaction.user, discord.Member):
            from config import DEFAULT_OWNER_ROLE_ID
            owner_role = interaction.guild.get_role(DEFAULT_OWNER_ROLE_ID)
            if owner_role and owner_role in interaction.user.roles:
                is_owner = True

        if not (is_claimed_admin or is_customer or is_owner):
            await interaction.response.send_message(
                f"❌ **คุณไม่มีสิทธิ์เข้าถึงห้องตั๋วนี้**\n"
                f"🔒 อนุญาตเฉพาะแอดมินผู้ที่กดรับงานนี้ (<@{claimed_admin_id}>) และลูกค้าเจ้าของตั๋วเท่านั้น",
                ephemeral=True
            )
            return

        ticket_channel = interaction.guild.get_channel(channel_id) if interaction.guild else None
        if not ticket_channel and interaction.guild:
            try:
                ticket_channel = await interaction.guild.fetch_channel(channel_id)
            except Exception:
                ticket_channel = None

        if not ticket_channel:
            await interaction.response.send_message("❌ ไม่พบห้องตั๋วงาน หรือห้องตั๋วนี้ถูกลบไปแล้ว", ephemeral=True)
            return

        jump_view = ui.View(timeout=120)
        jump_view.add_item(ui.Button(
            label=f"🚪 คลิกเข้าสู่ห้องตั๋ว #{tdata.get('ticket_num', 0):04d}",
            url=ticket_channel.jump_url,
            style=discord.ButtonStyle.link,
            emoji="🚀"
        ))
        await interaction.response.send_message(
            f"✅ **สิทธิ์เข้าถึงถูกต้อง!** ยินดีต้อนรับ {interaction.user.mention}\n"
            f"📍 **ห้องตั๋วงาน:** {ticket_channel.mention} (`#{ticket_channel.name}`)\n"
            f"👉 กดปุ่มด้านล่างเพื่อเข้าสู่ห้องตั๋วส่วนตัว",
            view=jump_view,
            ephemeral=True
        )


async def post_ongoing_card(
    guild: discord.Guild,
    ticket_data: Dict[str, Any],
    ticket_channel: discord.TextChannel
) -> Optional[int]:
    """Posts a new live card into the department's ongoing work channel."""
    if not guild or not ticket_channel:
        return None

    cat_key = ticket_data.get("category_key", "game")
    ongoing_ch_id = resolve_ongoing_channel_id(cat_key)
    if not ongoing_ch_id:
        return None

    ongoing_ch = guild.get_channel(ongoing_ch_id)
    if not isinstance(ongoing_ch, discord.TextChannel):
        try:
            ongoing_ch = await guild.fetch_channel(ongoing_ch_id)
        except Exception:
            ongoing_ch = None

    if not ongoing_ch:
        print(f"[-] [ONGOING] Channel {ongoing_ch_id} not found for {cat_key}")
        return None

    embed = build_ongoing_card_embed(ticket_data)
    view = OngoingCardView()

    try:
        msg = await ongoing_ch.send(embed=embed, view=view)
        db.set_ticket_ongoing_message(
            channel_id=ticket_channel.id,
            ongoing_msg_id=msg.id,
            ongoing_ch_id=ongoing_ch.id
        )
        asyncio.create_task(refresh_ongoing_board(guild, cat_key))
        return msg.id
    except Exception as e:
        print(f"[-] [ONGOING] Failed to post ongoing card: {e}")
        return None


async def update_ongoing_card(
    guild: discord.Guild,
    ticket_channel_id: int,
    stage_key: Optional[str] = None,
    amount: Optional[float] = None,
    paid_status: Optional[int] = None
):
    """Updates an existing ongoing card in the department channel."""
    if not guild:
        return

    tdata = db.get_ticket(ticket_channel_id)
    if not tdata:
        return

    ongoing_msg_id = tdata.get("ongoing_msg_id") or 0
    ongoing_ch_id = tdata.get("ongoing_ch_id") or 0

    if not ongoing_msg_id or not ongoing_ch_id:
        return

    ch = guild.get_channel(ongoing_ch_id)
    if not isinstance(ch, discord.TextChannel):
        try:
            ch = await guild.fetch_channel(ongoing_ch_id)
        except Exception:
            return

    try:
        msg = await ch.fetch_message(ongoing_msg_id)
    except Exception:
        return

    if stage_key:
        tdata["process_stage"] = stage_key
    if amount is not None:
        tdata["amount"] = amount
    if paid_status is not None:
        tdata["paid_status"] = paid_status

    updated_embed = build_ongoing_card_embed(tdata)
    try:
        await msg.edit(embed=updated_embed)
        cat_key = tdata.get("category_key", "game")
        asyncio.create_task(refresh_ongoing_board(guild, cat_key))
    except Exception as e:
        print(f"[-] [ONGOING] Failed to edit ongoing card: {e}")


async def complete_ongoing_card(
    guild: discord.Guild,
    ticket_channel_id: int,
    reason: str = "เสร็จสิ้นสมบูรณ์"
):
    """Deletes an ongoing card from the ongoing work channel when ticket closes."""
    if not guild:
        return

    tdata = db.get_ticket(ticket_channel_id)
    if not tdata:
        return

    ongoing_msg_id = tdata.get("ongoing_msg_id") or 0
    ongoing_ch_id = tdata.get("ongoing_ch_id") or 0

    if not ongoing_msg_id or not ongoing_ch_id:
        return

    ch = guild.get_channel(ongoing_ch_id)
    if not isinstance(ch, discord.TextChannel):
        try:
            ch = await guild.fetch_channel(ongoing_ch_id)
        except Exception:
            return

    try:
        msg = await ch.fetch_message(ongoing_msg_id)
        await msg.delete()
        print(f"[+] [ONGOING] Deleted ongoing card msg {ongoing_msg_id} in channel {ongoing_ch_id} on ticket close.")
        cat_key = tdata.get("category_key", "game")
        asyncio.create_task(refresh_ongoing_board(guild, cat_key))
    except Exception as e:
        print(f"[-] [ONGOING] Failed to delete ongoing card on close: {e}")


def build_department_ongoing_board(guild: discord.Guild, category_key: str) -> discord.Embed:
    """Builds a consolidated dashboard embed for all currently active tickets in a department."""
    dept = DEPARTMENTS.get(category_key, {"name": category_key, "emoji": "📌"})
    active_list = db.get_active_tickets_by_category(guild.id, category_key=category_key)

    lines = []
    for t in active_list:
        ticket_num = t.get("ticket_num", 0)
        ch_id = t.get("channel_id", 0)
        cid = t.get("customer_id", 0)
        aid = t.get("claimed_admin_id", 0)
        stage_key = t.get("process_stage", "queued")
        stage = STAGES.get(stage_key, STAGES["queued"])
        amt = t.get("amount", 0.0)
        paid = "🟢 ชำระแล้ว" if t.get("paid_status") else "🟡 รอชำระ"

        lines.append(
            f"• **ตั๋ว #{ticket_num:04d}** (<#{ch_id}>)\n"
            f"  └ ลูกค้า: <@{cid}> | แอดมิน: <@{aid}>\n"
            f"  └ สถานะ: `{stage['label']}` `{stage['progress_bar']}` | {paid} (`{amt:,.2f}` ฿)"
        )

    content = "\n\n".join(lines) if lines else "✨ **ขณะนี้ไม่มีงานที่กำลังดำเนินงานอยู่ (ทีมงานสแตนด์บายพร้อมรับงานตลอด 24 ชม.)**"

    embed = discord.Embed(
        title=f"🔄 กระดานงานที่กำลังดำเนินงานอยู่ • {dept.get('emoji', '')} {dept.get('name', category_key)}",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 **จำนวนตั๋วงานที่กำลังทำอยู่ทั้งหมด:** `{len(active_list):,}` งาน\n"
            f"⏰ **อัปเดตข้อมูลล่าสุด:** <t:{int(time.time())}:T>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{content}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0x00A8FF
    )
    embed.set_footer(text=f"💎 SC-HUB LIVE WORK TRACKER • แผนก {dept.get('name', category_key)}")
    return embed


class OngoingBoardView(ui.View):
    """Persistent View for department ongoing board with manual refresh button."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="🔄 รีเฟรชกระดานงาน (Refresh)",
        style=discord.ButtonStyle.secondary,
        emoji="🔄",
        custom_id="dispatch:ongoing:refresh_board"
    )
    async def btn_refresh_board(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ เซิร์ฟเวอร์ไม่ถูกต้อง", ephemeral=True)
            return

        cat_key = "game"
        if interaction.channel:
            cid = interaction.channel.id
            for k, ch_id in ONGOING_CHANNELS.items():
                if ch_id == cid:
                    cat_key = k
                    break

        await interaction.response.defer(ephemeral=True)
        await refresh_ongoing_board(guild, cat_key)
        await interaction.followup.send("✅ อัปเดตข้อมูลกระดานงานเป็นปัจจุบันเรียบร้อยแล้ว", ephemeral=True)


async def refresh_ongoing_board(guild: discord.Guild, category_key: str):
    """Refreshes the live standing board in the department's ongoing channel."""
    if not guild:
        return

    ongoing_ch_id = resolve_ongoing_channel_id(category_key)
    if not ongoing_ch_id:
        return

    ch = guild.get_channel(ongoing_ch_id)
    if not isinstance(ch, discord.TextChannel):
        try:
            ch = await guild.fetch_channel(ongoing_ch_id)
        except Exception:
            return

    board_msg_id = DEFAULT_ONGOING_BOARD_MSG_IDS.get(category_key)
    board_msg = None
    if board_msg_id:
        try:
            board_msg = await ch.fetch_message(board_msg_id)
        except Exception:
            board_msg = None

    if not board_msg:
        try:
            async for m in ch.history(limit=15):
                if m.author.id == guild.me.id and m.embeds:
                    if "กระดานงานที่กำลังดำเนินงานอยู่" in (m.embeds[0].title or ""):
                        board_msg = m
                        break
        except Exception:
            pass

    embed = build_department_ongoing_board(guild, category_key)
    view = OngoingBoardView()

    try:
        if board_msg:
            await board_msg.edit(embed=embed, view=view)
            print(f"[+] [ONGOING] Refreshed ongoing board {board_msg.id} for {category_key}")
        else:
            msg = await ch.send(embed=embed, view=view)
            print(f"[+] [ONGOING] Created new ongoing board {msg.id} for {category_key}")
    except Exception as e:
        print(f"[-] [ONGOING] Failed to refresh ongoing board for {category_key}: {e}")

