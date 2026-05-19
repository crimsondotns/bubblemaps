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

url = f"{API_BASE}/addresses/token-top-holders?count=250&nocache=false"
h = {**HEADERS, "x-validation": _make_validation(f"/addresses/token-top-holders?count=250&nocache=false")}
resp = requests.post(url, json={"address": token_addr, "chain": chain}, headers=h)
holders = resp.json()
addrs = [x["address"] for x in holders]

# 1 round magic
url2 = f"{API_BASE}/addresses/expand/magic"
h2 = {**HEADERS, "x-validation": _make_validation("/addresses/expand/magic")}
resp2 = requests.post(url2, json={"addresses": addrs, "token_ref": {"chain": chain, "address": token_addr}}, headers=h2)
magic = resp2.json() if isinstance(resp2.json(), list) else resp2.json().get("addresses", [])

all_holders = holders + magic
all_addrs = list(set(x["address"] for x in all_holders))

holder_map = {x["address"].lower(): x for x in all_holders}

url3 = f"{API_BASE}/relationships/subgraph?whitelist_token_address={token_addr}&whitelist_token_chain={chain}"
h3 = {**HEADERS, "x-validation": _make_validation(f"/relationships/subgraph?whitelist_token_address={token_addr}&whitelist_token_chain={chain}")}
resp3 = requests.post(url3, json=all_addrs, headers=h3)
rels = resp3.json()

print(f"Total relationships: {len(rels)}")

# Let's inspect target's relationships specifically
target_rels = [r for r in rels if r.get("from_address","").lower() == target or r.get("to_address","").lower() == target]
print(f"\nRelationships involving target ({target}):")
for r in target_rels:
    f = r.get("from_address")
    t = r.get("to_address")
    other = t if f.lower() == target else f
    other_details = holder_map.get(other.lower(), {}).get("address_details", {})
    label = other_details.get("label", "-")
    is_sn = other_details.get("is_supernode", False)
    is_cex = other_details.get("is_cex", False)
    is_dex = other_details.get("is_dex", False)
    is_contract = other_details.get("is_contract", False)
    
    print(f"  {f} -> {t} | Other: {other[:10]}... | SN: {is_sn} | CEX: {is_cex} | DEX: {is_dex} | Contract: {is_contract} | Label: {label}")
