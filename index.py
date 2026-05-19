from shared import (
    fetch_top_holders,
    get_gsheet_client,
    GSHEET_KEY
)

def get_top_wallet(token_address, chain):
    holders = fetch_top_holders(token_address, chain, count=250)
    
    if holders:
        # วนลูปหา Top Wallet แรกที่ตรงตามเงื่อนไข (is_supernode, is_contract, is_cex, is_dex เป็น False ทั้งหมด)
        for wallet in holders:
            address_details = wallet.get("address_details", {})
            
            is_supernode = address_details.get("is_supernode", False)
            is_contract = address_details.get("is_contract", False)
            is_cex = address_details.get("is_cex", False)
            is_dex = address_details.get("is_dex", False)
            
            if not is_supernode and not is_contract and not is_cex and not is_dex:
                return wallet  # เจอตัวที่ผ่านเงื่อนไข -> ส่งค่ากลับทันที
                
        print("❌ ไม่พบ Wallet ที่ตรงตามเงื่อนไข Filter")
    return None

def write_to_gsheet(wallet_data, token_address, chain):
    print("\nกำลังเชื่อมต่อกับ Google Sheets...")
    
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(GSHEET_KEY).worksheet("bubblemaps.io")
        
        # --- ดึงข้อมูลเพื่อเตรียมเขียน ---
        wallet_address = wallet_data.get("address", "N/A")
        
        holder_data = wallet_data.get("holder_data", {})
        amount = holder_data.get("amount", "N/A")
        share = holder_data.get("share", "N/A")
        
        address_details = wallet_data.get("address_details", {})
        label = address_details.get("label", "N/A")
        
        # จัดเรียงข้อมูล Column A-F ตามที่ต้องการ
        row = [token_address, chain, wallet_address, amount, share, label]
        
        sheet.append_row(row)
        print(f"✅ บันทึกข้อมูลสำเร็จเรียงตามคอลัมน์ A-F ใน bubblemaps.io เรียบร้อยแล้ว!")
        
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดขณะเขียนข้อมูลลง Google Sheets: {e}")

if __name__ == "__main__":
    TARGET_TOKEN = "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv"
    TARGET_CHAIN = "solana"
    
    top_wallet = get_top_wallet(TARGET_TOKEN, TARGET_CHAIN)
    
    if top_wallet:
        # --- แสดง Log อย่างละเอียดก่อนนำไปบันทึก ---
        print("\n" + "="*50)
        print("🎯 ตรวจพบ Top Wallet ที่ผ่านเงื่อนไข:")
        print(f"- Wallet Address: {top_wallet.get('address')}")
        print(f"- Amount: {top_wallet.get('holder_data', {}).get('amount')}")
        print(f"- Share: {top_wallet.get('holder_data', {}).get('share')}")
        print(f"- Label: {top_wallet.get('address_details', {}).get('label')}")
        print("="*50)
        
        # นำไปบันทึกลง Google Sheets
        write_to_gsheet(top_wallet, TARGET_TOKEN, TARGET_CHAIN)