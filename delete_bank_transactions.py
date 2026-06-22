"""Delete all Bank Transaction records so we can re-import cleanly."""
import requests

URL   = "http://localhost:8080"
HEADS = {
    "Authorization": "token 12d80506c40944c:903ef51e33f8869",
    "Content-Type":  "application/json",
}

r = requests.get(
    URL + "/api/resource/Bank Transaction",
    headers=HEADS,
    params={"fields": '["name","docstatus"]', "limit_page_length": 500},
    timeout=30,
)
bts = r.json().get("data", [])
print(f"Found {len(bts)} Bank Transactions")

cancelled = deleted = failed = 0
for bt in bts:
    name = bt["name"]
    enc  = requests.utils.quote(name)
    if bt["docstatus"] == 1:
        r2 = requests.put(
            f"{URL}/api/resource/Bank Transaction/{enc}",
            headers=HEADS, json={"data": {"docstatus": 2}}, timeout=30,
        )
        if r2.status_code in (200, 201):
            cancelled += 1
    r3 = requests.delete(f"{URL}/api/resource/Bank Transaction/{enc}", headers=HEADS, timeout=30)
    if r3.status_code in (200, 202, 204):
        deleted += 1
    else:
        failed += 1
        print(f"  FAIL delete {name}: {r3.status_code} {r3.text[:100]}")

print(f"Cancelled: {cancelled}, Deleted: {deleted}, Failed: {failed}")
