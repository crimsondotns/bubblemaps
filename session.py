import time
from shared import (
    fetch_top_holders,
    run_recursive_magic_expand,
    fetch_subgraph_data,
    calculate_cluster,
    get_gsheet_client,
    GSHEET_KEY
)

# ╔═══════════════════════════════════════════════════════════════════╗
# ║                     🔧 SETTINGS — แก้ตรงนี้                      ║
# ╚═══════════════════════════════════════════════════════════════════╝

# ── Token ที่ต้องการวิเคราะห์ ──
TARGET_TOKEN = "GHichsGq8aPnqJyz6Jp1ASTK4PNLpB5KrD6XrfDjpump"
TARGET_CHAIN = "solana"
TARGET_WALLET = ""  # ระบุ address ที่ต้องการดู cluster (เว้นว่าง = ใช้ holder อันดับ 1)
FETCH_COUNT = 250
MAX_MAGIC_ROUNDS = 5  # จำนวนรอบสูงสุดของ Recursive Magic Expand

# ── Google Sheets ──
GSHEET_KEY = "1VIu93hO3e8pTRC1FD8z3yehCvGqxGV1EfT41IIwLH7g"
GSHEET_WORKSHEET = "bubblemaps.io"
CREDENTIALS_FILE = "credentials.json"




# ─────────────────────── Google Sheets ───────────────────────────────

def write_to_gsheet(data_row):
    """บันทึกผลลัพธ์ลง Google Sheets"""
    print("\n5️⃣ กำลังบันทึกลง Google Sheets...")
    try:
        client = get_gsheet_client()

        sheet = client.open_by_key(GSHEET_KEY).worksheet(GSHEET_WORKSHEET)
        sheet.clear()
        headers = [
            "Token Address", "Chain", "Wallet Address",
            "Wallet Amount", "Wallet Share (%)", "Label",
            "Cluster Size (Addresses)", "Cluster Amount", "Cluster Supply (%)",
        ]
        sheet.append_row(headers)
        sheet.append_row(data_row)
        print("✅ บันทึกข้อมูลสำเร็จ! ตรวจสอบ Google Sheets ได้เลย")
    except Exception as e:
        print(f"❌ Error Google Sheets: {e}")


# ─────────────────────── Main ────────────────────────────────────────

if __name__ == "__main__":
    # Step 1: ดึง Top Holders
    holders = fetch_top_holders(TARGET_TOKEN, TARGET_CHAIN, FETCH_COUNT)
    if not holders:
        exit()

    # หา Target Wallet
    target_wallet = None
    if TARGET_WALLET:
        # ใช้ wallet ที่ระบุใน settings
        for w in holders:
            if w.get("address") == TARGET_WALLET:
                target_wallet = w
                break
        if not target_wallet:
            print(f"⚠️ ไม่พบ {TARGET_WALLET} ใน Top {FETCH_COUNT} — ใช้ holder อันดับ 1 แทน")
            target_wallet = holders[0]
    else:
        # ใช้ holder อันดับ 1 ที่ไม่ใช่ CEX/DEX/Contract (supernode OK)
        for w in holders:
            details = w.get("address_details", {})
            if not details.get("is_contract") and not details.get("is_cex") and not details.get("is_dex"):
                target_wallet = w
                break
        if not target_wallet:
            target_wallet = holders[0]

    if not target_wallet:
        print("❌ ไม่พบ Wallet ที่ตรงตามเงื่อนไข")
        exit()

    wallet_address = target_wallet.get("address")
    amount = target_wallet.get("holder_data", {}).get("amount", 0)
    share = target_wallet.get("holder_data", {}).get("share", 0)
    label = target_wallet.get("address_details", {}).get("label", "N/A")

    print(f"\n🎯 เจอ Top Wallet: {wallet_address}")
    print(f"   ├─ Amount: {amount:,.2f}")
    print(f"   ├─ Share: {share*100:.2f}%")
    print(f"   └─ Label: {label}")

    # Step 2: Recursive Magic Expand
    all_addresses = run_recursive_magic_expand(TARGET_TOKEN, TARGET_CHAIN, holders, MAX_MAGIC_ROUNDS)
    print(f"\n   📦 Addresses รวมทั้งหมด: {len(all_addresses)} ใบ")

    # Step 3: Subgraph
    relationships = fetch_subgraph_data(TARGET_TOKEN, TARGET_CHAIN, all_addresses)

    # Step 4: Calculate Cluster
    cluster_data = calculate_cluster(wallet_address, relationships, holders, TARGET_WALLET)
    cluster_size = cluster_data["size"]
    cluster_amount = cluster_data["amount"]
    cluster_supply_pct = cluster_data["share_pct"]
    wallet_address = cluster_data["center_wallet"]
    amount = cluster_data["center_amount"]
    share = cluster_data["center_share"]
    label = cluster_data["center_label"]

    print(f"\n{'='*60}")
    print(f"🔥 สรุปผลลัพธ์ Cluster Analysis")
    print(f"{'='*60}")
    print(f"   Token:          {TARGET_TOKEN}")
    print(f"   Chain:          {TARGET_CHAIN}")
    print(f"   Target Wallet:  {wallet_address}")
    print(f"   Cluster Size:   {cluster_size} กระเป๋า")
    print(f"   Cluster Amount: {cluster_amount:,.2f}")
    print(f"   Cluster Supply: {cluster_supply_pct:.2f}%")
    print(f"{'='*60}")

    # Step 5: Write to Google Sheets (share/supply เก็บเป็นทศนิยม ÷100)
    row_data = [
        TARGET_TOKEN, TARGET_CHAIN, wallet_address,
        amount, share, label,
        cluster_size, cluster_amount, cluster_supply_pct / 100,
    ]
    write_to_gsheet(row_data)