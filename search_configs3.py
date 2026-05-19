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
target = "0xa4644953ad98ed5a7ff106ed9a3909c9aebcbc31".lower()

burn_addresses = {
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
    "0xdead000000000000000042069420694206942069",
    "0xdeaddeaddeaddeaddeaddeaddeaddeaddead0000",
    "0x0000000000000000000000000000000000000001"
}

for count in [250, 500, 1000]:
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
        
    for showCex in [False, True]:
        for showDex in [False, True]:
            for showContracts in [False, True]:
                
                visible = set()
                for a, x in holder_map.items():
                    if a in burn_addresses: continue
                    d = x.get("address_details", {})
                    is_cex = d.get("is_cex", False)
                    is_dex = d.get("is_dex", False)
                    is_contract = d.get("is_contract", False)
                    degree = d.get("degree", 0)
                    
                    if is_cex or is_dex or is_contract:
                        is_vis = (is_cex and showCex) or (is_dex and showDex) or (is_contract and showContracts)
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
                    
                visited = set()
                queue = [target]
                if target in graph:
                    while queue:
                        c = queue.pop(0)
                        if c not in visited:
                            visited.add(c)
                            queue.extend(graph.get(c, []))
                else:
                    visited.add(target)
                    
                cluster_members = [a for a in visited if holder_map.get(a, {}).get("holder_data", {}).get("share", 0) > 0]
                total_share = sum(holder_map.get(a, {}).get("holder_data", {}).get("share", 0) for a in cluster_members)
                
                print(f"cnt={count} C={showCex} D={showDex} K={showContracts} | Cluster Size: {len(cluster_members)} | Supply: {total_share*100:.2f}%")
