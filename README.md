# 💎 SC-HUB Client Service & Work-Allocation Ticket Bot (SC-Script-Bot)
### ระบบบริหารจัดการงานแยกลูกค้า 3 แผนก, ตรวจสลิปอัตโนมัติ และเปิดตั๋วอัจฉริยะระดับองค์กร

![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?logo=python)
![Discord.py](https://img.shields.io/badge/Discord.py-v2.x-5865F2?logo=discord)
![License](https://img.shields.io/badge/License-Commercial%20Proprietary-gold)
![Status](https://img.shields.io/badge/Production-Ready-success)

---

## 🌟 ภาพรวมระบบ (Executive Overview)

**SC-HUB (SC-Script-Bot)** คือระบบบอท Discord สำหรับร้านค้า ผู้ให้บริการ และธุรกิจออนไลน์ ออกแบบมาเพื่อแก้ไขปัญหาความยุ่งเหยิงในการรับออเดอร์ การแย่งงานของแอดมิน การปลอมแปลงสลิป และการหลุดหายของประวัติการสนทนา 

บอทตัวนี้ทำงานเป็น **Client Portal** ระดับพรีเมียม ช่วยคัดกรองผู้ใช้จริงด้วยระบบ CAPTCHA, แยกหมวดหมู่ความต้องการของลูกค้าออกเป็น 3 แผนกหลักอย่างเป็นสัดส่วน, มีระบบ **Atomic Mutex Claim** ที่การันตีว่าแอดมินรับลูกค้าได้ทีละคนโดยไม่มีการแย่งงานชนกัน, ตรวจสอบสลิปผ่าน API ป้องกันการใช้สลิปซ้ำ และบันทึกประวัติการแชททั้งหมดเป็นไฟล์ HTML สวยงามส่งเข้าห้อง Audit Log อัตโนมัติ

---

## 🚀 จุดเด่นและฟังก์ชันการทำงานหลัก (Key Capabilities)

### 1. 🔒 Anti-Bot Visual CAPTCHA Gatekeeper (โคลนระบบต้นฉบับ 100%)
* แผงยืนยันตัวตน `PAYOMBØYZ Verification` พร้อมปุ่ม `[ ยืนยันตัวตน ]` สีเขียว
* สร้างภาพตัวอักษร 5 ตัวสุ่มแบบ Procedural บนหน่วยความจำด้วย `Pillow (PIL)` โดยไม่ต้องพึ่งพาไฟล์ Font ภายนอก
* ใส่เส้นรบกวน (Distortion Lines) และ Noise Particles เพื่อป้องกันโปรแกรม OCR / Bot ดักจับ
* ส่งแบบ **Ephemeral Message** (เห็นเฉพาะผู้กด) ป้องกันการส่องคำตอบ มีอายุ 5 นาที
* เมื่อตอบถูกผ่าน Modal ระบบจะมอบบทบาท `@Verified` ให้อัตโนมัติ

### 2. 🗂️ Dynamic Category Router (แยก 3 แผนกอิสระ)
* แผงเลือกหมวดหมู่บริการ 3 สายงานหลัก:
  - 🎮 **ห้องเติมเกมส์ (Game Topup):** เติมเกมออนไลน์, Robux, บัตรเติมเงิน
  - 📜 **ห้องซื้อขายสคริปต์ (Script Hub):** สคริปต์ Roblox Luau, บัตร VVIP, สคริปต์ฟาร์ม
  - 🌐 **ห้องรับทำ Website (Web & Bot):** รับทำเว็บไซต์, Web Application, Discord Bot
* **Role Isolation:** ลูกค้าที่เลือกแผนกใด จะได้รับบทบาทของแผนกนั้น และมองเห็นเฉพาะห้องในแผนกนั้นเท่านั้น เพื่อความเป็นระเบียบและไม่สับสน

### 3. ⚡ Single-Admin Mutex Claim Lobby (ป้องกันแอดมินแย่งงาน 100%)
* ในแต่ละแผนก มีแผงสำหรับลูกค้ากดปุ่ม `[ 🔔 เรียกแอดมิน ]` (พร้อม Cooldown 60 วินาที ป้องกันสแปม)
* ระบบส่งการ์ดแจ้งเตือนพร้อม Ping Role ทีมงานประจำแผนกนั้นทันที
* **Atomic Concurrency Mutex Lock:** ทีมงานกดปุ่ม `[ ⚡ รับลูกค้า (Claim) ]` ได้เพียง **คนเดียวเท่านั้น** 
* แอดมินคนที่กดช้ากว่า แม้เพียงเสี้ยววินาที ระบบจะปฏิเสธและขึ้นข้อความแจ้งเตือนทันที ป้องกันการเปิดห้องตั๋วซ้ำซ้อน

### 4. 🚪 Private Ticket Room Provisioning
* เมื่อแอดมินกดรับงาน บอทจะสร้างห้อง Text Channel ส่วนตัวให้ทันที
* **สิทธิ์การเข้าถึง (Permission Overwrites):**
  - มีเพียง **ลูกค้า** + **แอดมินคนที่กดรับงาน** + **@Owner (Bypass)** เท่านั้นที่เข้าถึงได้
  - แอดมินคนอื่นหรือสมาชิกคนอื่นในเซิร์ฟเวอร์จะถูกล็อกไม่ให้เห็นห้องนี้ 100%

### 5. 💳 Slip Verification API & Dual Kanban Progress Tracker
* ปุ่ม **`[ 💳 กดเพื่อชำระเงิน ]`** ในตั๋ว รองรับการกรอกเลขอ้างอิงสลิปหรือแนบภาพสลิปโอนเงิน
* เชื่อมต่อ API ตรวจสลิป (EasySlip, SlipOK หรือ Custom REST API)
* **Anti-Replay Ledger:** ตรวจสอบ Hash/Ref ของสลิปในฐานข้อมูล SQLite หากพบสลิปเดิมที่เคยใช้ไปแล้ว ระบบจะบล็อกทันที
* **กระดานติดตามสถานะงาน 2 ฝั่ง (Dual-Track Panel):**
  - 🛠️ **ฝั่งแอดมิน:** เมนู Dropdown ปรับสถานะงาน 5 สเต็ป (`⏳ รอคิว` ➔ `🚀 เริ่มต้น` ➔ `⚙️ ดำเนินการ` ➔ `🔍 ตรวจงาน` ➔ `✅ เสร็จสิ้น`)
  - 👤 **ฝั่งลูกค้า:** แถบความคืบหน้ากราฟิกเรียลไทม์ `[ 🟩🟩🟩⬜⬜ ] 60%` พร้อม 2 ปุ่มสำคัญ:
    - `[ 🚨 เรียก Owner (แจ้งปัญหา) ]` สำหรับแจ้งเหตุฉุกเฉินหรือข้อพิพาท
    - `[ 🎉 ได้รับสินค้าเรียบร้อยแล้ว ]` พร้อม Modal ยืนยันป้องกันการกดพลาด

### 6. 📡 Dual-Logging Pipeline & Automatic Cleanup
* **Log 1 (External Web API):** ยิงข้อมูลสรุปการจ้างงานแบบ Asynchronous JSON ไปยัง Website API ของคุณ (Discord ID ลูกค้า, ID แอดมิน, สลิป, ยอดเงิน)
* **Log 2 (Enforced Audit Channel):** ดึงประวัติการแชททั้งหมด แปลงเป็นไฟล์ **Standalone HTML5 Transcript** ดีไซน์ Discord Dark Mode แนบส่งเข้าห้อง Audit Log Channel ที่บังคับเลือกไว้ตั้งแต่ตั้งค่า
* ส่งสำเนา Transcript เข้า DM ของลูกค้าอัตโนมัติ
* ลบห้องตั๋วทิ้งอย่างปลอดภัยหลังจบงาน 5 วินาที

---

## 📁 โครงสร้างโปรเจกต์ (Project Architecture)

```
SC-Script-Bot/
├── ARCHITECT.md             # สถาปัตยกรรมระบบ Flowchart และ Concurrency State Machine
├── HOWTO.md                 # คู่มือการติดตั้งและใช้งานฉบับจับมือทำสำหรับผู้ซื้อ
├── README.md                # เอกสารแนะนำระบบฉบับเต็ม
├── .env                     # ไฟล์เก็บค่า Config และ Tokens ประจำเครื่อง
├── .env.example             # ไฟล์ตัวอย่างสำหรับการตั้งค่า
├── config.py                # ระบบโหลดค่า Environment และ Constants
├── database.py              # SQLite Async DB Handler + Mutex Claim + Slip Ledger
├── captcha_engine.py        # เอนจินเจนภาพ CAPTCHA ด้วย Pillow (Anti-OCR)
├── slip_verifier.py         # โมดูลตรวจสลิปผ่าน API + ป้องกันสลิปซ้ำ
├── transcript.py            # เอนจินแปลงประวัติแชทเป็นไฟล์ HTML5 พรีเมียม
├── user_service.py          # 🌐 userService: API เชื่อมต่อเว็บไซต์หลัก (Profile/Sync/Claim/Audit)
├── web_logger.py            # บริการส่ง Webhook สรุปผลเข้า Website API (เรียกผ่าน userService)
├── views/
│   ├── __init__.py
│   ├── verify_view.py       # แผงยืนยันตัวตน Captcha + Modal กรอกคำตอบ
│   ├── category_view.py     # แผงเลือก 3 แผนกงาน + Role Isolation
│   ├── lobby_view.py        # แผงเรียกลูกค้า + ปุ่มรับงาน Mutex Claim
│   ├── ticket_view.py       # ปุ่มในตั๋ว (ชำระเงิน, ปิดตั๋ว, สะกิดทีมงาน)
│   └── process_view.py      # กระดานสถานะ 5 ขั้นตอน + ลูกค้าคอนเฟิร์มรับของ
├── bot.py                   # ตัวรันบอทหลัก พร้อม Slash Commands 13 คำสั่ง
├── requirements.txt         # รายการแพ็กเกจ Python ที่ต้องใช้
└── start_bot.bat            # สคริปต์คลิกเดียวรันบอทบน Windows
```

---

## 🛠️ รายการคำสั่ง Slash Commands ทั้งหมด (13 คำสั่ง)

ระบบถูกออกแบบมาให้ควบคุมและปรับแต่งได้ทุกส่วนผ่าน Discord UI โดยไม่ต้องแก้ไขโค้ด:

| คำสั่ง (Command) | สิทธิ์ที่ต้องใช้ | คำอธิบายการทำงาน |
|---|---|---|
| `/setup_dispatch_system` | Administrator | **Wizard ติดตั้งระบบรอบเดียวจบ** (วางแผง Verify, แผงเลือกแผนก, และกำหนดห้อง Log) |
| `/setup_lobby_panel` | Administrator | ส่งแผงล็อบบี้เรียกลูกค้า/รับงาน เข้าห้องประจำแผนก (`game`, `script`, `web`) |
| `/panel_send` | Administrator | ส่งแผงควบคุมเดี่ยว (`verify` หรือ `category`) ไปยังห้องใดก็ได้ตามต้องการ |
| `/dispatch_view_config` | Administrator | **ดูการตั้งค่าทั้งหมดของเซิร์ฟเวอร์แบบการ์ดเดียว** (ยศ, ห้อง Log, หมวดหมู่, APIs) |
| `/config_apis` | Administrator | ปรับเปลี่ยน Web API URL, Token, และ Slip API URL/Key แบบสดๆ ไม่ต้องรีสตาร์ทบอท |
| `/config_roles` | Administrator | กำหนดหรือเปลี่ยนยศ Verified, Owner, Staff ส่วนกลาง และทีมงานเฉพาะ 3 แผนก |
| `/config_channels` | Administrator | เปลี่ยนห้อง Transcript Audit Log หรือหมวดหมู่ Category สร้างตั๋ว |
| `/ticket_add_user` | Manage Channels | เชิญสมาชิกหรือทีมงานเพิ่มเติมเข้ามาในห้องตั๋วส่วนตัว |
| `/ticket_remove_user` | Manage Channels | นำสมาชิกออกจากห้องตั๋วส่วนตัว |
| `/ticket_force_close` | Manage Channels | [แอดมิน] บังคับปิดตั๋วและประมวลผล Dual Logging ทันที |
| `/test_apis` | Administrator | **ทดสอบการเชื่อมต่อ API ทั้งสองระบบ** พร้อมแสดงค่าความหน่วง (Latency ms) |
| `/dispatch_status` | Administrator | ตรวจสอบสถิติเชิงลึก (ตั๋วสะสม, ตั๋วที่เปิดอยู่, สลิปที่ตรวจแล้ว, ยอดเงินรวม) |
| `/sync_commands` | Administrator | บังคับซิงค์คำสั่ง Slash Command ทั้งหมดกับ Discord ใหม่ทันที |

---

## 💻 วิธีการติดตั้งและรันบอท (Quick Start)

### 1. ติดตั้ง Dependencies
```bash
py -3.12 -m pip install -r requirements.txt
```

### 2. ตั้งค่าไฟล์ `.env`
เปิดไฟล์ `.env` แล้วระบุข้อมูลของคุณ:
```ini
DISCORD_BOT_TOKEN="YOUR_BOT_TOKEN"
DISCORD_CLIENT_ID="1548921066833838080"
DISCORD_GUILD_ID="1549398019970179152"

DEFAULT_STAFF_ROLE_ID="1549535328753164418"
DEFAULT_OWNER_ROLE_ID="1549535328753164418"
DEFAULT_CATEGORY_ID="1549803476094029834"

WEB_API_LOG_URL="https://payomboyzcreative.online/api/dispatch-logs"
SLIP_API_URL="https://api.easyslip.com/v1/verify"
SLIP_API_KEY="YOUR_SLIP_API_KEY"
```

### 3. เริ่มต้นรันบอท
ดับเบิลคลิกไฟล์ **`start_bot.bat`** บน Windows หรือรันผ่านเทอร์มินัล:
```bash
py -3.12 bot.py
```

> 📖 **ต้องการคำแนะนำขั้นตอนอย่างละเอียดแบบจับมือทำ?**  
> ให้อ่านคู่มือฉบับสมบูรณ์ได้ที่ไฟล์ [HOWTO.md](file:///d:/Deobfuscate/SC-Script-Bot/HOWTO.md)

---

## 🔒 มาตรฐานความปลอดภัย (Security Architecture)

1. **Anti-Replay Slip Protection:** ป้องกันการนำสลิปเก่ามาวนใช้ซ้ำ ด้วยการทำดัชนี Unique Ledger ใน SQLite
2. **Atomic Mutex Concurrency:** ป้องกัน Race Condition เมื่อมีแอดมินหลายคนกดรับงานในเสี้ยววินาทีเดียวกัน
3. **Memory Procedural Captcha:** เจนภาพรหัสสุ่มใน Memory Buffer โดยตรง ไม่ทิ้งไฟล์ภาพขยะไว้ในฮาร์ดดิสก์
4. **Isolated Permission Overwrites:** สิทธิ์ห้องตั๋วถูกปิดกั้นจาก `@everyone` อย่างเด็ดขาด มีเพียงลูกค้าและผู้รับงานเท่านั้นที่เข้าถึงได้

---

*💎 SC-HUB Client Service Bot — พัฒนาโดยทีมงาน PAYOMBØYZ สำหรับการใช้งานเชิงพาณิชย์ระดับมืออาชีพ*
