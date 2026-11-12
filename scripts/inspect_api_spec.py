import requests
import json

def main():
    url = "https://lpadmin.blackfx.com/assets/reference.json"
    print(f"Fetching {url}...")
    r = requests.get(url, timeout=15)
    print("Status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        print("Keys in reference.json:", list(data.keys()))
        print("OpenAPI version:", data.get("openapi") or data.get("swagger"))
        print("Info:", data.get("info"))
        paths = data.get("paths", {})
        print(f"Total endpoints (paths): {len(paths)}")
        
        # Save a local copy for analysis
        with open("jmeter_performance_tests/blacktrader_reference.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print("Saved to jmeter_performance_tests/blacktrader_reference.json")
        
        # Categorize endpoints
        categories = {}
        for path, methods in paths.items():
            for method, details in methods.items():
                if method.lower() not in ["get", "post", "put", "patch", "delete"]:
                    continue
                tag = (details.get("tags") or ["General"])[0]
                summary = details.get("summary") or details.get("operationId") or path
                categories.setdefault(tag, []).append((method.upper(), path, summary))
        
        print("\n--- Categorized Endpoints ---")
        for tag, eps in sorted(categories.items()):
            print(f"\n[{tag}] ({len(eps)} endpoints):")
            for m, p, s in eps[:10]:
                print(f"  {m:6} {p} - {s}")
            if len(eps) > 10:
                print(f"  ... and {len(eps) - 10} more")

if __name__ == '__main__':
    main()
