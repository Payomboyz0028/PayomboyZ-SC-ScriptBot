# -*- coding: utf-8 -*-
"""
💎 SC-HUB PromptPay Dynamic QR Code Engine (ระบบสร้าง QR Code ล็อคยอดเงินอัตโนมัติ)
Generates standard EMVCo Merchant-Presented Mode (MPM) PromptPay QR codes with locked transaction amounts.
Compatible with all Thai banking applications (K PLUS, SCB EASY, Krungthai NEXT, etc.).
"""

from __future__ import annotations
import io
import re
from typing import Optional, Tuple
import discord
import qrcode
from qrcode.constants import ERROR_CORRECT_M

from config import COLOR_PRIMARY_GOLD


def crc16_ccitt(data: str) -> str:
    """Calculates CRC16-CCITT (0x1021, init 0xFFFF) for EMVCo Tag 63."""
    crc = 0xFFFF
    for b in data.encode("ascii"):
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def format_emvco_tag(tag: str, value: str) -> str:
    """Formats an EMVCo tag: TAG (2 digits) + LENGTH (2 digits) + VALUE."""
    return f"{tag}{len(value):02d}{value}"


def sanitize_promptpay_target(target: str) -> Tuple[str, str]:
    """
    Sanitizes target into:
    - ('01', '0066...') for Mobile Phone
    - ('02', '13-digits') for Citizen ID / Tax ID
    - ('03', '15-digits') for e-Wallet
    """
    clean = re.sub(r"[^\d]", "", target.strip())
    if len(clean) == 10 and clean.startswith("0"):
        # Thai Mobile Phone: 0829934210 -> 0066829934210 (13 chars)
        formatted = "0066" + clean[1:]
        return "01", formatted
    elif len(clean) == 9 and not clean.startswith("0"):
        # 9-digit without leading 0 -> 0066...
        formatted = "0066" + clean
        return "01", formatted
    elif len(clean) == 13:
        # National Citizen ID / Tax ID
        return "02", clean
    elif len(clean) == 15:
        # e-Wallet ID
        return "03", clean
    else:
        # Fallback treat as mobile
        formatted = "0066" + clean.lstrip("0")
        return "01", formatted


def generate_promptpay_payload(target: str, amount: Optional[float] = None) -> str:
    """
    Constructs the EMVCo MPM PromptPay QR payload string.
    If amount is provided (> 0), generates a Dynamic QR (Point of Initiation Method = '12')
    with Tag 54 locked amount. Otherwise generates a Static QR ('11').
    """
    sub_tag, formatted_target = sanitize_promptpay_target(target)

    # Payload Format Indicator (00)
    payload = format_emvco_tag("00", "01")

    # Point of Initiation Method (01): 11 = Static, 12 = Dynamic (with amount)
    init_method = "12" if (amount is not None and amount > 0) else "11"
    payload += format_emvco_tag("01", init_method)

    # Merchant Account Information (29): PromptPay AID + Target
    aid_str = format_emvco_tag("00", "A000000677010111")
    target_str = format_emvco_tag(sub_tag, formatted_target)
    merchant_info = aid_str + target_str
    payload += format_emvco_tag("29", merchant_info)

    # Country Code (58): TH
    payload += format_emvco_tag("58", "TH")

    # Transaction Currency (53): 764 (THB)
    payload += format_emvco_tag("53", "764")

    # Transaction Amount (54): e.g. 150.00
    if amount is not None and amount > 0:
        amt_str = f"{amount:.2f}"
        payload += format_emvco_tag("54", amt_str)

    # Checksum Tag Header (63) with length 04
    payload += "6304"
    checksum = crc16_ccitt(payload)
    return payload + checksum


def generate_promptpay_qr_image(target: str, amount: Optional[float] = None) -> io.BytesIO:
    """Generates a high-resolution PNG image of the PromptPay QR code in memory."""
    payload = generate_promptpay_payload(target, amount)
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=12,
        border=3,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1E1F22", back_color="#FFFFFF")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def format_phone_display(phone: str) -> str:
    """Formats 0829934210 into 082-993-4210."""
    clean = re.sub(r"[^\d]", "", phone)
    if len(clean) == 10:
        return f"{clean[:3]}-{clean[3:6]}-{clean[6:]}"
    elif len(clean) == 13:
        return f"{clean[:1]}-{clean[1:5]}-{clean[5:10]}-{clean[10:12]}-{clean[12:]}"
    return clean


def build_promptpay_qr_embed(
    target: str,
    amount: float,
    ticket_num: int,
    dept_name: str = "บริการทั่วไป"
) -> Tuple[discord.Embed, discord.File]:
    """
    Creates a premium Discord embed with the attached PromptPay Dynamic QR code.
    Returns (discord.Embed, discord.File).
    """
    qr_buf = generate_promptpay_qr_image(target=target, amount=amount)
    filename = f"promptpay_qr_{ticket_num}_{int(amount)}.png"
    file = discord.File(fp=qr_buf, filename=filename)

    display_target = format_phone_display(target)

    embed = discord.Embed(
        title=f"💳 สแกนชำระเงินผ่านพร้อมเพย์ • ตั๋ว #{ticket_num:04d}",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **ยอดเงินที่ต้องชำระ:** `{amount:,.2f}` **บาท** (ล็อคยอดอัตโนมัติ)\n"
            f"📱 **บัญชีพร้อมเพย์:** `{display_target}`\n"
            f"🏷️ **แผนกบริการ:** `{dept_name}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📌 **ขั้นตอนการชำระเงิน:**\n"
            "1. เปิดแอปพลิเคชันธนาคารของคุณ (K PLUS, SCB EASY, Krungthai NEXT ฯลฯ)\n"
            "2. สแกน QR Code ด้านล่างนี้ (ระบบจะล็อคยอดเงินตามจริงให้อัตโนมัติ)\n"
            "3. กดยืนยันการโอนเงิน และบันทึกสลิปหลักฐานการโอน\n"
            "4. เมื่อ API ตรวจสอบสลิปเปิดใช้งาน ระบบจะตรวจสอบและปลดล็อกตั๋วให้อัตโนมัติทันที!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ *คำเตือน: โปรดโอนตามยอดที่ล็อคไว้พอดี ห้ามแก้ไขเศษสตางค์เด็ดขาด*"
        ),
        color=COLOR_PRIMARY_GOLD
    )
    embed.set_image(url=f"attachment://{filename}")
    embed.set_footer(text="💎 SC-HUB DYNAMIC PROMPTPAY ESCROW • ปลอดภัย รวดเร็ว ตรวจสอบได้")
    return embed, file
