import requests, uuid, time, jwt

_JWT_SECRET = "LTJBO6Dsb5dEJ9pS"
SESSION_ID = str(uuid.uuid4())

def _make_validation(api_path):
    payload = {"data": api_path, "exp": int(time.time()) + 300}
    return jwt.encode(payload, _JWT_SECRET, algorithm="HS256")

API_BASE = "https://api.bubblemaps.io"
HEADERS = {"accept": "application/json", "content-type": "application/json", "origin": "https://v2.bubblemaps.io", "x-session-id": SESSION_ID}

token_addr = "0xf819d9cb1c2a819fd991781a822de3ca8607c3c9"
chain = "eth"

count = 250
url = f"{API_BASE}/addresses/token-top-holders?count={count}&nocache=false"
h = {**HEADERS, "x-validation": _make_validation(f"/addresses/token-top-holders?count={count}&nocache=false")}
resp = requests.post(url, json={"address": token_addr, "chain": chain}, headers=h)
holders = resp.json()
addrs = [x["address"] for x in holders]

# 1 round magic
url2 = f"{API_BASE}/addresses/expand/magic"
h2 = {**HEADERS, "x-validation": _make_validation("/addresses/expand/magic")}
resp2 = requests.post(url2, json={"addresses": addrs, "token_ref": {"chain": chain, "address": token_addr}}, headers=h2)
magic1 = resp2.json() if isinstance(resp2.json(), list) else resp2.json().get("addresses", [])
all_holders = holders + magic1

all_addrs = list(set(x["address"] for x in all_holders))
holder_map = {x["address"].lower(): x for x in all_holders}

url3 = f"{API_BASE}/relationships/subgraph?whitelist_token_address={token_addr}&whitelist_token_chain={chain}"
h3 = {**HEADERS, "x-validation": _make_validation(f"/relationships/subgraph?whitelist_token_address={token_addr}&whitelist_token_chain={chain}")}
resp3 = requests.post(url3, json=all_addrs, headers=h3)
rels = resp3.json()

burn_addresses = {
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
    "0xdead000000000000000042069420694206942069",
    "0xdeaddeaddeaddeaddeaddeaddeaddeaddead0000",
    "0x0000000000000000000000000000000000000001"
}

visible = set()
for a, x in holder_map.items():
    if a in burn_addresses: continue
    d = x.get("address_details", {})
    is_cex = d.get("is_cex", False)
    is_dex = d.get("is_dex", False)
    is_contract = d.get("is_contract", False)
    degree = d.get("degree", 0)
    
    if is_cex or is_dex or is_contract:
        is_vis = False
    else:
        is_vis = degree < 200000
    if is_vis: visible.add(a)

graph = {}
for r in rels:
    f = r.get("from_address","").lower()
    t_ = r.get("to_address","").lower()
    if not f or not t_ or f == t_: continue
    if f not in visible or t_ not in visible: continue
    graph.setdefault(f, set()).add(t_)
    graph.setdefault(t_, set()).add(f)

# Find all components
visited = set()
components = []
for node in visible:
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
            components.append(comp)

# Calculate metrics for each component
print(f"Total components (size >= 2): {len(components)}")
for i, comp in enumerate(components):
    total_share = sum(holder_map.get(a, {}).get("holder_data", {}).get("share", 0) for a in comp)
    total_amt = sum(holder_map.get(a, {}).get("holder_data", {}).get("amount", 0) for a in comp)
    # The web might only count addresses with share > 0 for some things, but let's count both
    addrs_with_share = sum(1 for a in comp if holder_map.get(a, {}).get("holder_data", {}).get("share", 0) > 0)
    print(f"Cluster {i+1}: Size = {len(comp)} (with share: {addrs_with_share}), Amount = {total_amt:.2f}, Supply = {total_share*100:.2f}%")
    if len(comp) > 70 or 4.0 <= total_share*100 <= 5.0:
        print(f"  --> MATCH! Addresses: {len(comp)} or {addrs_with_share}")

print("\n--- Cluster 2 details ---")
comp2 = components[1]
for a in sorted(comp2, key=lambda x: holder_map.get(x, {}).get("holder_data", {}).get("share", 0), reverse=True)[:5]:
    share = holder_map.get(a, {}).get("holder_data", {}).get("share", 0)
    print(f"  {a} | Share: {share*100:.2f}%")

print("\n--- Cluster 15 details ---")
comp15 = components[14]
for a in sorted(comp15, key=lambda x: holder_map.get(x, {}).get("holder_data", {}).get("share", 0), reverse=True)[:5]:
    share = holder_map.get(a, {}).get("holder_data", {}).get("share", 0)
    print(f"  {a} | Share: {share*100:.2f}%")
