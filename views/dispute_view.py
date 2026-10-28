# -*- coding: utf-8 -*-
"""
💎 SC-HUB Executive Dispute & Issue Escalation Desk
Handles executive tickets routed directly to Owner, Head Staff, and Manager.
Completely isolated from regular department staff.
"""

from __future__ import annotations
import re
import time
import asyncio
from typing import Optional, Dict, Any
import discord
from discord import ui

import config
from database import db
from transcript import generate_ticket_transcript
from security_logger import log_security_anomaly


def build_dispute_panel_embed() -> discord.Embed:
    """Creates a high-end luxury embed for the executive dispute desk."""
    embed = discord.Embed(
        title="🚨 ศูนย์รับเรื่องร้องเรียนและแจ้งปัญหา • SC-HUB Executive Desk",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "ยินดีต้อนรับสู่ **ศูนย์รับเรื่องร้องเรียนระดับบริหาร**\n"
            "หากท่านพบปัญหาในการใช้บริการ หรือต้องการส่งเรื่องตรงถึงผู้บริหาร\n"
            "สามารถกดปุ่มด้านล่างเพื่อเปิด **ตั๋วความลับระดับสูง (Confidential Ticket)** ได้ทันที\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚖️ **ขอบเขตการรับเรื่อง:**\n"
            "• **ข้อพิพาท / รายงานการปฏิบัติงานของแอดมิน** (Staff Conduct Report)\n"
            "• **ปัญหาด้านการเงิน, การเติมเงิน, สลิปมีปัญหา หรือถูกฉ้อโกง** (Payment Dispute)\n"
            "• **พบบั๊กหรือช่องโหว่ร้ายแรงในระบบ** (Critical Security Bug)\n"
            "• **ข้อเสนอแนะเชิงธุรกิจ หรือเรื่องลับเฉพาะบุคคล** (Private Inquiry)\n\n"
            "🛡️ **การรับประกันความลับสูงสุด (Confidentiality Guaranteed):**\n"
            "• ตั๋วที่เปิดจากห้องนี้จะถูกส่งตรงไปยัง **👑 เจ้าของร้าน**, **⚜️ หัวหน้าทีมงาน** และ **🛡️ ผู้จัดการร้าน** เท่านั้น\n"
            "• **แอดมินและพนักงานทั่วไปจะไม่สามารถมองเห็นห้องนี้ได้ 100%**\n"
            "• ข้อมูลทุกอย่างได้รับการเข้ารหัสและบันทึกประวัติอย่างเป็นธรรม\n\n"
            "👇 *กดปุ่มสีแดงด้านล่าง เพื่อกรอกรายละเอียดและเปิดตั๋วติดต่อผู้บริหาร*"
        ),
        color=config.COLOR_DANGER
    )
    embed.set_thumbnail(url="https://payomboyzcreative.online/assets/images/logo.png")
    embed.set_footer(
        text="💎 SC-HUB EXECUTIVE DESK • ระบบส่งเรื่องตรงถึง Owner & หัวหน้าทีมงาน",
        icon_url="https://payomboyzcreative.online/assets/images/logo.png"
    )
    return embed


class DisputeReportModal(ui.Modal, title="🚨 แจ้งปัญหาตรงถึงผู้บริหาร"):
    topic_input = ui.TextInput(
        label="หัวข้อเรื่องที่ต้องการแจ้ง",
        placeholder="เช่น ข้อพิพาทกับแอดมิน, ปัญหาเติมเงิน, ตรวจสอบงานล่าช้า",
        required=True,
        max_length=100
    )
    detail_input = ui.TextInput(
        label="รายละเอียดปัญหาอย่างครบถ้วน",
        placeholder="ระบุข้อเท็จจริง วันเวลา หรือพฤติการณ์ที่เกิดขึ้นอย่างละเอียด...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )
    involved_input = ui.TextInput(
        label="แอดมิน/คู่กรณี หรือเลขออเดอร์ (ถ้ามี)",
        placeholder="ตัวอย่าง: แอดมิน A, หรือ Order #042 (ถ้าไม่มีให้ใส่ -)",
        required=False,
        max_length=100
    )
    evidence_input = ui.TextInput(
        label="ลิงก์หลักฐาน/รูปภาพประกอบ (ถ้ามี)",
        placeholder="ใส่ลิงก์รูปภาพ เช่น https://imgur.com/... หรือระบุว่าจะแนบในห้อง",
        required=False,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        if not guild or not isinstance(user, discord.Member):
            await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # 1. Check if user already has an active dispute ticket open
        with db._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT channel_id FROM active_tickets 
                WHERE guild_id = ? AND customer_id = ? AND category_key = 'dispute'
            """, (str(guild.id), user.id))
            row = c.fetchone()
            if row:
                existing_ch = guild.get_channel(row["channel_id"])
                if existing_ch:
                    await interaction.followup.send(
                        f"⚠️ **ท่านมีห้องแจ้งปัญหาที่กำลังเปิดอยู่แล้ว:** {existing_ch.mention}\n"
                        f"กรุณาใช้ห้องเดิม หรือปิดห้องเดิมก่อนแจ้งเรื่องใหม่ครับ",
                        ephemeral=True
                    )
                    return

        # 2. Get Guild Config & Target Category
        cfg = db.get_guild_config(guild.id)
        ticket_num = db.get_next_counter(guild.id)

        target_category = None
        # Priority 1: DISPUTE_CATEGORY_ID (1563251765200293959)
        if config.DISPUTE_CATEGORY_ID:
            target_category = guild.get_channel(config.DISPUTE_CATEGORY_ID)
        # Priority 2: Interaction channel's category
        if not isinstance(target_category, discord.CategoryChannel) and interaction.channel:
            target_category = interaction.channel.category
        # Priority 3: Default category
        if not isinstance(target_category, discord.CategoryChannel) and cfg.get("category_id"):
            target_category = guild.get_channel(cfg["category_id"])

        # 3. Roles to grant access
        owner_role_id = cfg.get("owner_role_id") or config.DEFAULT_OWNER_ROLE_ID
        head_staff_role_id = config.DEFAULT_HEAD_STAFF_ROLE_ID
        manager_role_id = cfg.get("manager_role_id") or config.DEFAULT_MANAGER_ROLE_ID

        owner_role = guild.get_role(owner_role_id)
        head_staff_role = guild.get_role(head_staff_role_id)
        manager_role = guild.get_role(manager_role_id)

        # 4. Strictly Isolated Permission Overwrites
        # @everyone: FALSE
        # Customer: TRUE
        # Owner Role: TRUE
        # Head Staff Role: TRUE
        # Manager Role: TRUE
        # Bot (guild.me): TRUE
        # All other roles: Inherit FALSE (Blocked)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True
            )
        }

        if owner_role:
            overwrites[owner_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True
            )
        if head_staff_role:
            overwrites[head_staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True
            )
        if manager_role:
            overwrites[manager_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True
            )

        # Format channel name
        clean_user = re.sub(r'[^a-zA-Z0-9_\-\u0E00-\u0E7F]', '', user.name)[:10] or f"{ticket_num:03d}"
        channel_name = f"🚨・ปัญหา-{clean_user}-{ticket_num:03d}"

        try:
            if isinstance(target_category, discord.CategoryChannel):
                dispute_channel = await target_category.create_text_channel(
                    name=channel_name,
                    overwrites=overwrites,
                    topic=f"🚨 ตั๋วแจ้งปัญหาส่งตรงถึงผู้บริหาร | ผู้แจ้ง: {user.name} ({user.id}) | เรื่อง: {self.topic_input.value.strip()[:50]}"
                )
            else:
                dispute_channel = await guild.create_text_channel(
                    name=channel_name,
                    overwrites=overwrites,
                    topic=f"🚨 ตั๋วแจ้งปัญหาส่งตรงถึงผู้บริหาร | ผู้แจ้ง: {user.name} ({user.id}) | เรื่อง: {self.topic_input.value.strip()[:50]}"
                )
        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการสร้างห้อง: `{e}`", ephemeral=True)
            return

        # 5. Register in Database
        head_id = head_staff_role_id if head_staff_role else owner_role_id
        db.register_ticket(
            channel_id=dispute_channel.id,
            ticket_num=ticket_num,
            guild_id=guild.id,
            category_key="dispute",
            customer_id=user.id,
            claimed_admin_id=head_id
        )

        # 6. Post Detail Card in the newly created Dispute Room
        pings = []
        if owner_role:
            pings.append(owner_role.mention)
        if head_staff_role:
            pings.append(head_staff_role.mention)
        pings.append(user.mention)
        pings_str = " ".join(pings)

        topic = self.topic_input.value.strip()
        details = self.detail_input.value.strip()
        involved = self.involved_input.value.strip() or "ไม่ระบุ / ไม่มีคู่กรณี"
        evidence = self.evidence_input.value.strip() or "ไม่มี (สามารถแนบรูปภาพหรือไฟล์ในห้องนี้ได้ทันที)"

        dispute_embed = discord.Embed(
            title=f"🚨 คำร้องเรียน/แจ้งปัญหาเร่งด่วน • ตั๋ว #{ticket_num:03d}",
            description=(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **ผู้แจ้งเรื่อง:** {user.mention} (`{user.id}`)\n"
                f"📋 **หัวข้อเรื่อง:** `{topic}`\n"
                f"🎯 **คู่กรณี / อ้างอิงคำสั่งซื้อ:** `{involved}`\n"
                f"⏰ **เวลาแจ้งเรื่อง:** <t:{int(time.time())}:F>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📝 **รายละเอียดปัญหา:**\n>>> {details}\n\n"
                f"🔗 **หลักฐานประกอบ:**\n{evidence}\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🛡️ **การคุ้มครองความปลอดภัยและความเป็นส่วนตัว:**\n"
                "• ตั๋วนี้มองเห็นได้เฉพาะ **เจ้าของร้าน, หัวหน้าทีมงาน, ผู้จัดการร้าน** และผู้แจ้งเท่านั้น\n"
                "• ทีมงานทั่วไปและบุคคลภายนอกไม่สามารถมองเห็นข้อความในห้องนี้ได้ 100%\n"
                "• หัวหน้าทีมงานหรือเจ้าของร้านจะเข้ามาตรวจสอบและพูดคุยในไม่ช้า"
            ),
            color=config.COLOR_DANGER
        )
        dispute_embed.set_footer(
            text="💎 SC-HUB EXECUTIVE DESK • ระบบพิทักษ์สิทธิ์และข้อพิพาทระดับสูง"
        )

        await dispute_channel.send(
            content=f"🔔 {pings_str}\n*มีคำร้องเรียนใหม่ส่งตรงถึงฝ่ายบริหาร กรุณาตรวจสอบรายละเอียดด้านล่าง:*",
            embed=dispute_embed,
            view=DisputeTicketControlView()
        )

        # 7. Dispatch Security Sentinel Log (Anomaly Channel: 1563251866517770250)
        asyncio.create_task(log_security_anomaly(
            guild=guild,
            title="🚨 มีการเปิดตั๋วแจ้งปัญหาส่งตรงถึงผู้บริหารและหัวหน้าทีมงาน",
            description=f"สมาชิก {user.mention} ได้ทำการเปิดตั๋วร้องเรียนเร่งด่วนในห้อง {dispute_channel.mention}",
            incident_type="EXECUTIVE_DISPUTE",
            severity="HIGH",
            user=user,
            channel=dispute_channel,
            fields=[
                ("📋 หัวข้อปัญหา", f"`{topic}`", True),
                ("🎯 คู่กรณี / รหัสคำสั่งซื้อ", f"`{involved}`", True),
                ("🎫 ห้องตั๋วข้อพิพาท", f"{dispute_channel.mention} (`{dispute_channel.id}`)", False),
                ("🛡️ ผู้มีสิทธิ์ดูแล", f"<@&{owner_role_id}> & <@&{head_staff_role_id}>", False)
            ]
        ))

        # 8. Respond ephemerally to the reporting user with a jump button
        jump_view = ui.View()
        jump_view.add_item(ui.Button(
            label="🎫 ไปยังห้องแจ้งปัญหาของคุณ",
            style=discord.ButtonStyle.link,
            url=dispute_channel.jump_url,
            emoji="🔗"
        ))

        success_embed = discord.Embed(
            title="✅ ส่งเรื่องตรงถึงผู้บริหารเรียบร้อยแล้ว",
            description=(
                f"ห้องตั๋วสำหรับแจ้งปัญหาของคุณถูกสร้างขึ้นแล้วที่: {dispute_channel.mention}\n\n"
                "👑 เจ้าของร้านและ ⚜️ หัวหน้าทีมงาน ได้รับการแจ้งเตือนแล้ว\n"
                "ท่านสามารถกดปุ่มลิงก์ด้านล่างเพื่อเข้าไปพิมพ์พูดคุยหรือแนบหลักฐานเพิ่มเติมได้ทันที"
            ),
            color=config.COLOR_SUCCESS
        )
        await interaction.followup.send(embed=success_embed, view=jump_view, ephemeral=True)


class DisputePanelView(ui.View):
    """Persistent view placed in the dispute panel channel."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="แจ้งปัญหา / ส่งเรื่องตรงถึงผู้บริหาร",
        style=discord.ButtonStyle.danger,
        emoji="🚨",
        custom_id="dispatch:dispute:open_btn"
    )
    async def btn_open_dispute(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(DisputeReportModal())


class DisputeTicketControlView(ui.View):
    """Persistent controls placed inside each dispute ticket room."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="ปิดตั๋วปัญหานี้ (Close Dispute)",
        style=discord.ButtonStyle.secondary,
        emoji="🔒",
        custom_id="dispatch:dispute:close_btn"
    )
    async def btn_close_dispute(self, interaction: discord.Interaction, button: ui.Button):
        user = interaction.user
        guild = interaction.guild
        channel = interaction.channel

        if not guild or not isinstance(channel, discord.TextChannel) or not isinstance(user, discord.Member):
            await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในห้องตั๋ว", ephemeral=True)
            return

        # Check permissions: Reporter, Owner, Head Staff, or Manager
        cfg = db.get_guild_config(guild.id)
        owner_role_id = cfg.get("owner_role_id") or config.DEFAULT_OWNER_ROLE_ID
        head_staff_role_id = config.DEFAULT_HEAD_STAFF_ROLE_ID
        manager_role_id = cfg.get("manager_role_id") or config.DEFAULT_MANAGER_ROLE_ID

        tdata = db.get_ticket(channel.id)
        reporter_id = tdata.get("customer_id") if tdata else 0

        is_authorized = (
            user.id == reporter_id or
            user.guild_permissions.administrator or
            any(r.id in (owner_role_id, head_staff_role_id, manager_role_id) for r in user.roles)
        )

        if not is_authorized:
            await interaction.response.send_message(
                "❌ คุณไม่มีสิทธิ์ปิดตั๋วนี้ (เฉพาะผู้แจ้งเรื่อง, เจ้าของร้าน หรือหัวหน้าทีมงานเท่านั้น)",
                ephemeral=True
            )
            return

        # Execute close and log
        await interaction.response.defer(thinking=True)

        closing_embed = discord.Embed(
            title=f"🔒 กำลังปิดและบันทึกข้อมูลตั๋ว #{channel.name}...",
            description=(
                f"• **ผู้สั่งปิด:** {user.mention}\n"
                f"• **ระบบ Audit Transcript:** กำลังส่งสำเนาประวัติการสนทนาไปยังห้องเก็บบันทึก\n"
                f"• ห้องนี้จะถูกลบอัตโนมัติในอีก **5 วินาที**"
            ),
            color=config.COLOR_PRIMARY_GOLD
        )
        await interaction.followup.send(embed=closing_embed)

        # 1. Generate Transcript
        transcript_file, msg_count = await generate_ticket_transcript(channel)

        # 2. Send transcript to Anomaly/Audit log channel
        audit_ch = guild.get_channel(config.ANOMALY_LOG_CHANNEL_ID)
        if isinstance(audit_ch, discord.TextChannel):
            log_embed = discord.Embed(
                title=f"📑 บันทึกประวัติตั๋วแจ้งปัญหา: #{channel.name}",
                description=(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 **ผู้แจ้งเรื่อง:** <@{reporter_id}>\n"
                    f"🔒 **ผู้สั่งปิด:** {user.mention}\n"
                    f"💬 **จำนวนข้อความ:** `{msg_count:,}` ข้อความ\n"
                    f"⏰ **เวลาปิด:** <t:{int(time.time())}:F>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=config.COLOR_DANGER
            )
            log_embed.set_footer(text="💎 SC-HUB EXECUTIVE AUDIT ARCHIVE")
            try:
                transcript_file.fp.seek(0)
                await audit_ch.send(embed=log_embed, file=transcript_file)
            except Exception as e:
                print(f"[-] Failed to send dispute transcript: {e}")

        # 3. Clean up database
        db.close_ticket(channel.id)

        # 4. Delete channel after 5 seconds
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Dispute resolved and closed by {user.name}")
        except Exception:
            pass

    @ui.button(
        label="ดาวน์โหลด Transcript",
        style=discord.ButtonStyle.primary,
        emoji="📑",
        custom_id="dispatch:dispute:transcript_btn"
    )
    async def btn_transcript(self, interaction: discord.Interaction, button: ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในห้องตั๋ว", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        transcript_file, msg_count = await generate_ticket_transcript(channel)
        await interaction.followup.send(
            content=f"📑 **ประวัติการสนทนาในตั๋วนี้ ({msg_count} ข้อความ):**",
            file=transcript_file,
            ephemeral=True
        )
