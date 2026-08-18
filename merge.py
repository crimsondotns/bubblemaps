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
# ลบแท็บ Batch_* ทิ้งหลังรวมเสร็จ — ลบต่อเมื่อเขียนชีตหลักสำเร็จแล้วเท่านั้น
CLEANUP_BATCH_TABS = os.getenv("CLEANUP_BATCH_TABS", "1") == "1"
# จำนวน batch ของรอบนี้ (จาก job plan) — แท็บที่เลขเกินนี้คือของเก่าค้างจากรอบ
# ที่ token เยอะกว่า ต้องไม่เอามารวม ไม่งั้นข้อมูลเก่าจะปนเข้ามา
BATCH_TOTAL = int(os.getenv("BATCH_TOTAL", "0"))


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

    stale = []
    if BATCH_TOTAL:
        stale = [ws for i, ws in tabs if i > BATCH_TOTAL]
        if stale:
            print(f"⚠️ ข้ามแท็บค้างจากรอบก่อน {len(stale)} แท็บ (เลขเกิน {BATCH_TOTAL}): "
                  f"{', '.join(w.title for w in stale)}")
        tabs = [(i, ws) for i, ws in tabs if i <= BATCH_TOTAL]

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
    ok = bulk_write_to_gsheet(merged, mode="clear", worksheet_name=GSHEET_WORKSHEET)

    if not ok:
        # แท็บ batch คือสำเนาเดียวที่เหลือของข้อมูลชุดนี้ — ห้ามแตะเด็ดขาด
        print(f"❌ เขียนลงแท็บ '{GSHEET_WORKSHEET}' ไม่สำเร็จ — ไม่ลบแท็บ batch, rerun merge ได้เลย")
        sys.exit(1)

    if CLEANUP_BATCH_TABS:
        # มาถึงตรงนี้ได้แปลว่าข้อมูลอยู่ในชีตหลักครบแล้ว แท็บ batch จึงเป็นสำเนาซ้ำ
        print("\n🧹 ลบแท็บ batch ทิ้ง...")
        failed = []
        # ลบแท็บค้างด้วย ไม่งั้นมันจะกวนรอบถัดๆ ไปตลอด
        for ws in [w for _i, w in tabs] + stale:
            try:
                sh.del_worksheet(ws)
                time.sleep(SHEETS_WRITE_DELAY_MS / 1000)
            except Exception as e:
                failed.append(ws.title)
                print(f"   ⚠️ ลบ {ws.title} ไม่สำเร็จ: {e}")
        if failed:
            # ไม่ใช่เรื่องคอขาดบาดตาย ข้อมูลปลอดภัยแล้ว รอบหน้าจะเขียนทับเอง
            print(f"   ℹ️ เหลือ {len(failed)} แท็บที่ลบไม่ได้ — รอบหน้าจะถูกเขียนทับอยู่ดี")
        else:
            print("   ✅ ลบแท็บ batch ครบแล้ว")

    print(f"\n✅ รวมข้อมูลเสร็จ — {len(merged)} แถวในแท็บ '{GSHEET_WORKSHEET}'")


if __name__ == "__main__":
    main()
