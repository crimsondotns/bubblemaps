import time
import os
import sys
from datetime import datetime, timezone, timedelta
import json
from shared import (
    get_gsheet_client,
    fetch_top_holders,
    run_recursive_magic_expand,
    fetch_subgraph_data,
    calculate_cluster,
    GSHEET_KEY,
)

# ╔═══════════════════════════════════════════════════════════════════╗
# ║                     🔧 SETTINGS — แก้ตรงนี้                      ║
# ╚═══════════════════════════════════════════════════════════════════╝

TARGET_WALLET = ""  # ระบุ address ที่ต้องการดู cluster (เว้นว่าง = ใช้ holder อันดับ 1)
FETCH_COUNT = 80
MAX_MAGIC_ROUNDS = 1  # จำนวนรอบสูงสุดของ Recursive Magic Expand
DELAY_BETWEEN_TOKENS = 10  # วินาทีระหว่างแต่ละ token
FLUSH_EVERY = int(os.getenv("FLUSH_EVERY", "25"))  # เขียนลงชีตทุกๆ กี่แถว (0 = เขียนครั้งเดียวตอนจบ)
SHEETS_WRITE_DELAY_MS = int(os.getenv("SHEETS_WRITE_DELAY_MS", "1500"))  # เว้นจังหวะเขียน (โควตารวมทุก runner)
TIME_LIMIT_HOURS = float(os.getenv("TIME_LIMIT_HOURS", "5.0"))

# ── Google Sheets ──
GSHEET_WORKSHEET = "merge"
SUBSCRIBE_WORKSHEET = "subscribetokens"

# ╔═══════════════════════════════════════════════════════════════════╗
# ║                     จบ SETTINGS — ไม่ต้องแก้ด้านล่าง               ║
# ╚═══════════════════════════════════════════════════════════════════╝

# ─────────────────────── Google Sheets ───────────────────────────────

HEADERS = [
    "Token Address", "Chain", "Wallet Address",
    "Wallet Amount", "Wallet Share (%)", "Label",
    "Addresses", "Cluster Size (Addresses)", "Cluster Amount", "Cluster Supply (%)",
    "Timestamp (UTC+7)",
]


def ensure_worksheet(name, rows=2000, cols=20):
    """คืน worksheet ชื่อ name — สร้างใหม่ให้ถ้ายังไม่มี

    ทำให้เพิ่มจำนวน batch ได้โดยไม่ต้องไปสร้างแท็บเองในชีต
    """
    for attempt in range(1, 4):
        try:
            sh = get_gsheet_client().open_by_key(GSHEET_KEY)
            try:
                return sh.worksheet(name)
            except Exception:
                print(f"   ➕ สร้างแท็บใหม่: '{name}'")
                return sh.add_worksheet(title=name, rows=str(rows), cols=str(cols))
        except Exception as e:
            # แท็บอาจถูกสร้างพร้อมกันโดย batch อื่น — ลองอ่านซ้ำ
            if attempt == 3:
                raise
            print(f"   ⚠️ เตรียมแท็บ '{name}' ไม่สำเร็จ ({e}) — ลองใหม่")
            time.sleep(2 ** attempt)


def bulk_write_to_gsheet(all_rows, mode="clear", worksheet_name=None, write_headers=False):
    """บันทึกผลลัพธ์หลายแถวลง Google Sheets (bulk write + retry)

    mode="clear"  → ล้างแท็บก่อนแล้วเขียนใหม่ (ใช้กับการเขียนครั้งแรกของ batch)
    mode="append" → ต่อท้ายข้อมูลเดิม ไม่ล้าง (ใช้กับ flush ครั้งถัดๆ ไป)

    worksheet_name = แท็บปลายทาง (default: GSHEET_WORKSHEET)
    แต่ละ batch เขียนแท็บของตัวเองเท่านั้น จึงไม่มีทางล้างข้อมูลของ batch อื่น

    คืน True ถ้าเขียนสำเร็จ, False ถ้าล้มเหลวหลัง retry ครบแล้ว
    ผู้เรียกต้องเช็คค่านี้ก่อนทำอะไรที่ทำลายข้อมูลต้นทาง (เช่นลบแท็บ)
    """
    if not all_rows and not write_headers:
        return True

    sheet_name = worksheet_name or GSHEET_WORKSHEET
    print(f"\n5️⃣ กำลังบันทึก {len(all_rows)} แถวลงแท็บ '{sheet_name}' (mode={mode})...")

    BATCH_SIZE = 500
    max_retries = 5

    for attempt in range(1, max_retries + 1):
        try:
            client = get_gsheet_client()
            sheet = client.open_by_key(GSHEET_KEY).worksheet(sheet_name)

            if mode == "clear":
                sheet.clear()
                all_data = [HEADERS] + all_rows
                start_offset = 0
            else:
                # append: หาแถวสุดท้ายที่มีข้อมูลแล้วต่อท้าย (ไม่ใส่ headers ซ้ำ)
                existing = sheet.col_values(1)  # Column A
                start_offset = len(existing)    # แถวถัดไปที่ว่าง (0-indexed)
                # ถ้าชีตยังว่างอยู่ (เช่นถูกล้างไว้) ต้องใส่ header ให้ด้วย
                all_data = all_rows if start_offset else [HEADERS] + all_rows

            for i in range(0, len(all_data), BATCH_SIZE):
                batch = all_data[i:i + BATCH_SIZE]
                start_row = start_offset + i + 1
                sheet.update(range_name=f"A{start_row}", values=batch)
                print(f"   📝 เขียนแถว {start_row}–{start_row + len(batch) - 1} ({len(batch)} แถว)...")
                # Google Sheets จำกัด ~60 writes/นาที ต่อ user และเป็นโควตา "รวม"
                # ทุก runner ที่รันขนานกัน — จึงต้องเว้นจังหวะทุกครั้ง ไม่ใช่เฉพาะตอนหลายก้อน
                time.sleep(SHEETS_WRITE_DELAY_MS / 1000)

            print("✅ บันทึกข้อมูลสำเร็จ! ตรวจสอบ Google Sheets ได้เลย")
            return True
        except Exception as e:
            wait_time = 2 ** attempt
            print(f"   ⚠️ ครั้งที่ {attempt}/{max_retries} — {e}")
            if attempt < max_retries:
                print(f"   ⏳ รอ {wait_time} วินาที แล้วลองใหม่...")
                time.sleep(wait_time)
            else:
                print(f"   ❌ ล้มเหลวหลัง {max_retries} ครั้ง — ข้อมูลไม่ได้บันทึก")

    return False


# ─────────────────────── Main ────────────────────────────────────────

def analyze_token(token_address, chain):
    """วิเคราะห์ cluster ของ token 1 ตัว — return row_data หรือ None"""
    print(f"\n{'#'*60}")
    print(f"# 🔍 เริ่มวิเคราะห์: {token_address[:12]}... ({chain})")
    print(f"{'#'*60}")

    # Step 1: ดึง Top Holders
    holders = fetch_top_holders(token_address, chain, FETCH_COUNT)
    if not holders:
        print("❌ ดึง Holders ไม่ได้ — ข้ามไป")
        return None

    # หา Target Wallet
    target_wallet = None
    if TARGET_WALLET:
        for w in holders:
            if w.get("address") == TARGET_WALLET:
                target_wallet = w
                break
        if not target_wallet:
            print(f"⚠️ ไม่พบ {TARGET_WALLET} ใน Top {FETCH_COUNT} — ใช้ holder อันดับ 1 แทน")
            target_wallet = holders[0]
    else:
        # ใช้ holder อันดับ 1 ที่เป็น Normal Wallet หรือเป็น Supernode ที่ไม่มี label (และไม่ใช่ CEX/DEX/Contract)
        for w in holders:
            details = w.get("address_details", {})
            
            is_supernode = details.get("is_supernode", False)
            label = details.get("label")
            is_contract = details.get("is_contract", False)
            is_cex = details.get("is_cex", False)
            is_dex = details.get("is_dex", False)

            if not is_contract and not is_cex and not is_dex:
                if not is_supernode or (is_supernode and not label):
                    target_wallet = w
                    break
        if not target_wallet:
            target_wallet = holders[0]

    if not target_wallet:
        print("❌ ไม่พบ Wallet ที่ตรงตามเงื่อนไข — ข้ามไป")
        return None

    wallet_address = target_wallet.get("address")
    amount = target_wallet.get("holder_data", {}).get("amount", 0)
    share = target_wallet.get("holder_data", {}).get("share", 0)
    label = target_wallet.get("address_details", {}).get("label", "N/A")

    print(f"\n🎯 เจอ Top Wallet: {wallet_address}")
    print(f"   ├─ Amount: {amount:,.2f}")
    print(f"   ├─ Share: {share*100:.2f}%")
    print(f"   └─ Label: {label}")
    print(f"   🔍 Debug Top Wallet Info:")
    
    # ดึงเฉพาะข้อมูลที่น่าสนใจมา Debug พิมพ์ (เพื่อไม่ให้รกเกินไป)
    debug_info = {
        "address": target_wallet.get("address"),
        "address_details": target_wallet.get("address_details", {}),
        "holder_data": target_wallet.get("holder_data", {})
    }
    print("   " + json.dumps(debug_info, indent=4).replace('\n', '\n   '))

    # Step 2: Recursive Magic Expand
    all_addresses = run_recursive_magic_expand(token_address, chain, holders, MAX_MAGIC_ROUNDS)
    
    # Step 3: Subgraph
    relationships = fetch_subgraph_data(token_address, chain, all_addresses)

    # Step 4: Calculate Cluster
    cluster_data = calculate_cluster(wallet_address, relationships, holders, TARGET_WALLET)
    cluster_size = cluster_data["size"]
    cluster_amount = cluster_data["amount"]
    cluster_supply_pct = cluster_data["share_pct"]
    top_cluster_wallet = cluster_data.get("top_cluster_wallet", "")

    # แต่ amount/share/label ยังคงเป็นของ Top Wallet ตัวแรกที่ตรวจพบ (ไม่เปลี่ยน)

    print(f"\n{'='*60}")
    print(f"🔥 สรุปผลลัพธ์ Cluster Analysis")
    print(f"{'='*60}")
    print(f"   Token:          {token_address}")
    print(f"   Chain:          {chain}")
    print(f"   Target Wallet:  {wallet_address}")
    print(f"   Cluster Size:   {cluster_size} กระเป๋า")
    print(f"   Cluster Amount: {cluster_amount:,.2f}")
    print(f"   Cluster Supply: {cluster_supply_pct:.2f}%")
    print(f"{'='*60}")

    # Return row data (share/supply เก็บเป็นทศนิยม ÷100)
    utc7 = datetime.now(timezone(timedelta(hours=7)))
    timestamp = utc7.strftime("%m/%d/%Y %-H:%M:%S")
    return [
        token_address, chain, wallet_address,
        amount, share, label,
        top_cluster_wallet, cluster_size, cluster_amount, cluster_supply_pct / 100,
        timestamp,
    ]


def read_subscribe_tokens():
    """อ่านรายชื่อ token จากชีต subscribetokens (B=chain, C=token address)"""
    gc = get_gsheet_client()
    sh = gc.open_by_key(GSHEET_KEY)
    ws = sh.worksheet(SUBSCRIBE_WORKSHEET)

    chains = ws.col_values(2)   # Column B
    tokens = ws.col_values(3)   # Column C

    # ข้ามแถวแรก (header) แล้วจับคู่
    pairs = []
    for i in range(1, max(len(chains), len(tokens))):
        chain = chains[i].strip() if i < len(chains) else ""
        token = tokens[i].strip() if i < len(tokens) else ""
        if chain and token:
            pairs.append((token, chain))

    return pairs


def resolve_batch():
    """อ่าน --batch N/TOTAL (หรือ BATCH_INDEX/BATCH_TOTAL) → (index, total) หรือ None

    index เริ่มที่ 1. ถ้าไม่ระบุ = โหมดรันเดียวจบ (ทำทุก token, เขียนชีตหลัก)
    """
    raw = None
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--batch" and i + 1 < len(argv):
            raw = argv[i + 1]
        elif a.startswith("--batch="):
            raw = a.split("=", 1)[1]

    index = total = None
    if raw:
        if "/" in raw:
            a, b = raw.split("/", 1)
            index, total = int(a), int(b)
        else:
            index = int(raw)
    if index is None and os.getenv("BATCH_INDEX"):
        index = int(os.getenv("BATCH_INDEX"))
    if total is None and os.getenv("BATCH_TOTAL"):
        total = int(os.getenv("BATCH_TOTAL"))

    if index is None:
        return None
    if not total or total < 1:
        raise SystemExit("❌ ระบุ --batch N ต้องมี TOTAL ด้วย (--batch N/TOTAL หรือ BATCH_TOTAL)")
    if not 1 <= index <= total:
        raise SystemExit(f"❌ batch index {index} ต้องอยู่ระหว่าง 1 ถึง {total}")
    return (index, total)


def slice_for_batch(items, index, total):
    """หั่น items เป็น total ชิ้นเท่าๆ กัน แล้วคืนชิ้นที่ index (เริ่มที่ 1)

    Deterministic: จำนวน token เท่าเดิม batch เดิมจะได้ token ชุดเดิมเสมอ
    เศษที่หารไม่ลงตัวจะถูกกระจายให้ batch แรกๆ ทีละ 1 ตัว
    """
    n = len(items)
    base, extra = divmod(n, total)
    start = (index - 1) * base + min(index - 1, extra)
    size = base + (1 if index <= extra else 0)
    return items[start:start + size], start


def batch_sheet_name(index):
    prefix = os.getenv("BATCH_SHEET_PREFIX", "Batch_")
    return f"{prefix}{index:02d}"


if __name__ == "__main__":
    batch = resolve_batch()

    print("📋 กำลังอ่านรายชื่อ token จากชีต subscribetokens...")
    token_pairs = read_subscribe_tokens()

    if not token_pairs:
        print("❌ ไม่พบรายชื่อ token ในชีต subscribetokens")
        sys.exit(1)

    print(f"✅ พบ {len(token_pairs)} token(s) ทั้งหมด")

    if batch:
        index, total = batch
        my_tokens, offset = slice_for_batch(token_pairs, index, total)
        target_sheet = batch_sheet_name(index)
        print(f"🧩 Batch {index}/{total} → token ลำดับ {offset + 1}–{offset + len(my_tokens)} "
              f"({len(my_tokens)} ตัว) เขียนลงแท็บ '{target_sheet}'")
        if not my_tokens:
            # batch เกินจำนวน token ที่มี (เช่นลบ token ออกจากชีต) — ไม่ใช่ error
            print("ℹ️ batch นี้ไม่มี token ที่ต้องทำ — จบการทำงาน")
            ensure_worksheet(target_sheet)
            bulk_write_to_gsheet([], mode="clear", worksheet_name=target_sheet, write_headers=True)
            sys.exit(0)
    else:
        my_tokens = token_pairs
        target_sheet = GSHEET_WORKSHEET
        print(f"🧩 โหมดรันเดียวจบ → token ทั้งหมด {len(my_tokens)} ตัว เขียนลงแท็บ '{target_sheet}'")

    # แต่ละ batch เป็นเจ้าของแท็บตัวเอง จึงล้างแท็บตัวเองได้อย่างปลอดภัย
    # ไม่มีการแตะแท็บของ batch อื่น — ปัญหา clear ทับกันจึงหมดไป
    ensure_worksheet(target_sheet)

    all_results = []
    total_written = 0
    first_write = True
    write_failed = False
    start_time = time.time()
    time_limit_sec = TIME_LIMIT_HOURS * 3600

    def flush():
        """เขียนผลที่สะสมไว้ลงแท็บของ batch นี้ — เรียกได้หลายครั้งระหว่างรัน"""
        global all_results, total_written, first_write, write_failed
        if not all_results:
            return
        # ครั้งแรกของรัน = ล้างแท็บตัวเองแล้วเขียนใหม่ (ข้อมูลรอบก่อนของ batch นี้)
        # ครั้งต่อๆ ไป = ต่อท้าย ไม่งั้นจะล้างของที่ตัวเองเพิ่งเขียน
        ok = bulk_write_to_gsheet(
            all_results,
            mode="clear" if first_write else "append",
            worksheet_name=target_sheet,
        )
        if not ok:
            # เก็บแถวไว้ในบัฟเฟอร์ ให้ flush ครั้งหน้าลองเขียนอีกที
            print(f"   ⚠️ เก็บ {len(all_results)} แถวไว้ลองใหม่รอบหน้า")
            write_failed = True
            return
        total_written += len(all_results)
        all_results = []
        first_write = False

    for idx, (token_address, chain) in enumerate(my_tokens):
        try:
            row = analyze_token(token_address, chain)
            if row:
                all_results.append(row)
                print(f"   📝 สะสมผล: {total_written + len(all_results)} แถว "
                      f"({idx + 1}/{len(my_tokens)} ของ batch)")
        except Exception as e:
            print(f"❌ Error วิเคราะห์ {token_address[:12]}...: {e}")

        # เขียนลงชีตเป็นระยะ เพื่อไม่ให้เสียงานทั้ง batch ถ้า job ตายกลางทาง
        if FLUSH_EVERY > 0 and len(all_results) >= FLUSH_EVERY:
            flush()

        elapsed_time = time.time() - start_time
        if elapsed_time >= time_limit_sec and idx + 1 < len(my_tokens):
            # ปกติไม่ควรถึงตรงนี้ — batch ถูกซอยให้เล็กพอจบในเวลา
            print(f"\n⏱️ เวลาทำงาน ({elapsed_time/3600:.2f} ชม.) ถึงขีดจำกัด ({TIME_LIMIT_HOURS} ชม.) — หยุด")
            print(f"⚠️ batch นี้ทำได้ {idx + 1}/{len(my_tokens)} token — ควรเพิ่มจำนวน batch ให้ซอยถี่ขึ้น")
            break

        if idx + 1 < len(my_tokens):
            print(f"\n⏳ รอ {DELAY_BETWEEN_TOKENS} วินาที ก่อนวิเคราะห์ตัวถัดไป...")
            time.sleep(DELAY_BETWEEN_TOKENS)

    flush()

    if total_written == 0:
        print("❌ ไม่มีผลลัพธ์ที่ต้องบันทึก")
        # เขียน header ไว้ ให้ขั้นรวมแท็บอ่านแท็บนี้ได้โดยไม่ error
        bulk_write_to_gsheet([], mode="clear", worksheet_name=target_sheet, write_headers=True)

    print(f"\n🏁 จบการทำงาน — บันทึก {total_written} แถวลงแท็บ '{target_sheet}'")

    if write_failed or all_results:
        # ต้องให้ job ขึ้นแดง ไม่งั้น merge จะรวมข้อมูลที่ไม่ครบไปเงียบๆ
        print(f"❌ มี {len(all_results)} แถวที่เขียนลงชีตไม่สำเร็จ — rerun batch นี้ได้เลย")
        sys.exit(1)
