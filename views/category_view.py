# -*- coding: utf-8 -*-
"""
💎 SC-HUB Department & Category Router View
Grants isolated department roles enabling access to specialized category channels.
Designed with high-aesthetic modern Discord layout.
"""

from __future__ import annotations
import asyncio
import discord
from discord import ui
from typing import Dict, Any, Optional

from config import DEPARTMENTS, COLOR_PRIMARY_GOLD, COLOR_INFO
from database import db


def build_category_router_embed() -> discord.Embed:
    embed = discord.Embed(
        title="💎 SC-HUB | ศูนย์รวมบริการลูกค้าและเลือกแผนกงาน",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "✨ **ยินดีต้อนรับสู่ศูนย์บริการลูกค้า SC-HUB (Client Portal)**\n"
            "กรุณาเลือกหมวดหมู่บริการที่คุณต้องการ เพื่อเข้าสู่ห้องงานและฝ่ายดูแลเฉพาะด้าน\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🎮 **1. แผนกเติมเกมส์ (Game Topup & Currency)**\n"
            "• บริการเติมเกมออนไลน์, เติม Robux เรทพิเศษ, บัตรเติมเงิน และแพ็กเกจเกมสุดคุ้ม\n\n"
            "📜 **2. แผนกซื้อขายสคริปต์ (Script Hub & VVIP Keys)**\n"
            "• สคริปต์ Roblox Luau คุณภาพสูง, รันง่าย ปลอดภัย, คีย์ VVIP และระบบฟาร์มอัตโนมัติ\n\n"
            "🌐 **3. แผนกรับทำ Website (Web & Bot Development)**\n"
            "• ออกแบบและพัฒนาเว็บไซต์ทันสมัย, Web Application, ระบบหลังบ้าน และบอท Discord อัจฉริยะ\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔒 *ระบบจะปรับแต่งการมองเห็นห้องของคุณให้ตรงกับหมวดที่เลือก เพื่อความเป็นส่วนตัวสูงสุด*"
        ),
        color=0x00A8FF  # Neon Electric Cyan
    )
    embed.set_footer(text="💎 SC-HUB CLIENT DISPATCHER • บริการรวดเร็ว ฉับไว ปลอดภัย 100%")
    return embed


async def assign_department_role(interaction: discord.Interaction, dept_key: str):
    user = interaction.user
    guild = interaction.guild
    if not guild or not isinstance(user, discord.Member):
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        else:
            await interaction.followup.send("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
        return

    dept = DEPARTMENTS.get(dept_key)
    if not dept:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ ไม่พบหมวดหมู่ที่ระบุ", ephemeral=True)
        else:
            await interaction.followup.send("❌ ไม่พบหมวดหมู่ที่ระบุ", ephemeral=True)
        return

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)

    cfg = db.get_guild_config(guild.id)
    dept_roles = cfg.get("dept_roles", {})
    role_id = dept_roles.get(dept_key) or dept.get("role_id")

    target_role = guild.get_role(role_id) if role_id else None

    # Fallback to search by name or create role if missing
    if not target_role:
        for r in guild.roles:
            if dept["role_name"].lower() in r.name.lower() or dept_key in r.name.lower():
                target_role = r
                break

    if not target_role:
        try:
            target_role = await guild.create_role(
                name=dept["role_name"],
                reason=f"Auto-created department role for {dept['name']}"
            )
            dept_roles[dept_key] = target_role.id
            db.update_guild_config(guild.id, dept_roles=dept_roles)
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ บอทไม่มีสิทธิ์สร้างหรือมอบ Role `{dept['role_name']}` ให้คุณ (โปรดตรวจสอบ Permission)",
                ephemeral=True
            )
            return

    # 1. รวบรวม ID และชื่อยศลูกค้าทุกแผนกเพื่อใช้ตรวจสอบการลบยศเก่า
    all_dept_role_ids = set()
    for k, d in DEPARTMENTS.items():
        rid = dept_roles.get(k) or d.get("role_id")
        if rid:
            try:
                all_dept_role_ids.add(int(rid))
            except (ValueError, TypeError):
                pass

    all_dept_role_names = {d["role_name"].lower() for d in DEPARTMENTS.values()}

    # 2. ตรวจสอบยศแผนกเดิมที่ผู้ใช้มีอยู่ (ที่ไม่ใช่ target_role) เพื่อทำการลบออก
    roles_to_remove: list[discord.Role] = []
    for r in user.roles:
        if r.id == target_role.id:
            continue
        # กรองยศแผนก: ตรงกับ role_id ที่ตั้งค่า, ตรงชื่อยศลูกค้า หรือขึ้นต้นด้วย 'ลูกค้า-'
        if r.id in all_dept_role_ids or r.name.lower() in all_dept_role_names or (r.name.startswith("ลูกค้า-") and not r.name.startswith("แอดมิน-")):
            roles_to_remove.append(r)

    # กรณีผู้ใช้อยู่ในแผนกนี้อยู่แล้ว และไม่มียศเก่าค้างอยู่
    if target_role in user.roles and not roles_to_remove:
        already_embed = discord.Embed(
            title=f"ℹ️ คุณอยู่ในแผนก {dept['name']} อยู่แล้ว",
            description=(
                f"คุณ {user.mention} มีบทบาท {target_role.mention} เรียบร้อยแล้วครับ\n"
                f"👉 สามารถคลิกเข้าไปที่ห้องของแผนกเพื่อติดต่อทีมงานได้ทันที"
            ),
            color=COLOR_INFO
        )
        already_embed.set_footer(text="💎 SC-HUB CLIENT SERVICE")
        await interaction.followup.send(embed=already_embed, ephemeral=True)
        return

    try:
        # 3. ลบยศแผนกเดิมออกก่อน (Clean removal)
        if roles_to_remove:
            await user.remove_roles(*roles_to_remove, reason=f"สลับแผนกบริการ: ถอดยศเดิมออกเพื่อเข้าสู่ {dept['name']}")
            await asyncio.sleep(0.2)

        # 4. มอบยศแผนกใหม่
        if target_role not in user.roles:
            await user.add_roles(target_role, reason=f"เลือกเข้าแผนก: {dept['name']}")

        removed_line = ""
        if roles_to_remove:
            removed_mentions = ", ".join(r.mention for r in roles_to_remove)
            removed_line = f"• **ยศแผนกเดิมที่ถูกลบออก:** {removed_mentions}\n"

        success_embed = discord.Embed(
            title=f"✅ เปลี่ยนยศเข้าสู่แผนก {dept['name']} เรียบร้อยแล้ว!",
            description=(
                f"ยินดีต้อนรับ {user.mention} 👋\n"
                f"• **บทบาทปัจจุบัน:** {target_role.mention}\n"
                f"{removed_line}"
                f"• **ห้องประจำแผนก:** ขณะนี้ห้องสำหรับ **{dept['name']}** ปรากฏขึ้นในรายการห้องของคุณแล้ว\n\n"
                "👉 *กรุณาคลิกเข้าไปที่ห้องของแผนกเพื่อกดเรียกทีมงานหรือติดต่อบริการได้ทันที*"
            ),
            color=0x2ECC71
        )
        success_embed.set_footer(text="💎 SC-HUB CLIENT SERVICE • ระบบเปลี่ยนยศและลบยศเดิมอัตโนมัติ")
        await interaction.followup.send(embed=success_embed, ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(
            f"❌ บอทไม่มีสิทธิ์ปรับเปลี่ยน Role {target_role.mention} ให้คุณ (โปรดเลื่อนยศของบอทให้อยู่เหนือยศนี้ใน Server Settings)",
            ephemeral=True
        )


class CategorySelectDropdown(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="ห้องเติมเกมส์ (Game Topup)",
                value="game",
                description="บริการเติมเกม, เติม Robux, คีย์เกมออนไลน์",
                emoji="🎮"
            ),
            discord.SelectOption(
                label="ห้องซื้อขายสคริปต์ (Script Trading)",
                value="script",
                description="สั่งซื้อสคริปต์ Luau, คีย์ VVIP, สคริปต์ฟาร์ม",
                emoji="📜"
            ),
            discord.SelectOption(
                label="ห้องรับทำ Website (Web & Bot)",
                value="web",
                description="พัฒนาเว็บไซต์, Web Application, Discord Bot",
                emoji="🌐"
            ),
        ]
        super().__init__(
            placeholder="คลิกเลือกหมวดหมู่บริการที่ต้องการติดต่อ...",
            min_values=1,
            max_values=1,
            custom_id="dispatch:category:select_dropdown",
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        await assign_department_role(interaction, self.values[0])


class CategoryRouterView(ui.View):
    """Persistent View for department selection (buttons only)."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="ห้องเติมเกมส์",
        style=discord.ButtonStyle.primary,
        emoji="🎮",
        custom_id="dispatch:category:btn_game",
        row=0
    )
    async def btn_game(self, interaction: discord.Interaction, button: ui.Button):
        await assign_department_role(interaction, "game")

    @ui.button(
        label="ห้องซื้อขายสคริปต์",
        style=discord.ButtonStyle.success,
        emoji="📜",
        custom_id="dispatch:category:btn_script",
        row=0
    )
    async def btn_script(self, interaction: discord.Interaction, button: ui.Button):
        await assign_department_role(interaction, "script")

    @ui.button(
        label="ห้องรับทำ Website",
        style=discord.ButtonStyle.secondary,
        emoji="🌐",
        custom_id="dispatch:category:btn_web",
        row=0
    )
    async def btn_web(self, interaction: discord.Interaction, button: ui.Button):
        await assign_department_role(interaction, "web")

