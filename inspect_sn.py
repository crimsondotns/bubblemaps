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

# Fetch holders
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

sn = "0xe4f7ac28efbf2229c8908e2014418d0b37cd2f9f".lower()
sn_rels = [r for r in rels if r.get("from_address","").lower() == sn or r.get("to_address","").lower() == sn]
print(f"Total relations for SN: {len(sn_rels)}")

for r in sn_rels[:30]:
    f = r.get("from_address","").lower()
    t = r.get("to_address","").lower()
    other = t if f == sn else f
    other_details = holder_map.get(other, {}).get("address_details", {})
    is_sn = other_details.get("is_supernode", False)
    is_cex = other_details.get("is_cex", False)
    is_dex = other_details.get("is_dex", False)
    is_contract = other_details.get("is_contract", False)
    label = other_details.get("label", "-")
    print(f"  {f[:10]}... -> {t[:10]}... | Other: {other[:10]}... | SN: {is_sn} | CEX: {is_cex} | DEX: {is_dex} | Contract: {is_contract} | Label: {label}")
