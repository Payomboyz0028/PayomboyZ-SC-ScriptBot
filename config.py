"""
💎 SC-HUB Client Service & Work-Allocation Dispatch System — Central Configuration
Loads environment variables and sets system-wide constants.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Dict, Any

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 0. Multi-Layer Hardware-Bound Security Vault & Anti-Exfiltration
from security_vault import (
    sync_and_lock_vault,
    scrub_process_environment,
    install_zero_leak_streams,
    apply_ntfs_acl_lockdown
)

# Install Zero-Leak stream wrapper to redact sensitive tokens in stdout/stderr
install_zero_leak_streams()

# 1. Load & Unseal Credentials from Hardware-Bound Vault & .env
vault_creds = sync_and_lock_vault()

# Apply Windows NTFS ACL permissions lockdown to .env, data/, and vault.enc
apply_ntfs_acl_lockdown()

# 2. Discord Credentials (Decrypted from Hardware-Bound Vault)
DISCORD_BOT_TOKEN = (
    vault_creds.get("DISCORD_BOT_TOKEN") or
    vault_creds.get("DISCORD_DISPATCH_BOT_TOKEN") or
    vault_creds.get("DISCORD_ROLE_BOT_TOKEN") or
    os.environ.get("DISCORD_BOT_TOKEN") or
    ""
)

DISCORD_CLIENT_ID = vault_creds.get("DISCORD_CLIENT_ID") or os.environ.get("DISCORD_CLIENT_ID", "1562840210234933318")
DEFAULT_GUILD_ID = int(vault_creds.get("DISCORD_GUILD_ID") or os.environ.get("DISCORD_GUILD_ID", "1562827586101317672"))
COMMAND_PREFIX = vault_creds.get("COMMAND_PREFIX") or os.environ.get("COMMAND_PREFIX", "!")

# Default Role & Category IDs
DEFAULT_OWNER_ROLE_ID = int(vault_creds.get("DEFAULT_OWNER_ROLE_ID") or os.environ.get("DEFAULT_OWNER_ROLE_ID", "1563251630101766211"))      # Owner
DEFAULT_HEAD_STAFF_ROLE_ID = int(vault_creds.get("DEFAULT_HEAD_STAFF_ROLE_ID") or os.environ.get("DEFAULT_HEAD_STAFF_ROLE_ID", "1563251634119778346"))  # หัวหน้าทีมงาน
DEFAULT_MANAGER_ROLE_ID = int(vault_creds.get("DEFAULT_MANAGER_ROLE_ID") or os.environ.get("DEFAULT_MANAGER_ROLE_ID", "1563251632253304872"))  # ผู้จัดการร้าน
DEFAULT_STAFF_ROLE_ID = int(vault_creds.get("DEFAULT_STAFF_ROLE_ID") or os.environ.get("DEFAULT_STAFF_ROLE_ID", "1563251632253304872"))      # Staff / ผู้จัดการ
DEFAULT_VERIFIED_ROLE_ID = int(vault_creds.get("DEFAULT_VERIFIED_ROLE_ID") or os.environ.get("DEFAULT_VERIFIED_ROLE_ID", "1563251669662171216"))  # Role หลัง Verify
DEFAULT_CATEGORY_ID = int(vault_creds.get("DEFAULT_CATEGORY_ID") or os.environ.get("DEFAULT_CATEGORY_ID", "1549803476094029834"))
DISPUTE_CATEGORY_ID = int(vault_creds.get("DISPUTE_CATEGORY_ID") or os.environ.get("DISPUTE_CATEGORY_ID", "1563251765200293959"))        # 🛟・ศูนย์ช่วยเหลือ

# Dedicated Security, Financial, Audit & Dispute Channels
ANOMALY_LOG_CHANNEL_ID = int(vault_creds.get("ANOMALY_LOG_CHANNEL") or os.environ.get("ANOMALY_LOG_CHANNEL", "1563251866517770250"))
DAILY_SUMMARY_CHANNEL_ID = int(vault_creds.get("DAILY_SUMMARY_CHANNEL") or os.environ.get("DAILY_SUMMARY_CHANNEL", "1563251868501803048"))
MEMBER_AUDIT_CHANNEL_ID = int(vault_creds.get("MEMBER_AUDIT_CHANNEL") or os.environ.get("MEMBER_AUDIT_CHANNEL", "1563251902307901584"))
DISPUTE_PANEL_CHANNEL_ID = int(vault_creds.get("DISPUTE_PANEL_CHANNEL") or os.environ.get("DISPUTE_PANEL_CHANNEL", "1563251767674667019"))  # 🎫・ติดต่อและแจ้งปัญหา
VERIFIED_SLIP_CHANNEL_ID = int(vault_creds.get("VERIFIED_SLIP_CHANNEL") or os.environ.get("VERIFIED_SLIP_CHANNEL", "1563251864256909444"))  # ✅・ตรวจสอบสำเร็จ
ROLE_AUDIT_CHANNEL_ID = int(vault_creds.get("ROLE_AUDIT_CHANNEL") or os.environ.get("ROLE_AUDIT_CHANNEL", "1563251907567419532"))        # 🎭・ประวัติเปลี่ยนยศ
WELCOME_CHANNEL_ID = int(vault_creds.get("WELCOME_CHANNEL_ID") or os.environ.get("WELCOME_CHANNEL_ID", "1563251676830236782"))            # 👋・ยินดีต้อนรับ

# 3. External API Endpoints & userService Configuration
WEB_API_BASE_URL = vault_creds.get("WEB_API_BASE_URL") or os.environ.get("WEB_API_BASE_URL", "https://payomboyzcreative.online/api")
WEB_API_LOG_URL = vault_creds.get("WEB_API_LOG_URL") or os.environ.get("WEB_API_LOG_URL", "https://payomboyzcreative.online/api/dispatch-logs")
WEB_API_SECRET_KEY = vault_creds.get("WEB_API_SECRET_KEY") or vault_creds.get("WEB_API_KEY") or vault_creds.get("WEB_API_LOG_TOKEN") or ""
WEB_API_LOG_TOKEN = WEB_API_SECRET_KEY

SLIP_API_URL = vault_creds.get("SLIP_API_URL") or os.environ.get("SLIP_API_URL", "https://api.easyslip.com/v1/verify")
SLIP_API_KEY = vault_creds.get("SLIP_API_KEY") or os.environ.get("SLIP_API_KEY", "")
TRUEMONEY_PHONE = vault_creds.get("TRUEMONEY_PHONE") or os.environ.get("TRUEMONEY_PHONE", "0829934210")

# 4. In-Memory Sanitization: Wipe sensitive tokens from os.environ
scrub_process_environment()

# 4. Color Palette Tokens
COLOR_PRIMARY_GOLD = 0xF1C40F
COLOR_EMBED_DARK = 0x1E1F22
COLOR_SUCCESS = 0x2ECC71
COLOR_DANGER = 0xE74C3C
COLOR_INFO = 0x3498DB
COLOR_NEUTRAL = 0x95A5A6

# 5. Department Definitions with Explicit Role & Admin Channel Mapping
DEPARTMENTS: Dict[str, Dict[str, Any]] = {
    "game": {
        "id": "game",
        "name": "ห้องเติมเกมส์",
        "emoji": "🎮",
        "desc": "บริการเติมเกม บัตรเติมเงิน และแพ็กเกจเกมออนไลน์",
        "role_name": "ลูกค้า-เติมเกม",
        "role_id": int(os.environ.get("ROLE_CUSTOMER_GAME", "1563251664192929975")),
        "staff_role_name": "แอดมิน-เติมเกม",
        "staff_role_id": int(os.environ.get("ROLE_STAFF_GAME", "1563251654520868925")),
        "admin_channel_id": int(os.environ.get("ADMIN_CHANNEL_GAME", "1563251828425228328")),
        "ongoing_channel_id": int(os.environ.get("ONGOING_CHANNEL_GAME", "1563251830677315666")),
        "channel_prefix": "🎮・เติมเกม"
    },
    "script": {
        "id": "script",
        "name": "ห้องซื้อขายสคริปต์",
        "emoji": "📜",
        "desc": "สั่งซื้อสคริปต์ Luau, ซื้อคีย์ VVIP, จ้างโมดิฟายด์สคริปต์",
        "role_name": "ลูกค้า-สคริปต์",
        "role_id": int(os.environ.get("ROLE_CUSTOMER_SCRIPT", "1563251667552444499")),
        "staff_role_name": "แอดมิน-สคริปต์",
        "staff_role_id": int(os.environ.get("ROLE_STAFF_SCRIPT", "1563251658069254206")),
        "admin_channel_id": int(os.environ.get("ADMIN_CHANNEL_SCRIPT", "1563251851598626927")),
        "ongoing_channel_id": int(os.environ.get("ONGOING_CHANNEL_SCRIPT", "1563251853477552259")),
        "channel_prefix": "📜・สคริปต์"
    },
    "web": {
        "id": "web",
        "name": "ห้องรับทำ Website",
        "emoji": "🌐",
        "desc": "รับออกแบบและพัฒนาเว็บไซต์, Web Apps, Next.js, Discord Bots",
        "role_name": "ลูกค้า-เว็บไซต์",
        "role_id": int(os.environ.get("ROLE_CUSTOMER_WEB", "1563251665560408137")),
        "staff_role_name": "แอดมิน-เว็บไซต์",
        "staff_role_id": int(os.environ.get("ROLE_STAFF_WEB", "1563251656596918412")),
        "admin_channel_id": int(os.environ.get("ADMIN_CHANNEL_WEB", "1563251839670034505")),
        "ongoing_channel_id": int(os.environ.get("ONGOING_CHANNEL_WEB", "1563251842232615052")),
        "channel_prefix": "🌐・เว็บไซต์"
    }
}

ONGOING_CHANNELS: Dict[str, int] = {
    "game": int(os.environ.get("ONGOING_CHANNEL_GAME", "1563251830677315666")),
    "web": int(os.environ.get("ONGOING_CHANNEL_WEB", "1563251842232615052")),
    "script": int(os.environ.get("ONGOING_CHANNEL_SCRIPT", "1563251853477552259"))
}

DEFAULT_ONGOING_BOARD_MSG_IDS: Dict[str, int] = {
    "game": int(os.environ.get("ONGOING_BOARD_MSG_GAME", "1563632221435330701")),
    "web": int(os.environ.get("ONGOING_BOARD_MSG_WEB", "1563632223465513204")),
    "script": int(os.environ.get("ONGOING_BOARD_MSG_SCRIPT", "1563632225361199216"))
}


# 6. Database Configuration
DB_PATH = DATA_DIR / "dispatch.sqlite3"
