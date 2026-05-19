import requests, uuid, time, jwt

_JWT_SECRET = "LTJBO6Dsb5dEJ9pS"
SESSION_ID = str(uuid.uuid4())

def _make_validation(api_path):
    payload = {"data": api_path, "exp": int(time.time()) + 300}
    return jwt.encode(payload, _JWT_SECRET, algorithm="HS256")

API_BASE = "https://api.bubblemaps.io"
HEADERS = {"accept": "application/json", "content-type": "application/json", "origin": "https://v2.bubblemaps.io", "x-session-id": SESSION_ID}

target_sn = "0xe4f7ac28efbf2229c8908e2014418d0b37cd2f9f"

url = f"{API_BASE}/addresses/from-list"
h = {**HEADERS, "x-validation": _make_validation(f"/addresses/from-list")}
resp = requests.post(url, json=[target_sn], headers=h)
print(resp.json())
