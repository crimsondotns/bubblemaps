import json

target = "0xa4644953ad98ed5a7ff106ed9a3909c9aebcbc31"

with open("find_clusters.py") as f:
    code = f.read()
code_parts = code.split("# Calculate metrics for each component")
exec(code_parts[0])
for i, comp in enumerate(components):
    total_share = sum(holder_map.get(a, {}).get("holder_data", {}).get("share", 0) for a in comp)
    if len(comp) > 70 or 4.0 <= total_share*100 <= 5.0:
        print(f"\n--- BIG Cluster {i+1} ---")
        for a in sorted(comp, key=lambda x: holder_map.get(x, {}).get("holder_data", {}).get("share", 0), reverse=True)[:5]:
            share = holder_map.get(a, {}).get("holder_data", {}).get("share", 0)
            print(f"  {a} | Share: {share*100:.2f}%")
    
    if target in comp:
        print(f"\n--- Target Cluster {i+1} ---")
        for a in sorted(comp, key=lambda x: holder_map.get(x, {}).get("holder_data", {}).get("share", 0), reverse=True)[:5]:
            share = holder_map.get(a, {}).get("holder_data", {}).get("share", 0)
            print(f"  {a} | Share: {share*100:.2f}%")

