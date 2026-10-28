# -*- coding: utf-8 -*-
"""
PAYOMBØYZ Verification View & CAPTCHA Modal
Exact clone of PAYOMBØYZ Verification UI with randomized visual distorted CAPTCHA.
"""

from __future__ import annotations
import discord
from discord import ui
from typing import Optional

from config import COLOR_DANGER, COLOR_SUCCESS, DEFAULT_VERIFIED_ROLE_ID
from database import db
from captcha_engine import generate_captcha_image


def build_verification_panel_embed(guild: discord.Guild, verified_role: Optional[discord.Role] = None) -> discord.Embed:
    """Builds the public verification panel embed matching the original Discord channel."""
    role_str = verified_role.mention if verified_role else "@-:-. ยืนยันตัวตนแล้ว •"
    
    embed = discord.Embed(
        title="PAYOMBØYZ Verification",
        description=(
            "โปรดกดปุ่ม \"ยืนยันตัวตน\" ด้านล่าง และนำเลข Captcha ไปใส่ในช่อง เพื่อยืนยันตัวตน "
            "ว่าคนนะไม่ใช่หุ่นยนต์ ที่จะทนตากแดดทั้งวัน\n\n"
            f"Verified role: {role_str} •"
        ),
        color=COLOR_DANGER  # Red left stripe as seen in the reference screenshot
    )
    embed.set_footer(text="💎 SC-HUB VERIFICATION SYSTEM • ปลอดภัยจากบอท 100%")
    return embed


class CaptchaAnswerModal(ui.Modal, title="ยืนยันคำตอบ Captcha"):
    code_input = ui.TextInput(
        label="นำตัวอักษร 5 หลักตามภาพมาใส่ในช่องนี้",
        placeholder="ตัวอย่าง: R G 2 G K",
        required=True,
        min_length=3,
        max_length=12
    )

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        if not guild or not isinstance(user, discord.Member):
            await interaction.response.send_message("❌ คำสั่งนี้ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
            return

        raw_answer = self.code_input.value
        is_valid = db.verify_captcha(user.id, raw_answer)

        if not is_valid:
            fail_cnt = db.record_captcha_failure(user.id)
            if fail_cnt >= 3:
                try:
                    from security_logger import log_security_anomaly
                    import asyncio
                    asyncio.create_task(log_security_anomaly(
                        guild=guild,
                        title="ตรวจพบพฤติกรรมสุ่มตอบ Captcha ผิดซ้ำซ้อน (Bot / Brute Force Suspect)",
                        description=f"ผู้ใช้กรอกรหัส Captcha ผิดพลาดติดต่อกัน `{fail_cnt}` ครั้ง กรุณาเฝ้าระวังพฤติกรรมบอท",
                        incident_type="CAPTCHA_BRUTE_FORCE",
                        severity="MEDIUM",
                        user=user,
                        fields=[
                            ("🔢 จำนวนครั้งที่ผิด", f"`{fail_cnt}` ครั้ง", True),
                            ("📝 คำตอบล่าสุดที่กรอก", f"`{raw_answer[:20]}`", True)
                        ]
                    ))
                except Exception:
                    pass

            await interaction.response.send_message(
                f"❌ **รหัส Captcha ไม่ถูกต้องหรือหมดอายุแล้ว!** (ผิดพลาดครั้งที่ {fail_cnt})\nโปรดกดปุ่ม \"ยืนยันตัวตน\" เพื่อสุ่มรหัสชุดใหม่",
                ephemeral=True
            )
            return

        # Verification succeeded: reset failure count
        db.reset_captcha_failure(user.id)

        # Fetch configured verified role
        cfg = db.get_guild_config(guild.id)
        role_id = cfg.get("verified_role_id") or DEFAULT_VERIFIED_ROLE_ID
        verified_role = guild.get_role(role_id) if role_id else None

        # Fallback role lookup by name
        if not verified_role:
            for r in guild.roles:
                if any(w in r.name.lower() for w in ("ยืนยันตัวตน", "verified", "member")):
                    verified_role = r
                    break

        if verified_role:
            try:
                await user.add_roles(verified_role, reason="PAYOMBØYZ CAPTCHA Verification Passed")
                
                # Log to MEMBER_AUDIT_CHANNEL_ID (1563251902307901584)
                try:
                    from member_logger import log_member_verified
                    import asyncio
                    asyncio.create_task(log_member_verified(guild=guild, member=user, role=verified_role))
                except Exception as e:
                    print(f"[-] Member audit verify log error: {e}")

                # Send High-End Welcome Card Announcement to WELCOME_CHANNEL_ID (1563251676830236782)
                try:
                    from welcome_card import send_welcome_announcement
                    import asyncio
                    asyncio.create_task(send_welcome_announcement(guild=guild, member=user, verified_role=verified_role))
                except Exception as e:
                    print(f"[-] Welcome card announcement error: {e}")

                await interaction.response.send_message(
                    f"🎉 **ยืนยันตัวตนสำเร็จแล้ว!** คุณได้รับยศ {verified_role.mention} เรียบร้อยแล้ว ยินดีต้อนรับสู่สังคม PAYOMBØYZ!",
                    ephemeral=True
                )
                return
            except discord.Forbidden:
                await interaction.response.send_message(
                    "⚠️ ยืนยันตัวตนถูกต้อง แต่บอทไม่มีสิทธิ์มอบ Role ให้คุณ (โปรดตรวจสอบลำดับ Role Hierarchy ของบอท)",
                    ephemeral=True
                )
                return
        
        await interaction.response.send_message(
            "✅ **ยืนยันตัวตนถูกต้อง!** (ระบบไม่พบบทบาทที่ตั้งค่าไว้ โปรดแจ้งแอดมิน)",
            ephemeral=True
        )


class CaptchaChallengeView(ui.View):
    """Ephemeral view containing the 'ยืนยันคำตอบ' button."""
    def __init__(self):
        super().__init__(timeout=300)

    @ui.button(
        label="ยืนยันคำตอบ",
        style=discord.ButtonStyle.primary,
        custom_id="dispatch:captcha:answer_btn"
    )
    async def btn_answer(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CaptchaAnswerModal())


class VerificationPanelView(ui.View):
    """Persistent view for the public verification panel — survives bot restarts."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="ยืนยันตัวตน",
        style=discord.ButtonStyle.success,
        custom_id="dispatch:verify:main_btn"
    )
    async def btn_verify(self, interaction: discord.Interaction, button: ui.Button):
        user = interaction.user
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ ใช้ได้เฉพาะในเซิร์ฟเวอร์", ephemeral=True)
            return

        # Check if already verified
        cfg = db.get_guild_config(guild.id)
        role_id = cfg.get("verified_role_id")
        if role_id and isinstance(user, discord.Member):
            has_role = any(r.id == role_id for r in user.roles)
            if has_role:
                await interaction.response.send_message("✅ คุณผ่านการยืนยันตัวตนไปเรียบร้อยแล้ว!", ephemeral=True)
                return

        # Generate fresh CAPTCHA code and distorted image
        code, img_buf = generate_captcha_image(length=5)
        db.create_captcha_session(user.id, code, ttl=300)

        file = discord.File(img_buf, filename="captcha.png")

        challenge_embed = discord.Embed(
            title="Captcha Challenge",
            description="Type the characters shown in the image. This challenge expires in 5 minutes.",
            color=COLOR_DANGER
        )
        challenge_embed.set_image(url="attachment://captcha.png")

        await interaction.response.send_message(
            embed=challenge_embed,
            file=file,
            view=CaptchaChallengeView(),
            ephemeral=True
        )
