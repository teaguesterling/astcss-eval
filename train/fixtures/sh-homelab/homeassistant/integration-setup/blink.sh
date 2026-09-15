#!/bin/bash
# Blink (re-)add via Home Assistant's config-flow API — bypasses the broken UI.
# PREREQ: restart HA first so any dangling in-progress flows are cleared
#   (REST can't list/abort them; a restart drops them since they're in-memory):
#     sudo systemctl restart homeassistant ; sleep 25 ; bash ~/foo.sh
set -uo pipefail

cat > /tmp/blink_add.py <<'PY'
import os, json, urllib.request, urllib.error
ha, tok = os.environ["HA"], os.environ["TOKEN"]

def call(method, path, body=None):
    r = urllib.request.Request(
        ha + path,
        data=(json.dumps(body).encode() if body is not None else None),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        return json.load(urllib.request.urlopen(r))
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:
            return {"_http": e.code}

# remove any leftover (dead) blink config ENTRY so the add isn't 'already_configured'
ents = call("GET", "/api/config/config_entries/entry")
if isinstance(ents, list):
    for e in ents:
        if isinstance(e, dict) and e.get("domain") == "blink":
            print("removing stale blink entry", e["entry_id"], "->",
                  call("DELETE", f"/api/config/config_entries/entry/{e['entry_id']}"))

# fresh flow + creds (triggers Blink to send the 2FA code)
flow = call("POST", "/api/config/config_entries/flow", {"handler": "blink"})
fid = flow["flow_id"]
res = call("POST", f"/api/config/config_entries/flow/{fid}",
           {"username": os.environ["BU"], "password": os.environ["BP"]})
print("after creds -> type:", res.get("type"),
      "step:", res.get("step_id"), "errors:", res.get("errors"))

if res.get("type") == "form" and res.get("step_id") != "user":
    fields = [f.get("name") for f in (res.get("data_schema") or [])]
    field = fields[0] if fields else "2fa"
    print(">> Blink just sent a code to your email/SMS. <<")
    otp = input("Enter the Blink code: ").strip()
    res = call("POST", f"/api/config/config_entries/flow/{fid}", {field: otp})

if res.get("type") == "create_entry":
    print("OK - Blink added:", res.get("title"))
else:
    print(json.dumps(res, indent=2))
    if res.get("errors", {}).get("base") == "unknown":
        print("\n(still 'unknown'? restart HA to clear stuck flows, then re-run:")
        print(" sudo systemctl restart homeassistant ; sleep 25 ; bash ~/foo.sh )")
PY

export HA=http://localhost:8123
export TOKEN=$(cat ~/.config/homelab/ha-token)
read -rp 'Blink email: ' BU
read -rsp 'Blink password: ' BP; echo
export BU BP
python3 /tmp/blink_add.py
rm -f /tmp/blink_add.py
unset BP BU
