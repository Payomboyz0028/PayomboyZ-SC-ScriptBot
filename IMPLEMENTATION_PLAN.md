# 📋 IMPLEMENTATION & ROLLOUT PLAN
## Project: SC-Script-Bot (PAYOMBØYZ Work Allocation Engine)

แผนดำเนินงานพัฒนาและเปิดใช้งานระบบแบ่งงานและตั๋วอัตโนมัติ 6 สเต็ป

---

## 🧭 แผนการทำงานแบ่งตาม Phase

### Phase 1: Core Foundation & Configuration
- [x] ออกแบบ System Architecture (`ARCHITECT.md`)
- [x] ออกแบบคู่มือและสเปกการติดตั้ง (`README.md`)
- [x] สร้างโครงสร้างโฟลเดอร์ `d:/Deobfuscate/SC-Script-Bot`
- [ ] สร้าง `config.py` จัดการ Environment, Tokens, Channel/Role IDs
- [ ] สร้าง `database.py` สถาปัตยกรรม SQLite WAL Mode พร้อม Async Connection Pool & Transaction Guards

### Phase 2: Anti-Bot CAPTCHA Gatekeeper
- [ ] สร้าง `captcha_engine.py` ใช้ Pillow เจนภาพสุ่ม 5 ตัวอักษร พร้อมเส้นรบกวน (Distort Lines) และ Noise
- [ ] สร้าง `views/verify_view.py` โคลน UI จากลิงก์ Discord ต้นฉบับ:
  - Embed: `PAYOMBØYZ Verification`
  - Button: `[ ยืนยันตัวตน ]` (สีเขียว)
  - Ephemeral Message: ภาพ Captcha + ปุ่ม `[ ยืนยันคำตอบ ]` (สีน้ำเงิน)
  - Modal: กรอกรหัส Captcha 5 ตัวอักษร พร้อมตรวจคำตอบและแจกยศ `@Verified`

### Phase 3: Category Router & Role Isolation Hub
- [ ] สร้าง `views/category_view.py`:
  - 🎮 ห้องเติมเกมส์
  - 📜 ห้องซื้อขายสคริปต์
  - 🌐 ห้องรับทำ Website
- [ ] จัดการ Role Isolation (มอบยศให้มองเห็นเฉพาะห้องในสายงานที่เลือก)

### Phase 4: Department Lobby & Single-Admin Mutex Claim
- [ ] สร้าง `views/lobby_view.py`:
  - ฝ่ายลูกค้า: ปุ่ม `[ 🔔 เรียกแอดมิน ]` พร้อม Rate-limit Cooldown
  - ฝ่ายแอดมิน: การ์ดแจ้งเตือนพร้อมปุ่ม `[ ⚡ รับลูกค้า ]`
  - Atomic Mutex Lock: การันตีแอดมินรับได้คนเดียว ใครกดช้ากว่าจะถูกปฏิเสธทันที

### Phase 5: Ticket Provisioning, Slip API & Process Tracker
- [ ] สร้าง `views/ticket_view.py` คุมสิทธิ์ห้อง Private Text Channel (ลูกค้า + แอดมินที่รับ + Owner เท่านั้น)
- [ ] สร้าง `slip_verifier.py` ระบบตรวจสลิปผ่าน API + บันทึก Hash ใน SQLite กันสลิปซ้ำ
- [ ] สร้าง `views/process_view.py` ระบบติดตามสถานะงาน 2 ฝั่ง:
  - ฝั่งแอดมิน: อัปเดต 5 สเต็ป (`รอคิว`, `เริ่มต้น`, `กำลังดำเนินการ`, `ขั้นตอนสุดท้าย`, `เสร็จสิ้น`)
  - ฝั่งลูกค้า: Real-time status + ปุ่ม `[ 🚨 เรียก Owner ]` + ปุ่ม `[ 🎉 ได้รับสินค้าเรียบร้อยแล้ว ]` พร้อมยืนยัน

### Phase 6: Dual Logging Engine & Channel Cleanup
- [ ] สร้าง `web_logger.py` ส่ง JSON สรุปการจ้างผ่าน Asynchronous HTTP Request ไปยัง Website ของ dj
- [ ] สร้าง `transcript.py` ดึง Chat History แปลงเป็นไฟล์ HTML5 Dark Theme
- [ ] บันทึก Transcript และส่งเข้า Enforced Audit Log Channel พร้อมนับถอยหลังลบห้องตั๋ว

### Phase 7: Bot Integration, Slash Commands & Startup Automation
- [ ] สร้าง `bot.py` รวบรวม Persistent Views ทั้งหมด รองรับ Bot Restart ไม่หลุด State
- [ ] เพิ่มคำสั่ง `/setup_dispatch_system` สำหรับตั้งค่า Role, หมวดหมู่ และห้อง Log แบบเบ็ดเสร็จ
- [ ] สร้าง `start_bot.bat` และ `requirements.txt`
- [ ] ทดสอบรันและตรวจสอบ Syntax ทุกโมดูล
