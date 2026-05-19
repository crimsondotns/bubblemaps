import time
from datetime import datetime, timezone, timedelta
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
GSHEET_WORKSHEET = "bubblemaps.io"
SUBSCRIBE_WORKSHEET = "subscribetokens"

# ╔═══════════════════════════════════════════════════════════════════╗
# ║                     จบ SETTINGS — ไม่ต้องแก้ด้านล่าง               ║
# ╚═══════════════════════════════════════════════════════════════════╝

# ─────────────────────── Google Sheets ───────────────────────────────

def write_to_gsheet(all_rows):
    """บันทึกผลลัพธ์ลง Google Sheets แบบ Batch"""
    if not all_rows:
        return

    print(f"\n5️⃣ กำลังบันทึก {len(all_rows)} แถวลง Google Sheets...")
    headers = [
        "Token Address", "Chain", "Wallet Address",
        "Wallet Amount", "Wallet Share (%)", "Label",
        "Addresses", "Cluster Size (Addresses)", "Cluster Amount", "Cluster Supply (%)",
        "Timestamp (UTC+7)",
    ]
    all_data = [headers] + all_rows

    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(GSHEET_KEY).worksheet(GSHEET_WORKSHEET)
        sheet.clear()
        sheet.update(range_name="A1", values=all_data)
        print("✅ บันทึกข้อมูลสำเร็จ! ตรวจสอบ Google Sheets ได้เลย")
    except Exception as e:
        print(f"   ❌ ล้มเหลวในการบันทึกข้อมูล: {e}")


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
        # ใช้ holder อันดับ 1 ที่เป็น Supernode (แต่ไม่มี label) และไม่ใช่ CEX/DEX/Contract
        for w in holders:
            details = w.get("address_details", {})
            if (details.get("is_supernode") and 
                not details.get("label") and 
                not details.get("is_contract") and 
                not details.get("is_cex") and 
                not details.get("is_dex")):
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

    # Step 2: Recursive Magic Expand
    all_addresses = run_recursive_magic_expand(token_address, chain, holders, MAX_MAGIC_ROUNDS)
    
    # Step 3: Subgraph
    relationships = fetch_subgraph_data(token_address, chain, all_addresses)

    # Step 4: Calculate Cluster
    cluster_data = calculate_cluster(wallet_address, relationships, holders, TARGET_WALLET)
    cluster_size = cluster_data["size"]
    cluster_amount = cluster_data["amount"]
    cluster_supply_pct = cluster_data["share_pct"]
    top_cluster_wallet = cluster_data["top_cluster_wallet"]

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
    print("📋 กำลังอ่านรายชื่อ token จากชีต subscribetokens...")
    token_pairs = read_subscribe_tokens()

    if not token_pairs:
        print("❌ ไม่พบรายชื่อ token ในชีต subscribetokens")
        exit()

    print(f"✅ พบ {len(token_pairs)} token(s) ที่ต้องวิเคราะห์\n")

    # สะสมผลลัพธ์ทุก token
    all_results = []

    for idx, (token_address, chain) in enumerate(token_pairs):
        try:
            row = analyze_token(token_address, chain)
            if row:
                all_results.append(row)
                print(f"   📝 สะสมผล: {len(all_results)}/{len(token_pairs)}")
        except Exception as e:
            print(f"❌ Error วิเคราะห์ {token_address[:12]}...: {e}")

        # หน่วงเวลาระหว่าง token (ยกเว้นตัวสุดท้าย)
        if idx < len(token_pairs) - 1:
            print(f"\n⏳ รอ {DELAY_BETWEEN_TOKENS} วินาที ก่อนวิเคราะห์ตัวถัดไป...")
            time.sleep(DELAY_BETWEEN_TOKENS)

    # Bulk write ทีเดียว
    if all_results:
        write_to_gsheet(all_results)
    else:
        print("❌ ไม่มีผลลัพธ์ที่ต้องบันทึก")

    print(f"\n🏁 วิเคราะห์ครบทั้ง {len(token_pairs)} token(s) — บันทึก {len(all_results)} แถว!")