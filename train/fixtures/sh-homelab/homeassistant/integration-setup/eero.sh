#!/bin/bash
# Add the schmittx eero integration to HA via the config-flow API.
# Interactive: eero login + verification code. Auto: all selected networks, all
# eeros + profiles, NO per-client device_trackers (add later via Configure),
# defaults for activity/misc/advanced.
#
# Run on dobby. Prereq: custom_components/eero installed + HA restarted, and
# ~/.config/homelab/ha-token present. (UI config-flow is flaky here — see README.)
set -eu
export HA=http://localhost:8123
export TOKEN=$(cat ~/.config/homelab/ha-token)

cat > /tmp/eero-flow.py <<'PY'
import os, json, urllib.request, urllib.error
ha, tok = os.environ["HA"], os.environ["TOKEN"]
def call(m, p, b=None):
    r = urllib.request.Request(ha+p, data=(json.dumps(b).encode() if b is not None else None),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}, method=m)
    try: return json.load(urllib.request.urlopen(r))
    except urllib.error.HTTPError as e:
        try: return json.load(e)
        except Exception: return {"_http": e.code}
def opts(d, name):
    for f in (d.get("data_schema") or []):
        if f.get("name") == name:
            return (f.get("selector", {}) or {}).get("select", {}).get("options", [])
    return []
def fields(d): return [f.get("name") for f in (d.get("data_schema") or [])]

flow = call("POST", "/api/config/config_entries/flow", {"handler": "eero"})
fid = flow["flow_id"]
post = lambda b: call("POST", f"/api/config/config_entries/flow/{fid}", b)

# 1. login  ->  2. verification code (field name is dynamic)
d = post({"login": input("eero account email or phone: ").strip()})
if d.get("type") == "form" and d.get("step_id") != "user" and fields(d):
    print(">> eero sent a verification code (email/SMS). <<")
    d = post({fields(d)[0]: input("eero verification code: ").strip()})

# 3+. drive the remaining steps automatically
while d.get("type") == "form":
    s = d.get("step_id")
    if s in ("user",):                       # bad creds -> stop
        print("login rejected:", d.get("errors")); break
    elif s == "networks":
        d = post({"networks": opts(d, "networks")})           # all networks on the account
    elif s == "resources":
        d = post({"eeros": opts(d, "eeros"), "profiles": opts(d, "profiles"),
                  "wired_clients": [], "wired_clients_filter": "include",
                  "wireless_clients": [], "wireless_clients_filter": "include",
                  "backup_networks": opts(d, "backup_networks")})
    elif s == "activity":
        d = post({"network": [], "eeros": [], "profiles": []})
    elif s == "advanced":
        d = post({"save_responses": False, "scan_interval": 120, "timeout": 30})
    else:                                    # miscellaneous etc. -> defaults
        d = post({})

print("RESULT:", d.get("type"), "-", d.get("title") or d.get("errors"))
PY
python3 /tmp/eero-flow.py
rm -f /tmp/eero-flow.py
