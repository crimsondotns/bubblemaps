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

for count in [150, 250]:
    url = f"{API_BASE}/addresses/token-top-holders?count={count}&nocache=false"
    h = {**HEADERS, "x-validation": _make_validation(f"/addresses/token-top-holders?count={count}&nocache=false")}
    resp = requests.post(url, json={"address": token_addr, "chain": chain}, headers=h)
    holders = resp.json()
    addrs = [x["address"] for x in holders]
    
    for rounds in [0, 1]:
        if rounds == 0:
            all_holders = holders
        else:
            url2 = f"{API_BASE}/addresses/expand/magic"
            h2 = {**HEADERS, "x-validation": _make_validation("/addresses/expand/magic")}
            resp2 = requests.post(url2, json={"addresses": addrs, "token_ref": {"chain": chain, "address": token_addr}}, headers=h2)
            magic = resp2.json() if isinstance(resp2.json(), list) else resp2.json().get("addresses", [])
            all_holders = holders + magic
            
        all_addrs = list(set(x["address"] for x in all_holders))
        
        holder_map = {}
        for x in all_holders:
            a = x.get("address","").lower()
            if a: holder_map[a] = x
            
        hidden_cex = set()
        hidden_dex = set()
        hidden_contract = set()
        supernodes = set()
        for a, x in holder_map.items():
            d = x.get("address_details", {})
            if d.get("is_supernode"): supernodes.add(a)
            if d.get("is_cex"): hidden_cex.add(a)
            if d.get("is_dex"): hidden_dex.add(a)
            if d.get("is_contract"): hidden_contract.add(a)
            
        url3 = f"{API_BASE}/relationships/subgraph?whitelist_token_address={token_addr}&whitelist_token_chain={chain}"
        h3 = {**HEADERS, "x-validation": _make_validation(f"/relationships/subgraph?whitelist_token_address={token_addr}&whitelist_token_chain={chain}")}
        resp3 = requests.post(url3, json=all_addrs, headers=h3)
        rels = resp3.json()
        
        for showCex in [False, True]:
            for showDex in [False, True]:
                for showContracts in [False, True]:
                    hide = set()
                    if not showCex: hide.update(hidden_cex)
                    if not showDex: hide.update(hidden_dex)
                    if not showContracts: hide.update(hidden_contract)
                    
                    visible = set(holder_map.keys()) - hide
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
                        
                    # Also count without magic nodes (i.e. strictly ruleNodes in cluster)
                    # wait, ruleNodes = top holders
                    # magicNodes = expanded nodes
                    # Let's count how many addresses in the visited set belong to holders vs magic
                    top_holders_in_cluster = [a for a in visited if a in [x["address"].lower() for x in holders]]
                    top_holders_with_balance = sum(1 for a in top_holders_in_cluster if holder_map.get(a, {}).get("holder_data", {}).get("share", 0) > 0)
                    top_holders_share = sum(holder_map.get(a, {}).get("holder_data", {}).get("share", 0) for a in top_holders_in_cluster)
                    
                    with_balance = sum(1 for a in visited if holder_map.get(a, {}).get("holder_data", {}).get("share", 0) > 0)
                    total_share = sum(holder_map.get(a, {}).get("holder_data", {}).get("share", 0) for a in visited)
                    
                    print(f"cnt={count} rnds={rounds} C={showCex} D={showDex} K={showContracts} | Full: sz={len(visited)} bal={with_balance} sh={total_share*100:.2f}% | TopOnly: sz={len(top_holders_in_cluster)} bal={top_holders_with_balance} sh={top_holders_share*100:.2f}%")
