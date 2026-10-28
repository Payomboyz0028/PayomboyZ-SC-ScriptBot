# -*- coding: utf-8 -*-
"""
💎 SC-HUB Client Service & Work-Allocation System — User & Web API Service (userService)
====================================================================================
Production-grade external Website & Backend API connector.
Provides bi-directional synchronization between Discord guild activities and the web panel:
- Customer profile lookup (balance, rank, purchases, subscriptions)
- Discord user registration & account linking
- License verification & key validation
- Real-time ticket claim dispatch (when admin claims a customer)
- Final transaction & audit ticket logging
"""

from __future__ import annotations
import aiohttp
import time
import json
import logging
from typing import Dict, Any, Optional, Tuple

from config import WEB_API_BASE_URL, WEB_API_LOG_URL, WEB_API_SECRET_KEY, WEB_API_LOG_TOKEN
from database import db

logger = logging.getLogger("SC-HUB.UserService")


class UserService:
    """
    Central API bridge for connecting SC-HUB Discord Bot with external website/backend.
    Can be imported directly as `from user_service import userService`.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        log_url: Optional[str] = None,
        timeout_seconds: float = 8.0
    ):
        self.default_base_url = (base_url or WEB_API_BASE_URL).rstrip("/")
        self.default_api_key = api_key or WEB_API_SECRET_KEY or WEB_API_LOG_TOKEN
        self.default_log_url = log_url or WEB_API_LOG_URL
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    def _resolve_endpoints(self, guild_id: Optional[int | str] = None) -> Tuple[str, str, str]:
        """
        Resolves active API endpoints and Secret Key, giving precedence to guild-specific DB config.
        """
        base_url = self.default_base_url
        log_url = self.default_log_url
        api_key = self.default_api_key

        if guild_id:
            cfg = db.get_guild_config(guild_id)
            if cfg.get("web_api_url"):
                log_url = cfg["web_api_url"]
            if cfg.get("web_api_token"):
                api_key = cfg["web_api_token"]

        return base_url, log_url, api_key

    def _build_headers(self, api_key: str) -> Dict[str, str]:
        """Builds standard authorization & content headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SC-HUB-Discord-Bridge/2.0 (PayomboyZ Engine)"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            headers["X-API-Key"] = api_key
        return headers

    async def get_user_profile(
        self,
        discord_id: int | str,
        guild_id: Optional[int | str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Fetches user profile, web wallet balance, and VIP tier from the website.
        Endpoint: GET {base_url}/users/{discord_id}
        """
        base_url, _, api_key = self._resolve_endpoints(guild_id)
        if not base_url:
            return False, {"error": "ไม่มีการตั้งค่า WEB_API_BASE_URL ใน .env"}

        url = f"{base_url}/users/{discord_id}"
        headers = self._build_headers(api_key)

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return True, data
                    elif resp.status == 404:
                        return False, {"error": "ไม่พบบัญชีผู้ใช้งานบนเว็บไซต์ (User not registered)"}
                    else:
                        text = await resp.text()
                        return False, {"error": f"API ตอบกลับ HTTP {resp.status}: {text[:120]}"}
        except Exception as e:
            logger.warning(f"Failed to fetch user profile for {discord_id}: {e}")
            return False, {"error": f"เชื่อมต่อ Website API ไม่สำเร็จ: {e}"}

    async def sync_user_registration(
        self,
        discord_id: int | str,
        username: str,
        roles: Optional[list[str]] = None,
        guild_id: Optional[int | str] = None
    ) -> Tuple[bool, str]:
        """
        Registers or updates a customer in the web database upon Discord verification.
        Endpoint: POST {base_url}/users/sync
        """
        base_url, _, api_key = self._resolve_endpoints(guild_id)
        if not base_url:
            return False, "ไม่มีการตั้งค่า WEB_API_BASE_URL"

        url = f"{base_url}/users/sync"
        headers = self._build_headers(api_key)
        payload = {
            "event": "USER_VERIFIED",
            "discord_id": str(discord_id),
            "username": username,
            "roles": roles or [],
            "timestamp": time.time()
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status in (200, 201):
                        return True, "ซิงค์ข้อมูลผู้ใช้ไปยังเว็บไซต์สำเร็จ"
                    text = await resp.text()
                    return False, f"API HTTP {resp.status}: {text[:100]}"
        except Exception as e:
            return False, f"เชื่อมต่อเว็บไม่สำเร็จ: {e}"

    async def verify_user_license(
        self,
        discord_id: int | str,
        product_slug: str,
        guild_id: Optional[int | str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Validates whether the user owns an active license/key for a specific script/product.
        Endpoint: POST {base_url}/licenses/verify
        """
        base_url, _, api_key = self._resolve_endpoints(guild_id)
        if not base_url:
            return False, {"valid": False, "reason": "ไม่มีการตั้งค่า Web API"}

        url = f"{base_url}/licenses/verify"
        headers = self._build_headers(api_key)
        payload = {
            "discord_id": str(discord_id),
            "product": product_slug,
            "timestamp": time.time()
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("valid", False), data
                    text = await resp.text()
                    return False, {"valid": False, "reason": f"HTTP {resp.status}: {text[:100]}"}
        except Exception as e:
            return False, {"valid": False, "reason": str(e)}

    async def report_ticket_claim(
        self,
        guild_id: int | str,
        ticket_data: Dict[str, Any],
        admin_id: int | str,
        admin_name: str
    ) -> Tuple[bool, str]:
        """
        Fires an event to the web API when an Admin claims a pending customer job.
        Endpoint: POST {base_url}/tickets/claim
        """
        base_url, log_url, api_key = self._resolve_endpoints(guild_id)
        target_url = f"{base_url}/tickets/claim" if base_url else log_url
        if not target_url:
            return False, "ไม่มีการตั้งค่า Endpoint สำหรับ Ticket Claim"

        headers = self._build_headers(api_key)
        payload = {
            "event": "TICKET_CLAIMED",
            "timestamp": time.time(),
            "guild_id": str(guild_id),
            "ticket": {
                "ticket_num": ticket_data.get("ticket_num"),
                "channel_id": str(ticket_data.get("channel_id")),
                "category": ticket_data.get("category_key"),
                "created_at": ticket_data.get("created_at")
            },
            "customer_id": str(ticket_data.get("customer_id")),
            "admin": {
                "id": str(admin_id),
                "username": admin_name
            }
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(target_url, json=payload, headers=headers) as resp:
                    if resp.status in (200, 201, 204):
                        return True, "แจ้งเตือน Admin Claim ไปยังเว็บสำเร็จ"
                    text = await resp.text()
                    return False, f"เว็บตอบกลับ HTTP {resp.status}: {text[:100]}"
        except Exception as e:
            return False, f"ส่ง Claim Event ไม่สำเร็จ: {e}"

    async def send_ticket_completed_log(
        self,
        guild_id: int | str,
        ticket_data: Dict[str, Any],
        customer_name: str,
        admin_name: str,
        override_api_url: Optional[str] = None,
        override_api_token: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Dispatches final ticket closure summary, payment records, and user IDs to the website API.
        Endpoint: POST {override_api_url or web_api_url or WEB_API_LOG_URL}
        """
        cfg = db.get_guild_config(guild_id)
        api_url = override_api_url or cfg.get("web_api_url") or self.default_log_url
        api_token = override_api_token or cfg.get("web_api_token") or self.default_api_key

        if not api_url:
            return False, "ไม่มีการตั้งค่า Web API URL"

        payload = {
            "event": "TICKET_COMPLETED",
            "timestamp": time.time(),
            "guild_id": str(guild_id),
            "ticket": {
                "ticket_num": ticket_data.get("ticket_num"),
                "channel_id": str(ticket_data.get("channel_id")),
                "category": ticket_data.get("category_key"),
                "created_at": ticket_data.get("created_at"),
                "closed_at": time.time()
            },
            "customer": {
                "id": str(ticket_data.get("customer_id")),
                "username": customer_name
            },
            "admin": {
                "id": str(ticket_data.get("claimed_admin_id")),
                "username": admin_name
            },
            "payment": {
                "is_paid": bool(ticket_data.get("paid_status")),
                "amount": float(ticket_data.get("amount", 0.0)),
                "slip_ref": ticket_data.get("slip_ref") or "N/A",
                "slip_image_path": ticket_data.get("slip_image_path") or ""
            }
        }

        headers = self._build_headers(api_token)

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(api_url, json=payload, headers=headers) as resp:
                    if resp.status in (200, 201, 204):
                        return True, "ส่ง Log ไปยัง Website API สำเร็จ"
                    else:
                        text = await resp.text()
                        return False, f"Website API ตอบกลับรหัส {resp.status}: {text[:150]}"
        except Exception as e:
            return False, f"เกิดข้อผิดพลาดในการเชื่อมต่อ Website API: {e}"

    async def check_health(self, guild_id: Optional[int | str] = None) -> Tuple[bool, str]:
        """
        Health check verifying connectivity to the configured Website API.
        """
        base_url, log_url, api_key = self._resolve_endpoints(guild_id)
        target = base_url or log_url
        if not target:
            return False, "ไม่มี URL สำหรับทดสอบ"

        headers = self._build_headers(api_key)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5.0)) as session:
                async with session.get(target, headers=headers) as resp:
                    return True, f"เชื่อมต่อสำเร็จ (HTTP {resp.status})"
        except Exception as e:
            return False, f"การเชื่อมต่อล้มเหลว: {e}"


# Global Exported Singleton Instances
userService = UserService()
user_service = userService

# Backward-compatible direct function for web_logger callers
async def send_ticket_completed_log(*args, **kwargs):
    return await userService.send_ticket_completed_log(*args, **kwargs)
