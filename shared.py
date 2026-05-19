import uuid
import time
import requests
# pyrefly: ignore [missing-import]
import jwt
# pyrefly: ignore [missing-import]
import gspread
# pyrefly: ignore [missing-import]
from google.oauth2.service_account import Credentials

# ── Google Sheets ──
GSHEET_KEY = "1VIu93hO3e8pTRC1FD8z3yehCvGqxGV1EfT41IIwLH7g"
CREDENTIALS_FILE = "credentials.json"

# ── API Auth ──
_JWT_SECRET = "LTJBO6Dsb5dEJ9pS"
SESSION_ID = str(uuid.uuid4())
API_BASE = "https://api.bubblemaps.io"

COMMON_HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": "https://v2.bubblemaps.io",
    "referer": "https://v2.bubblemaps.io/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "x-session-id": SESSION_ID,
}

def get_gsheet_client():
    """Initializes and returns a Google Sheets client."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return gspread.authorize(creds)

def _make_validation(api_path):
    """Generates x-validation JWT token for the given API path."""
    payload = {"data": api_path, "exp": int(time.time()) + 300}
    return jwt.encode(payload, _JWT_SECRET, algorithm="HS256")

def fetch_top_holders(token_address, chain, count=250):
    """Fetches Top Holders from the API."""
    url = f"{API_BASE}/addresses/token-top-holders?count={count}&nocache=false"
    payload = {"address": token_address, "chain": chain}
    headers = {**COMMON_HEADERS, "x-validation": _make_validation(f"/addresses/token-top-holders?count={count}&nocache=false")}

    print(f"1️⃣ กำลังดึงรายชื่อ Top {count} Holders...")
    print(f"   📡 POST {url}")
    response = requests.post(url, json=payload, headers=headers)
    print(f"   📥 Response: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        holders = data if isinstance(data, list) else data.get('holders', data.get('data', []))

        supernodes = sum(1 for h in holders if h.get('address_details', {}).get('is_supernode'))
        contracts = sum(1 for h in holders if h.get('address_details', {}).get('is_contract'))
        cex_count = sum(1 for h in holders if h.get('address_details', {}).get('is_cex'))
        dex_count = sum(1 for h in holders if h.get('address_details', {}).get('is_dex'))
        normal = len(holders) - supernodes - contracts - cex_count - dex_count

        print(f"   ✅ ได้ Holders ทั้งหมด: {len(holders)} ราย")
        print(f"   ├─ 👤 Normal Wallets: {normal}")
        print(f"   ├─ 🌐 Supernodes: {supernodes}")
        print(f"   ├─ 📜 Contracts: {contracts}")
        print(f"   ├─ 🏦 CEX: {cex_count}")
        print(f"   └─ 💱 DEX: {dex_count}")
        return holders
    else:
        print(f"❌ Error Holders API: {response.status_code} - {response.text}")
        return []

def fetch_magic_expand_once(token_address, chain, addresses_list):
    """Calls Magic Expand API once and returns a list of holder objects."""
    url = f"{API_BASE}/addresses/expand/magic"
    payload = {
        "addresses": addresses_list,
        "token_ref": {"chain": chain, "address": token_address}
    }
    headers = {**COMMON_HEADERS, "x-validation": _make_validation("/addresses/expand/magic")}

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data if isinstance(data, list) else data.get('addresses', data.get('data', []))
    else:
        print(f"   ⚠️ Magic Expand ไม่สำเร็จ: {response.status_code} - {response.text}")
        return []

def fetch_subgraph_data(token_address, chain, addresses_list):
    """Fetches Subgraph relationships between all provided addresses."""
    url = f"{API_BASE}/relationships/subgraph?whitelist_token_address={token_address}&whitelist_token_chain={chain}"
    payload = addresses_list
    headers = {**COMMON_HEADERS, "x-validation": _make_validation(f"/relationships/subgraph?whitelist_token_address={token_address}&whitelist_token_chain={chain}")}

    print(f"\n3️⃣ กำลังส่งรายชื่อกระเป๋าทั้งหมด ({len(addresses_list)} ใบ) ไปหาเส้นความสัมพันธ์ (Subgraph)...")
    print(f"   📡 POST {url}")
    response = requests.post(url, json=payload, headers=headers)
    print(f"   📥 Response: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ ได้ Relationships ทั้งหมด: {len(data)} เส้น")
        return data
    else:
        print(f"❌ Error Subgraph API: {response.status_code} - {response.text}")
        return []

def run_recursive_magic_expand(token_address, chain, holders, max_rounds=1):
    """
    Recursively calls Magic Expand API up to max_rounds times.
    Appends new full objects to `holders` to retain metadata for filtering.
    Returns a list of all expanded addresses (strings).
    """
    all_addresses_set = set(h.get("address") for h in holders if h.get("address"))
    total_new = 0
    total_supernodes = 0
    total_hidden = 0

    print(f"\n2️⃣ Recursive Magic Expand (สูงสุด {max_rounds} รอบ)")

    for round_num in range(1, max_rounds + 1):
        current_addresses = list(all_addresses_set)
        print(f"\n   🔄 รอบที่ {round_num}: ส่ง {len(current_addresses)} addresses...")

        magic_results = fetch_magic_expand_once(token_address, chain, current_addresses)
        if not magic_results:
            print(f"   ⚠️  ไม่ได้ผลลัพธ์ — หยุด")
            break

        round_new = 0
        round_supernodes = 0
        round_hidden = 0

        for item in magic_results:
            if isinstance(item, dict):
                addr = item.get("address", "")
                if addr and addr not in all_addresses_set:
                    round_new += 1
                    all_addresses_set.add(addr)
                    holders.append(item)
                    details = item.get("address_details", {})
                    if details.get("is_supernode"):
                        round_supernodes += 1
                    if details.get("is_contract") or details.get("is_cex") or details.get("is_dex"):
                        round_hidden += 1
            elif isinstance(item, str):
                if item not in all_addresses_set:
                    round_new += 1
                    all_addresses_set.add(item)

        total_new += round_new
        total_supernodes += round_supernodes
        total_hidden += round_hidden

        print(f"   ✅ รอบ {round_num}: เจอกระเป๋าใหม่ {round_new} ใบ (Supernodes: {round_supernodes}, Hidden: {round_hidden})")

        if round_new == 0:
            print(f"   🏁 ไม่มีกระเป๋าใหม่แล้ว — หยุดวนลูป")
            break

    print(f"\n   📊 สรุป Magic Expand ทั้งหมด:")
    print(f"      ├─ กระเป๋าใหม่รวม: {total_new} ใบ")
    print(f"      ├─ Supernodes: {total_supernodes}")
    print(f"      └─ Hidden (CEX/DEX/Contract): {total_hidden}")
    print(f"\n   📦 Addresses รวมทั้งหมด: {len(all_addresses_set)} ใบ")

    return list(all_addresses_set)

def calculate_cluster(target_wallet_address, relationships, all_holders, target_wallet_config=""):
    """
    Analyzes the cluster using Bubblemaps rules (matching the frontend logic exactly).
    Returns metrics and the center node of the cluster.
    """
    print(f"\n4️⃣ กำลังวิเคราะห์ Cluster ของ {target_wallet_address[:8]}...{target_wallet_address[-6:]}")

    if not relationships:
        print("   ⚠️  ไม่มี Relationships เลย — ไม่สามารถหา Cluster ได้")
        return {"amount": 0.0, "share_pct": 0.0, "size": 0, "center_wallet": target_wallet_address, "center_amount": 0.0, "center_share": 0.0, "center_label": "N/A", "top_cluster_wallet": target_wallet_address}

    # 1. Create lookup table & normalize addresses to lowercase
    holder_map = {}
    for h in all_holders:
        addr = h.get("address")
        if addr:
            holder_map[addr.lower()] = h

    # 2. Burn addresses that are always hidden
    B6 = {
        "0x0000000000000000000000000000000000000000",
        "0x000000000000000000000000000000000000dead",
        "0xdead000000000000000042069420694206942069",
        "0xdeaddeaddeaddeaddeaddeaddeaddeaddead0000",
        "0x0000000000000000000000000000000000000001"
    }

    # 3. Determine visible nodes based on default filter logic (z6)
    visible_addresses = set()
    supernode_addresses = set()
    for a, h in holder_map.items():
        if a in B6:
            continue
        
        details = h.get("address_details", {})
        if details.get("is_supernode", False):
            supernode_addresses.add(a)
            
        is_cex = details.get("is_cex", False)
        is_dex = details.get("is_dex", False)
        is_contract = details.get("is_contract", False)
        degree = details.get("degree", 0)

        if is_cex or is_dex or is_contract:
            is_visible = False
        else:
            is_visible = degree < 200000
            
        if is_visible:
            visible_addresses.add(a)

    print(f"   👁️ Visible addresses: {len(visible_addresses)} ใบ")

    # 4. Build graph: exclude self-loops and hidden nodes
    graph = {}
    total_edges = 0
    kept_edges = 0

    for rel in relationships:
        from_addr = rel.get("from_address", "").lower()
        to_addr = rel.get("to_address", "").lower()
        if not from_addr or not to_addr:
            continue
            
        total_edges += 1
        if from_addr == to_addr:
            continue
        if from_addr not in visible_addresses or to_addr not in visible_addresses:
            continue

        kept_edges += 1
        graph.setdefault(from_addr, set()).add(to_addr)
        graph.setdefault(to_addr, set()).add(from_addr)

    print(f"   📊 กราฟ: {total_edges} เส้นทั้งหมด → {kept_edges} visible edges, {len(graph)} nodes")

    # 5. BFS: Find all connected components of size >= 2
    visited = set()
    clusters = []

    for node in visible_addresses:
        if node not in visited:
            comp = []
            queue = [node]
            visited.add(node)
            while queue:
                curr = queue.pop(0)
                comp.append(curr)
                for neighbor in graph.get(curr, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            if len(comp) >= 2:
                clusters.append(comp)
                
    print(f"   🔍 พบ Clusters ทั้งหมด (ขนาด >= 2): {len(clusters)} กลุ่ม")

    # 6. Select target cluster
    target_cluster = None
    if target_wallet_config and target_wallet_config.lower() in holder_map:
        for comp in clusters:
            if target_wallet_config.lower() in comp:
                target_cluster = comp
                break
        if not target_cluster:
            target_cluster = [target_wallet_config.lower()]
            print(f"   ⚠️  Target wallet ไม่เชื่อมกับใครเลย — นับแค่ตัวเอง")
    else:
        def cluster_supply(comp):
            return sum(holder_map.get(a, {}).get("holder_data", {}).get("share", 0) for a in comp)

        if clusters:
            target_cluster = max(clusters, key=cluster_supply)
        else:
            target_cluster = [target_wallet_address.lower()]
            
    # Find Center Node (F6 logic: max connections within the cluster)
    center_node = target_cluster[0]
    max_connections = -1
    for node in target_cluster:
        connections_in_cluster = len([n for n in graph.get(node, []) if n in target_cluster])
        if connections_in_cluster > max_connections:
            max_connections = connections_in_cluster
            center_node = node
            
    wallet_address = center_node
    center_holder = holder_map.get(wallet_address, {})
    amount = center_holder.get("holder_data", {}).get("amount", 0)
    share = center_holder.get("holder_data", {}).get("share", 0)
    label = center_holder.get("address_details", {}).get("label", "N/A")
    
    print(f"   🌟 Center Node (F6): {wallet_address} (Connections: {max_connections})")

    cluster_wallets = set(target_cluster)
    supernodes_in_cluster = cluster_wallets & supernode_addresses
    print(f"   🔍 สรุป Cluster: {len(cluster_wallets)} กระเป๋า (รวม {len(supernodes_in_cluster)} supernodes)")

    # 7. Calculate final metrics
    total_cluster_amount = 0.0
    total_cluster_share = 0.0
    cluster_members = []

    for addr in cluster_wallets:
        h = holder_map.get(addr)
        if h:
            s = h.get("holder_data", {}).get("share", 0)
            a = h.get("holder_data", {}).get("amount", 0)
            l = h.get("address_details", {}).get("label", "")
            
            total_cluster_share += s
            total_cluster_amount += a
            cluster_members.append((addr, a, s, l))

    print(f"\n   📋 รายชื่อสมาชิก Cluster ({len(cluster_members)} ราย):")
    print(f"   {'─'*90}")
    print(f"   {'#':<4} {'Address':<48} {'Amount':>18} {'Share':>8}  Label")
    print(f"   {'─'*90}")
    for i, (addr, amt, sh, lbl) in enumerate(sorted(cluster_members, key=lambda x: -x[2]), 1):
        label_str = lbl if lbl else "-"
        print(f"   {i:<4} {addr:<48} {amt:>18,.2f} {sh*100:>7.2f}%  {label_str}")
    print(f"   {'─'*90}")
    print(f"   {'TOTAL':<53} {total_cluster_amount:>18,.2f} {total_cluster_share*100:>7.2f}%")

    top_cluster_wallet = sorted(cluster_members, key=lambda x: -x[2])[0][0] if cluster_members else ""

    return {
        "amount": total_cluster_amount,
        "share_pct": total_cluster_share * 100,
        "size": len(cluster_members),
        "top_cluster_wallet": top_cluster_wallet,
        "center_wallet": wallet_address,
        "center_amount": amount,
        "center_share": share,
        "center_label": label
    }
