import os
import sys
import uuid
import time
import requests
import datetime
# pyrefly: ignore [missing-import]
import jwt
# pyrefly: ignore [missing-import]
import gspread
# pyrefly: ignore [missing-import]
from google.oauth2.service_account import Credentials
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ── Google Sheets ──
GSHEET_KEY = os.getenv("GSHEET_KEY")
CREDENTIALS_FILE = "credentials.json"

# ── API Auth ──
_JWT_SECRET = os.getenv("JWT_SECRET")
SESSION_ID = str(uuid.uuid4())
API_BASE = os.getenv("API_BASE")
API_ORIGIN = os.getenv("API_ORIGIN")

if not all([GSHEET_KEY, _JWT_SECRET, API_BASE, API_ORIGIN]):
    print("Execution Error: Missing required configurations.")
    sys.exit(1)

COMMON_HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": API_ORIGIN,
    "referer": f"{API_ORIGIN}/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "x-session-id": SESSION_ID,
}

def get_formatted_time():
    """Returns current time in requested format: m/d/yyyy H:mm:ss"""
    return datetime.datetime.now().strftime("%-m/%-d/%Y %H:%M:%S")

def get_gsheet_client():
    """Initializes and returns a Google Sheets client."""
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        return gspread.authorize(creds)
    except Exception:
        print("Error: Could not initialize data store connection.")
        sys.exit(1)

def _make_validation(api_path):
    """Generates x-validation JWT token for the given API path."""
    try:
        payload = {"data": api_path, "exp": int(time.time()) + 300}
        return jwt.encode(payload, _JWT_SECRET, algorithm="HS256")
    except Exception:
        print("Error: Could not generate validation token.")
        sys.exit(1)

def fetch_top_holders(token_address, chain, count=250):
    """Fetches Top Holders from the target API."""
    try:
        url = f"{API_BASE}/addresses/token-top-holders?count={count}&nocache=false"
        payload = {"address": token_address, "chain": chain}
        headers = {**COMMON_HEADERS, "x-validation": _make_validation(f"/addresses/token-top-holders?count={count}&nocache=false")}

        print(f"1️⃣ Fetching top {count} entities...")
        response = requests.post(url, json=payload, headers=headers)
        print(f"   📥 Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            holders = data if isinstance(data, list) else data.get('holders', data.get('data', []))

            supernodes = sum(1 for h in holders if h.get('address_details', {}).get('is_supernode'))
            contracts = sum(1 for h in holders if h.get('address_details', {}).get('is_contract'))
            cex_count = sum(1 for h in holders if h.get('address_details', {}).get('is_cex'))
            dex_count = sum(1 for h in holders if h.get('address_details', {}).get('is_dex'))
            normal = len(holders) - supernodes - contracts - cex_count - dex_count

            print(f"   ✅ Fetched entities: {len(holders)}")
            print(f"   ├─ 👤 Type N: {normal}")
            print(f"   ├─ 🌐 Type S: {supernodes}")
            print(f"   ├─ 📜 Type C: {contracts}")
            print(f"   ├─ 🏦 Type X: {cex_count}")
            print(f"   └─ 💱 Type D: {dex_count}")
            return holders
        else:
            print(f"❌ Target Error 1: {response.status_code}")
            return []
    except Exception:
        print("❌ Unexpected error during fetch step 1.")
        return []

def fetch_magic_expand_once(token_address, chain, addresses_list):
    """Calls expansion API once and returns a list of objects."""
    try:
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
            print(f"   ⚠️ Expand failed: {response.status_code}")
            return []
    except Exception:
        print("❌ Unexpected error during expansion.")
        return []

def fetch_subgraph_data(token_address, chain, addresses_list):
    """Fetches relationships between all provided addresses."""
    try:
        url = f"{API_BASE}/relationships/subgraph?whitelist_token_address={token_address}&whitelist_token_chain={chain}"
        payload = addresses_list
        headers = {**COMMON_HEADERS, "x-validation": _make_validation(f"/relationships/subgraph?whitelist_token_address={token_address}&whitelist_token_chain={chain}")}

        print(f"\n3️⃣ Requesting relationships for ({len(addresses_list)}) entities...")
        response = requests.post(url, json=payload, headers=headers)
        print(f"   📥 Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Fetched relationships: {len(data)}")
            return data
        else:
            print(f"❌ Target Error 2: {response.status_code}")
            return []
    except Exception:
        print("❌ Unexpected error during fetch step 3.")
        return []

def run_recursive_magic_expand(token_address, chain, holders, max_rounds=1):
    """
    Recursively calls expansion API up to max_rounds times.
    Appends new full objects to `holders` to retain metadata for filtering.
    Returns a list of all expanded addresses (strings).
    """
    try:
        all_addresses_set = set(h.get("address") for h in holders if h.get("address"))
        total_new = 0
        total_supernodes = 0
        total_hidden = 0

        print(f"\n2️⃣ Recursive Expansion (max {max_rounds} rounds)")

        for round_num in range(1, max_rounds + 1):
            current_addresses = list(all_addresses_set)
            print(f"\n   🔄 Round {round_num}: Sending {len(current_addresses)} entities...")

            magic_results = fetch_magic_expand_once(token_address, chain, current_addresses)
            if not magic_results:
                print(f"   ⚠️  No results — stopping.")
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

            print(f"   ✅ Round {round_num}: Found {round_new} new (S: {round_supernodes}, H: {round_hidden})")

            if round_new == 0:
                print(f"   🏁 No new entities — stopping.")
                break

        print(f"\n   📊 Expansion Summary:")
        print(f"      ├─ Total new: {total_new}")
        print(f"      ├─ Type S: {total_supernodes}")
        print(f"      └─ Type H: {total_hidden}")
        print(f"\n   📦 Total entities: {len(all_addresses_set)}")

        return list(all_addresses_set)
    except Exception:
        print("❌ Unexpected error during expansion loop.")
        return []

def calculate_cluster(target_wallet_address, relationships, all_holders, target_wallet_config=""):
    """
    Analyzes the group using generic connectivity rules.
    Returns metrics and the center node of the group.
    """
    try:
        print(f"\n4️⃣ Analyzing group for {target_wallet_address[:8]}...{target_wallet_address[-6:]}")

        if not relationships:
            print("   ⚠️  No relationships found — skipping group logic.")
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

        # 3. Determine visible nodes based on default filter logic
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

        print(f"   👁️ Visible nodes: {len(visible_addresses)}")

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

        print(f"   📊 Net: {total_edges} total -> {kept_edges} visible edges, {len(graph)} active nodes")

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
                    
        print(f"   🔍 Found groups (size >= 2): {len(clusters)}")

        # 6. Select target group
        target_cluster = None
        if target_wallet_config and target_wallet_config.lower() in holder_map:
            for comp in clusters:
                if target_wallet_config.lower() in comp:
                    target_cluster = comp
                    break
            if not target_cluster:
                target_cluster = [target_wallet_config.lower()]
                print(f"   ⚠️  Target not connected — single node group")
        else:
            def cluster_supply(comp):
                return sum(holder_map.get(a, {}).get("holder_data", {}).get("share", 0) for a in comp)

            if clusters:
                target_cluster = max(clusters, key=cluster_supply)
            else:
                target_cluster = [target_wallet_address.lower()]
                
        # Find Center Node (max connections within the group)
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
        
        print(f"   🌟 Center Node: {wallet_address} (Conns: {max_connections})")

        cluster_wallets = set(target_cluster)
        supernodes_in_cluster = cluster_wallets & supernode_addresses
        print(f"   🔍 Group summary: {len(cluster_wallets)} entities (incl {len(supernodes_in_cluster)} Type S)")

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

        print(f"\n   📋 Group Roster ({len(cluster_members)} entities):")
        print(f"   {'─'*90}")
        print(f"   {'#':<4} {'Entity':<48} {'Val':>18} {'Pct':>8}  Tag")
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
    except Exception:
        print("❌ Unexpected error during calculation.")
        return {"amount": 0.0, "share_pct": 0.0, "size": 0, "center_wallet": target_wallet_address, "center_amount": 0.0, "center_share": 0.0, "center_label": "N/A", "top_cluster_wallet": target_wallet_address}
