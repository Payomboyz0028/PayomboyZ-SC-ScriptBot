# -*- coding: utf-8 -*-
"""
💎 SC-HUB In-Ticket Action Controls View
Handles payment submission, slip verification trigger, staff pings, and ticket closure.
Enhanced with high-end customer styling.
"""

from __future__ import annotations
import time
import asyncio
from typing import Optional, Dict, Any
import discord
from discord import ui

import config
from config import COLOR_PRIMARY_GOLD, COLOR_SUCCESS, COLOR_DANGER, DEFAULT_OWNER_ROLE_ID, DEFAULT_STAFF_ROLE_ID
from database import db
from slip_verifier import verify_slip_image_or_payload
from transcript import generate_ticket_transcript
from web_logger import send_ticket_completed_log
from financial_auditor import post_verified_slip_receipt
from truemoney_engine import redeem_truemoney_voucher
from promptpay_engine import build_promptpay_qr_embed

_TICKET_PING_COOLDOWNS: Dict[int, float] = {}


class PaymentAmountModal(ui.Modal, title="💳 ระบุยอดเงินชำระ (PromptPay QR)"):
    amount_input = ui.TextInput(
        label="ยอดเงินที่ชำระ (บาท)",
        placeholder="ตัวอย่าง: 250 หรือ 490",
        required=True,
        max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.channel
        guild = interaction.guild
        user = interaction.user
        if not isinstance(channel, discord.TextChannel) or not guild:
            await interaction.response.send_message("❌ ใช้ได้เฉพาะในห้องตั๋ว", ephemeral=True)
            return

        tdata = db.get_ticket(channel.id)
        if not tdata:
            await interaction.response.send_message("❌ ไม่พบข้อมูลตั๋วในระบบ", ephemeral=True)
            return

        try:
            amount = float(self.amount_input.value.strip().replace(",", ""))
            if amount <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ รูปแบบจำนวนเงินไม่ถูกต้อง กรุณากรอกเป็นตัวเลขมากกว่า 0", ephemeral=True)
            return

        # Defer ephemeral response
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Update ticket pending expected amount in DB
        db.update_ticket_amount(channel.id, amount)

        # Target phone number (Default 0829934210)
        cfg = db.get_guild_config(guild.id)
        pp_target = cfg.get("truemoney_phone") or config.TRUEMONEY_PHONE or "0829934210"

        category_key = tdata.get("category_key", "game")
        dept = config.DEPARTMENTS.get(category_key, {"name": "บริการทั่วไป"})

        qr_embed, qr_file = build_promptpay_qr_embed(
            target=pp_target,
            amount=amount,
            ticket_num=tdata.get("ticket_num", 0),
            dept_name=dept.get("name", "บริการทั่วไป")
        )

        instructions_text = (
            f"📱 **QR Code สแกนชำระเงิน (PromptPay ล็อคยอด `฿{amount:,.2f}` บาท)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **ผู้ทำรายการ:** {user.mention}\n"
            f"💰 **ยอดชำระที่ต้องโอน:** `฿{amount:,.2f}` บาท (ตรงตามยอด ห้ามปัดเศษ)\n"
            f"📞 **เบอร์พร้อมเพย์:** `{pp_target}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📥 **ขั้นตอนการชำระเงิน & ตรวจสอบสลิปผ่าน QR:**\n"
            "1. เปิดแอปพลิเคชันธนาคาร สแกน QR Code ด้านล่างเพื่อชำระเงิน\n"
            "2. เมื่อโอนเงินเสร็จแล้ว **ให้ส่งรูปภาพสลิปธนาคาร (ที่มี Mini-QR Code)** ลงในห้องตั๋วนี้ได้ทันที\n"
            "3. ระบบ SC-HUB AI จะสแกน QR Code บนสลิปและยืนยันการชำระเงินให้อัตโนมัติทันที!\n"
            "*(ข้อความนี้แสดงเฉพาะคุณเท่านั้น - Ephemeral)*"
        )

        await interaction.followup.send(content=instructions_text, embed=qr_embed, file=qr_file, ephemeral=True)


PaymentInputModal = PaymentAmountModal


class TrueMoneyInputModal(ui.Modal, title="🧧 เติมเงินด้วยซองของขวัญ TrueMoney"):
    voucher_input = ui.TextInput(
        label="ลิงก์ซองของขวัญ TrueMoney",
        placeholder="https://gift.truemoney.com/campaign/?v=...",
        required=True,
        max_length=150
    )

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.channel
        user = interaction.user
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ ใช้ได้เฉพาะในห้องตั๋ว", ephemeral=True)
            return

        tdata = db.get_ticket(channel.id)
        if not tdata:
            await interaction.response.send_message("❌ ไม่พบข้อมูลตั๋วในระบบ", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        raw_link = self.voucher_input.value.strip()
        result = await redeem_truemoney_voucher(
            voucher_input=raw_link,
            channel_id=channel.id,
            customer_id=user.id,
            guild=interaction.guild,
            user=user
        )

        if not result.success:
            await interaction.followup.send(result.message, ephemeral=True)
            return

        # Update Payment Record in DB
        db.update_ticket_payment(channel.id, slip_ref=f"TMN_{result.voucher_hash}", amount=result.amount)

        # Sync live payment to department's ongoing work channel
        try:
            from ongoing_manager import update_ongoing_card
            asyncio.create_task(update_ongoing_card(interaction.guild, channel.id, amount=result.amount, paid_status=1))
        except Exception:
            pass

        # Dispatch Verified Receipt to Channel: 1563251864256909444
        asyncio.create_task(post_verified_slip_receipt(
            guild=interaction.guild,
            channel=channel,
            customer=user,
            amount=result.amount,
            slip_ref=f"TMN_{result.voucher_hash}",
            payment_method="ซองของขวัญ TrueMoney (Gift Voucher)",
            admin=interaction.guild.get_member(tdata.get("claimed_admin_id") or 0),
            department_name=tdata.get("category_key", "general")
        ))

        # Notify channel publicly with Payment Receipt Embed
        receipt_embed = discord.Embed(
            title="🧧 ยืนยันการรับเงินจากซองของขวัญ TrueMoney สำเร็จ!",
            description=(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **ผู้ส่งซอง:** {user.mention}\n"
                f"💰 **ยอดเงินในซอง:** `{result.amount:,.2f}` บาท\n"
                f"🧾 **รหัสซอง (Hash):** `TMN_{result.voucher_hash}`\n"
                f"⏰ **เวลาทำรายการ:** <t:{int(time.time())}:F>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🛡️ **ระบบปลดล็อกกระบวนการทำงานเรียบร้อย:**\n"
                "• **ฝั่งแอดมิน:** สามารถกดเปลี่ยนสถานะงานตามขั้นตอนจริงได้ทันทีที่แผงควบคุมด้านล่าง\n"
                "• **ฝั่งลูกค้า:** สามารถติดตามความคืบหน้าสด และกดยืนยันเมื่อได้รับสินค้าครบถ้วน"
            ),
            color=0x2ECC71
        )
        receipt_embed.set_footer(text="💎 SC-HUB TRUEMONEY REDEEMER • รับเงินเข้าวอลเล็ทและบันทึกลง Ledger")

        # Import Process Views
        from views.process_view import (
            build_process_status_embed, 
            ProcessAdminControlView, 
            ProcessCustomerControlView
        )

        status_embed = build_process_status_embed(stage_key="queued", amount=result.amount, slip_ref=f"TMN_{result.voucher_hash}")

        await channel.send(embed=receipt_embed)

        # Admin Control Panel
        admin_id = tdata.get("claimed_admin_id")
        await channel.send(
            content=f"🛠️ <@{admin_id}> **แผงควบคุมสถานะงาน (ฝั่งแอดมิน):**",
            embed=status_embed,
            view=ProcessAdminControlView(channel_id=channel.id)
        )

        # Customer Control Panel
        customer_id = tdata.get("customer_id")
        await channel.send(
            content=f"👤 <@{customer_id}> **แผงติดตามและยืนยันการรับสินค้า (ฝั่งลูกค้า):**",
            view=ProcessCustomerControlView(channel_id=channel.id)
        )

        await interaction.followup.send(f"✅ รับเงินจากซองของขวัญเรียบร้อยแล้ว จำนวน `{result.amount:,.2f}` บาท!", ephemeral=True)


class TicketCloseConfirmModal(ui.Modal, title="ปิดตั๋ว (Close Ticket)"):
    reason_input = ui.TextInput(
        label="เหตุผลในการปิดตั๋ว (ไม่บังคับ)",
        placeholder="เช่น ส่งมอบสินค้าเรียบร้อย, ลูกค้าได้รับบริการแล้ว",
        required=False,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.reason_input.value.strip() or "ปิดงานเสร็จสมบูรณ์"
        await execute_close_and_dual_log(interaction, reason=reason)


class PromptPayQRRequestModal(ui.Modal, title="📱 สร้าง QR Code ล็อคยอด (PromptPay)"):
    amount_input = ui.TextInput(
        label="ระบุจำนวนเงินที่ต้องชำระ (บาท)",
        placeholder="ตัวอย่าง: 150 หรือ 350.50",
        required=True,
        max_length=15
    )
    note_input = ui.TextInput(
        label="รายละเอียด / รายการสั่งซื้อ (ไม่บังคับ)",
        placeholder="เช่น เติม Robux 500, สคริปต์ฟาร์มอัตโนมัติ",
        required=False,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.channel
        guild = interaction.guild
        if not isinstance(channel, discord.TextChannel) or not guild:
            await interaction.response.send_message("❌ ใช้ได้เฉพาะในห้องตั๋ว", ephemeral=True)
            return

        tdata = db.get_ticket(channel.id)
        if not tdata:
            await interaction.response.send_message("❌ ไม่พบข้อมูลตั๋วในระบบ", ephemeral=True)
            return

        try:
            amount = float(self.amount_input.value.strip().replace(",", ""))
            if amount <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ กรุณาระบุจำนวนเงินเป็นตัวเลขที่ถูกต้อง (มากกว่า 0 บาท)", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        cfg = db.get_guild_config(guild.id)
        pp_target = cfg.get("truemoney_phone") or config.TRUEMONEY_PHONE or "0829934210"

        category_key = tdata.get("category_key", "game")
        dept = config.DEPARTMENTS.get(category_key, {"name": "บริการทั่วไป"})

        qr_embed, qr_file = build_promptpay_qr_embed(
            target=pp_target,
            amount=amount,
            ticket_num=tdata.get("ticket_num", 0),
            dept_name=dept.get("name", "บริการทั่วไป")
        )

        note = self.note_input.value.strip()
        header_text = f"📱 **QR Code ล็อคยอดเงินสำหรับตั๋วนี้** (สร้างโดย {interaction.user.mention})"
        if note:
            header_text += f"\n📝 **รายการ:** `{note}`"

        await channel.send(content=header_text, embed=qr_embed, file=qr_file)
        await interaction.followup.send(f"✅ สร้าง QR Code ล็อคยอดเงิน `฿{amount:,.2f} บาท` เรียบร้อยแล้ว!", ephemeral=True)


class TicketControlView(ui.View):
    """Persistent controls displayed in private ticket rooms."""
    def __init__(self, ticket_channel_id: int = 0, customer_id: int = 0, admin_id: int = 0):
        super().__init__(timeout=None)
        self.ticket_channel_id = ticket_channel_id
        self.customer_id = customer_id
        self.admin_id = admin_id

    @ui.button(
        label="โอนผ่านธนาคาร / ขอ QR",
        style=discord.ButtonStyle.success,
        emoji="💳",
        custom_id="dispatch:ticket:payment_btn",
        row=0
    )
    async def btn_payment(self, interaction: discord.Interaction, button: ui.Button):
        channel = interaction.channel
        tdata = db.get_ticket(channel.id)
        if tdata and tdata.get("paid_status") == 1:
            await interaction.response.send_message(
                f"✅ **ตั๋วนี้ชำระเงินเรียบร้อยแล้ว!**\nยอดเงิน: `{tdata.get('amount', 0):,.2f}` บาท (สลิป/ซอง: `{tdata.get('slip_ref')}`)",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(PaymentAmountModal())

    @ui.button(
        label="ซองทรูมันนี่ (TrueMoney)",
        style=discord.ButtonStyle.danger,
        emoji="🧧",
        custom_id="dispatch:ticket:truemoney_btn",
        row=0
    )
    async def btn_truemoney(self, interaction: discord.Interaction, button: ui.Button):
        channel = interaction.channel
        tdata = db.get_ticket(channel.id)
        if tdata and tdata.get("paid_status") == 1:
            await interaction.response.send_message(
                f"✅ **ตั๋วนี้ชำระเงินเรียบร้อยแล้ว!**\nยอดเงิน: `{tdata.get('amount', 0):,.2f}` บาท (สลิป/ซอง: `{tdata.get('slip_ref')}`)",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(TrueMoneyInputModal())

    @ui.button(
        label="ขอ QR ล็อคยอด",
        style=discord.ButtonStyle.primary,
        emoji="📱",
        custom_id="dispatch:ticket:qr_btn",
        row=0
    )
    async def btn_promptpay_qr(self, interaction: discord.Interaction, button: ui.Button):
        channel = interaction.channel
        tdata = db.get_ticket(channel.id)
        if tdata and tdata.get("paid_status") == 1:
            await interaction.response.send_message(
                f"✅ **ตั๋วนี้ชำระเงินเรียบร้อยแล้ว!**\nยอดเงิน: `{tdata.get('amount', 0):,.2f}` บาท",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(PaymentAmountModal())

    @ui.button(
        label="สะกิดทีมงาน",
        style=discord.ButtonStyle.secondary,
        emoji="🔔",
        custom_id="dispatch:ticket:ping_btn",
        row=1
    )
    async def btn_ping(self, interaction: discord.Interaction, button: ui.Button):
        now = time.time()
        last = _TICKET_PING_COOLDOWNS.get(interaction.user.id, 0)
        if now - last < 45:
            rem = int(45 - (now - last))
            await interaction.response.send_message(f"⏱️ โปรดรออีก `{rem}` วินาทีก่อนสะกิดทีมงานซ้ำ", ephemeral=True)
            return

        _TICKET_PING_COOLDOWNS[interaction.user.id] = now
        tdata = db.get_ticket(interaction.channel_id)
        admin_mention = f"<@{tdata['claimed_admin_id']}>" if tdata else "@Staff"

        await interaction.response.send_message("🔔 สะกิดทีมงานเรียบร้อยแล้ว!", ephemeral=True)
        await interaction.channel.send(
            content=f"🔔 {admin_mention} ลูกค้า {interaction.user.mention} กำลังรอการตอบกลับในตั๋วนี้ครับ!"
        )

    @ui.button(
        label="ปิดตั๋ว",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="dispatch:ticket:close_btn",
        row=1
    )
    async def btn_close(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TicketCloseConfirmModal())


async def execute_close_and_dual_log(interaction: discord.Interaction, reason: str = "ปิดโดยผู้ใช้"):
    """
    Step 6: Closes ticket and executes DUAL LOGGING:
    - Log 1: Asynchronous JSON to External Website API
    - Log 2: Enforced HTML Transcript sent to configured audit channel
    - Channel cleanup after 5 seconds
    """
    channel = interaction.channel
    guild = interaction.guild
    if not isinstance(channel, discord.TextChannel) or not guild:
        await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในห้องตั๋ว", ephemeral=True)
        return

    tdata = db.get_ticket(channel.id)
    if not tdata:
        tdata = {
            "ticket_num": 0,
            "channel_id": channel.id,
            "category_key": "general",
            "customer_id": interaction.user.id,
            "claimed_admin_id": interaction.user.id,
            "paid_status": 0,
            "amount": 0.0,
            "slip_ref": "N/A",
            "created_at": time.time()
        }

    closing_embed = discord.Embed(
        title=f"🔒 กำลังปิดตั๋ว #{channel.name}...",
        description=(
            f"• **เหตุผลในการปิด:** `{reason}`\n"
            f"• **ระบบ Dual Logging:** บันทึก JSON สู่ Web API และสร้าง HTML Transcript อัตโนมัติ\n"
            f"• ห้องนี้จะถูกลบในอีก **5 วินาที** ขอบคุณที่ใช้บริการ SC-HUB ครับ 🙏"
        ),
        color=COLOR_PRIMARY_GOLD
    )
    await interaction.response.send_message(embed=closing_embed, ephemeral=False)

    # 1. GENERATE LOG 2: HTML Transcript
    transcript_file, msg_count = await generate_ticket_transcript(channel)

    cfg = db.get_guild_config(guild.id)
    cat_key = tdata.get("category_key", "game")

    # Resolve specific department transcript log channel or fallback to general
    dept_log_mapping = {
        "game": 1563251889041055937,
        "web": 1563251890916032632,
        "script": 1563251892958666823
    }
    log_channel_id = (
        cfg.get(f"{cat_key}_transcript_channel_id") or
        dept_log_mapping.get(cat_key) or
        cfg.get("transcript_log_channel_id")
    )

    # Send Transcript to Department Log Channel
    if log_channel_id:
        log_ch = guild.get_channel(log_channel_id)
        if isinstance(log_ch, discord.TextChannel):
            log_embed = discord.Embed(
                title=f"📑 บันทึกประวัติการปิดตั๋ว: #{channel.name}",
                description=(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 **ลูกค้า:** <@{tdata.get('customer_id')}>\n"
                    f"🛡️ **ผู้รับผิดชอบงาน:** <@{tdata.get('claimed_admin_id')}>\n"
                    f"🔒 **ผู้สั่งปิด:** {interaction.user.mention}\n"
                    f"📝 **เหตุผล:** `{reason}`\n"
                    f"💳 **ยอดเงินชำระ:** `{tdata.get('amount', 0.0):,.2f}` บาท\n"
                    f"🧾 **สลิป:** `{tdata.get('slip_ref') or 'ไม่มี'}`\n"
                    f"💬 **จำนวนข้อความในตั๋ว:** `{msg_count:,}` ข้อความ\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=0x00A8FF
            )
            log_embed.set_footer(text="💎 SC-HUB AUDIT ARCHIVE")
            try:
                transcript_file.fp.seek(0)
                await log_ch.send(embed=log_embed, file=transcript_file)
            except Exception as e:
                print(f"[-] Transcript audit log send error: {e}")

    # Send Financial Transaction Record to Transaction Log Channel (1563251895332638730)
    tx_log_channel_id = cfg.get("transaction_log_channel_id") or 1563251895332638730
    if tx_log_channel_id:
        tx_ch = guild.get_channel(tx_log_channel_id)
        if isinstance(tx_ch, discord.TextChannel):
            tx_embed = discord.Embed(
                title=f"💳 บันทึกธุรกรรมการเงิน • ตั๋ว #{channel.name}",
                description=(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 **ลูกค้า:** <@{tdata.get('customer_id')}>\n"
                    f"🛡️ **แอดมินผู้ดูแล:** <@{tdata.get('claimed_admin_id')}>\n"
                    f"📂 **แผนกบริการ:** `{cat_key}`\n"
                    f"💰 **ยอดเงินทำรายการ:** `{tdata.get('amount', 0.0):,.2f}` บาท\n"
                    f"🧾 **เลขอ้างอิงสลิป:** `{tdata.get('slip_ref') or 'ไม่มีสลิป'}`\n"
                    f"✅ **สถานะ:** {'ชำระเงินสำเร็จ' if tdata.get('paid_status') else 'ไม่มีการชำระเงิน'}\n"
                    f"⏰ **เวลา:** <t:{int(time.time())}:F>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=COLOR_SUCCESS if tdata.get("paid_status") else COLOR_PRIMARY_GOLD
            )
            tx_embed.set_footer(text="💎 SC-HUB FINANCIAL AUDIT")
            try:
                await tx_ch.send(embed=tx_embed)
            except Exception as e:
                print(f"[-] Transaction log send error: {e}")

    # 2. GENERATE LOG 1: External Website REST API
    customer_user = guild.get_member(tdata.get("customer_id"))
    admin_user = guild.get_member(tdata.get("claimed_admin_id"))
    c_name = customer_user.name if customer_user else f"User-{tdata.get('customer_id')}"
    a_name = admin_user.name if admin_user else f"Admin-{tdata.get('claimed_admin_id')}"

    # Non-blocking web log dispatch
    asyncio.create_task(send_ticket_completed_log(
        guild_id=guild.id,
        ticket_data=tdata,
        customer_name=c_name,
        admin_name=a_name
    ))

    # DM Transcript copy to Customer if possible
    try:
        if customer_user:
            dm_embed = discord.Embed(
                title=f"📑 สำเนาประวัติการสนทนา • #{channel.name}",
                description=(
                    f"ตั๋วของคุณใน **{guild.name}** ปิดเรียบร้อยแล้ว\n"
                    f"• **เหตุผล:** `{reason}`\n"
                    f"• ประวัติการสนทนาฉบับเต็มแนบมาด้านล่างแล้ว ขอบคุณที่ไว้วางใจ SC-HUB ครับ 🙏"
                ),
                color=COLOR_PRIMARY_GOLD
            )
            transcript_file.fp.seek(0)
            await customer_user.send(embed=dm_embed, file=transcript_file)
    except Exception:
        pass

    # 3. Mark live card as completed in ongoing channel
    try:
        from ongoing_manager import complete_ongoing_card
        await complete_ongoing_card(guild, channel.id, reason=reason)
    except Exception as e:
        print(f"[-] Failed to mark ongoing card completed: {e}")

    # 4. Clean up database record and archive to ticket_history
    try:
        db.record_ticket_history(tdata, close_reason=reason)
    except Exception as e:
        print(f"[-] Failed to archive ticket history: {e}")

    db.close_ticket(channel.id)
    await asyncio.sleep(5)
    try:
        await channel.delete(reason=f"Closed by {interaction.user.name}: {reason}")
    except Exception:
        pass
