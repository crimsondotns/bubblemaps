import time
import os
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
FETCH_COUNT = 250
MAX_MAGIC_ROUNDS = 1  # จำนวนรอบสูงสุดของ Recursive Magic Expand
DELAY_BETWEEN_TOKENS = 10  # วินาทีระหว่างแต่ละ token

# ── Google Sheets ──
GSHEET_WORKSHEET = "bubbleeee"
SUBSCRIBE_WORKSHEET = "subscribetokens"

# ╔═══════════════════════════════════════════════════════════════════╗
# ║                     จบ SETTINGS — ไม่ต้องแก้ด้านล่าง               ║
# ╚═══════════════════════════════════════════════════════════════════╝

# ─────────────────────── Google Sheets ───────────────────────────────

def bulk_write_to_gsheet(all_rows, mode="clear"):
    """บันทึกผลลัพธ์หลายแถวลง Google Sheets (bulk write + retry)
    
    mode="clear"  → ล้างชีตก่อนแล้วเขียนใหม่ (default, ใช้กับ workflow_1)
    mode="append" → ต่อท้ายข้อมูลเดิม ไม่ล้าง (ใช้กับ workflow_2 เป็นต้นไป)
    """
    if not all_rows:
        return

    print(f"\n5️⃣ กำลังบันทึก {len(all_rows)} แถวลง Google Sheets (mode={mode})...")

    headers = [
        "Token Address", "Chain", "Wallet Address",
        "Wallet Amount", "Wallet Share (%)", "Label",
        "Addresses", "Cluster Size (Addresses)", "Cluster Amount", "Cluster Supply (%)",
        "Timestamp (UTC+7)",
    ]

    BATCH_SIZE = 500
    max_retries = 5

    for attempt in range(1, max_retries + 1):
        try:
            client = get_gsheet_client()
            sheet = client.open_by_key(GSHEET_KEY).worksheet(GSHEET_WORKSHEET)

            if mode == "clear":
                sheet.clear()
                all_data = [headers] + all_rows
                start_offset = 0
            else:
                # append: หาแถวสุดท้ายที่มีข้อมูลแล้วต่อท้าย (ไม่ใส่ headers ซ้ำ)
                existing = sheet.col_values(1)  # Column A
                start_offset = len(existing)    # แถวถัดไปที่ว่าง (0-indexed)
                all_data = all_rows

            for i in range(0, len(all_data), BATCH_SIZE):
                batch = all_data[i:i + BATCH_SIZE]
                start_row = start_offset + i + 1
                sheet.update(range_name=f"A{start_row}", values=batch)
                if len(all_data) > BATCH_SIZE:
                    print(f"   📝 เขียนแถว {start_row}–{start_row + len(batch) - 1} ({len(batch)} แถว)...")
                    time.sleep(1)

            print("✅ บันทึกข้อมูลสำเร็จ! ตรวจสอบ Google Sheets ได้เลย")
            return
        except Exception as e:
            wait_time = 2 ** attempt
            print(f"   ⚠️ ครั้งที่ {attempt}/{max_retries} — {e}")
            if attempt < max_retries:
                print(f"   ⏳ รอ {wait_time} วินาที แล้วลองใหม่...")
                time.sleep(wait_time)
            else:
                print(f"   ❌ ล้มเหลวหลัง {max_retries} ครั้ง — ข้อมูลไม่ได้บันทึก")


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


if __name__ == "__main__":
    TIME_LIMIT_HOURS = float(os.getenv("TIME_LIMIT_HOURS", "5.5"))
    WRITE_MODE = os.getenv("WRITE_MODE", "clear")

    print("📋 กำลังอ่านรายชื่อ token จากชีต subscribetokens...")
    token_pairs = read_subscribe_tokens()

    if not token_pairs:
        print("❌ ไม่พบรายชื่อ token ในชีต subscribetokens")
        exit()

    print(f"✅ พบ {len(token_pairs)} token(s) ทั้งหมด")

    client = get_gsheet_client()
    try:
        state_sheet = client.open_by_key(GSHEET_KEY).worksheet("state")
        start_index_str = state_sheet.acell('A1').value
        start_index = int(start_index_str) if start_index_str and start_index_str.isdigit() else 0
    except Exception as e:
        print(f"⚠️ ไม่สามารถอ่านชีต 'state' ได้ หรือไม่มีข้อมูล (เริ่มจาก 0)")
        start_index = 0

    if start_index >= len(token_pairs):
        start_index = 0

    print(f"▶️ เริ่มต้นรันที่ index {start_index} (WRITE_MODE={WRITE_MODE})")

    # สะสมผลลัพธ์ทุก token
    all_results = []
    start_time = time.time()
    time_limit_sec = TIME_LIMIT_HOURS * 3600
    next_index = start_index

    for idx, (token_address, chain) in enumerate(token_pairs[start_index:]):
        current_index = start_index + idx
        try:
            row = analyze_token(token_address, chain)
            if row:
                all_results.append(row)
                print(f"   📝 สะสมผล: {len(all_results)} แถว")
        except Exception as e:
            print(f"❌ Error วิเคราะห์ {token_address[:12]}...: {e}")

        next_index = current_index + 1
        
        elapsed_time = time.time() - start_time
        if elapsed_time >= time_limit_sec:
            print(f"\n⏱️ เวลาทำงาน ({elapsed_time/3600:.2f} ชม.) ถึงขีดจำกัดแล้ว ({TIME_LIMIT_HOURS} ชม.) — หยุด loop")
            break

        # หน่วงเวลาระหว่าง token (ยกเว้นตัวสุดท้ายหรือถึง limit)
        if next_index < len(token_pairs):
            print(f"\n⏳ รอ {DELAY_BETWEEN_TOKENS} วินาที ก่อนวิเคราะห์ตัวถัดไป...")
            time.sleep(DELAY_BETWEEN_TOKENS)

    # Bulk write ทีเดียว
    if all_results:
        bulk_write_to_gsheet(all_results, mode=WRITE_MODE)
    else:
        print("❌ ไม่มีผลลัพธ์ที่ต้องบันทึก")

    # บันทึก State
    try:
        if next_index >= len(token_pairs):
            next_index = 0
            print("🏁 รันครบทุก token แล้ว! รีเซ็ต index กลับเป็น 0")
        else:
            print(f"⏸️ หยุดพักที่ index {next_index} บันทึกลง sheet 'state'")
            
        try:
            state_sheet = client.open_by_key(GSHEET_KEY).worksheet("state")
        except:
            # ถ้ายังไม่มี sheet ชื่อ state ให้สร้างใหม่
            state_sheet = client.open_by_key(GSHEET_KEY).add_worksheet(title="state", rows="10", cols="10")
            
        state_sheet.update_acell('A1', str(next_index))
    except Exception as e:
        print(f"❌ ไม่สามารถบันทึก state ลงชีต 'state' ได้: {e}")

    print(f"\n🏁 วิเคราะห์จบการทำงานรอบนี้ — บันทึกไป {len(all_results)} แถว")