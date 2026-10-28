# -*- coding: utf-8 -*-
"""
=============================================================================
👑 PAYOMBØYZ WORK-ALLOCATION & DISPATCH TICKET ENGINE (SC-Script-Bot)
=============================================================================
Main Bot Application with Slash Command Tree, Dynamic Persistent Views,
Anti-Bot Captcha Verification, Atomic Concurrency Mutex Claim, Slip API & Dual-Logging.
"""

from __future__ import annotations
import sys
import os
import io
import time
import asyncio
from pathlib import Path
from typing import Optional, Literal

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from database import db
from views.verify_view import VerificationPanelView, build_verification_panel_embed
from views.category_view import CategoryRouterView, build_category_router_embed
from views.lobby_view import DepartmentLobbyView, build_department_lobby_embed
from views.ticket_view import TicketControlView
from views.process_view import build_process_status_embed, ProcessAdminControlView, ProcessCustomerControlView
from views.dispute_view import DisputePanelView, DisputeTicketControlView, build_dispute_panel_embed
from member_logger import log_member_join, log_member_remove, log_member_verified, log_role_changes
from daily_summary import post_daily_summary, get_bangkok_now, build_daily_summary_embed
from security_logger import log_security_anomaly
from truemoney_engine import redeem_truemoney_voucher, extract_voucher_code
from financial_auditor import post_verified_slip_receipt
from slip_verifier import verify_slip_image_or_payload
from malware_scanner import intercept_and_neutralize_threat
from ongoing_manager import OngoingCardView, OngoingBoardView


ENABLE_MEMBERS_INTENT = os.environ.get("ENABLE_MEMBERS_INTENT", "false").lower() in ("true", "1", "yes")

intents = discord.Intents.default()
intents.guilds = True
if ENABLE_MEMBERS_INTENT:
    intents.members = True

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents, help_command=None)

BANGKOK_TZ = datetime.timezone(datetime.timedelta(hours=7))
MIDNIGHT_TIME = datetime.time(hour=0, minute=0, second=0, tzinfo=BANGKOK_TZ)


# ─────────────────────────────────────────────────────────────
# 🔄 LIFECYCLE & PERSISTENT VIEW REHYDRATION
# ─────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print("=" * 66)
    print("  💎 SC-HUB CLIENT SERVICE & DISPATCH SYSTEM IS ONLINE")
    print("=" * 66)
    user_tag = f"{bot.user.name}#{bot.user.discriminator}" if bot.user.discriminator != "0" else bot.user.name
    print(f"👤 Logged in as: {user_tag} (ID: {bot.user.id})")
    print(f"🏰 Connected Guilds: {len(bot.guilds)}")
    print(f"📁 Database: {config.DB_PATH}")
    print(f"👥 Server Members Intent: {'✅ Active' if bot.intents.members else '⚠️ Disabled (Waiting for Dev Portal Toggle)'}")
    print("=" * 66)

    # 1. Register Persistent Views (Survives bot restarts)
    bot.add_view(VerificationPanelView())
    bot.add_view(CategoryRouterView())
    bot.add_view(DepartmentLobbyView("game"))
    bot.add_view(DepartmentLobbyView("script"))
    bot.add_view(DepartmentLobbyView("web"))
    bot.add_view(TicketControlView())
    bot.add_view(ProcessCustomerControlView(channel_id=0))
    bot.add_view(DisputePanelView())
    bot.add_view(DisputeTicketControlView())
    bot.add_view(OngoingCardView())
    bot.add_view(OngoingBoardView())
    print("[+] Registered all persistent SC-HUB dispatch views successfully.")

    # 2. Sync Slash Commands globally
    try:
        synced = await bot.tree.sync()
        print(f"[+] Synced {len(synced)} global slash commands.")
    except Exception as e:
        print(f"[-] Slash sync failed: {e}")

    # 3. Start Scheduled Midnight Task
    if not midnight_summary_task.is_running():
        midnight_summary_task.start()
        print("[+] Started Midnight Daily Summary task loop (00:00 Bangkok ICT).")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="💎 SC-HUB Client Portal | /setup_dispatch_system"
        ),
        status=discord.Status.online
    )


# ─────────────────────────────────────────────────────────────
# 👥 MEMBER AUDIT LISTENERS (Channel: 1563251902307901584)
# ─────────────────────────────────────────────────────────────
@bot.event
async def on_member_join(member: discord.Member):
    await log_member_join(member.guild, member)


@bot.event
async def on_member_remove(member: discord.Member):
    await log_member_remove(member.guild, member)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    cfg = db.get_guild_config(after.guild.id)
    verified_id = cfg.get("verified_role_id") or config.DEFAULT_VERIFIED_ROLE_ID

    # 1. Audit Verified Role Gain
    if verified_id:
        had_role = any(r.id == verified_id for r in before.roles)
        has_role = any(r.id == verified_id for r in after.roles)
        if not had_role and has_role:
            verified_r = after.guild.get_role(verified_id)
            await log_member_verified(after.guild, after, verified_r)
            try:
                from welcome_card import send_welcome_announcement
                asyncio.create_task(send_welcome_announcement(guild=after.guild, member=after, verified_role=verified_r))
            except Exception as e:
                print(f"[-] [WELCOME] on_member_update error: {e}")

    # 2. Audit Other Role Changes (Excluding Verified Role & @everyone) -> Channel: 1563251907567419532
    before_set = set(before.roles)
    after_set = set(after.roles)
    added = [r for r in after.roles if r not in before_set]
    removed = [r for r in before.roles if r not in after_set]

    if added or removed:
        await log_role_changes(after.guild, after, added_roles=added, removed_roles=removed)


# ─────────────────────────────────────────────────────────────
# 🧧 AUTOMATIC TRUEMONEY VOUCHER SNIFFER (ระบบดักซองทรูในตั๋ว)
# ─────────────────────────────────────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # 🛡️ LAYER 3: Anti-Malware, Anti-Trojan & Payload Scanner
    if message.attachments:
        threat_neutralized = await intercept_and_neutralize_threat(message)
        if threat_neutralized:
            return  # Stop processing malicious payload immediately!

    # 💳 AUTOMATIC BANK TRANSFER SLIP QR SCANNER (ระบบตรวจสอบสลิปผ่าน QR อัตโนมัติในตั๋ว)
    if message.attachments:
        tdata = db.get_ticket(message.channel.id)
        if tdata and tdata.get("paid_status") == 0:
            img_att = next(
                (att for att in message.attachments if (att.content_type and att.content_type.startswith("image/")) or att.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))),
                None
            )
            if img_att:
                loading_msg = await message.reply("🔍 **ตรวจพบรูปภาพสลิป!** กำลังสแกน QR Code และตรวจสอบความถูกต้องของสลิป...")
                try:
                    img_bytes = await img_att.read()
                    expected_amount = tdata.get("amount") or 0.0

                    # Run Slip Verifier Engine (Decodes QR, checks Anti-Replay & EasySlip API)
                    res = await verify_slip_image_or_payload(
                        channel_id=message.channel.id,
                        customer_id=message.author.id,
                        image_bytes=img_bytes,
                        expected_amount=expected_amount,
                        guild=message.guild,
                        user=message.author
                    )

                    if res.success:
                        verified_amount = res.amount if res.amount > 0 else (expected_amount or 100.0)

                        # Save slip image to Website/static/uploads/slips
                        slip_filename = f"slip_{res.slip_ref}_{int(time.time())}.png"
                        safe_slip_filename = "".join(c for c in slip_filename if c.isalnum() or c in "._-")
                        slip_save_dir = BASE_DIR / "Website" / "static" / "uploads" / "slips"
                        slip_save_dir.mkdir(parents=True, exist_ok=True)
                        slip_file_path = slip_save_dir / safe_slip_filename
                        slip_web_path = ""
                        try:
                            with open(slip_file_path, "wb") as f_slip:
                                f_slip.write(img_bytes)
                            slip_web_path = f"/static/uploads/slips/{safe_slip_filename}"
                        except Exception as e:
                            print(f"[-] Failed to save slip image to disk: {e}")

                        # Record payment in DB with slip image path
                        db.update_ticket_payment(message.channel.id, slip_ref=res.slip_ref, amount=verified_amount, slip_image_path=slip_web_path)

                        # Sync live payment to department's ongoing work channel
                        try:
                            from ongoing_manager import update_ongoing_card
                            asyncio.create_task(update_ongoing_card(message.guild, message.channel.id, amount=verified_amount, paid_status=1))
                        except Exception:
                            pass

                        # Dispatch to Verified Receipts Channel: 1563251864256909444
                        asyncio.create_task(post_verified_slip_receipt(
                            guild=message.guild,
                            channel=message.channel,
                            customer=message.author,
                            amount=verified_amount,
                            slip_ref=res.slip_ref,
                            payment_method="โอนเงินผ่านธนาคาร (ตรวจสอบสลิปผ่าน QR Code)",
                            admin=message.guild.get_member(tdata.get("claimed_admin_id") or 0),
                            department_name=tdata.get("category_key", "general")
                        ))

                        admin_id = tdata.get("claimed_admin_id")
                        customer_id = tdata.get("customer_id") or message.author.id

                        # Post receipt embed in ticket (Visible to BOTH customer and staff)
                        receipt_embed = discord.Embed(
                            title="💳 ยืนยันการชำระเงินสำเร็จเรียบร้อย! (Payment Verified)",
                            description=(
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"👤 **ผู้ชำระเงิน:** {message.author.mention}\n"
                                f"💰 **ยอดเงินชำระ:** `{verified_amount:,.2f}` บาท\n"
                                f"🧾 **รหัสสลิป / QR Ref:** `{res.slip_ref}`\n"
                                f"🔍 **การตรวจสอบ:** `สแกน QR Code บนสลิปผ่าน 100% (Anti-Replay Passed)`\n"
                                f"⏰ **เวลาทำรายการ:** <t:{int(time.time())}:F>\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                "🛡️ **ระบบปลดล็อกกระบวนการทำงานเรียบร้อย:**\n"
                                "• **ฝั่งแอดมิน:** สามารถกดเปลี่ยนสถานะงานตามขั้นตอนจริงได้ทันทีที่แผงควบคุมด้านล่าง\n"
                                "• **ฝั่งลูกค้า:** สามารถติดตามความคืบหน้าสด และกดยืนยันเมื่อได้รับสินค้าครบถ้วน"
                            ),
                            color=0x2ECC71
                        )
                        receipt_embed.set_footer(text="💎 SC-HUB ESCROW ENGINE • สลิปได้รับการตรวจสอบผ่าน QR Code และบันทึกลง Ledger")

                        status_embed = build_process_status_embed(stage_key="queued", amount=verified_amount, slip_ref=res.slip_ref)

                        # Public announcement in ticket visible to BOTH parties
                        await message.channel.send(
                            content=f"🎉 **แจ้งเตือนชำระเงินสำเร็จ!** <@{customer_id}> ได้ทำการชำระเงินเรียบร้อยแล้ว ทีมงาน <@{admin_id}> สามารถเริ่มดำเนินงานได้ทันทีครับ",
                            embed=receipt_embed
                        )

                        # Admin Control Panel
                        await message.channel.send(
                            content=f"🛠️ <@{admin_id}> **แผงควบคุมสถานะงาน (ฝั่งแอดมิน):**",
                            embed=status_embed,
                            view=ProcessAdminControlView(channel_id=message.channel.id)
                        )

                        # Customer Control Panel
                        await message.channel.send(
                            content=f"👤 <@{customer_id}> **แผงติดตามและยืนยันการรับสินค้า (ฝั่งลูกค้า):**",
                            view=ProcessCustomerControlView(channel_id=message.channel.id)
                        )

                        try:
                            await loading_msg.delete()
                        except Exception:
                            pass
                    else:
                        try:
                            await loading_msg.edit(content=f"{res.message}")
                        except Exception:
                            pass
                except Exception as ex:
                    print(f"[-] Slip QR scan error: {ex}")
                    try:
                        await loading_msg.edit(content=f"❌ เกิดข้อผิดพลาดในการตรวจสอบสลิป: `{ex}`")
                    except Exception:
                        pass

    # Check if message contains a TrueMoney gift voucher link
    if "gift.truemoney.com/campaign/?v=" in message.content:
        # Check if sent inside an active ticket channel
        tdata = db.get_ticket(message.channel.id)
        if tdata and tdata.get("paid_status") == 0:
            voucher_code = extract_voucher_code(message.content)
            if voucher_code:
                loading_msg = await message.reply("🧧 **ตรวจพบซองของขวัญ TrueMoney!** กำลังตรวจสอบและรับเงินเข้าสู่ระบบ...")
                res = await redeem_truemoney_voucher(
                    voucher_input=voucher_code,
                    channel_id=message.channel.id,
                    customer_id=message.author.id,
                    guild=message.guild,
                    user=message.author
                )
                if res.success:
                    db.update_ticket_payment(message.channel.id, slip_ref=f"TMN_{res.voucher_hash}", amount=res.amount)
                    try:
                        from ongoing_manager import update_ongoing_card
                        asyncio.create_task(update_ongoing_card(message.guild, message.channel.id, amount=res.amount, paid_status=1))
                    except Exception:
                        pass

                    # Dispatch to Verified Receipts Channel: 1563251864256909444
                    asyncio.create_task(post_verified_slip_receipt(
                        guild=message.guild,
                        channel=message.channel,
                        customer=message.author,
                        amount=res.amount,
                        slip_ref=f"TMN_{res.voucher_hash}",
                        payment_method="ซองของขวัญ TrueMoney (ดักซองอัตโนมัติ)",
                        admin=message.guild.get_member(tdata.get("claimed_admin_id") or 0),
                        department_name=tdata.get("category_key", "general")
                    ))

                    # Post receipt embed in ticket
                    receipt_embed = discord.Embed(
                        title="🧧 ยืนยันการรับเงินจากซองของขวัญ TrueMoney สำเร็จ!",
                        description=(
                            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 **ผู้ส่งซอง:** {message.author.mention}\n"
                            f"💰 **ยอดเงินในซอง:** `{res.amount:,.2f}` บาท\n"
                            f"🧾 **รหัสซอง (Hash):** `TMN_{res.voucher_hash}`\n"
                            f"⏰ **เวลาทำรายการ:** <t:{int(time.time())}:F>\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            "🛡️ **ระบบปลดล็อกกระบวนการทำงานเรียบร้อย:**\n"
                            "• แอดมินสามารถกดเปลี่ยนสถานะงานตามขั้นตอนจริงได้ทันทีที่แผงควบคุมด้านล่าง\n"
                            "• ลูกค้าสามารถติดตามความคืบหน้าสด และกดยืนยันเมื่อได้รับสินค้าครบถ้วน"
                        ),
                        color=0x2ECC71
                    )
                    receipt_embed.set_footer(text="💎 SC-HUB TRUEMONEY REDEEMER • ระบบดักซองอัตโนมัติ")

                    status_embed = build_process_status_embed(stage_key="queued", amount=res.amount, slip_ref=f"TMN_{res.voucher_hash}")
                    await message.channel.send(embed=receipt_embed)

                    admin_id = tdata.get("claimed_admin_id")
                    await message.channel.send(
                        content=f"🛠️ <@{admin_id}> **แผงควบคุมสถานะงาน (ฝั่งแอดมิน):**",
                        embed=status_embed,
                        view=ProcessAdminControlView(channel_id=message.channel.id)
                    )
                    customer_id = tdata.get("customer_id")
                    await message.channel.send(
                        content=f"👤 <@{customer_id}> **แผงติดตามและยืนยันการรับสินค้า (ฝั่งลูกค้า):**",
                        view=ProcessCustomerControlView(channel_id=message.channel.id)
                    )

                    try:
                        await loading_msg.edit(content=f"🎉 **รับเงินสำเร็จ!** ได้รับยอด `{res.amount:,.2f}` บาท บันทึกลงระบบและปลดล็อกตั๋วเรียบร้อยแล้ว!")
                    except Exception:
                        pass
                else:
                    try:
                        await loading_msg.edit(content=f"❌ {res.message}")
                    except Exception:
                        pass

    await bot.process_commands(message)


# ─────────────────────────────────────────────────────────────
# ⏰ SCHEDULED MIDNIGHT REVENUE SUMMARY (Channel: 1563251868501803048)
# ─────────────────────────────────────────────────────────────
@tasks.loop(time=MIDNIGHT_TIME)
async def midnight_summary_task():
    print("[*] [MIDNIGHT TASK] Running Midnight Daily Summary...")
    for guild in bot.guilds:
        try:
            ok, embed, msg = await post_daily_summary(guild)
            print(f"[+] [MIDNIGHT TASK] {guild.name}: {msg}")
        except Exception as e:
            print(f"[-] [MIDNIGHT TASK] Error for {guild.name}: {e}")


@midnight_summary_task.before_loop
async def before_midnight_summary():
    await bot.wait_until_ready()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, "original", error)
    print(f"[-] Command Error: {type(original).__name__}: {original}")
    msg = f"❌ เกิดข้อผิดพลาดในการประมวลผลคำสั่ง: `{original}`"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# 🛠️ SLASH COMMANDS: SETUP & DISPATCH ENGINE
# ─────────────────────────────────────────────────────────────

@bot.tree.command(
    name="setup_dispatch_system",
    description="ติดตั้งระบบจัดสรรงานและตั๋วครบวงจร (Verify + แยก 3 แผนก + บังคับเลือกห้อง Log)"
)
@app_commands.describe(
    verify_channel="ห้องสำหรับวางแผงยืนยันตัวตน Captcha",
    verified_role="บทบาทที่จะมอบให้เมื่อผู้ใช้ผ่านการยืนยันตัวตน",
    category_select_channel="ห้องสำหรับวางแผงเลือกหมวดหมู่ 3 สายงาน",
    transcript_log_channel="ห้องสำหรับเก็บบันทึกประวัติการแชท (HTML Transcript Audit Log) *บังคับเลือก*",
    ticket_category="หมวดหมู่หลัก (Category) ที่จะใช้สร้างห้องตั๋วงาน",
    owner_role="บทบาท Owner สำหรับเข้าถึงทุกห้องและรับแจ้งปัญหา",
    staff_role="บทบาท Staff/ทีมงาน ที่จะรับแจ้งเตือนเมื่อมีลูกค้าเรียก"
)
@app_commands.default_permissions(administrator=True)
async def setup_dispatch_system(
    interaction: discord.Interaction,
    verify_channel: discord.TextChannel,
    verified_role: discord.Role,
    category_select_channel: discord.TextChannel,
    transcript_log_channel: discord.TextChannel,
    ticket_category: Optional[discord.CategoryChannel] = None,
    owner_role: Optional[discord.Role] = None,
    staff_role: Optional[discord.Role] = None
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    # 1. Save Configurations to SQLite
    owner_role_id = owner_role.id if owner_role else config.DEFAULT_OWNER_ROLE_ID
    staff_role_id = staff_role.id if staff_role else config.DEFAULT_STAFF_ROLE_ID
    target_category_id = ticket_category.id if ticket_category else config.DEFAULT_CATEGORY_ID

    db.update_guild_config(
        guild.id,
        verified_role_id=verified_role.id,
        owner_role_id=owner_role_id,
        staff_role_id=staff_role_id,
        category_id=target_category_id,
        transcript_log_channel_id=transcript_log_channel.id
    )

    # 2. Deploy Step 1: Verification Panel
    verify_embed = build_verification_panel_embed(guild=guild, verified_role=verified_role)
    await verify_channel.send(embed=verify_embed, view=VerificationPanelView())

    # 3. Deploy Step 2: Category Selector Panel
    cat_embed = build_category_router_embed()
    await category_select_channel.send(embed=cat_embed, view=CategoryRouterView())

    # 4. Confirmation Follow-up
    summary_embed = discord.Embed(
        title="✅ ติดตั้งระบบ PAYOMBØYZ Dispatch สำเร็จเรียบร้อย!",
        description=(
            f"📍 **ห้อง Verify (Captcha):** {verify_channel.mention}\n"
            f"🎖️ **Verified Role:** {verified_role.mention}\n"
            f"🗂️ **ห้องเลือกหมวดหมู่:** {category_select_channel.mention}\n"
            f"📑 **ห้องเก็บบันทึก Transcript (Audit):** {transcript_log_channel.mention}\n"
            f"🛡️ **Owner Role:** <@&{owner_role_id}>\n"
            f"👥 **Staff Role:** <@&{staff_role_id}>\n\n"
            "💡 **ขั้นตอนต่อไป:**\n"
            "ใช้คำสั่ง `/setup_lobby_panel` ในห้องของแต่ละหมวดหมู่ (ห้องเติมเกมส์, สคริปต์, เว็บไซต์) "
            "เพื่อวางปุ่ม **[ 🔔 เรียกแอดมิน ]** และเปิดใช้งานระบบ Atomic Claim"
        ),
        color=config.COLOR_SUCCESS
    )
    await interaction.followup.send(embed=summary_embed, ephemeral=True)


@bot.tree.command(
    name="setup_lobby_panel",
    description="ส่งแผงเรียกลูกค้า/แอดมินรับงาน (Atomic Mutex Claim) เข้าห้องประจำแผนก"
)
@app_commands.describe(
    category="เลือกแผนกงานที่จะติดตั้งแผงควบคุม",
    target_channel="ห้องที่ต้องการส่งแผงควบคุม (เว้นว่างเพื่อส่งในห้องปัจจุบัน)"
)
@app_commands.default_permissions(administrator=True)
async def setup_lobby_panel(
    interaction: discord.Interaction,
    category: Literal["game", "script", "web"],
    target_channel: Optional[discord.TextChannel] = None
):
    channel = target_channel or interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ กรุณาเลือกห้อง Text Channel", ephemeral=True)
        return

    embed = build_department_lobby_embed(dept_key=category)
    view = DepartmentLobbyView(dept_key=category)

    await channel.send(embed=embed, view=view)
    dept_info = config.DEPARTMENTS.get(category, {})
    await interaction.response.send_message(
        f"✅ ติดตั้งแผงล็อบบี้แผนก **{dept_info.get('name', category)}** ในห้อง {channel.mention} สำเร็จแล้ว!",
        ephemeral=True
    )


@bot.tree.command(
    name="setup_dispute_panel",
    description="ติดตั้งแผงรับเรื่องร้องเรียนและแจ้งปัญหาส่งตรงถึงผู้บริหาร (Owner & หัวหน้าทีมงาน)"
)
@app_commands.describe(
    target_channel="ห้องที่ต้องการวางแผงแจ้งปัญหา (เว้นว่างเพื่อใช้ห้อง 🎫・ติดต่อและแจ้งปัญหา 1563251767674667019)"
)
@app_commands.default_permissions(administrator=True)
async def setup_dispute_panel(
    interaction: discord.Interaction,
    target_channel: Optional[discord.TextChannel] = None
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    channel = target_channel
    if not channel:
        ch_id = config.DISPUTE_PANEL_CHANNEL_ID
        ch = guild.get_channel(ch_id)
        if isinstance(ch, discord.TextChannel):
            channel = ch
        else:
            channel = interaction.channel

    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ กรุณาเลือกห้อง Text Channel", ephemeral=True)
        return

    embed = build_dispute_panel_embed()
    view = DisputePanelView()

    await channel.send(embed=embed, view=view)
    await interaction.response.send_message(
        f"✅ ติดตั้ง **แผงรับเรื่องร้องเรียนและแจ้งปัญหา (Executive Dispute Desk)** ในห้อง {channel.mention} สำเร็จแล้ว!\n"
        f"👑 เจ้าของร้าน: <@&{config.DEFAULT_OWNER_ROLE_ID}>\n"
        f"⚜️ หัวหน้าทีมงาน: <@&{config.DEFAULT_HEAD_STAFF_ROLE_ID}>",
        ephemeral=True
    )


# ─────────────────────────────────────────────────────────────
# 💳 FINANCIAL MANAGEMENT COMMANDS (LOCKED TO ROLE: OWNER)
# ─────────────────────────────────────────────────────────────

def check_is_owner(interaction: discord.Interaction) -> bool:
    """Strictly checks if user holds the Owner Role (1563251630101766211) or is Guild Owner."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.id == interaction.guild.owner_id:
        return True
    cfg = db.get_guild_config(interaction.guild.id)
    owner_role_id = cfg.get("owner_role_id") or config.DEFAULT_OWNER_ROLE_ID
    is_owner = any(r.id == owner_role_id for r in interaction.user.roles)

    if not is_owner:
        # Audit unauthorized administrative breach attempt immediately
        asyncio.create_task(log_security_anomaly(
            guild=interaction.guild,
            title="🚨 ตรวจพบความพยายามเข้าถึงการตั้งค่าการเงินโดยไม่ได้รับอนุญาต (Unauthorized Finance Access)",
            description=f"ผู้ใช้ {interaction.user.mention} พยายามเรียกใช้คำสั่งบริหารการเงินโดยไม่มีบทบาท Owner",
            incident_type="UNAUTHORIZED_FINANCE_ACCESS",
            severity="HIGH",
            user=interaction.user,
            channel=interaction.channel,
            fields=[
                ("👤 ผู้พยายามเข้าถึง", f"{interaction.user.mention} (`{interaction.user.id}`)", True),
                ("🛡️ บทบาทที่จำเป็น", f"<@&{owner_role_id}>", True)
            ]
        ))
    return is_owner


@bot.tree.command(
    name="config_finance",
    description="ตั้งค่าระบบการเงิน: API ตรวจสลิปธนาคาร และเบอร์รับซองทรู (🔒 เฉพาะยศ Owner เท่านั้น)"
)
@app_commands.describe(
    slip_api_url="URL สำหรับส่งตรวจสลิป (เช่น https://api.easyslip.com/v1/verify)",
    slip_api_key="API Key / Token สำหรับตรวจสลิป",
    truemoney_phone="เบอร์โทรศัพท์ TrueMoney Wallet สำหรับรับเงินซองของขวัญ (เช่น 0812345678)"
)
async def cmd_config_finance(
    interaction: discord.Interaction,
    slip_api_url: Optional[str] = None,
    slip_api_key: Optional[str] = None,
    truemoney_phone: Optional[str] = None
):
    guild = interaction.guild
    if not guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    # STRICT OWNER ROLE LOCK
    if not check_is_owner(interaction):
        await interaction.response.send_message(
            f"❌ **ปฏิเสธการเข้าถึง:** การตั้งค่าระบบการเงินถูกล็อกไว้สำหรับ **👑 เจ้าของร้าน (Owner: <@&{config.DEFAULT_OWNER_ROLE_ID}>)** เท่านั้น!",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    updates = {}
    changes_desc = []

    if slip_api_url is not None:
        clean_url = slip_api_url.strip()
        updates["slip_api_url"] = clean_url
        changes_desc.append(f"• **Bank Slip API URL:** `{clean_url}`")

    if slip_api_key is not None:
        clean_key = slip_api_key.strip()
        updates["slip_api_key"] = clean_key
        masked_key = f"{clean_key[:4]}••••{clean_key[-4:]}" if len(clean_key) > 8 else "••••••••"
        changes_desc.append(f"• **Bank Slip API Key:** `{masked_key}`")

    if truemoney_phone is not None:
        clean_p = re.sub(r'[^0-9]', '', truemoney_phone.strip())
        if len(clean_p) != 10 or not clean_p.startswith("0"):
            await interaction.followup.send(
                "❌ รูปแบบเบอร์ TrueMoney ไม่ถูกต้อง (ต้องเป็นตัวเลข 10 หลักขึ้นต้นด้วย 0 เช่น `0812345678`)",
                ephemeral=True
            )
            return
        updates["truemoney_phone"] = clean_p
        changes_desc.append(f"• **เบอร์รับซอง TrueMoney Wallet:** `{clean_p[:3]}••••{clean_p[-3:]}`")

    if not updates:
        await interaction.followup.send("⚠️ กรุณาระบุค่าที่ต้องการเปลี่ยนแปลงอย่างน้อย 1 รายการ", ephemeral=True)
        return

    db.update_guild_config(guild.id, **updates)

    embed = discord.Embed(
        title="💳 อัปเดตการตั้งค่าระบบการเงินสำเร็จ (Finance Config Updated)",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 **ผู้ดำเนินการ:** {interaction.user.mention}\n"
            "🔒 **ระดับความปลอดภัย:** `Owner Permission Verified`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📝 **รายการที่เปลี่ยนแปลง:**\n" + "\n".join(changes_desc) + "\n\n"
            "🛡️ *การตั้งค่านี้มีผลต่อระบบตรวจสลิปและระบบดักซองทรูทันที*"
        ),
        color=config.COLOR_SUCCESS
    )
    embed.set_footer(text="💎 SC-HUB FINANCIAL SECURITY ENGINE")
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(
    name="view_finance_config",
    description="ดูการตั้งค่าระบบการเงินและเบอร์รับซองทรูในปัจจุบัน (🔒 เฉพาะยศ Owner เท่านั้น)"
)
async def cmd_view_finance_config(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    if not check_is_owner(interaction):
        await interaction.response.send_message(
            f"❌ **ปฏิเสธการเข้าถึง:** คำสั่งนี้สงวนสิทธิ์เฉพาะบทบาท **👑 เจ้าของร้าน (Owner: <@&{config.DEFAULT_OWNER_ROLE_ID}>)** เท่านั้น!",
            ephemeral=True
        )
        return

    cfg = db.get_guild_config(guild.id)
    slip_url = cfg.get("slip_api_url") or config.SLIP_API_URL or "ไม่ได้กำหนด"
    raw_key = (cfg.get("slip_api_key") or config.SLIP_API_KEY or "").strip()
    masked_key = f"{raw_key[:4]}••••{raw_key[-4:]}" if len(raw_key) > 8 else ("ตั้งค่าแล้ว" if raw_key else "ไม่ได้กำหนด (ยังไม่เปิดให้บริการ)")
    phone = cfg.get("truemoney_phone") or config.TRUEMONEY_PHONE or "ไม่ได้กำหนด"
    masked_phone = f"{phone[:3]}••••{phone[-3:]}" if len(phone) == 10 else phone
    bank_status = "🟢 พร้อมใช้งาน (EasySlip Connected)" if raw_key else "🟡 ยังไม่เปิดให้บริการ (รอใส่ API Key)"

    embed = discord.Embed(
        title="💳 การตั้งค่าระบบการเงินปัจจุบัน (Active Financial Settings)",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 **สถานะระบบชำระผ่านธนาคาร:** `{bank_status}`\n"
            f"🌐 **Bank Slip API URL:** `{slip_url}`\n"
            f"🔑 **Bank Slip API Key:** `{masked_key}`\n"
            f"📱 **เบอร์รับซอง TrueMoney / พร้อมเพย์:** `{masked_phone}`\n"
            f"✅ **ห้องสลิปที่ตรวจสำเร็จ:** <#{cfg.get('verified_slip_channel_id') or config.VERIFIED_SLIP_CHANNEL_ID}>\n"
            f"🎭 **ห้องประวัติเปลี่ยนยศ:** <#{cfg.get('role_audit_channel_id') or config.ROLE_AUDIT_CHANNEL_ID}>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "💡 *ต้องการเปลี่ยน API Key หรือเบอร์รับซอง ให้ใช้คำสั่ง `/config_finance` (เฉพาะยศ Owner)*"
        ),
        color=config.COLOR_PRIMARY_GOLD
    )
    embed.set_footer(text="💎 SC-HUB FINANCIAL DESK")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="create_qr",
    description="สร้าง QR Code พร้อมเพย์ล็อคยอดเงินอัตโนมัติ (Dynamic PromptPay QR)"
)
@app_commands.describe(
    amount="ยอดเงินที่ต้องการล็อค (เช่น 150 หรือ 350.50)",
    promptpay_target="เบอร์พร้อมเพย์หรือเลขบัตร (หากไม่ระบุ จะใช้เบอร์ของร้านตามค่าเริ่มต้น)",
    note="รายละเอียดหรือรายการสั่งซื้อ (ไม่บังคับ)"
)
async def cmd_create_qr(
    interaction: discord.Interaction,
    amount: float,
    promptpay_target: Optional[str] = None,
    note: Optional[str] = None
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("❌ ยอดเงินต้องมากกว่า 0 บาท", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    cfg = db.get_guild_config(guild.id)
    target = promptpay_target or cfg.get("truemoney_phone") or config.TRUEMONEY_PHONE or "0829934210"

    from promptpay_engine import build_promptpay_qr_embed
    qr_embed, qr_file = build_promptpay_qr_embed(
        target=target,
        amount=amount,
        ticket_num=0,
        dept_name="SC-HUB PromptPay Gateway"
    )

    content = f"📱 **QR Code พร้อมเพย์ล็อคยอดเงิน** (สร้างโดย {interaction.user.mention})"
    if note:
        content += f"\n📝 **รายการ:** `{note}`"

    await interaction.followup.send(content=content, embed=qr_embed, file=qr_file)


@bot.tree.command(
    name="dispatch_status",
    description="ตรวจสอบสถิติการเปิดตั๋ว, คิวงาน และประวัติสลิปในเซิร์ฟเวอร์"
)
@app_commands.default_permissions(administrator=True)
async def dispatch_status(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    cfg = db.get_guild_config(guild.id)
    
    with db._get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM active_tickets WHERE guild_id = ?", (str(guild.id),))
        active_cnt = c.fetchone()["cnt"]

        c.execute("SELECT COUNT(*) as cnt FROM pending_calls WHERE guild_id = ? AND status = 'waiting'", (str(guild.id),))
        waiting_cnt = c.fetchone()["cnt"]

        c.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(amount), 0.0) as total FROM slip_ledger")
        slip_row = c.fetchone()
        slip_cnt = slip_row["cnt"]
        total_revenue = slip_row["total"]

    log_ch = guild.get_channel(cfg.get("transcript_log_channel_id") or 0)
    log_ch_str = log_ch.mention if log_ch else "ยังไม่กำหนด"

    embed = discord.Embed(
        title="📊 สถิติระบบ SC-HUB Dispatch & Ticket System",
        description=(
            f"🔢 **หมายเลขตั๋วสะสมทั้งหมด:** `{cfg.get('counter', 0):,}` ตั๋ว\n"
            f"🎫 **ตั๋วที่กำลังดำเนินการอยู่:** `{active_cnt:,}` ห้อง\n"
            f"⏳ **คิวลูกค้าที่รอแอดมินรับงาน:** `{waiting_cnt:,}` คิว\n"
            f"🧾 **สลิปที่ผ่านการตรวจสอบแล้ว:** `{slip_cnt:,}` รายการ\n"
            f"💰 **ยอดเงินรวมในระบบ:** `{total_revenue:,.2f}` บาท\n"
            f"📑 **ห้อง Audit Transcript:** {log_ch_str}\n"
            f"🌐 **Website API Webhook:** `{cfg.get('web_api_url') or config.WEB_API_LOG_URL}`"
        ),
        color=config.COLOR_PRIMARY_GOLD
    )
    embed.set_footer(text="💎 SC-HUB DISPATCH METRICS")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="dispatch_view_config",
    description="ดูการตั้งค่าทั้งหมดของระบบ SC-HUB ในเซิร์ฟเวอร์นี้ (Roles, Channels, APIs)"
)
@app_commands.default_permissions(administrator=True)
async def dispatch_view_config(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    cfg = db.get_guild_config(guild.id)
    dept_roles = cfg.get("dept_roles", {})

    verified_r = guild.get_role(cfg.get("verified_role_id") or config.DEFAULT_VERIFIED_ROLE_ID or 0)
    owner_r = guild.get_role(cfg.get("owner_role_id") or config.DEFAULT_OWNER_ROLE_ID or 0)
    manager_r = guild.get_role(cfg.get("manager_role_id") or config.DEFAULT_MANAGER_ROLE_ID or 0)
    staff_r = guild.get_role(cfg.get("staff_role_id") or config.DEFAULT_STAFF_ROLE_ID or 0)

    game_staff_r = guild.get_role(dept_roles.get("game_staff_role_id") or config.DEPARTMENTS["game"]["staff_role_id"] or 0)
    script_staff_r = guild.get_role(dept_roles.get("script_staff_role_id") or config.DEPARTMENTS["script"]["staff_role_id"] or 0)
    web_staff_r = guild.get_role(dept_roles.get("web_staff_role_id") or config.DEPARTMENTS["web"]["staff_role_id"] or 0)

    log_ch = guild.get_channel(cfg.get("transcript_log_channel_id") or 0)
    cat_ch = guild.get_channel(cfg.get("category_id") or 0)

    # Mask API keys
    raw_slip_key = cfg.get("slip_api_key") or config.SLIP_API_KEY or ""
    masked_slip_key = f"{raw_slip_key[:4]}••••{raw_slip_key[-4:]}" if len(raw_slip_key) > 8 else ("ตั้งค่าแล้ว" if raw_slip_key else "ไม่ได้ตั้งค่า")
    
    raw_web_token = cfg.get("web_api_token") or config.WEB_API_LOG_TOKEN or ""
    masked_web_token = f"{raw_web_token[:3]}••••{raw_web_token[-3:]}" if len(raw_web_token) > 6 else ("ตั้งค่าแล้ว" if raw_web_token else "ไม่ได้ตั้งค่า")

    embed = discord.Embed(
        title="⚙️ การตั้งค่าระบบ SC-HUB ทั้งหมด (Active Server Config)",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎖️ **การตั้งค่าบทบาท (Roles):**\n"
            f"• **Verified Role (Captcha):** {verified_r.mention if verified_r else '`ยังไม่ได้ตั้ง`'}\n"
            f"• **Owner Role (Bypass/Alert):** {owner_r.mention if owner_r else '`ยังไม่ได้ตั้ง`'}\n"
            f"• **ผู้จัดการร้าน (Manager):** {manager_r.mention if manager_r else '`ยังไม่ได้ตั้ง`'}\n"
            f"• **Staff Role (ส่วนกลาง):** {staff_r.mention if staff_r else '`ยังไม่ได้ตั้ง`'}\n"
            f"• **แอดมินแผนกเติมเกม:** {game_staff_r.mention if game_staff_r else '`(ใช้ยศส่วนกลาง)`'}\n"
            f"• **แอดมินแผนกสคริปต์:** {script_staff_r.mention if script_staff_r else '`(ใช้ยศส่วนกลาง)`'}\n"
            f"• **แอดมินแผนกเว็บไซต์:** {web_staff_r.mention if web_staff_r else '`(ใช้ยศส่วนกลาง)`'}\n\n"
            "📁 **การตั้งค่าห้อง & หมวดหมู่ (Channels):**\n"
            f"• **ห้องเก็บบันทึก Transcript (Audit):** {log_ch.mention if log_ch else '`❌ ยังไม่ได้ตั้ง (บังคับตั้ง)`'}\n"
            f"• **หมวดหมู่สำหรับเปิดตั๋ว (Category):** {cat_ch.name if cat_ch else '`หมวดหมู่ปัจจุบัน`'}\n\n"
            "🌐 **การตั้งค่า API เชื่อมต่อภายนอก (External APIs):**\n"
            f"• **Web API URL (Website Logs):** `{cfg.get('web_api_url') or config.WEB_API_LOG_URL}`\n"
            f"• **Web API Token:** `{masked_web_token}`\n"
            f"• **Slip API URL:** `{cfg.get('slip_api_url') or config.SLIP_API_URL}`\n"
            f"• **Slip API Key:** `{masked_slip_key}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *คุณสามารถแก้ไขค่าเหล่านี้ได้ทันทีผ่านคำสั่ง `/config_roles`, `/config_channels` และ `/config_apis`*"
        ),
        color=0x00A8FF
    )
    embed.set_footer(text="💎 SC-HUB CONFIGURATION MANAGER")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="config_apis",
    description="ปรับแต่งการตั้งค่า Website Log API และ Slip Verification API"
)
@app_commands.describe(
    web_api_url="URL Endpoint ของเว็บไซต์สำหรับรับ Log สรุปการปิดตั๋ว",
    web_api_token="Authorization Bearer Token สำหรับ Web API (เว้นว่างได้)",
    slip_api_url="URL Endpoint สำหรับตรวจสอบสลิป (เช่น EasySlip / SlipOK)",
    slip_api_key="API Key สำหรับตรวจสอบสลิป"
)
@app_commands.default_permissions(administrator=True)
async def config_apis(
    interaction: discord.Interaction,
    web_api_url: Optional[str] = None,
    web_api_token: Optional[str] = None,
    slip_api_url: Optional[str] = None,
    slip_api_key: Optional[str] = None
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    updates = {}
    if web_api_url is not None:
        updates["web_api_url"] = web_api_url.strip()
    if web_api_token is not None:
        updates["web_api_token"] = web_api_token.strip()
    if slip_api_url is not None:
        updates["slip_api_url"] = slip_api_url.strip()
    if slip_api_key is not None:
        updates["slip_api_key"] = slip_api_key.strip()

    if not updates:
        await interaction.response.send_message("⚠️ กรุณาระบุค่าอย่างน้อย 1 อย่างที่ต้องการปรับแต่ง", ephemeral=True)
        return

    db.update_guild_config(guild.id, **updates)

    lines = []
    for k, v in updates.items():
        masked_v = f"{v[:4]}••••{v[-4:]}" if "key" in k or "token" in k and len(v) > 8 else v
        lines.append(f"• **{k}:** `{masked_v}`")

    embed = discord.Embed(
        title="✅ อัปเดตการตั้งค่า API สำเร็จเรียบร้อย!",
        description="รายการที่ถูกเปลี่ยนแปลง:\n" + "\n".join(lines),
        color=config.COLOR_SUCCESS
    )
    embed.set_footer(text="💎 SC-HUB API CONFIG")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="config_roles",
    description="ปรับแต่งบทบาท (Roles) ทั้งยศยืนยันตัวตน, Owner, ผู้จัดการ, ยศทีมงาน และยศลูกค้า 3 แผนก"
)
@app_commands.describe(
    verified_role="บทบาทเมื่อผู้ใช้ผ่านการยืนยันตัวตน Captcha",
    owner_role="บทบาท Owner สำหรับเข้าถึงทุกห้องและรับแจ้งเหตุฉุกเฉิน",
    manager_role="บทบาทผู้จัดการร้าน (Manager) ดูแลทุกตั๋วงาน",
    general_staff_role="บทบาททีมงานส่วนกลาง (เมื่อแผนกไม่มีแอดมินเฉพาะ)",
    game_staff_role="บทบาทแอดมินเฉพาะแผนกเติมเกมส์",
    script_staff_role="บทบาทแอดมินเฉพาะแผนกซื้อขายสคริปต์",
    web_staff_role="บทบาทแอดมินเฉพาะแผนกรับทำ Website",
    customer_game_role="บทบาทลูกค้าเฉพาะแผนกเติมเกมส์",
    customer_script_role="บทบาทลูกค้าเฉพาะแผนกซื้อขายสคริปต์",
    customer_web_role="บทบาทลูกค้าเฉพาะแผนกรับทำ Website"
)
@app_commands.default_permissions(administrator=True)
async def config_roles(
    interaction: discord.Interaction,
    verified_role: Optional[discord.Role] = None,
    owner_role: Optional[discord.Role] = None,
    manager_role: Optional[discord.Role] = None,
    general_staff_role: Optional[discord.Role] = None,
    game_staff_role: Optional[discord.Role] = None,
    script_staff_role: Optional[discord.Role] = None,
    web_staff_role: Optional[discord.Role] = None,
    customer_game_role: Optional[discord.Role] = None,
    customer_script_role: Optional[discord.Role] = None,
    customer_web_role: Optional[discord.Role] = None
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    cfg = db.get_guild_config(guild.id)
    dept_roles = cfg.get("dept_roles", {})

    updates = {}
    lines = []

    if verified_role:
        updates["verified_role_id"] = verified_role.id
        lines.append(f"• **Verified Role:** {verified_role.mention}")
    if owner_role:
        updates["owner_role_id"] = owner_role.id
        lines.append(f"• **Owner Role:** {owner_role.mention}")
    if manager_role:
        updates["manager_role_id"] = manager_role.id
        lines.append(f"• **ผู้จัดการร้าน (Manager):** {manager_role.mention}")
    if general_staff_role:
        updates["staff_role_id"] = general_staff_role.id
        lines.append(f"• **Staff Role (ส่วนกลาง):** {general_staff_role.mention}")
    if game_staff_role:
        dept_roles["game_staff_role_id"] = game_staff_role.id
        lines.append(f"• **แอดมินแผนกเติมเกมส์:** {game_staff_role.mention}")
    if script_staff_role:
        dept_roles["script_staff_role_id"] = script_staff_role.id
        lines.append(f"• **แอดมินแผนกสคริปต์:** {script_staff_role.mention}")
    if web_staff_role:
        dept_roles["web_staff_role_id"] = web_staff_role.id
        lines.append(f"• **แอดมินแผนกเว็บไซต์:** {web_staff_role.mention}")
    if customer_game_role:
        dept_roles["game"] = customer_game_role.id
        lines.append(f"• **ลูกค้ารับบทบาทเติมเกมส์:** {customer_game_role.mention}")
    if customer_script_role:
        dept_roles["script"] = customer_script_role.id
        lines.append(f"• **ลูกค้ารับบทบาทสคริปต์:** {customer_script_role.mention}")
    if customer_web_role:
        dept_roles["web"] = customer_web_role.id
        lines.append(f"• **ลูกค้ารับบทบาทเว็บไซต์:** {customer_web_role.mention}")

    if not updates and not lines:
        await interaction.response.send_message("⚠️ กรุณาเลือกบทบาทที่ต้องการเปลี่ยนอย่างน้อย 1 รายการ", ephemeral=True)
        return

    if dept_roles:
        updates["dept_roles"] = dept_roles

    db.update_guild_config(guild.id, **updates)

    embed = discord.Embed(
        title="✅ อัปเดตการตั้งค่าบทบาท (Roles) สำเร็จเรียบร้อย!",
        description="รายการบทบาทที่ได้รับการตั้งค่าใหม่:\n" + "\n".join(lines),
        color=config.COLOR_SUCCESS
    )
    embed.set_footer(text="💎 SC-HUB ROLE MANAGER")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="config_channels",
    description="ปรับแต่งห้องบันทึกประวัติ (Audit Transcript Log), ห้องต้อนรับ และหมวดหมู่สร้างตั๋ว (Category)"
)
@app_commands.describe(
    transcript_log_channel="ห้อง Text Channel สำหรับบันทึกไฟล์ประวัติแชท HTML เมื่อปิดตั๋ว",
    ticket_category="หมวดหมู่หลัก (Category Channel) สำหรับสร้างห้องตั๋วงาน",
    welcome_channel="ห้องสำหรับส่งข้อความและ Welcome Banner ต้อนรับสมาชิกใหม่ (ค่าเริ่มต้น: 1563251676830236782)"
)
@app_commands.default_permissions(administrator=True)
async def config_channels(
    interaction: discord.Interaction,
    transcript_log_channel: Optional[discord.TextChannel] = None,
    ticket_category: Optional[discord.CategoryChannel] = None,
    welcome_channel: Optional[discord.TextChannel] = None
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    updates = {}
    lines = []
    if transcript_log_channel:
        updates["transcript_log_channel_id"] = transcript_log_channel.id
        lines.append(f"• **ห้องเก็บบันทึก Transcript (Audit):** {transcript_log_channel.mention}")
    if ticket_category:
        updates["category_id"] = ticket_category.id
        lines.append(f"• **หมวดหมู่สร้างตั๋ว (Category):** `{ticket_category.name}`")
    if welcome_channel:
        updates["welcome_channel_id"] = welcome_channel.id
        lines.append(f"• **ห้องต้อนรับสมาชิก (Welcome Channel):** {welcome_channel.mention}")

    if not updates:
        await interaction.response.send_message("⚠️ กรุณาระบุห้องหรือหมวดหมู่ที่ต้องการเปลี่ยน", ephemeral=True)
        return

    db.update_guild_config(guild.id, **updates)

    embed = discord.Embed(
        title="✅ อัปเดตห้องและหมวดหมู่สำเร็จเรียบร้อย!",
        description="รายการที่ถูกเปลี่ยนแปลง:\n" + "\n".join(lines),
        color=config.COLOR_SUCCESS
    )
    embed.set_footer(text="💎 SC-HUB CHANNEL MANAGER")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name="test_welcome",
    description="ทดสอบส่งข้อความต้อนรับและ Welcome Banner ลงในห้องต้อนรับ (1563251676830236782)"
)
@app_commands.describe(
    target_member="เลือกสมาชิกที่ต้องการใช้ทดสอบ (ค่าเริ่มต้น: ตัวคุณเอง)"
)
@app_commands.default_permissions(administrator=True)
async def test_welcome(
    interaction: discord.Interaction,
    target_member: Optional[discord.Member] = None
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    member = target_member or interaction.user
    if not isinstance(member, discord.Member):
        try:
            member = await guild.fetch_member(member.id)
        except Exception:
            pass

    from welcome_card import send_welcome_announcement
    ok = await send_welcome_announcement(guild=guild, member=member)
    if ok:
        await interaction.followup.send(
            f"✅ ส่งการ์ดต้อนรับของ {member.mention} ไปยังห้องต้อนรับ <#1563251676830236782> เรียบร้อยแล้ว!",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "⚠️ ไม่สามารถส่งการ์ดต้อนรับได้ (โปรดตรวจสอบห้องต้อนรับและสิทธิ์ของบอท)",
            ephemeral=True
        )


@bot.tree.command(
    name="panel_send",
    description="ส่งแผงควบคุมเดี่ยว (Verify Panel หรือ Category Router) ไปยังห้องที่เลือก"
)
@app_commands.describe(
    panel_type="เลือกประเภทแผงควบคุมที่จะส่ง",
    target_channel="ห้องที่ต้องการส่ง (เว้นว่างเพื่อส่งในห้องปัจจุบัน)"
)
@app_commands.default_permissions(administrator=True)
async def panel_send(
    interaction: discord.Interaction,
    panel_type: Literal["verify", "category"],
    target_channel: Optional[discord.TextChannel] = None
):
    channel = target_channel or interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ กรุณาเลือกห้อง Text Channel", ephemeral=True)
        return

    guild = interaction.guild
    if panel_type == "verify":
        cfg = db.get_guild_config(guild.id)
        role = guild.get_role(cfg.get("verified_role_id") or 0)
        embed = build_verification_panel_embed(guild=guild, verified_role=role)
        view = VerificationPanelView()
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ ส่งแผง **Verification Panel** ไปที่ {channel.mention} สำเร็จแล้ว!", ephemeral=True)
    elif panel_type == "category":
        embed = build_category_router_embed()
        view = CategoryRouterView()
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ ส่งแผง **Category Router** ไปที่ {channel.mention} สำเร็จแล้ว!", ephemeral=True)


@bot.tree.command(
    name="ticket_add_user",
    description="เพิ่มสมาชิกหรือทีมงานเพิ่มเติมเข้ามาในห้องตั๋วนี้"
)
@app_commands.describe(user="สมาชิกที่ต้องการเชิญเข้ามาในห้องตั๋ว")
@app_commands.default_permissions(manage_channels=True)
async def ticket_add_user(interaction: discord.Interaction, user: discord.Member):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในห้องตั๋ว", ephemeral=True)
        return

    tdata = db.get_ticket(channel.id)
    if not tdata:
        await interaction.response.send_message("❌ ห้องนี้ไม่ใช่ห้องตั๋วที่ลงทะเบียนในระบบ", ephemeral=True)
        return

    try:
        await channel.set_permissions(
            user,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        )
        await interaction.response.send_message(f"✅ เพิ่ม {user.mention} เข้าสู่ห้องตั๋วนี้เรียบร้อยแล้ว!")
    except Exception as e:
        await interaction.response.send_message(f"❌ ไม่สามารถเพิ่มสมาชิกได้: {e}", ephemeral=True)


@bot.tree.command(
    name="ticket_remove_user",
    description="นำสมาชิกออกจากห้องตั๋วนี้"
)
@app_commands.describe(user="สมาชิกที่ต้องการนำออกจากห้องตั๋ว")
@app_commands.default_permissions(manage_channels=True)
async def ticket_remove_user(interaction: discord.Interaction, user: discord.Member):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในห้องตั๋ว", ephemeral=True)
        return

    tdata = db.get_ticket(channel.id)
    if not tdata:
        await interaction.response.send_message("❌ ห้องนี้ไม่ใช่ห้องตั๋วที่ลงทะเบียนในระบบ", ephemeral=True)
        return

    try:
        await channel.set_permissions(user, overwrite=None)
        await interaction.response.send_message(f"✅ นำ {user.mention} ออกจากห้องตั๋วนี้เรียบร้อยแล้ว!")
    except Exception as e:
        await interaction.response.send_message(f"❌ ไม่สามารถนำสมาชิกออกได้: {e}", ephemeral=True)


@bot.tree.command(
    name="ticket_force_close",
    description="[แอดมิน] บังคับปิดตั๋วและประมวลผล Dual Logging ทันที"
)
@app_commands.describe(reason="เหตุผลในการบังคับปิดตั๋ว")
@app_commands.default_permissions(manage_channels=True)
async def ticket_force_close(interaction: discord.Interaction, reason: Optional[str] = "บังคับปิดโดยแอดมิน"):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในห้องตั๋ว", ephemeral=True)
        return

    from views.ticket_view import execute_close_and_dual_log
    await execute_close_and_dual_log(interaction, reason=reason)


@bot.tree.command(
    name="test_apis",
    description="ทดสอบการเชื่อมต่อ Website API และ Slip API พร้อมวัดเวลาตอบสนอง (Latency)"
)
@app_commands.default_permissions(administrator=True)
async def test_apis(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    cfg = db.get_guild_config(guild.id)

    web_url = cfg.get("web_api_url") or config.WEB_API_LOG_URL
    slip_url = cfg.get("slip_api_url") or config.SLIP_API_URL

    results = []

    # 1. Test Web API
    if web_url:
        t0 = time.time()
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(web_url, timeout=5) as resp:
                    lat = int((time.time() - t0) * 1000)
                    results.append(f"🌐 **Website API:** 🟢 เชื่อมต่อได้ (Status: `{resp.status}`, `{lat}ms`)")
        except Exception as e:
            results.append(f"🌐 **Website API:** 🔴 ล้มเหลว (`{e}`)")
    else:
        results.append("🌐 **Website API:** ⚪ ไม่ได้กำหนด URL")

    # 2. Test Slip API
    if slip_url:
        t0 = time.time()
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(slip_url, timeout=5) as resp:
                    lat = int((time.time() - t0) * 1000)
                    results.append(f"🧾 **Slip API:** 🟢 เชื่อมต่อได้ (Status: `{resp.status}`, `{lat}ms`)")
        except Exception as e:
            results.append(f"🧾 **Slip API:** 🟡 สื่อสารได้แต่อาจต้องใช้ POST (`{type(e).__name__}`)")
    else:
        results.append("🧾 **Slip API:** ⚪ ไม่ได้กำหนด URL")

    test_embed = discord.Embed(
        title="📡 ผลการทดสอบการเชื่อมต่อ API (Connectivity Diagnostics)",
        description="\n".join(results),
        color=config.COLOR_PRIMARY_GOLD
    )
    test_embed.set_footer(text="💎 SC-HUB DIAGNOSTICS")
    await interaction.followup.send(embed=test_embed, ephemeral=True)


@bot.tree.command(
    name="sync_commands",
    description="บังคับซิงค์ Slash Commands ใหม่ทันที"
)
@app_commands.default_permissions(administrator=True)
async def sync_commands(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        synced = await bot.tree.sync()
        await interaction.followup.send(f"✅ ซิงค์ Slash Commands เรียบร้อยแล้ว (ทั้งหมด {len(synced)} คำสั่ง)", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ ซิงค์คำสั่งล้มเหลว: `{e}`", ephemeral=True)


@bot.tree.command(
    name="daily_summary",
    description="สร้างและส่งรายงานสรุปยอดรายวันรอบเที่ยงคืนทันที (สรุปยอดขาย 3 แผนก + สถิติงาน)"
)
@app_commands.describe(
    send_to_channel="ส่งเข้าห้องสรุปยอดจริง (1563251868501803048) หรือไม่ (ค่าเริ่มต้น: ดูเฉพาะคุณ)",
    lookback_hours="ช่วงเวลาย้อนหลังที่ต้องการคำนวณยอด (ชั่วโมง, ค่าเริ่มต้น: 24)"
)
@app_commands.default_permissions(administrator=True)
async def cmd_daily_summary(
    interaction: discord.Interaction,
    send_to_channel: bool = False,
    lookback_hours: int = 24
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=not send_to_channel, thinking=True)
    lookback_seconds = max(1, lookback_hours) * 3600
    now_ts = time.time()
    data = db.get_daily_summary_data(guild.id, start_ts=now_ts - lookback_seconds, end_ts=now_ts)
    embed = build_daily_summary_embed(guild, data)

    if send_to_channel:
        ch = guild.get_channel(config.DAILY_SUMMARY_CHANNEL_ID)
        if isinstance(ch, discord.TextChannel):
            await ch.send(embed=embed)
            await interaction.followup.send(f"✅ ส่งรายงานสรุปยอดรายวันไปยัง {ch.mention} เรียบร้อยแล้ว!", ephemeral=True)
        else:
            await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(
    name="test_anomaly_log",
    description="ทดสอบส่งการแจ้งเตือนความผิดปรกติเข้าห้อง Sentinel Guard (1563251866517770250)"
)
@app_commands.describe(
    incident_type="ประเภทเหตุการณ์จำลอง",
    severity="ระดับความรุนแรง"
)
@app_commands.default_permissions(administrator=True)
async def cmd_test_anomaly_log(
    interaction: discord.Interaction,
    incident_type: Literal["duplicate_slip", "fake_slip", "captcha_brute_force", "mutex_collision", "emergency_escalation"] = "duplicate_slip",
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "URGENT"] = "HIGH"
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    mock_scenarios = {
        "duplicate_slip": (
            "ตรวจพบการส่งสลิปซ้ำ (Duplicate Slip Replay)",
            "ผู้ใช้ส่งสลิปที่มีเลขอ้างอิง `TX_MOCK_DUPLICATE_99` ซึ่งมีในระบบแล้ว",
            [("🧾 หมายเลขอ้างอิง", "`TX_MOCK_DUPLICATE_99`", True), ("💰 ยอดเงินในสลิป", "`500.00 บาท`", True)]
        ),
        "fake_slip": (
            "ตรวจพบสลิปปลอมแปลง / สลิปไม่ถูกต้อง",
            "API ตรวจสอบสลิปปฏิเสธ: ไม่พบรายการโอนเงินในระบบธนาคาร",
            [("🔍 ผลการสแกน", "`API Error: Transaction not found`", False)]
        ),
        "captcha_brute_force": (
            "ตรวจพบพฤติกรรมสุ่มตอบ Captcha ผิดซ้ำซ้อน",
            "ผู้ใช้กรอกรหัส Captcha ผิดพลาดติดต่อกัน 3 ครั้ง อาจเป็นบอทหรือสคริปต์สแปม",
            [("🔢 ผิดพลาดสะสม", "`3 ครั้ง`", True)]
        ),
        "mutex_collision": (
            "ตรวจพบการแย่งรับงานชนกัน (Mutex Lock Contention)",
            "แอดมินสองท่านกดปุ่มรับลูกค้าในเวลาเดียวกัน ระบบ Atomic Lock มอบสิทธิ์ให้แอดมินคนแรก",
            [("⚡ สถานะ", "`Mutex Resolved Safely`", False)]
        ),
        "emergency_escalation": (
            "ลูกค้ากดเรียก Owner ระงับข้อพิพาทในตั๋ว",
            "ลูกค้าส่งสัญญาณฉุกเฉินต้องการให้เจ้าของร้านเข้ามาช่วยตรวจสอบ",
            [("📍 ห้องตั๋ว", f"{interaction.channel.mention}", True)]
        )
    }

    title, desc, fields = mock_scenarios.get(incident_type, ("เหตุการณ์จำลอง", "คำอธิบาย", []))
    ok = await log_security_anomaly(
        guild=guild,
        title=title,
        description=desc,
        incident_type=incident_type.upper(),
        severity=severity,
        user=interaction.user,
        channel=interaction.channel,
        fields=fields
    )

    if ok:
        await interaction.followup.send(f"✅ ส่งการแจ้งเตือนความผิดปรกติเข้าห้อง <#{config.ANOMALY_LOG_CHANNEL_ID}> สำเร็จแล้ว!", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ ไม่สามารถส่งข้อความเข้าห้อง <#{config.ANOMALY_LOG_CHANNEL_ID}> ได้ (โปรดตรวจสอบสิทธิ์บอทในห้องดังกล่าว)", ephemeral=True)


@bot.tree.command(
    name="ongoing_board",
    description="แสดงหรือส่งกระดานงานที่กำลังดำเนินงานอยู่ (Live Ongoing Work Dashboard) ประจำแผนก"
)
@app_commands.describe(
    category="เลือกแผนกที่ต้องการดูงาน หรือเลือกทั้งหมด",
    send_to_channel="ส่งข้อความลงในห้อง 🔄・กำลังดำเนินการ ของแผนกนั้นโดยตรงหรือไม่ (ค่าเริ่มต้น: ดูเฉพาะคุณ)"
)
@app_commands.default_permissions(administrator=True)
async def cmd_ongoing_board(
    interaction: discord.Interaction,
    category: Literal["all", "game", "web", "script"] = "all",
    send_to_channel: bool = False
):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=not send_to_channel, thinking=True)

    from ongoing_manager import build_department_ongoing_board, resolve_ongoing_channel_id

    cats_to_run = ["game", "web", "script"] if category == "all" else [category]
    embeds = [build_department_ongoing_board(guild, c) for c in cats_to_run]

    if send_to_channel:
        sent_channels = []
        for c, emb in zip(cats_to_run, embeds):
            ch_id = resolve_ongoing_channel_id(c)
            if ch_id:
                ch = guild.get_channel(ch_id)
                if isinstance(ch, discord.TextChannel):
                    await ch.send(embed=emb)
                    sent_channels.append(ch.mention)
        await interaction.followup.send(
            f"✅ ส่งกระดานงานกำลังดำเนินการไปยัง {', '.join(sent_channels)} สำเร็จแล้ว!",
            ephemeral=True
        )
    else:
        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0], ephemeral=True)
        else:
            for emb in embeds:
                await interaction.followup.send(embed=emb, ephemeral=True)


# ─────────────────────────────────────────────────────────────
# 🚀 MAIN ENTRYPOINT
# ─────────────────────────────────────────────────────────────
def main():
    token = config.DISCORD_BOT_TOKEN
    if not token:
        print("[!] ERROR: DISCORD_BOT_TOKEN is not set in environment or config.py")
        print("[!] Please configure DISCORD_BOT_TOKEN in .env file.")
        return

    print("[*] Starting SC-HUB Dispatch & Client Service Bot...")
    try:
        bot.run(token)
    except discord.errors.PrivilegedIntentsRequired:
        print("=" * 66)
        print("[⚠️ NOTICE] Server Members Intent is disabled in Discord Developer Portal!")
        print("[⚠️ NOTICE] To enable full Member Join/Leave tracking (Channel 1563251902307901584):")
        print("  1. Open: https://discord.com/developers/applications/1562840210234933318/bot")
        print("  2. Scroll to 'Privileged Gateway Intents'")
        print("  3. Toggle ON: 'SERVER MEMBERS INTENT'")
        print("  4. Click 'Save Changes' at the bottom.")
        print("=" * 66)


if __name__ == "__main__":
    main()
