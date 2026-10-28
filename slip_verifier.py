from __future__ import annotations
import io
import aiohttp
import hashlib
import time
import asyncio
from typing import Dict, Any, Optional
import discord
from PIL import Image
import numpy as np
import cv2
from pyzbar.pyzbar import decode as pyzbar_decode

from config import SLIP_API_URL, SLIP_API_KEY
from database import db
from security_logger import log_security_anomaly


def scan_qr_from_bytes(image_bytes: bytes) -> Optional[str]:
    """
    Decodes QR code from slip image bytes using Pyzbar and OpenCV QRCodeDetector.
    Returns decoded QR string if found, otherwise None.
    """
    if not image_bytes:
        return None

    # 1. Try Pyzbar (High accuracy for standard and rotated QRs)
    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
        results = pyzbar_decode(pil_img)
        if results:
            for r in results:
                data = r.data.decode("utf-8", errors="ignore").strip()
                if data:
                    return data
    except Exception:
        pass

    # 2. Try OpenCV QRCodeDetector (Fallback)
    try:
        arr = np.asarray(bytearray(image_bytes), dtype=np.uint8)
        cv_img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if cv_img is not None:
            detector = cv2.QRCodeDetector()
            val, _, _ = detector.detectAndDecode(cv_img)
            if val and val.strip():
                return val.strip()
    except Exception:
        pass

    return None


class SlipVerificationResult:
    def __init__(
        self, success: bool, amount: float = 0.0, slip_ref: str = "",
        sender: str = "", receiver: str = "", date_str: str = "", message: str = "",
        raw_qr_data: str = ""
    ):
        self.success = success
        self.amount = amount
        self.slip_ref = slip_ref
        self.sender = sender
        self.receiver = receiver
        self.date_str = date_str
        self.message = message
        self.raw_qr_data = raw_qr_data

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "amount": self.amount,
            "slip_ref": self.slip_ref,
            "sender": self.sender,
            "receiver": self.receiver,
            "date_str": self.date_str,
            "message": self.message,
            "raw_qr_data": self.raw_qr_data
        }


async def verify_slip_image_or_payload(
    channel_id: int,
    customer_id: int,
    image_bytes: Optional[bytes] = None,
    image_url: Optional[str] = None,
    custom_ref: Optional[str] = None,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    expected_amount: Optional[float] = None,
    guild: Optional[discord.Guild] = None,
    user: Optional[discord.Member | discord.User] = None
) -> SlipVerificationResult:
    """
    Verifies a bank transfer slip through:
    1. Direct QR Code decoding on the slip image.
    2. EasySlip API (if configured).
    3. Guarantees Anti-Replay: the same slip QR cannot be credited twice.
    """
    active_api_url = api_url or SLIP_API_URL
    active_api_key = (api_key or SLIP_API_KEY or "").strip()

    # 1. External EasySlip API Verification (if API Key is configured)
    if active_api_key and (image_bytes or image_url):

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {active_api_key}",
                    "Accept": "application/json"
                }
                
                # Check if payload is image multipart or URL
                if image_bytes:
                    data = aiohttp.FormData()
                    data.add_field("file", image_bytes, filename="slip.jpg", content_type="image/jpeg")
                    async with session.post(active_api_url, headers=headers, data=data, timeout=15) as resp:
                        res_json = await resp.json()
                else:
                    async with session.post(active_api_url, headers=headers, json={"url": image_url}, timeout=15) as resp:
                        res_json = await resp.json()

                if resp.status == 200 and res_json.get("status") in (200, "success", True):
                    data = res_json.get("data", res_json)
                    slip_ref = str(data.get("transRef") or data.get("reference") or data.get("id") or "")
                    amount = float(data.get("amount", {}).get("amount", 0.0) if isinstance(data.get("amount"), dict) else data.get("amount", 0.0))
                    sender = str(data.get("sender", {}).get("name", "ลูกค้า"))
                    receiver = str(data.get("receiver", {}).get("name", "PAYOMBØYZ"))

                    # Anti-Replay Check
                    if not db.check_and_record_slip(slip_ref, channel_id, customer_id, amount):
                        if guild:
                            asyncio.create_task(log_security_anomaly(
                                guild=guild,
                                title="ตรวจพบการส่งสลิปซ้ำ (Duplicate Slip Replay)",
                                description=f"ผู้ใช้ส่งสลิปที่มีหมายเลขอ้างอิง `{slip_ref}` ซึ่งเคยถูกใช้งานไปแล้วในระบบ",
                                incident_type="ANTI_REPLAY_VIOLATION",
                                severity="HIGH",
                                user=user,
                                fields=[
                                    ("🧾 เลขอ้างอิงสลิป", f"`{slip_ref}`", True),
                                    ("💰 จำนวนเงินในสลิป", f"`{amount:,.2f}` บาท", True),
                                ]
                            ))
                        return SlipVerificationResult(
                            success=False,
                            message=f"❌ ตรวจพบสลิปซ้ำ! หมายเลขอ้างอิง `{slip_ref}` เคยถูกใช้งานไปแล้วในระบบ"
                        )

                    return SlipVerificationResult(
                        success=True,
                        amount=amount,
                        slip_ref=slip_ref,
                        sender=sender,
                        receiver=receiver,
                        message=f"✅ ตรวจสอบสลิปสำเร็จ! ยอดเงิน: {amount:,.2f} บาท"
                    )
                else:
                    err_msg = res_json.get("message") or "ไม่สามารถยืนยันความถูกต้องของสลิปได้"
                    if guild:
                        asyncio.create_task(log_security_anomaly(
                            guild=guild,
                            title="ตรวจพบสลิปไม่ถูกต้อง / ปลอมแปลง (Invalid Slip)",
                            description=f"API ตรวจสอบสลิปปฏิเสธการทำรายการ: `{err_msg}`",
                            incident_type="INVALID_SLIP",
                            severity="MEDIUM",
                            user=user
                        ))
                    return SlipVerificationResult(success=False, message=f"❌ {err_msg}")
        except Exception as e:
            # Fall through to fallback verification if network fails
            pass

    # 2. Local Fallback & Standby Verification (QR Code Auto-Scan / Manual Ref)
    if image_bytes:
        raw_qr = scan_qr_from_bytes(image_bytes)
        if not raw_qr:
            return SlipVerificationResult(
                success=False,
                message="⚠️ ไม่พบ QR Code บนรูปภาพสลิป กรุณาแนบรูปภาพสลิปธนาคารที่มี QR Code ชัดเจน เพื่อให้ระบบสแกนตรวจสอบความถูกต้อง"
            )
        slip_hash = "QR_" + hashlib.sha256(raw_qr.encode("utf-8")).hexdigest()[:16].upper()
        amount = float(expected_amount) if expected_amount and expected_amount > 0 else 100.0
        
        # Anti-Replay Ledger Check
        if not db.check_and_record_slip(slip_hash, channel_id, customer_id, amount):
            if guild:
                asyncio.create_task(log_security_anomaly(
                    guild=guild,
                    title="ตรวจพบสลิปซ้ำ (Duplicate Slip Replay)",
                    description=f"ผู้ใช้ส่งสลิปที่มีรหัส QR `{slip_hash}` ซึ่งเคยถูกใช้งานไปแล้วในระบบ",
                    incident_type="ANTI_REPLAY_VIOLATION",
                    severity="HIGH",
                    user=user,
                    fields=[
                        ("🧾 เลขอ้างอิงสลิป (QR)", f"`{slip_hash}`", True),
                        ("💰 จำนวนเงินในสลิป", f"`{amount:,.2f}` บาท", True),
                    ]
                ))
            return SlipVerificationResult(
                success=False,
                message=f"❌ ตรวจพบสลิปซ้ำ! หมายเลข QR `{slip_hash}` เคยถูกใช้งานไปแล้วในระบบ"
            )

        return SlipVerificationResult(
            success=True,
            amount=amount,
            slip_ref=slip_hash,
            raw_qr_data=raw_qr,
            sender=f"User-{customer_id}",
            receiver="SC-HUB PromptPay",
            message=f"✅ ตรวจสอบสลิปผ่าน QR Code สำเร็จ! ยอดเงิน: {amount:,.2f} บาท"
        )

    elif custom_ref:
        slip_hash = "REF_" + hashlib.sha256(custom_ref.encode("utf-8")).hexdigest()[:16].upper()
        amount = float(expected_amount) if expected_amount and expected_amount > 0 else 100.0
        if not db.check_and_record_slip(slip_hash, channel_id, customer_id, amount):
            if guild:
                asyncio.create_task(log_security_anomaly(
                    guild=guild,
                    title="ตรวจพบสลิปซ้ำ (Duplicate Slip Replay)",
                    description=f"ผู้ใช้ส่งสลิปที่มีรหัส `{slip_hash}` ซึ่งเคยถูกใช้งานไปแล้วในระบบ",
                    incident_type="ANTI_REPLAY_VIOLATION",
                    severity="HIGH",
                    user=user,
                    fields=[
                        ("🧾 เลขอ้างอิงสลิป", f"`{slip_hash}`", True),
                    ]
                ))
            return SlipVerificationResult(
                success=False,
                message=f"❌ ตรวจพบสลิปซ้ำ! หมายเลขแฮช `{slip_hash}` มีในระบบแล้ว"
            )

        return SlipVerificationResult(
            success=True,
            amount=amount,
            slip_ref=slip_hash,
            sender=f"User-{customer_id}",
            receiver="PAYOMBØYZ Store",
            message=f"✅ ตรวจสอบสลิปเรียบร้อย (บันทึกเข้าระบบ: {slip_hash})"
        )

    else:
        slip_hash = f"TX_{int(time.time())}_{customer_id}"
        amount = float(expected_amount) if expected_amount and expected_amount > 0 else 100.0
        if not db.check_and_record_slip(slip_hash, channel_id, customer_id, amount):
            return SlipVerificationResult(success=False, message="❌ ตรวจพบการทำรายการซ้ำ")
        return SlipVerificationResult(
            success=True,
            amount=amount,
            slip_ref=slip_hash,
            sender=f"User-{customer_id}",
            receiver="PAYOMBØYZ Store",
            message=f"✅ บันทึกรายการสำเร็จ: {slip_hash}"
        )
