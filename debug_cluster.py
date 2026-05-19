import requests, uuid, time, jwt

_JWT_SECRET = "LTJBO6Dsb5dEJ9pS"
SESSION_ID = str(uuid.uuid4())

def _make_validation(api_path):
    payload = {"data": api_path, "exp": int(time.time()) + 300}
    return jwt.encode(payload, _JWT_SECRET, algorithm="HS256")

API_BASE = "https://api.bubblemaps.io"
HEADERS = {"accept": "application/json", "content-type": "application/json", "origin": "https://v2.bubblemaps.io", "x-session-id": SESSION_ID}

token = "0xf819d9cb1c2a819fd991781a822de3ca8607c3c9"
chain = "eth"
target = "0xa4644953ad98ed5a7ff106ed9a3909c9aebcbc31"

# Fetch holders
url = f"{API_BASE}/addresses/token-top-holders?count=250&nocache=false"
h = {**HEADERS, "x-validation": _make_validation(f"/addresses/token-top-holders?count=250&nocache=false")}
resp = requests.post(url, json={"address": token, "chain": chain}, headers=h)
holders = resp.json()

# Magic expand 1 round
addrs = [x["address"] for x in holders]
url2 = f"{API_BASE}/addresses/expand/magic"
h2 = {**HEADERS, "x-validation": _make_validation("/addresses/expand/magic")}
resp2 = requests.post(url2, json={"addresses": addrs, "token_ref": {"chain": chain, "address": token}}, headers=h2)
magic = resp2.json()
all_holders = holders + (magic if isinstance(magic, list) else magic.get("addresses", []))
all_addrs = list(set(x["address"] for x in all_holders))

# Build holder map
holder_map = {}
for x in all_holders:
    a = x.get("address","").lower()
    if a: holder_map[a] = x

hidden = set()
supernodes = set()
for a, x in holder_map.items():
    d = x.get("address_details", {})
    if d.get("is_supernode"): supernodes.add(a)
    if d.get("is_contract") or d.get("is_cex") or d.get("is_dex"): hidden.add(a)

visible = set(holder_map.keys()) - hidden

# Subgraph
url3 = f"{API_BASE}/relationships/subgraph?whitelist_token_address={token}&whitelist_token_chain={chain}"
h3 = {**HEADERS, "x-validation": _make_validation(f"/relationships/subgraph?whitelist_token_address={token}&whitelist_token_chain={chain}")}
resp3 = requests.post(url3, json=all_addrs, headers=h3)
rels = resp3.json()

# Find target's neighbors
t = target.lower()
neighbors = set()
for r in rels:
    f = r.get("from_address","").lower()
    to = r.get("to_address","").lower()
    if f == t and to != t: neighbors.add(to)
    if to == t and f != t: neighbors.add(f)

print(f"Target: {t}")
print(f"Target neighbors (ALL): {len(neighbors)}")
print(f"Target visible neighbors: {len(neighbors & visible)}")
print(f"Target hidden neighbors: {len(neighbors & hidden)}")
print(f"Target supernode neighbors: {len(neighbors & supernodes)}")

for n in sorted(neighbors & visible)[:5]:
    is_sn = "SN" if n in supernodes else "  "
    # How many visible connections does this neighbor have?
    nn = set()
    for r in rels:
        f = r.get("from_address","").lower()
        to = r.get("to_address","").lower()
        if f == n and to != n and to in visible: nn.add(to)
        if to == n and f != n and f in visible: nn.add(f)
    print(f"  {is_sn} {n[:12]}... → {len(nn)} visible connections")
