# 🏛️ SYSTEM ARCHITECTURE SPECIFICATION
## Project: PAYOMBØYZ Work-Allocation & Dispatch Ticket Engine (SC-Script-Bot)
**Target Platform:** Discord.py 2.x | Python 3.11+ / 3.12 | SQLite WAL Mode  
**Architecture Author:** PAYOMBØYZ Team  
**Scope:** Multi-department task routing, single-admin claim concurrency, captcha gatekeeper, slip verification API, 5-stage order progression, and dual logging.

---

## 1. High-Level System Overview & Flowchart

```mermaid
flowchart TD
    %% Node Definitions
    User([👤 ลูกค้าใหม่ / Unverified User]) --> Step1[1. Gateway: CAPTCHA Verification]
    Step1 -->|กด 'ยืนยันตัวตน'| CaptchaModal[ส่งภาพ Captcha Distort สุ่ม 5 ตัวอักษร Expire 5m]
    CaptchaModal -->|กรอกถูก| RoleVerified[ได้รับ Role: @Verified]
    CaptchaModal -->|กรอกผิด/หมดอายุ| Step1

    RoleVerified --> Step2[2. Category Router Hub]
    Step2 -->|เลือก เติมเกมส์| RoleDept1[ได้รับ Role: @Dept-Game]
    Step2 -->|เลือก ซื้อสคริปต์| RoleDept2[ได้รับ Role: @Dept-Script]
    Step2 -->|เลือก ทำเว็บไซต์| RoleDept3[ได้รับ Role: @Dept-Web]

    RoleDept1 --> Lobby1[3. Department Lobby: ห้องเติมเกมส์]
    RoleDept2 --> Lobby2[3. Department Lobby: ห้องซื้อขายสคริปต์]
    RoleDept3 --> Lobby3[3. Department Lobby: ห้องรับทำ Website]

    Lobby1 & Lobby2 & Lobby3 --> CustomerCall[👤 ลูกค้ากด: 🔔 เรียกแอดมิน]
    CustomerCall --> StaffNotify[ส่ง Notification Card + Ping Staff Role ของหมวดนั้น]

    StaffNotify --> AdminClaim{แอดมิน / พาร์ทเนอร์ กด: ⚡ รับลูกค้า}
    AdminClaim -->|คนแรกชนะ: Mutex Lock Acquired| TicketCreate[4. สร้าง Private Ticket Room]
    AdminClaim -->|กดช้ากว่า: Lock Failed| ClaimReject[แจ้งเตือน: มีแอดมินรับงานนี้ไปแล้ว!]

    TicketCreate --> TicketOverwrites[ตั้ง Permissions: เฉพาะ ลูกค้า + แอดมินคนที่รับ + Owner]

    TicketOverwrites --> Negotiation[5. สนทนา & ตกลงราคา]
    Negotiation --> PaymentClick[ลูกค้ากดปุ่ม: 💳 ชำระเงิน]
    PaymentClick --> SlipUpload[แนบสลิป / ส่ง QR]
    SlipUpload --> SlipAPI[ระบบตรวจสลิปผ่าน API EasySlip/SlipOK + เช็ค Hash กันซ้ำ]

    SlipAPI -->|สลิปถูกต้อง| ProcessInit[เปิดแผง Process Control Panel]
    SlipAPI -->|สลิปปลอม/ใช้ซ้ำ| SlipFail[แจ้งเตือนสลิปไม่ถูกต้อง] --> PaymentClick

    ProcessInit --> DualTrack[ระบบติดตามงาน 2 ฝั่ง]
    
    subgraph "Dual Track Process"
        AdminPanel[🛡️ ฝั่งแอดมิน: เปลี่ยนสถานะ 5 ขั้น\n⏳รอคิว ➔ 🚀เริ่มต้น ➔ ⚙️ดำเนินการ ➔ 🔍ตรวจงาน ➔ ✅เสร็จสิ้น]
        CustomerPanel[👤 ฝั่งลูกค้า: Real-time Status Mirror\n- ปุ่ม: 🚨 เรียก Owner แจ้งปัญหา\n- ปุ่ม: 🎉 ได้รับสินค้าเรียบร้อยแล้ว]
    end

    DualTrack --> ConfirmReceive[ลูกค้ากดยืนยัน: ได้รับสินค้าเรียบร้อยแล้ว]
    ConfirmReceive --> ConfirmModal[Modal กดยืนยันซ้ำป้องกันพลาด]

    ConfirmModal --> Step6[6. ปิดตั๋ว & Dual Logging Engine]
    
    subgraph "Dual Logging Pipeline"
        Log1[📡 Log 1: ส่ง JSON ไปยัง External Website API\nCustomer ID, Admin ID, Slip Ref, ยอดเงิน, เวลา]
        Log2[📑 Log 2: ส่ง HTML Chat Transcript เข้า Audit Channel ที่บังคับเลือกไว้]
    end

    Step6 --> Log1 & Log2
    Log2 --> PurgeChannel[ลบห้อง Ticket ทิ้งอย่างปลอดภัย]
```

---

## 2. Concurrency & Anti-Race Condition Algorithm (Single Admin Claim Mutex)

### ปัญหาที่ต้องแก้ไข (Race Condition):
เมื่อมีลูกค้ากดเรียกแอดมิน อาจมีแอดมินหรือพาร์ทเนอร์ 2 คนขึ้นไปกดปุ่ม `[ ⚡ รับลูกค้า ]` ในเวลาเสี้ยววินาทีเดียวกัน หากไม่มีกลไก Concurrency Guard บอทจะเปิดห้องตั๋วซ้ำ 2 ห้อง หรือดึงแอดมินทั้ง 2 คนเข้ามาพร้อมกัน ทำให้เกิดความสับสนและแย่งลูกค้า

### อัลกอริทึมแก้ปัญหา (Atomic Compare-And-Swap ใน SQLite):
ระบบใช้คำสั่ง SQL Atomic Update ด้วย Conditional State Check ร่วมกับ `asyncio.Lock` ระดับ In-Memory:

```python
# Pseudo-code / Algorithm Implementation:
async def claim_customer_call(call_id: str, admin_id: int) -> bool:
    async with db_lock:
        # Atomic Update: จะอัปเดตสำเร็จก็ต่อเมื่อสถานะปัจจุบันยังคงเป็น 'waiting' เท่านั้น
        cursor = await db.execute("""
            UPDATE pending_calls 
            SET status = 'claimed', 
                claimed_by = ?, 
                claimed_at = ? 
            WHERE call_id = ? AND status = 'waiting'
        """, (str(admin_id), time.time(), call_id))
        
        await db.commit()
        
        # ถ้ายอดแถวที่ถูกแก้ = 1 แสดงว่าแอดมินคนนี้คือคนแรกที่คว้า Lock ได้
        if cursor.rowcount == 1:
            return True
        # ถ้า = 0 แสดงว่ามีแอดมินท่านอื่นชิงกดไปก่อนแล้ว
        return False
```

**ผลลัพธ์:**
- คนแรก: ได้รับผล `True` -> บอทสร้างห้อง Ticket และเชิญเฉพาะแอดมินท่านนี้
- คนถัดไป: ได้รับผล `False` -> บอทแสดง Ephemeral message: `⚠️ งานนี้ถูกรับไปแล้วโดยแอดมินท่านอื่น!` และเปลี่ยนปุ่มเป็นการ์ดสีเทา (Disabled)

---

## 3. Dynamic Captcha Engine Architecture

### ข้อกำหนดด้านความปลอดภัย (Anti-Bypass & Anti-OCR):
1. **No External Assets Required:** เจนเนอเรตแบบ Procedural บนแรมด้วย `Pillow (PIL)` โดยใช้ฟอนต์มาตรฐานหรือ Vector Drawing
2. **Visual Noise & Distortion Matrix:**
   - Background Color: `#0A0D14` (Dark Space Theme)
   - Foreground Text: สีฟ้าสว่าง `#4AE0FF` ถึงสีขาว `#FFFFFF`
   - Noise Dots: จุดสุ่ม 80-120 จุดกระจายทั่วภาพ
   - Interference Lines: เส้นคลื่นสับสน 4-6 เส้น พาดผ่านตัวอักษรเพื่อตัด Edge Detection ของ OCR
   - Text Jitter: หมุนองศาตัวอักษรทีละตัว (-15° ถึง +15°)
3. **Session Replay Guard:**
   - โค้ดแต่ละชุดมีอายุการใช้งาน 300 วินาที (5 นาที)
   - โค้ดจะถูกผูกกับ `user_id` และ `session_id` เมื่อยืนยันเสร็จหรือหมดอายุจะถูกทำลายทิ้งทันที
   - ไม่สามารถนำภาพเดิมมาส่งซ้ำได้

---

## 4. Slip Verification API & Anti-Replay Architecture

```
[ สลิปภาพ / QR Payload ] 
          │
          ▼
   [ CRC32 / SHA-256 Hash ]
          │
          ├──► ตรวจสอบใน `slip_ledger` (SQLite)
          │    └──► หากพบ Hash เดิม ──► REJECT: "สลิปนี้ถูกใช้งานไปแล้ว"
          │
          └──► หากเป็นสลิปใหม่ ──► ยิงตรวจเช็คกับ API ภายนอก (EasySlip / SlipOK / Custom)
               ├──► ตรวจสอบชื่อบัญชีผู้รับเงิน (Receiver Account Match)
               ├──► ตรวจสอบยอดเงินขั้นต่ำ (Amount >= Minimum Threshold)
               └──► ตรวจสอบวันที่ทำรายการ (Transaction Timestamp <= 24 ชม.)
                    │
                    ▼
               บันทึกลง `slip_ledger` ทันที ──► ปลดล็อกสถานะ "ชำระเงินสำเร็จ"
```

---

## 5. Dual-Logging Pipeline Specification

### Log 1: REST API / Webhook Payload (External Website)
ส่งข้อมูลผ่าน `aiohttp` เป็น JSON Payload:
```json
{
  "event_type": "TICKET_COMPLETED",
  "ticket_metadata": {
    "ticket_id": 108,
    "channel_id": "1549803866134941767",
    "category": "game_topup",
    "opened_at": 1729738000,
    "closed_at": 1729742400
  },
  "customer": {
    "discord_id": "1549398019970179152",
    "username": "PayomCustomer"
  },
  "admin": {
    "discord_id": "1549535328753164418",
    "username": "PayomAdmin"
  },
  "transaction": {
    "amount": 490.00,
    "slip_ref": "2026102402348912",
    "verified_at": 1729739500
  }
}
```

### Log 2: Audit HTML Chat Transcript
- บังคับเลือก Channel ตั้งแต่ตอนรันคำสั่ง `/setup_dispatch`
- บันทึกข้อความทุกข้อความ, Embed, เวลา (Timestamps), รูปโปรไฟล์ผู้ส่ง, และไฟล์แนบ
- แปลงเป็นเอกสาร Standalone HTML5 Dark Theme
- ส่งเข้า Log Channel พร้อม Embed สรุปสาระสำคัญ เพื่อให้ Owner ตรวจสอบย้อนหลังได้ทุกเมื่อ
