# bubblemaps

วิเคราะห์ cluster ของ token holder แล้วบันทึกผลลง Google Sheets โดยอัตโนมัติ
ผ่าน GitHub Actions

## สถาปัตยกรรม

รันแบบ **fan-out / fan-in** — หั่นรายการ token เป็นชิ้นๆ กระจายให้หลาย job
รันพร้อมกัน แล้วรวมผลกลับมาเป็นชีตเดียวตอนจบ

```
plan ──> analyze (matrix: batch 1..N) ──> merge
 │             │                            │
 │             └─ แต่ละ job เขียนแท็บ        └─ รวมทุกแท็บ → 'merge'
 │                Batch_01 … Batch_NN
 └─ นับ token ในชีต แล้วคำนวณว่าต้องใช้กี่ batch
```

**จำนวน batch ไม่ได้ฮาร์ดโค้ดไว้** — `plan.py` นับ token จากชีต
`subscribetokens` ทุกครั้งที่รัน แล้วสร้าง matrix ตามจำนวนจริง
เพิ่มหรือลบ token ในชีตได้เลย ไม่ต้องกลับมาแก้ไฟล์ workflow

การหั่นเป็น **deterministic** — จำนวน token เท่าเดิม batch เดิมจะได้ token
ชุดเดิมเสมอ จึงไม่ต้องเก็บ state ที่ไหน และ rerun batch เดียวได้อย่างปลอดภัย

### ทำไมต้องแยกแท็บ

แต่ละ batch เป็นเจ้าของแท็บ `Batch_NN` ของตัวเองคนเดียว จะล้างหรือเขียนทับ
แท็บตัวเองยังไงก็ไม่กระทบใคร งานที่รันขนานกันจึงไม่มีทางลบข้อมูลของกันเอง
`merge.py` เป็นตัวเดียวที่แตะชีตหลัก และรันหลัง batch ทั้งหมดจบแล้ว

## ไฟล์

| ไฟล์ | หน้าที่ |
|---|---|
| `plan.py` | นับ token → คำนวณจำนวน batch → พ่น matrix ให้ Actions |
| `cluster.py` | วิเคราะห์ token 1 batch → เขียนแท็บ `Batch_NN` |
| `merge.py` | รวมทุกแท็บ `Batch_NN` → ชีตหลัก |
| `shared.py` | เรียก API + auth + client ของ Google Sheets |

## การตั้งค่า

ปรับผ่าน `workflow_dispatch` inputs หรือ env ใน `.github/workflows/analyze.yml`

| ตัวแปร | default | ความหมาย |
|---|---|---|
| `TOKENS_PER_BATCH` | `60` | token ต่อ 1 job — ยิ่งน้อย job ยิ่งเยอะแต่สั้นลง |
| `max_parallel` | `3` | จำนวน job ที่รันพร้อมกัน |
| `TIME_LIMIT_HOURS` | `1.75` | เพดานเวลาต่อ batch (ต้องต่ำกว่า `timeout-minutes`) |
| `FLUSH_EVERY` | `25` | เขียนลงชีตทุกๆ กี่แถว — กันงานหายถ้า job ตายกลางทาง |
| `SHEETS_WRITE_DELAY_MS` | `1500` | เว้นจังหวะเขียน (Google จำกัด ~60 writes/นาที **รวมทุก runner**) |
| `HTTP_MAX_ATTEMPTS` | `4` | จำนวนครั้งที่ retry เมื่อ API ตอบ 5xx / 429 |
| `MAX_BATCHES` | `256` | เพดานจำนวน job ต่อรอบ (ลิมิตของ GitHub) |
| `CLEANUP_BATCH_TABS` | `1` | ลบแท็บ `Batch_NN` ทิ้งหลังรวมเสร็จ — ตั้ง `0` ถ้าอยากเก็บไว้ตรวจสอบ |

### ปรับ max_parallel ยังไง

API ที่ใช้อยู่ไม่ได้จำกัด rate แบบเข้มงวด (จาก log 1776 requests ใน 5.5 ชม.
ไม่เจอ 429 เลย) จึงขนานได้จริง ถ้าอยากเร็วขึ้นให้ค่อยๆ เพิ่มจาก 3 ขึ้นไป
แล้วดูใน log ว่าเริ่มมี 429 หรือ 5xx ถี่ขึ้นหรือยัง

ตัวจำกัดที่มาถึงก่อนมักเป็นโควตาเขียนของ Google Sheets ไม่ใช่ API ต้นทาง —
ถ้าเจอ 429 จาก Google ให้เพิ่ม `SHEETS_WRITE_DELAY_MS` แทนที่จะลด parallel

## รันเองที่เครื่อง

ต้องมี `credentials.json` (service account) และ `.env`

```bash
pip install requests gspread google-auth pyjwt python-dotenv

python cluster.py                 # ทำทุก token เขียนลงชีตหลักเลย
python cluster.py --batch 3/20    # ทำเฉพาะ batch 3 จาก 20 เขียนลงแท็บ Batch_03
python merge.py                   # รวมทุกแท็บ Batch_NN → ชีตหลัก
```

## เมื่อ batch ไหนพัง

`fail-fast: false` — batch อื่นรันต่อจนจบ และ `merge` ใช้ `if: always()`
จึงยังรวมของที่สำเร็จได้ ไม่ต้องรอให้ครบทุกตัว

rerun เฉพาะ batch ที่พังจากหน้า Actions ได้เลย มันจะเขียนทับแท็บตัวเอง
แล้วค่อยรัน `merge` ซ้ำ — ไม่กระทบข้อมูลของ batch อื่น

**ข้อควรรู้เรื่องการลบแท็บ**: `merge` จะลบแท็บ `Batch_NN` ก็ต่อเมื่อเขียนลง
ชีต `merge` สำเร็จแล้วเท่านั้น ถ้าเขียนพลาดจะไม่แตะแท็บใดเลยแล้ว exit 1
แต่เมื่อลบไปแล้ว การ rerun `merge` เดี่ยวๆ จะไม่มีข้อมูลให้รวมอีก —
ต้องรัน analyze ใหม่ ถ้าอยากเก็บแท็บไว้ตรวจสอบให้ตั้ง `cleanup_batch_tabs` = `0`
