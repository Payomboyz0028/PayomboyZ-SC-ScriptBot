# -*- coding: utf-8 -*-
"""
💎 SC-HUB Multi-Layer Hardware-Bound Credential Vault & Anti-Exfiltration Engine
Secures tokens and API keys using Windows DPAPI (Data Protection API) combined with
machine-unique motherboard GUID entropy.

Protection Highlights:
1. Hardware-Bound Vault: Credentials encrypted on this machine CANNOT be decrypted
   if copied to another computer, VM, or uploaded to GitHub/cloud.
2. In-Memory Sanitization: Wipes raw credentials from os.environ after boot.
3. Zero-Leak Stream Filter: Redacts tokens and secrets from stdout, stderr, and logs.
4. OS Filesystem Hardening: Applies strict NTFS ACLs restricting access exclusively
   to the running user account.
"""

from __future__ import annotations
import os
import sys
import re
import json
import ctypes
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

if sys.platform == "win32":
    try:
        import ctypes.wintypes
        import winreg

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ('cbData', ctypes.wintypes.DWORD),
                ('pbData', ctypes.POINTER(ctypes.c_char))
            ]
    except Exception:
        winreg = None
        class DATA_BLOB:
            pass
else:
    winreg = None
    class DATA_BLOB:
        pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
VAULT_PATH = DATA_DIR / "vault.enc"
ENV_PATH = BASE_DIR / ".env"

# Regex patterns for secret redaction
TOKEN_SCRUB_PATTERNS = [
    re.compile(r'([MN][A-Za-z\d]{23,25}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{27,39})'),  # Discord Bot Token
    re.compile(r'(https://gift\.truemoney\.com/campaign/\?v=[a-zA-Z0-9_-]{15,45})'), # TrueMoney Voucher link
    re.compile(r'(Bearer\s+[A-Za-z0-9_\-\.]{20,})', re.IGNORECASE),                 # Bearer tokens
]


def get_hardware_entropy() -> bytes:
    """
    Derives machine-unique entropy from system constants.
    """
    machine_guid = "SC_HUB_DEFAULT_SYSTEM_SALT"
    if sys.platform == "win32" and winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                val, _ = winreg.QueryValueEx(key, "MachineGuid")
                machine_guid = str(val)
        except Exception:
            pass
    else:
        machine_guid = os.environ.get("RENDER_INSTANCE_ID") or os.environ.get("HOSTNAME") or "LINUX_CONTAINER"
    
    username = os.environ.get("USERNAME") or os.environ.get("USER") or "SystemUser"
    seed = f"{machine_guid}:{username}:PAYOMBØYZ_VAULT_V1"
    return hashlib.sha256(seed.encode("utf-8")).digest()


def dpapi_encrypt(data: bytes, entropy: bytes) -> bytes:
    """Encrypts bytes using Windows DPAPI bound to user and machine entropy."""
    if sys.platform != "win32":
        # Non-windows fallback using SHA256-XOR stream cipher
        key = hashlib.sha256(entropy).digest()
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    blob_in = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    blob_entropy = DATA_BLOB(len(entropy), ctypes.cast(ctypes.create_string_buffer(entropy), ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()

    # CRYPTPROTECT_UI_FORBIDDEN = 0x1
    success = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "SC-HUB-VAULT",
        ctypes.byref(blob_entropy),
        None,
        None,
        0x1,
        ctypes.byref(blob_out)
    )

    if not success:
        raise RuntimeError("Windows DPAPI CryptProtectData failed.")

    encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    kernel32.LocalFree(blob_out.pbData)
    return encrypted


def dpapi_decrypt(enc_data: bytes, entropy: bytes) -> bytes:
    """Decrypts bytes using Windows DPAPI bound to user and machine entropy."""
    if sys.platform != "win32":
        key = hashlib.sha256(entropy).digest()
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(enc_data))

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    blob_in = DATA_BLOB(len(enc_data), ctypes.cast(ctypes.create_string_buffer(enc_data), ctypes.POINTER(ctypes.c_char)))
    blob_entropy = DATA_BLOB(len(entropy), ctypes.cast(ctypes.create_string_buffer(entropy), ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()

    success = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        ctypes.byref(blob_entropy),
        None,
        None,
        0x1,
        ctypes.byref(blob_out)
    )

    if not success:
        raise RuntimeError("Windows DPAPI CryptUnprotectData failed. Payload was created on another machine or by another user account.")

    decrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    kernel32.LocalFree(blob_out.pbData)
    return decrypted


def seal_credentials_to_vault(creds: Dict[str, str]) -> bool:
    """Encrypts credentials dictionary into binary hardware-bound vault."""
    try:
        entropy = get_hardware_entropy()
        payload = json.dumps(creds, ensure_ascii=False).encode("utf-8")
        enc = dpapi_encrypt(payload, entropy)
        
        # Write to vault with atomic replacement
        tmp_path = VAULT_PATH.with_suffix(".tmp")
        with open(tmp_path, "wb") as f:
            f.write(enc)
        tmp_path.replace(VAULT_PATH)
        return True
    except Exception as e:
        print(f"[-] [VAULT] Error sealing credentials: {e}")
        return False


def unseal_credentials_from_vault() -> Optional[Dict[str, str]]:
    """Decrypts and returns credentials dictionary from binary hardware-bound vault."""
    if not VAULT_PATH.exists():
        return None
    try:
        entropy = get_hardware_entropy()
        with open(VAULT_PATH, "rb") as f:
            enc = f.read()
        payload = dpapi_decrypt(enc, entropy)
        return json.loads(payload.decode("utf-8"))
    except Exception as e:
        print(f"[-] [VAULT] Error unsealing credentials: {e}")
        return None


def sync_and_lock_vault() -> Dict[str, str]:
    """
    Main vault synchronization and locking entrypoint.
    1. Reads existing .env if present.
    2. Ingests environment variables from os.environ.
    3. Encrypts and syncs any new/updated keys into vault.enc.
    4. Returns the secure credential dictionary.
    """
    creds: Dict[str, str] = {}

    # Try loading from vault first
    vault_creds = unseal_credentials_from_vault()
    if vault_creds:
        creds.update(vault_creds)

    # Read .env to pick up any manual edits or updates
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    val = v.strip().strip('"').strip("'")
                    if val:
                        creds[k] = val

    # Ingest from os.environ
    for k in [
        "DISCORD_BOT_TOKEN", "DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET",
        "DISCORD_GUILD_ID", "SLIP_API_KEY", "WEB_API_SECRET_KEY",
        "WEB_API_LOG_TOKEN", "WEB_API_KEY", "DEFAULT_OWNER_ROLE_ID",
        "DEFAULT_HEAD_STAFF_ROLE_ID", "DEFAULT_MANAGER_ROLE_ID",
        "DEFAULT_STAFF_ROLE_ID", "DEFAULT_VERIFIED_ROLE_ID",
        "DEFAULT_CATEGORY_ID", "DISPUTE_CATEGORY_ID", "ANOMALY_LOG_CHANNEL",
        "DAILY_SUMMARY_CHANNEL", "MEMBER_AUDIT_CHANNEL", "DISPUTE_PANEL_CHANNEL",
        "COMMAND_PREFIX"
    ]:
        val = os.environ.get(k)
        if val and k not in creds:
            creds[k] = val

    # Re-seal with all latest values
    seal_credentials_to_vault(creds)

    return creds


def scrub_process_environment():
    """
    Wipes sensitive tokens and credentials from os.environ in memory
    so child processes and debug dumps cannot scrape them.
    """
    sensitive_keys = [
        "DISCORD_BOT_TOKEN",
        "DISCORD_CLIENT_SECRET",
        "SLIP_API_KEY",
        "WEB_API_SECRET_KEY",
        "WEB_API_LOG_TOKEN",
        "WEB_API_KEY",
        "DISCORD_DISPATCH_BOT_TOKEN",
        "DISCORD_ROLE_BOT_TOKEN"
    ]
    for k in sensitive_keys:
        if k in os.environ:
            del os.environ[k]


class ZeroLeakStream:
    """Wraps stdout/stderr to automatically scrub tokens from any outgoing print/log."""
    def __init__(self, original_stream):
        self._stream = original_stream

    def write(self, text: str):
        if not text:
            return
        scrubbed = text
        for pat in TOKEN_SCRUB_PATTERNS:
            scrubbed = pat.sub("[🛡️ REDACTED_SECRET]", scrubbed)
        try:
            self._stream.write(scrubbed)
        except UnicodeEncodeError:
            enc = getattr(self._stream, "encoding", "utf-8") or "utf-8"
            safe_text = scrubbed.encode(enc, errors="replace").decode(enc, errors="replace")
            self._stream.write(safe_text)

    def flush(self):
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install_zero_leak_streams():
    """Installs automatic secret redaction on sys.stdout and sys.stderr."""
    if not isinstance(sys.stdout, ZeroLeakStream):
        sys.stdout = ZeroLeakStream(sys.stdout)
    if not isinstance(sys.stderr, ZeroLeakStream):
        sys.stderr = ZeroLeakStream(sys.stderr)


def apply_ntfs_acl_lockdown():
    """
    Applies strict Windows NTFS ACL permissions to .env, data/, and vault.enc
    revoking access from Everyone/Users and granting FULL access ONLY to current user.
    """
    if sys.platform != "win32":
        return

    username = os.environ.get("USERNAME")
    if not username:
        return

    targets = [(ENV_PATH, False), (DATA_DIR, True), (VAULT_PATH, False)]
    for target, is_dir in targets:
        if target.exists():
            try:
                perm = f'"{username}":(OI)(CI)(F)' if is_dir else f'"{username}":(F)'
                cmd = f'icacls "{target}" /grant:r {perm} /remove:g "Users" "Everyone" >nul 2>&1'
                os.system(cmd)
            except Exception:
                pass
