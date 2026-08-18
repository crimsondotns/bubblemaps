"""รวมผลจากทุกแท็บ Batch_NN กลับมาเป็นชีตหลักแผ่นเดียว (fan-in)

รันเป็น job สุดท้ายหลัง matrix จบ ด้วย if: always() — batch ไหนพังก็ยังรวม
ของที่เหลือได้ ไม่ต้องรอให้ครบทุกตัว
"""
import os
import sys
import time

from cluster import HEADERS, GSHEET_WORKSHEET, ensure_worksheet, bulk_write_to_gsheet
from shared import get_gsheet_client, GSHEET_KEY

BATCH_SHEET_PREFIX = os.getenv("BATCH_SHEET_PREFIX", "Batch_")
SHEETS_WRITE_DELAY_MS = int(os.getenv("SHEETS_WRITE_DELAY_MS", "1500"))
# ลบแท็บ Batch_* ทิ้งหลังรวมเสร็จ (default: เก็บไว้ ใช้ไล่ดูตอนมีปัญหา)
CLEANUP_BATCH_TABS = os.getenv("CLEANUP_BATCH_TABS", "0") == "1"


def batch_index(title):
    """ดึงเลข batch จากชื่อแท็บ — คืน None ถ้าไม่ใช่แท็บ batch"""
    if not title.startswith(BATCH_SHEET_PREFIX):
        return None
    suffix = title[len(BATCH_SHEET_PREFIX):]
    return int(suffix) if suffix.isdigit() else None


def main():
    sh = get_gsheet_client().open_by_key(GSHEET_KEY)

    # เรียงตามเลข batch เพื่อให้ลำดับแถวในชีตหลักคงที่ทุกรอบ
    tabs = sorted(
        ((batch_index(ws.title), ws) for ws in sh.worksheets()),
        key=lambda pair: pair[0] if pair[0] is not None else -1,
    )
    tabs = [(i, ws) for i, ws in tabs if i is not None]

    if not tabs:
        print(f"❌ ไม่พบแท็บที่ขึ้นต้นด้วย '{BATCH_SHEET_PREFIX}' — ไม่มีอะไรให้รวม")
        sys.exit(1)

    print(f"🔗 พบ {len(tabs)} แท็บ batch — กำลังรวมข้อมูล...")

    merged = []
    empty_tabs = []
    for index, ws in tabs:
        # UNFORMATTED_VALUE เพื่อให้ตัวเลข (amount/share) กลับมาเป็น number ไม่ใช่ string
        # ไม่งั้นชีตหลักจะได้ค่าเป็นข้อความ เอาไปคำนวณ/เรียงต่อไม่ได้
        try:
            rows = ws.get_values(value_render_option="UNFORMATTED_VALUE")
        except TypeError:
            # gspread รุ่นเก่าที่ยังไม่รับ value_render_option
            rows = ws.get_all_values()
        # แถวแรกเป็น header ของแท็บนั้น — ตัดทิ้ง
        body = [r for r in rows[1:] if any(str(cell).strip() for cell in r)]
        if body:
            merged.extend(body)
        else:
            empty_tabs.append(ws.title)
        print(f"   ├─ {ws.title}: {len(body)} แถว")
        time.sleep(SHEETS_WRITE_DELAY_MS / 1000)

    if empty_tabs:
        print(f"   ⚠️ แท็บที่ไม่มีข้อมูล ({len(empty_tabs)}): {', '.join(empty_tabs)}")

    print(f"\n📦 รวมได้ทั้งหมด {len(merged)} แถว → เขียนลงแท็บ '{GSHEET_WORKSHEET}'")

    if not merged:
        print("❌ ไม่มีข้อมูลให้รวม — ไม่แตะชีตหลัก เพื่อไม่ให้ข้อมูลรอบก่อนหาย")
        sys.exit(1)

    ensure_worksheet(GSHEET_WORKSHEET, rows=max(2000, len(merged) + 100), cols=len(HEADERS) + 2)
    bulk_write_to_gsheet(merged, mode="clear", worksheet_name=GSHEET_WORKSHEET)

    if CLEANUP_BATCH_TABS:
        print("\n🧹 ลบแท็บ batch ทิ้ง...")
        for _index, ws in tabs:
            try:
                sh.del_worksheet(ws)
                time.sleep(SHEETS_WRITE_DELAY_MS / 1000)
            except Exception as e:
                print(f"   ⚠️ ลบ {ws.title} ไม่สำเร็จ: {e}")

    print(f"\n✅ รวมข้อมูลเสร็จ — {len(merged)} แถวในแท็บ '{GSHEET_WORKSHEET}'")


if __name__ == "__main__":
    main()
