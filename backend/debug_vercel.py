"""Debug Vercel deployment - retrieve real error metadata and logs."""
import json
import os
import urllib.request
import urllib.error

VERCEL_TOKEN = os.getenv("VERCEL_TOKEN", "")
if not VERCEL_TOKEN:
    # Read from .env
    with open("T:/D-drive/Sem - 5/sgp - 2/backend/.env") as f:
        for line in f:
            line = line.strip()
            if line.startswith("VERCEL_TOKEN="):
                VERCEL_TOKEN = line.split("=", 1)[1]
                break

DEPLOYMENT_ID = "dpl_HvPyKz9xE7aGe5gEyCA2nEAsKdZh"
VERCEL_API = "https://api.vercel.com"


def api_get(path):
    url = VERCEL_API + path
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {VERCEL_TOKEN}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"  HTTP {exc.code}: {body[:2000]}")
        return None


print("=" * 70)
print("1. DEPLOYMENT METADATA")
print("=" * 70)
dep = api_get(f"/v13/deployments/{DEPLOYMENT_ID}")
if dep:
    print(f"  id:              {dep.get('id')}")
    print(f"  projectId:       {dep.get('projectId')}")
    print(f"  name:            {dep.get('name')}")
    print(f"  url:             {dep.get('url')}")
    print(f"  readyState:      {dep.get('readyState')}")
    print(f"  state:           {dep.get('state')}")
    print(f"  target:          {dep.get('target')}")
    print(f"  errorCode:       {dep.get('errorCode')}")
    print(f"  errorMessage:    {dep.get('errorMessage')}")
    print(f"  createdAt:       {dep.get('createdAt')}")
    print(f"  buildingAt:      {dep.get('buildingAt')}")
    print(f"  readyAt:         {dep.get('readyAt')}")
    print(f"  canceledAt:      {dep.get('canceledAt')}")
    print(f"  createdIn:       {dep.get('createdIn')}")
    
    # Git source
    gs = dep.get("gitSource", {})
    print(f"\n  gitSource:")
    print(f"    type:  {gs.get('type')}")
    print(f"    ref:   {gs.get('ref')}")
    print(f"    org:   {gs.get('org')}")
    print(f"    repo:  {gs.get('repo')}")
    print(f"    sha:   {gs.get('sha')}")
    
    # Project settings used for this deployment
    ps = dep.get("projectSettings", {})
    print(f"\n  projectSettings:")
    for k, v in (ps.items() if ps else []):
        print(f"    {k}: {v}")
    
    # Meta
    meta = dep.get("meta", {})
    if meta:
        print(f"\n  meta:")
        for k, v in meta.items():
            print(f"    {k}: {v}")
    
    # Full raw dump for deeper inspection
    print(f"\n  --- Full raw keys ---")
    for k in sorted(dep.keys()):
        v = dep[k]
        vstr = str(v)[:200]
        print(f"    {k}: {vstr}")

print()
print("=" * 70)
print("2. DEPLOYMENT EVENTS (BUILD LOG)")
print("=" * 70)
events = api_get(f"/v3/deployments/{DEPLOYMENT_ID}/events")
if events and isinstance(events, list):
    for ev in events:
        ts = ev.get("createdAt", "")
        typ = ev.get("type", "")
        text = ""
        payload = ev.get("payload", {})
        if isinstance(payload, dict):
            text = payload.get("text", "") or payload.get("message", "") or ""
            error = payload.get("error", {})
            if isinstance(error, dict):
                text += f" | error_code={error.get('code','')} msg={error.get('message','')[:300]}"
        print(f"  [{ts}] {typ}: {text[:500]}")
elif events:
    print(f"  Response: {json.dumps(events, indent=2)[:3000]}")
else:
    print("  No events returned.")

print()
print("=" * 70)
print("3. PROJECT DETAILS")
print("=" * 70)
if dep and dep.get("projectId"):
    proj = api_get(f"/v9/projects/{dep['projectId']}")
    if proj:
        print(f"  name:           {proj.get('name')}")
        print(f"  framework:      {proj.get('framework')}")
        print(f"  buildCommand:   {proj.get('buildCommand')}")
        print(f"  outputDirectory:{proj.get('outputDirectory')}")
        print(f"  rootDirectory:  {proj.get('rootDirectory')}")
        print(f"  installCommand: {proj.get('installCommand')}")
        print(f"  nodeVersion:    {proj.get('nodeVersion')}")
        link = proj.get("link", {})
        print(f"  linked repo:    {link.get('org')}/{link.get('repo')} (branch={link.get('productionBranch')})")
