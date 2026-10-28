# -*- coding: utf-8 -*-
"""
💎 SC-HUB Department Lobby & Atomic Mutex Claim View
Handles customer admin calls and guarantees single-admin claiming concurrency.
Polished with premium customer-centric UI layout.
"""

from __future__ import annotations
import time
import re
import asyncio
from typing import Dict, Any, Optional
import discord
from discord import ui

from config import (
    DEPARTMENTS, COLOR_PRIMARY_GOLD, COLOR_SUCCESS, COLOR_DANGER,
    DEFAULT_OWNER_ROLE_ID, DEFAULT_MANAGER_ROLE_ID, DEFAULT_STAFF_ROLE_ID
)
from database import db
from user_service import userService

# Cooldown memory: {user_id: timestamp}
_LOBBY_CALL_COOLDOWNS: Dict[int, float] = {}


def build_department_lobby_embed(dept_key: str) -> discord.Embed:
    dept = DEPARTMENTS.get(dept_key, DEPARTMENTS["game"])
    embed = discord.Embed(
        title=f"💎 SC-HUB | แผนกบริการ: {dept['name']}",
        description=(
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✨ **ยินดีต้อนรับเข้าสู่พื้นที่ดูแล {dept['name']} ของ SC-HUB**\n"
            f"*{dept['desc']}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🟢 **สถานะทีมงาน:** พร้อมดูแลและให้บริการตลอด 24 ชั่วโมง\n"
            "⚡ **ความเร็วในการดูแล:** มีทีมงานสแตนด์บายตอบกลับทันที\n"
            "🔒 **ความปลอดภัย:** ระบบห้องบริการส่วนตัว (Private Ticket Room) เฉพาะคุณกับผู้รับงาน\n\n"
            "📌 **คำแนะนำสำหรับลูกค้า:**\n"
            "• กดปุ่ม **[ 🔔 เรียกแอดมิน ]** ด้านล่าง เพื่อส่งสัญญาณเรียกทีมงานเข้ามารับเรื่อง\n"
            "• เมื่อทีมงานกดรับงาน ระบบจะสร้างห้องตั๋วสนทนาส่วนตัวให้คุณอัตโนมัติทันที!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=0xF1C40F  # Premium Gold
    )
    embed.set_footer(text=f"💎 SC-HUB CLIENT DISPATCH • แผนก {dept['name']}")
    return embed


class ClaimedAdminNotificationView(ui.View):
    """View shown on the claimed card in the Admin Work Channel with jump button and dismiss button."""
    def __init__(self, jump_url: str):
        super().__init__(timeout=None)
        self.add_item(ui.Button(
            label="🎫 ไปยังห้องตั๋วส่วนตัว",
            url=jump_url,
            style=discord.ButtonStyle.link,
            emoji="🎫"
        ))

    @ui.button(
        label="ลบการ์ดนี้ (ปิดข้อความ)",
        style=discord.ButtonStyle.secondary,
        emoji="🗑️",
        custom_id="dispatch:admin:dismiss_claim_card"
    )
    async def btn_dismiss(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.message.delete()
        except discord.Forbidden:
            await interaction.response.send_message("❌ บอทไม่มีสิทธิ์ลบข้อความนี้", ephemeral=True)
        except Exception:
            pass


class AdminClaimView(ui.View):
    """View attached to staff notification card containing the atomic 'รับลูกค้า' button."""
    def __init__(self, call_id: str):
        super().__init__(timeout=None)
        self.call_id = call_id
        self.btn_claim.custom_id = f"dispatch:claim:{call_id}"

    @ui.button(
        label="รับลูกค้า (Claim)",
        style=discord.ButtonStyle.success,
        emoji="⚡"
    )
    async def btn_claim(self, interaction: discord.Interaction, button: ui.Button):
        admin = interaction.user
        guild = interaction.guild
        if not guild or not isinstance(admin, discord.Member):
            await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
            return

        # 1. ATOMIC MUTEX CLAIM (Race Condition Guard)
        success, call_data = await db.claim_pending_call_atomic(self.call_id, admin.id)

        if not success:
            button.disabled = True
            button.label = "มีแอดมินรับงานแล้ว"
            button.style = discord.ButtonStyle.secondary
            try:
                await interaction.message.edit(view=self)
            except Exception:
                pass
            await interaction.response.send_message(
                "⚠️ **ช้าไปนิดเดียว!** งานนี้ถูกรับไปแล้วโดยแอดมินท่านอื่นเรียบร้อยแล้ว",
                ephemeral=True
            )
            return

        # Admin won the mutex race!
        await interaction.response.defer(ephemeral=True, thinking=True)

        customer_id = call_data["customer_id"]
        category_key = call_data["category_key"]
        dept = DEPARTMENTS.get(category_key, DEPARTMENTS["game"])

        customer = guild.get_member(customer_id)
        if not customer:
            try:
                customer = await guild.fetch_member(customer_id)
            except Exception:
                customer = None

        if not customer:
            await interaction.followup.send("❌ ไม่พบข้อมูลลูกค้าในเซิร์ฟเวอร์ (ลูกค้าอาจออกจากเซิร์ฟเวอร์ไปแล้ว)", ephemeral=True)
            return

        # 2. STEP 4: Private Ticket Room Creation
        cfg = db.get_guild_config(guild.id)
        ticket_num = db.get_next_counter(guild.id)
        
        target_category = None
        if cfg.get("category_id"):
            target_category = guild.get_channel(cfg["category_id"])
        if not isinstance(target_category, discord.CategoryChannel):
            target_category = interaction.channel.category

        owner_role = guild.get_role(cfg.get("owner_role_id", DEFAULT_OWNER_ROLE_ID))

        clean_user = re.sub(r'[^a-zA-Z0-9_\-\u0E00-\u0E7F]', '', customer.name)[:10] or f"{ticket_num:03d}"
        channel_name = f"{dept['channel_prefix']}-{clean_user}-{ticket_num:03d}"

        # Overwrites: Only Customer + Claimed Admin + Owner bypass
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            customer: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True
            ),
            admin: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True
            )
        }

        if owner_role:
            overwrites[owner_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=target_category,
                overwrites=overwrites,
                topic=f"SC-HUB Ticket #{ticket_num:04d} | ลูกค้า: {customer.name} ({customer.id}) | ผู้รับงาน: {admin.name} ({admin.id}) | แผนก: {dept['name']}",
                reason=f"SC-HUB Dispatch Ticket #{ticket_num:04d} claimed by {admin.name}"
            )

            # Register in active_tickets DB
            db.register_ticket(
                channel_id=ticket_channel.id,
                ticket_num=ticket_num,
                guild_id=guild.id,
                category_key=category_key,
                customer_id=customer.id,
                claimed_admin_id=admin.id
            )

            # Post Live Ongoing Work Card to Department's Ongoing Channel
            try:
                from ongoing_manager import post_ongoing_card
                tdata_init = {
                    "channel_id": ticket_channel.id,
                    "ticket_num": ticket_num,
                    "guild_id": guild.id,
                    "category_key": category_key,
                    "customer_id": customer.id,
                    "claimed_admin_id": admin.id,
                    "process_stage": "queued",
                    "paid_status": 0,
                    "amount": 0.0,
                    "slip_ref": "",
                    "created_at": time.time()
                }
                asyncio.create_task(post_ongoing_card(guild, tdata_init, ticket_channel))
            except Exception as e:
                print(f"[-] Failed to dispatch ongoing card: {e}")

            # Update Lobby Notification Card in Admin Work Channel
            button.disabled = True
            button.label = f"รับงานแล้วโดย {admin.display_name}"
            button.style = discord.ButtonStyle.secondary
            
            claimed_embed = discord.Embed(
                title=f"✅ แอดมินรับงานเรียบร้อยแล้ว! • {dept['name']}",
                description=(
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 **ลูกค้า:** {customer.mention} (`{customer.name}`)\n"
                    f"🛡️ **ผู้รับผิดชอบงาน:** {admin.mention}\n"
                    f"📍 **ห้องตั๋วส่วนตัว:** {ticket_channel.mention}\n"
                    f"⏰ **เวลารับงาน:** <t:{int(time.time())}:T>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=0x2ECC71
            )
            claimed_embed.set_footer(text="💎 SC-HUB DISPATCH ENGINE")
            
            claimed_view = ClaimedAdminNotificationView(jump_url=ticket_channel.jump_url)
            try:
                await interaction.message.edit(embed=claimed_embed, view=claimed_view)
            except Exception:
                pass

            # Import Ticket Views
            from views.ticket_view import TicketControlView

            # Send Initial Welcome & Ticket Control Panel inside the private room
            welcome_embed = discord.Embed(
                title=f"👑 SC-HUB PRIVATE ROOM #{ticket_num:04d} • {dept['name']}",
                description=(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✨ สวัสดีครับ {customer.mention} ยินดีต้อนรับสู่ห้องบริการส่วนตัว\n"
                    f"🛡️ ผู้รับผิดชอบดูแลงานของคุณคือ: {admin.mention}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "📌 **ขั้นตอนการรับบริการ:**\n"
                    "1️⃣ พิมพ์พูดคุย แจ้งรายละเอียดสินค้าหรืองานที่ต้องการ\n"
                    "2️⃣ เมื่อตกลงราคากันเรียบร้อยแล้ว กดปุ่ม **[ 💳 กดเพื่อชำระเงิน ]** ด้านล่าง\n"
                    "3️⃣ ระบบจะตรวจสลิปผ่าน API อัตโนมัติ พร้อมเปิดกระดานอัปเดตสถานะงานสด\n"
                    "4️⃣ เมื่องานเสร็จสิ้น กด **[ 🎉 ได้รับสินค้าเรียบร้อยแล้ว ]** เพื่อปิดงาน\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "🔒 *ห้องนี้มีความปลอดภัยสูง มีเพียงคุณ ผู้รับงาน และเจ้าของร้านเท่านั้นที่เข้าถึงได้*"
                ),
                color=0xF1C40F
            )
            welcome_embed.set_footer(text="💎 SC-HUB CLIENT SERVICE • ดูแลด้วยใจ มาตรฐานระดับพรีเมียม")

            await ticket_channel.send(
                content=f"{customer.mention} {admin.mention}",
                embed=welcome_embed,
                view=TicketControlView(
                    ticket_channel_id=ticket_channel.id,
                    customer_id=customer.id,
                    admin_id=admin.id
                )
            )

            # Direct Message notification to customer
            try:
                dm_embed = discord.Embed(
                    title=f"⚡ แอดมินรับงานของคุณแล้ว! • {dept['name']}",
                    description=(
                        f"สวัสดีครับ {customer.mention} 👋\n\n"
                        f"แอดมิน **{admin.display_name}** ได้กดรับงานของคุณในแผนก **{dept['name']}** เรียบร้อยแล้วครับ\n"
                        "ห้องตั๋วส่วนตัวถูกสร้างขึ้นแล้ว สามารถคลิกปุ่มด้านล่างเพื่อเข้าไปคุยกับแอดมินได้ทันที:"
                    ),
                    color=0x2ECC71
                )
                dm_embed.add_field(name="📍 ห้องตั๋วของคุณ", value=f"{ticket_channel.mention}", inline=False)
                dm_embed.set_footer(text="💎 SC-HUB CLIENT NOTIFICATION")

                dm_view = ui.View()
                dm_view.add_item(ui.Button(label="🎫 ไปยังห้องตั๋วส่วนตัว", url=ticket_channel.jump_url, style=discord.ButtonStyle.link))
                await customer.send(embed=dm_embed, view=dm_view)
            except Exception:
                # Customer might have DMs closed, post temporary auto-deleting notice in lobby
                try:
                    await interaction.channel.send(
                        content=f"{customer.mention} ⚡ แอดมิน **{admin.display_name}** รับงานแล้ว! (เนื่องจาก DM ปิดอยู่ โปรดเข้าห้อง: {ticket_channel.mention})",
                        delete_after=25.0
                    )
                except Exception:
                    pass

            # Sync Ticket Claim with External Website Backend (userService)
            try:
                ticket_payload = {
                    "ticket_num": ticket_num,
                    "channel_id": ticket_channel.id,
                    "category_key": self.dept_key,
                    "created_at": time.time(),
                    "customer_id": customer.id
                }
                asyncio.create_task(userService.report_ticket_claim(
                    guild_id=guild.id,
                    ticket_data=ticket_payload,
                    admin_id=admin.id,
                    admin_name=admin.display_name
                ))
            except Exception:
                pass

            await interaction.followup.send(
                f"✅ **คุณได้รับงานสำเร็จ!** ห้องตั๋วส่วนตัวถูกสร้างแล้ว: {ticket_channel.mention}",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ บอทไม่มีสิทธิ์สร้างห้อง Text Channel (โปรดตรวจสอบสิทธิ์ Manage Channels ของบอท)",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการเปิดตั๋ว: {e}", ephemeral=True)


class DepartmentLobbyView(ui.View):
    """Persistent View displayed in each department's main channel with 'เรียกแอดมิน' button."""
    def __init__(self, dept_key: str = "game"):
        super().__init__(timeout=None)
        self.dept_key = dept_key
        self.btn_call_admin.custom_id = f"dispatch:lobby:call_{dept_key}"

    @ui.button(
        label="เรียกแอดมิน",
        style=discord.ButtonStyle.primary,
        emoji="🔔"
    )
    async def btn_call_admin(self, interaction: discord.Interaction, button: ui.Button):
        user = interaction.user
        guild = interaction.guild
        if not guild or not isinstance(user, discord.Member):
            await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
            return

        dept = DEPARTMENTS.get(self.dept_key, DEPARTMENTS["game"])

        # Check existing open ticket
        existing_ticket = db.find_user_open_ticket(guild.id, user.id)
        if existing_ticket:
            ch = guild.get_channel(existing_ticket["channel_id"])
            ch_mention = ch.mention if ch else f"ID: {existing_ticket['channel_id']}"
            await interaction.response.send_message(
                f"⚠️ **คุณมีตั๋วที่เปิดค้างไว้อยู่แล้ว!**\nกรุณาใช้ห้องเดิมของคุณที่ {ch_mention}",
                ephemeral=True
            )
            return

        # 60s Cooldown Guard
        now = time.time()
        last_call = _LOBBY_CALL_COOLDOWNS.get(user.id, 0)
        if now - last_call < 60:
            rem = int(60 - (now - last_call))
            await interaction.response.send_message(
                f"⏱️ คุณเพิ่งกดเรียกไป โปรดรออีก `{rem}` วินาทีก่อนกดเรียกซ้ำ",
                ephemeral=True
            )
            return

        _LOBBY_CALL_COOLDOWNS[user.id] = now

        # Staff role lookup for ping (Priority: Specific Dept Staff > General Staff)
        cfg = db.get_guild_config(guild.id)
        dept_roles = cfg.get("dept_roles", {})
        specific_staff_id = dept_roles.get(f"{self.dept_key}_staff_role_id") or dept.get("staff_role_id")
        staff_role_id = specific_staff_id or cfg.get("staff_role_id", DEFAULT_STAFF_ROLE_ID)
        staff_role = guild.get_role(staff_role_id) if staff_role_id else None

        if not staff_role:
            for r in guild.roles:
                if any(w in r.name.lower() for w in (dept["staff_role_name"].lower(), "staff", "admin", "แอดมิน", "ทีมงาน", "พาร์ทเนอร์")):
                    staff_role = r
                    break

        staff_mention = staff_role.mention if staff_role else "@here"

        # Resolve target Admin Work Channel (ห้องรับงานของแอดมิน)
        admin_ch_id = cfg.get(f"{self.dept_key}_admin_channel_id") or dept.get("admin_channel_id")
        admin_ch = guild.get_channel(admin_ch_id) if admin_ch_id else interaction.channel
        if not isinstance(admin_ch, discord.TextChannel):
            admin_ch = interaction.channel

        # Acknowledge user via EPHEMERAL message (Customer only sees this, channel stays clean!)
        ack_embed = discord.Embed(
            title="🔔 ส่งสัญญาณเรียกทีมงานเรียบร้อยแล้ว!",
            description=(
                f"สัญญาณแจ้งเตือนได้ถูกส่งตรงไปยังห้องรับงานของทีมงาน **{dept['name']}** แล้วครับ\n\n"
                "⚡ **เมื่อมีแอดมินกดรับงาน:**\n"
                "• ระบบจะส่งแจ้งเตือนพร้อมปุ่มทางเข้าห้องตั๋ว **ไปยังแชทส่วนตัว (DM) ของคุณทันที**\n"
                "• ห้องตั๋วส่วนตัวจะถูกสร้างขึ้นเพื่อคุยงานแบบ 1:1\n\n"
                "*(ข้อความนี้จะแสดงเฉพาะคุณเท่านั้น สามารถกดปิดข้อความได้)*"
            ),
            color=0x2ECC71
        )
        await interaction.response.send_message(embed=ack_embed, ephemeral=True)

        # Notification Card posted exclusively in the ADMIN WORK CHANNEL
        call_embed = discord.Embed(
            title=f"🔔 มีลูกค้าใหม่รอรับบริการ! • {dept['name']}",
            description=(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **ลูกค้า:** {user.mention} (`{user.name}`)\n"
                f"📌 **แผนกงาน:** `{dept['name']}`\n"
                f"📍 **เรียกจากห้อง:** {interaction.channel.mention}\n"
                f"⏰ **เวลาเรียก:** <t:{int(now)}:R>\n\n"
                "⚡ **สำหรับทีมงาน:** กดปุ่ม **[ รับลูกค้า (Claim) ]** ด้านล่างเพื่อรับเคส\n"
                "*(ระบบ Atomic Lock จะมอบสิทธิ์ให้แก่แอดมินคนแรกที่กดเท่านั้น)*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=COLOR_PRIMARY_GOLD
        )
        call_embed.set_footer(text="💎 SC-HUB DISPATCH ENGINE")

        call_id = db.create_pending_call(
            guild_id=guild.id,
            category_key=self.dept_key,
            customer_id=user.id,
            channel_id=admin_ch.id,
            message_id=0
        )

        claim_view = AdminClaimView(call_id=call_id)
        msg = await admin_ch.send(
            content=f"🔔 {staff_mention} — มีลูกค้าเรียกทีมงาน!",
            embed=call_embed,
            view=claim_view,
            allowed_mentions=discord.AllowedMentions(roles=True, users=True, everyone=True)
        )

        with db._get_connection() as conn:
            conn.execute("UPDATE pending_calls SET message_id = ? WHERE call_id = ?", (msg.id, call_id))
            conn.commit()
