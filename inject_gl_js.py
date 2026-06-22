"""
Inject GL clickable script into the General Ledger Report via bench execute.
"""
import subprocess
import json
import sys
import re

# Read the JS from gl_clickable.py
with open("gl_clickable.py", encoding="utf-8") as f:
    content = f.read()

m = re.search(r'CLIENT_SCRIPT\s*=\s*r"""(.*?)"""', content, re.DOTALL)
if not m:
    print("Could not extract CLIENT_SCRIPT from gl_clickable.py")
    sys.exit(1)

js = m.group(1)
print(f"JS length: {len(js)} chars")

args_json = json.dumps(["Report", "General Ledger", "javascript", js])

cmd = [
    "docker", "exec", "erpnext-backend-1",
    "bench", "--site", "erpnext.localhost",
    "execute", "frappe.db.set_value",
    "--args", args_json,
]

result = subprocess.run(cmd, capture_output=True, text=True)
print("returncode:", result.returncode)
if result.stdout:
    print("stdout:", result.stdout[:300])
if result.stderr:
    print("stderr:", result.stderr[:300])
if result.returncode == 0:
    print("Success — hard-refresh General Ledger report in browser.")
