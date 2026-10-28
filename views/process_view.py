# -*- coding: utf-8 -*-
"""
💎 SC-HUB Dual-Track Process & Order Progression View
Provides Admin stage management (5 stages) and Customer confirmation & escalation controls.
Crafted with high-visual graphical progress bars.
"""

from __future__ import annotations
import discord
from discord import ui
from typing import Optional, Dict, Any

from config import (
    COLOR_PRIMARY_GOLD, COLOR_SUCCESS, COLOR_INFO, COLOR_DANGER,
    DEFAULT_OWNER_ROLE_ID, DEFAULT_MANAGER_ROLE_ID
)
from database import db


STAGES: Dict[str, Dict[str, Any]] = {
    "queued": {
        "index": 1,
        "label": "รอคิวงาน",
        "emoji": "⏳",
        "desc": "งานได้รับเข้าระบบเรียบร้อยแล้ว กำลังจัดเตรียมคิวงาน",
        "progress_bar": "🟩⬜⬜⬜⬜ (20%)",
        "step_badge": "STEP 1/5"
    },
    "started": {
        "index": 2,
        "label": "เริ่มต้นดำเนินงาน",
        "emoji": "🚀",
        "desc": "ทีมงานเริ่มต้นเตรียมข้อมูลและเซ็ตอัปสิ่งแวดล้อมงาน",
        "progress_bar": "🟩🟩⬜⬜⬜ (40%)",
        "step_badge": "STEP 2/5"
    },
    "in_progress": {
        "index": 3,
        "label": "กำลังดำเนินการ",
        "emoji": "⚙️",
        "desc": "ทีมงานกำลังลงมือดำเนินงานอย่างเต็มกำลัง พร้อมตรวจสอบความสมบูรณ์",
        "progress_bar": "🟩🟩🟩⬜⬜ (60%)",
        "step_badge": "STEP 3/5"
    },
    "final_stage": {
        "index": 4,
        "label": "ขั้นตอนสุดท้าย / ตรวจงาน",
        "emoji": "🔍",
        "desc": "ตรวจสอบความเรียบร้อยรอบสุดท้าย และเตรียมส่งมอบให้ลูกค้า",
        "progress_bar": "🟩🟩🟩🟩⬜ (80%)",
        "step_badge": "STEP 4/5"
    },
    "completed": {
        "index": 5,
        "label": "เสร็จสิ้นสมบูรณ์",
        "emoji": "✅",
        "desc": "งานเสร็จสิ้น 100%! กรุณาลูกค้าตรวจสอบและกดยืนยันรับสินค้า",
        "progress_bar": "🟩🟩🟩🟩🟩 (100%)",
        "step_badge": "COMPLETED"
    }
}


def build_process_status_embed(
    stage_key: str = "queued",
    amount: float = 0.0,
    slip_ref: str = "N/A"
) -> discord.Embed:
    stage = STAGES.get(stage_key, STAGES["queued"])
    embed = discord.Embed(
        title=f"🚀 SC-HUB LIVE ORDER TRACKER • {stage['emoji']} {stage['label']}",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 **ระดับความคืบหน้า:** `{stage['progress_bar']}`\n"
            f"🏷️ **ลำดับขั้นตอน:** `{stage['step_badge']}`\n"
            f"📝 **คำอธิบาย:** *{stage['desc']}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 **ยอดเงินชำระ:** `{amount:,.2f}` บาท\n"
            f"🧾 **รหัสสลิปอ้างอิง:** `{slip_ref}`\n\n"
            "📌 **การทำงานของระบบ:**\n"
            "• **สำหรับแอดมิน:** ใช้เมนูด้านล่างเพื่อสลับสถานะงานตามขั้นตอนจริง\n"
            "• **สำหรับลูกค้า:** เมื่อได้รับสินค้าและบริการครบถ้วน ให้กดปุ่ม **[ 🎉 ได้รับสินค้าเรียบร้อยแล้ว ]**"
        ),
        color=0x2ECC71 if stage_key == "completed" else 0x00A8FF
    )
    embed.set_footer(text="💎 SC-HUB KANBAN PROGRESS TRACKER")
    return embed


# ─────────────────────────────────────────────────────────────
# 1. 🛡️ ฝั่งแอดมิน: สลับสถานะงาน 5 ขั้นตอน
# ─────────────────────────────────────────────────────────────
class ProcessStageSelect(ui.Select):
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        options = [
            discord.SelectOption(label="⏳ 1. รอคิวงาน (Queued)", value="queued", description="จัดเตรียมคิวงาน"),
            discord.SelectOption(label="🚀 2. เริ่มต้นดำเนินงาน (Started)", value="started", description="เริ่มเซ็ตอัปและเตรียมระบบ"),
            discord.SelectOption(label="⚙️ 3. กำลังดำเนินการ (In Progress)", value="in_progress", description="กำลังลงมือทำอย่างเต็มสูบ"),
            discord.SelectOption(label="🔍 4. ขั้นตอนสุดท้าย (Final Stage)", value="final_stage", description="ตรวจสอบความถูกต้องก่อนส่งมอบ"),
            discord.SelectOption(label="✅ 5. เสร็จสิ้นสมบูรณ์ (Completed)", value="completed", description="งานเสร็จสมบูรณ์พร้อมส่งมอบ"),
        ]
        super().__init__(
            placeholder="คลิกเพื่ออัปเดตสถานะความคืบหน้าของงาน...",
            min_values=1,
            max_values=1,
            custom_id=f"dispatch:process:select_{channel_id}",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        user = interaction.user
        tdata = db.get_ticket(channel.id)
        if not tdata:
            await interaction.response.send_message("❌ ไม่พบข้อมูลตั๋ว", ephemeral=True)
            return

        cfg = db.get_guild_config(interaction.guild_id)
        owner_id = cfg.get("owner_role_id", DEFAULT_OWNER_ROLE_ID)
        is_owner = any(r.id == owner_id for r in user.roles) if isinstance(user, discord.Member) else False

        if user.id != tdata.get("claimed_admin_id") and not is_owner and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ คุณไม่ใช่แอดมินผู้รับผิดชอบตั๋วนี้", ephemeral=True)
            return

        new_stage = self.values[0]
        db.update_ticket_stage(channel.id, new_stage)

        stage_info = STAGES.get(new_stage, STAGES["queued"])
        updated_embed = build_process_status_embed(
            stage_key=new_stage,
            amount=tdata.get("amount", 0.0),
            slip_ref=tdata.get("slip_ref", "N/A")
        )

        try:
            await interaction.message.edit(embed=updated_embed)
            await interaction.response.send_message(
                f"✅ อัปเดตสถานะงานเป็น **{stage_info['emoji']} {stage_info['label']}** เรียบร้อยแล้ว!",
                ephemeral=True
            )
            # Public announcement in ticket
            await channel.send(
                f"📢 **แจ้งเตือนความคืบหน้า (SC-HUB):** สถานะงานถูกเปลี่ยนเป็น **{stage_info['emoji']} {stage_info['label']}** `{stage_info['progress_bar']}`\n"
                f"*{stage_info['desc']}*"
            )

            # Sync live update to department's ongoing work channel
            try:
                from ongoing_manager import update_ongoing_card
                import asyncio
                asyncio.create_task(update_ongoing_card(interaction.guild, channel.id, stage_key=new_stage))
            except Exception:
                pass
        except Exception as e:
            await interaction.response.send_message(f"❌ ไม่สามารถแก้ไขสถานะได้: {e}", ephemeral=True)


class ProcessAdminControlView(ui.View):
    """View placed on the Admin process message."""
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.add_item(ProcessStageSelect(channel_id))


# ─────────────────────────────────────────────────────────────
# 2. 👤 ฝั่งลูกค้า: เรียก Owner (แจ้งปัญหา) + ยืนยันรับสินค้า
# ─────────────────────────────────────────────────────────────
class CustomerConfirmReceivedModal(ui.Modal, title="🎉 ยืนยันการรับสินค้าและบริการ"):
    confirm_text = ui.TextInput(
        label="พิมพ์คำว่า 'ยืนยัน' เพื่อยืนยันว่าได้รับสินค้าแล้ว",
        placeholder="ยืนยัน",
        required=True,
        max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm_text.value.strip() != "ยืนยัน":
            await interaction.response.send_message("⚠️ การยืนยันถูกยกเลิก (กรุณาพิมพ์คำว่า 'ยืนยัน' ให้ถูกต้อง)", ephemeral=True)
            return

        from views.ticket_view import execute_close_and_dual_log
        await execute_close_and_dual_log(interaction, reason="ลูกค้าได้รับสินค้าและบริการเรียบร้อย 100%")


class ProcessCustomerControlView(ui.View):
    """View placed for customer actions: Call Owner & Confirm Receipt."""
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.channel_id = channel_id

    @ui.button(
        label="เรียก Owner (แจ้งปัญหา)",
        style=discord.ButtonStyle.danger,
        emoji="🚨",
        custom_id="dispatch:process:call_owner"
    )
    async def btn_call_owner(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
            return

        cfg = db.get_guild_config(guild.id)
        owner_role_id = cfg.get("owner_role_id", DEFAULT_OWNER_ROLE_ID)
        manager_role_id = cfg.get("manager_role_id", DEFAULT_MANAGER_ROLE_ID)
        owner_role = guild.get_role(owner_role_id)
        manager_role = guild.get_role(manager_role_id)

        mentions = []
        if owner_role:
            mentions.append(owner_role.mention)
        if manager_role and manager_role != owner_role:
            mentions.append(manager_role.mention)
        if not mentions:
            mentions.append(guild.owner.mention if guild.owner else "@Owner")
        escalation_mentions = " ".join(mentions)

        await interaction.response.send_message("🚨 ส่งสัญญาณแจ้งเหตุฉุกเฉินไปยัง Owner และผู้จัดการร้านเรียบร้อยแล้ว!", ephemeral=True)

        alert_embed = discord.Embed(
            title="🚨 มีการแจ้งปัญหาในห้องตั๋ว (Owner & Manager Escalation Alert)",
            description=(
                f"👤 **ผู้แจ้ง:** {interaction.user.mention}\n"
                f"📍 **ห้องตั๋ว:** {interaction.channel.mention}\n"
                f"⏰ **เวลา:** <t:{int(interaction.created_at.timestamp())}:F>\n\n"
                "โปรดเข้ามาตรวจสอบข้อพิพาทหรือปัญหาในตั๋วนี้โดยด่วน"
            ),
            color=COLOR_DANGER
        )
        await interaction.channel.send(
            content=f"🚨 {escalation_mentions} — มีการแจ้งปัญหาจาก {interaction.user.mention}!",
            embed=alert_embed,
            allowed_mentions=discord.AllowedMentions(roles=True, users=True)
        )

        # Log emergency escalation anomaly to ANOMALY_LOG_CHANNEL_ID
        try:
            from security_logger import log_security_anomaly
            import asyncio
            asyncio.create_task(log_security_anomaly(
                guild=guild,
                title="ลูกค้ากดเรียก Owner ระงับข้อพิพาทในตั๋ว",
                description=f"ลูกค้าส่งสัญญาณฉุกเฉินต้องการให้เจ้าของร้านหรือผู้จัดการเข้ามาเคลียร์ปัญหา",
                incident_type="OWNER_ESCALATION",
                severity="URGENT",
                user=interaction.user,
                channel=interaction.channel
            ))
        except Exception:
            pass

    @ui.button(
        label="ได้รับสินค้าเรียบร้อยแล้ว",
        style=discord.ButtonStyle.success,
        emoji="🎉",
        custom_id="dispatch:process:confirm_received"
    )
    async def btn_confirm_received(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CustomerConfirmReceivedModal())
