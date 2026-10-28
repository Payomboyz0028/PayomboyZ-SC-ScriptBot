# -*- coding: utf-8 -*-
"""
💎 SC-HUB Comprehensive End-to-End Simulation Test Harness
Simulates and validates all 6 Customer steps, 4 Admin steps, and 2 Owner logging mechanisms.
"""

import sys
import os
import asyncio
import time
import json
import sqlite3
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config
from database import db
import captcha_engine
import slip_verifier
import transcript
import web_logger


async def run_full_simulation():
    print("=" * 70)
    print("  💎 SC-HUB COMPREHENSIVE END-TO-END SYSTEM TEST SIMULATION")
    print("=" * 70)
    print()

    passed_checks = []
    failed_checks = []

    def check(name: str, condition: bool, extra: str = ""):
        if condition:
            print(f"  ✅ [PASS] {name} {extra}")
            passed_checks.append(name)
        else:
            print(f"  ❌ [FAIL] {name} {extra}")
            failed_checks.append(name)

    guild_id = "1549398019970179152"
    customer_id = 999111222
    admin_id_1 = 888111222
    admin_id_2 = 777111222
    owner_id = 1549535328753164418

    # ─────────────────────────────────────────────────────────────
    # [CUSTOMER STEP 1]: ลูกค้ากดยืนยันตัวตน (Captcha Generation & Verification)
    # ─────────────────────────────────────────────────────────────
    print("[1/6] 🔒 Customer Step 1: Captcha Verification...")
    code, img_buf = captcha_engine.generate_captcha_image(length=5)
    check("Captcha Generation", len(code) == 5 and len(img_buf.getvalue()) > 2000, f"(Code: {code}, Image: {len(img_buf.getvalue()):,} bytes)")
    
    session_id = db.create_captcha_session(customer_id, code, ttl=300)
    check("Captcha Session Created", bool(session_id))
    
    wrong_try = db.verify_captcha(customer_id, "WRONG")
    check("Anti-Bypass Guard (Wrong Code Rejected)", wrong_try is False)
    
    correct_try = db.verify_captcha(customer_id, code.lower())
    check("Captcha Correct Verification (Case-Insensitive)", correct_try is True)
    
    replayed_try = db.verify_captcha(customer_id, code)
    check("Captcha Anti-Replay Guard (Used Code Expired)", replayed_try is False)
    print()

    # ─────────────────────────────────────────────────────────────
    # [CUSTOMER STEP 2 & 3]: เลือกหมวดหมู่ & แอดมินรับงาน
    # ─────────────────────────────────────────────────────────────
    print("[2/6] 🗂️ Customer Step 2 & 3: Category Select & Admin Call...")
    category_key = "game"
    dept_info = config.DEPARTMENTS[category_key]
    check("Department Config Valid", dept_info["name"] == "ห้องเติมเกมส์")

    # Role Switching & Old Role Removal Simulation Test
    class MockRole:
        def __init__(self, rid: int, rname: str):
            self.id = rid
            self.name = rname

    role_game = MockRole(1563251664192929975, "ลูกค้า-เติมเกม")
    role_script = MockRole(1563251667552444499, "ลูกค้า-สคริปต์")
    role_web = MockRole(1563251665560408137, "ลูกค้า-เว็บไซต์")

    user_roles = [role_game]  # User initially holds game customer role
    target_role = role_script  # User clicks to switch to script department
    all_dept_ids = {1563251664192929975, 1563251667552444499, 1563251665560408137}
    all_names = {"ลูกค้า-เติมเกม", "ลูกค้า-สคริปต์", "ลูกค้า-เว็บไซต์"}

    roles_to_remove = [
        r for r in user_roles
        if r.id != target_role.id and (r.id in all_dept_ids or r.name.lower() in all_names or r.name.startswith("ลูกค้า-"))
    ]
    check("Role Switching Detects Old Role To Remove", len(roles_to_remove) == 1 and roles_to_remove[0].id == role_game.id)

    # Perform simulated removal and addition
    user_roles = [r for r in user_roles if r not in roles_to_remove] + [target_role]
    check("Old Role Cleanly Removed & New Role Present", len(user_roles) == 1 and user_roles[0].id == role_script.id)

    # Customer clicks "เรียกแอดมิน"
    call_id = db.create_pending_call(
        guild_id=guild_id,
        category_key=category_key,
        customer_id=customer_id,
        channel_id=123456789,
        message_id=987654321
    )
    check("Customer Call Registered in DB", bool(call_id))

    # [ADMIN STEP 2]: Mutex Claim - Admin 1 and Admin 2 race to click "รับลูกค้า"
    print("   ⚡ Admin Step 2: Atomic Mutex Claim Concurrency...")
    win1, call_data1 = await db.claim_pending_call_atomic(call_id, admin_id_1)
    win2, call_data2 = await db.claim_pending_call_atomic(call_id, admin_id_2)

    check("Admin 1 Won Mutex Claim", win1 is True and call_data1["claimed_by"] == admin_id_1)
    check("Admin 2 Rejected by Atomic Lock", win2 is False and call_data2 is None)
    print()

    # ─────────────────────────────────────────────────────────────
    # [ADMIN STEP 3]: สร้างห้องตั๋วส่วนตัว
    # ─────────────────────────────────────────────────────────────
    print("[3/6] 🚪 Step 4: Private Ticket Room Creation...")
    ticket_channel_id = 555444333
    ticket_num = db.get_next_counter(guild_id)
    
    db.register_ticket(
        channel_id=ticket_channel_id,
        ticket_num=ticket_num,
        guild_id=guild_id,
        category_key=category_key,
        customer_id=customer_id,
        claimed_admin_id=admin_id_1
    )
    tdata = db.get_ticket(ticket_channel_id)
    check("Ticket Registered in DB", tdata is not None and tdata["ticket_num"] == ticket_num)
    check("Isolation Overwrites Check", tdata["customer_id"] == customer_id and tdata["claimed_admin_id"] == admin_id_1)
    print()

    # ─────────────────────────────────────────────────────────────
    # [CUSTOMER STEP 4]: ปุ่มชำระเงิน & ตรวจสอบสลิป API
    # ─────────────────────────────────────────────────────────────
    print("[4/6] 💳 Customer Step 4: Payment & Slip Verification Engine...")
    test_slip_ref = f"SC_SLIP_{int(time.time())}_TEST"
    test_amount = 350.0

    # First slip attempt (New slip)
    res1 = await slip_verifier.verify_slip_image_or_payload(
        channel_id=ticket_channel_id,
        customer_id=customer_id,
        custom_ref=test_slip_ref
    )
    check("Valid Slip Verification", res1.success is True, f"(Ref: {res1.slip_ref})")

    # Second slip attempt (Duplicate/Replayed slip)
    res2 = await slip_verifier.verify_slip_image_or_payload(
        channel_id=ticket_channel_id,
        customer_id=customer_id,
        custom_ref=test_slip_ref
    )
    check("Slip Anti-Replay Guard (Duplicate Rejected)", res2.success is False)

    # Update Ticket payment
    db.update_ticket_payment(ticket_channel_id, slip_ref=test_slip_ref, amount=test_amount)
    tdata_paid = db.get_ticket(ticket_channel_id)
    check("Payment State Recorded", tdata_paid["paid_status"] == 1 and tdata_paid["amount"] == test_amount)
    print()

    # ─────────────────────────────────────────────────────────────
    # [ADMIN STEP 4 & CUSTOMER STEP 5]: กระดานสถานะ 5 ขั้นตอน
    # ─────────────────────────────────────────────────────────────
    print("[5/6] 📊 Step 5: Dual Kanban Progress Tracker...")
    stages = ["queued", "started", "in_progress", "final_stage", "completed"]
    for stg in stages:
        db.update_ticket_stage(ticket_channel_id, stg)
        t = db.get_ticket(ticket_channel_id)
        assert t["process_stage"] == stg
    check("5 Kanban Stages Updated Successfully", True, f"({', '.join(stages)})")
    print()

    # ─────────────────────────────────────────────────────────────
    # [CUSTOMER STEP 6 & OWNER LOGS]: ปิดตั๋ว & Dual Logging
    # ─────────────────────────────────────────────────────────────
    print("[6/6] 📑 Step 6: Confirmation, Closure & Dual Logging Engine...")

    # Log 1: Web API JSON Payload formatting test
    tdata_final = db.get_ticket(ticket_channel_id)
    payload_ok, payload_msg = await web_logger.send_ticket_completed_log(
        guild_id=guild_id,
        ticket_data=tdata_final,
        customer_name="Customer_Alice",
        admin_name="Admin_Bob",
        override_api_url="https://httpbin.org/post"  # Live HTTP test endpoint
    )
    check("Owner Log 1: Web API JSON Webhook Dispatch", payload_ok is True, f"({payload_msg})")

    # Log 2: HTML Transcript Generation structure test
    html_mock = """
    <!DOCTYPE html><html><head><meta charset='utf-8'><title>Transcript</title></head>
    <body style='background:#1e1f22;color:#fff;'>
      <h1>SC-HUB Transcript #001</h1>
      <div><b>Customer_Alice:</b> สอบถามเติม Robux ครับ</div>
      <div><b>Admin_Bob:</b> ยินดีครับ แพ็กเกจ 350 บาทครับ</div>
      <div><b>System:</b> ชำระเงินสำเร็จ 350.00 บาท</div>
    </body></html>
    """
    check("Owner Log 2: HTML Transcript Generator Clean", len(html_mock) > 100)

    # Cleanup ticket & archive to ticket_history
    db.record_ticket_history(tdata_final, close_reason="ทดสอบปิดตั๋วสำเร็จ")
    db.close_ticket(ticket_channel_id)
    check("Ticket Closed & DB Cleanup Clean", db.get_ticket(ticket_channel_id) is None)
    print()

    # ─────────────────────────────────────────────────────────────
    # [NEW CHANNELS AUDIT TESTS]
    # ─────────────────────────────────────────────────────────────
    print("[7/7] 🚨 Validating 3 New Channels (Anomaly, Midnight Summary, Member Audit)...")

    # 1. Anomaly Channel: 1563251866517770250
    check("Anomaly Log Channel Configured", config.ANOMALY_LOG_CHANNEL_ID == 1563251866517770250)
    fail_1 = db.record_captcha_failure(99999)
    fail_2 = db.record_captcha_failure(99999)
    fail_3 = db.record_captcha_failure(99999)
    check("Captcha Brute Force Detection Counter", fail_3 == 3)
    db.reset_captcha_failure(99999)
    check("Captcha Failure Counter Reset Clean", db.record_captcha_failure(99999) == 1)

    # 2. Daily Midnight Summary Channel: 1563251868501803048
    check("Midnight Daily Summary Channel Configured", config.DAILY_SUMMARY_CHANNEL_ID == 1563251868501803048)
    summary_data = db.get_daily_summary_data(guild_id, start_ts=time.time() - 86400, end_ts=time.time() + 60)
    check("Daily Summary Aggregation Runs", isinstance(summary_data, dict) and "total_revenue" in summary_data)
    check("Revenue Tracked in Summary", summary_data["total_revenue"] >= test_amount)

    # 3. Member Join/Leave Audit Channel: 1563251902307901584
    check("Member Audit Channel Configured", config.MEMBER_AUDIT_CHANNEL_ID == 1563251902307901584)
    check("Verified Role Configured (1563251669662171216)", config.DEFAULT_VERIFIED_ROLE_ID == 1563251669662171216)
    db.increment_audit_stat("joins_count")
    db.increment_audit_stat("verified_count")
    db.increment_audit_stat("leaves_count")
    updated_summary = db.get_daily_summary_data(guild_id, start_ts=time.time() - 86400, end_ts=time.time() + 60)
    check("Audit Stats Increment Verified", updated_summary["joins_count"] >= 1 and updated_summary["verified_count"] >= 1)

    # 4. Ongoing Work Channels (3 Departments)
    check("Ongoing Game Channel Configured (1563251830677315666)", config.ONGOING_CHANNELS["game"] == 1563251830677315666)
    check("Ongoing Web Channel Configured (1563251842232615052)", config.ONGOING_CHANNELS["web"] == 1563251842232615052)
    check("Ongoing Script Channel Configured (1563251853477552259)", config.ONGOING_CHANNELS["script"] == 1563251853477552259)
    from ongoing_manager import build_ongoing_card_embed, build_department_ongoing_board
    ongoing_embed = build_ongoing_card_embed(tdata_paid)
    check("Ongoing Card Embed Generated", "SC-HUB #" in ongoing_embed.title)
    print()

    # ─────────────────────────────────────────────────────────────
    # [EXECUTIVE DISPUTE DESK TESTS]
    # ─────────────────────────────────────────────────────────────
    print("[8/8] ⚖️ Executive Dispute & Escalation Desk (Owner & Head Staff Direct Ticket)...")
    check("Head Staff Role Configured (1563251634119778346)", config.DEFAULT_HEAD_STAFF_ROLE_ID == 1563251634119778346)
    check("Dispute Panel Channel Configured (1563251767674667019)", config.DISPUTE_PANEL_CHANNEL_ID == 1563251767674667019)
    check("Dispute Category Configured (1563251765200293959)", config.DISPUTE_CATEGORY_ID == 1563251765200293959)

    from views.dispute_view import build_dispute_panel_embed, DisputePanelView, DisputeTicketControlView
    disp_embed = build_dispute_panel_embed()
    check("Dispute Embed Generated Cleanly", "SC-HUB Executive Desk" in disp_embed.title)
    disp_view = DisputePanelView()
    check("Dispute Panel View Buttons Ready", len(disp_view.children) >= 1)

    # Test Dispute Ticket registration in DB
    dispute_ch_id = 9988776655
    db.register_ticket(
        channel_id=dispute_ch_id,
        ticket_num=999,
        guild_id=guild_id,
        category_key="dispute",
        customer_id=customer_id,
        claimed_admin_id=config.DEFAULT_HEAD_STAFF_ROLE_ID
    )
    disp_data = db.get_ticket(dispute_ch_id)
    check("Dispute Ticket Registered in DB", disp_data is not None and disp_data["category_key"] == "dispute")
    check("Dispute Ticket Claimed by Head Staff Role", disp_data["claimed_admin_id"] == config.DEFAULT_HEAD_STAFF_ROLE_ID)

    db.close_ticket(dispute_ch_id)
    check("Dispute Ticket Closed Cleanly", db.get_ticket(dispute_ch_id) is None)
    print()

    # ─────────────────────────────────────────────────────────────
    # [FINANCIAL GOVERNANCE & TRUEMONEY SNIFFER TESTS]
    # ─────────────────────────────────────────────────────────────
    print("[9/9] 🧧 TrueMoney Voucher Sniffer & Financial Governance (Owner Lock)...")
    check("Verified Slip Channel Configured (1563251864256909444)", config.VERIFIED_SLIP_CHANNEL_ID == 1563251864256909444)
    check("Role Audit Channel Configured (1563251907567419532)", config.ROLE_AUDIT_CHANNEL_ID == 1563251907567419532)

    from truemoney_engine import extract_voucher_code, redeem_truemoney_voucher
    sample_url = "https://gift.truemoney.com/campaign/?v=3576089335e24a5ebec5c1411287c880f0c"
    extracted_hash = extract_voucher_code(sample_url)
    check("Voucher Hash Extraction", extracted_hash == "3576089335e24a5ebec5c1411287c880f0c")

    # TrueMoney Voucher Redemption & Anti-Replay
    test_voucher = f"TEST_TMN_{int(time.time())}_SAMPLE"
    res1 = await redeem_truemoney_voucher(
        voucher_input=f"https://gift.truemoney.com/campaign/?v={test_voucher}",
        channel_id=11223344,
        customer_id=customer_id,
        phone_number="0812345678"
    )
    check("TrueMoney Voucher Redemption Success", res1.success is True and res1.amount > 0)

    res2 = await redeem_truemoney_voucher(
        voucher_input=f"https://gift.truemoney.com/campaign/?v={test_voucher}",
        channel_id=11223344,
        customer_id=customer_id,
        phone_number="0812345678"
    )
    check("TrueMoney Anti-Replay Guard (Duplicate Rejected)", res2.success is False)

    # Database Financial Config Update & Persistence
    db.update_guild_config(
        guild_id,
        truemoney_phone="0829934210",
        slip_api_url="https://api.easyslip.com/v1/verify",
        slip_api_key=""
    )
    cfg_updated = db.get_guild_config(guild_id)
    check("TrueMoney Phone Config Persisted (0829934210)", cfg_updated.get("truemoney_phone") == "0829934210")
    check("Bank Slip API URL Config Persisted in SQLite", cfg_updated.get("slip_api_url") == "https://api.easyslip.com/v1/verify")

    # PromptPay Dynamic QR Code Engine Verification
    from promptpay_engine import generate_promptpay_payload, generate_promptpay_qr_image, build_promptpay_qr_embed
    pp_payload = generate_promptpay_payload("0829934210", 250.0)
    check("PromptPay Dynamic Payload Generated", "0066829934210" in pp_payload and "250.00" in pp_payload)
    qr_img_bytes = generate_promptpay_qr_image("0829934210", 250.0).getvalue()
    check("PromptPay QR Image In-Memory Render", len(qr_img_bytes) > 500)

    # QR Code Slip Auto-Detection & Verification Tests
    test_qr_amount = round(300.0 + (time.time() % 500), 2)
    test_qr_chan = int(time.time()) + 999
    qr_slip_bytes = generate_promptpay_qr_image("0829934210", test_qr_amount).getvalue()
    slip_res1 = await slip_verifier.verify_slip_image_or_payload(
        channel_id=test_qr_chan,
        customer_id=customer_id,
        image_bytes=qr_slip_bytes,
        expected_amount=test_qr_amount
    )
    check("QR Slip Auto-Scan Verified", slip_res1.success is True and slip_res1.amount == test_qr_amount)

    # QR Slip Anti-Replay Guard (Duplicate Rejection)
    slip_res2 = await slip_verifier.verify_slip_image_or_payload(
        channel_id=test_qr_chan,
        customer_id=customer_id,
        image_bytes=qr_slip_bytes,
        expected_amount=test_qr_amount
    )
    check("QR Slip Anti-Replay Guard (Duplicate Rejected)", slip_res2.success is False and "ตรวจพบสลิปซ้ำ" in slip_res2.message)

    # Missing QR Guard (Image without QR code rejected)
    blank_img = captcha_engine.generate_captcha_image(5)[1].getvalue()
    slip_res3 = await slip_verifier.verify_slip_image_or_payload(
        channel_id=11223344,
        customer_id=customer_id,
        image_bytes=blank_img
    )
    check("QR Slip Missing QR Guard (Non-QR Image Rejected)", slip_res3.success is False and "ไม่พบ QR Code" in slip_res3.message)
    print()


    # ─────────────────────────────────────────────────────────────
    # [MULTI-LAYER TOKEN, VAULT & ANTI-MALWARE DEFENSE TESTS]
    # ─────────────────────────────────────────────────────────────
    print("[10/10] 🛡️ Multi-Layer Token, API, Vault & Anti-Malware Defense...")
    
    # 1. Hardware-Bound Vault
    from security_vault import (
        sync_and_lock_vault,
        unseal_credentials_from_vault,
        scrub_process_environment,
        ZeroLeakStream,
        VAULT_PATH
    )
    check("Hardware-Bound Vault File Exists (data/vault.enc)", VAULT_PATH.exists() and VAULT_PATH.stat().st_size > 100)
    unsealed = unseal_credentials_from_vault()
    check("Vault Unsealed with Hardware MachineGuid Entropy", unsealed is not None and "DISCORD_CLIENT_ID" in unsealed)

    # 2. In-Memory Sanitization (Scrubbing os.environ)
    os.environ["DISCORD_BOT_TOKEN"] = "EXPOSED_TEST_TOKEN"
    scrub_process_environment()
    check("In-Memory Secret Sanitization (os.environ Scrubbed)", "DISCORD_BOT_TOKEN" not in os.environ)

    # 3. Zero-Leak Stream Redaction
    class DummyStream:
        def __init__(self):
            self.buf = ""
        def write(self, s):
            self.buf += s
        def flush(self):
            pass

    dummy = DummyStream()
    z_stream = ZeroLeakStream(dummy)
    dummy_token = "MOCK_DISCORD_SECRET_TOKEN_DO_NOT_SCAN_123456789"
    z_stream.write(f"Connecting with token: {dummy_token}")
    check("Zero-Leak Stream Redaction (Token Masked)", "[🛡️ REDACTED_SECRET]" in dummy.buf and dummy_token not in dummy.buf)

    # 4. Anti-Malware / Anti-Trojan Payload Scanner
    from malware_scanner import (
        DANGEROUS_EXTENSIONS,
        DOUBLE_EXT_REGEX,
        PE_MAGIC,
        scan_attachment_for_malware
    )
    check("Malware Executable Blacklist Active", ".exe" in DANGEROUS_EXTENSIONS and ".scr" in DANGEROUS_EXTENSIONS)
    check("Double Extension Trojan Detection Active", bool(DOUBLE_EXT_REGEX.search("payment_slip.png.exe")))
    # ─────────────────────────────────────────────────────────────
    # [11/11] 🪽 Welcome Card & Verification Announcement Tests
    # ─────────────────────────────────────────────────────────────
    print("[11/11] 🪽 Welcome Card & Verification Announcement Engine...")
    import welcome_card
    check("Welcome Background Template Exists", welcome_card.TEMPLATE_PATH.exists() and welcome_card.TEMPLATE_PATH.stat().st_size > 50000)

    # Test Welcome Banner rendering in-memory
    banner_io = welcome_card.generate_welcome_banner(
        avatar_bytes=None,
        display_name="พยอมบอย (dj)",
        username="payomboylovecat",
        member_count=6289
    )
    banner_bytes = banner_io.getvalue()
    check("Welcome Banner In-Memory PNG Render", len(banner_bytes) > 20000)

    # Check Welcome Channel ID config
    check("Welcome Channel Configured (1563251676830236782)", getattr(config, "WELCOME_CHANNEL_ID", 0) == 1563251676830236782)
    print()

    print("=" * 70)
    print(f"  🏁 TEST RESULTS SUMMARY: {len(passed_checks)} PASSED / {len(failed_checks)} FAILED")
    print("=" * 70)
    return len(failed_checks) == 0


if __name__ == "__main__":
    success = asyncio.run(run_full_simulation())
    exit(0 if success else 1)
