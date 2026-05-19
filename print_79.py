import json
with open("find_clusters.py") as f:
    code = f.read()
code_parts = code.split("# Calculate metrics for each component")
exec(code_parts[0])
for i, comp in enumerate(components):
    if len(comp) == 79:
        print(f"\n--- Cluster 79 addresses ---")
        for a in sorted(comp, key=lambda x: holder_map.get(x, {}).get("holder_data", {}).get("share", 0), reverse=True)[:10]:
            share = holder_map.get(a, {}).get("holder_data", {}).get("share", 0)
            print(f"  {a} | Share: {share*100:.2f}%")
