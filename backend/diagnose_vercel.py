"""Diagnostic script to verify Vercel token, GitHub repo, and Vercel project."""
import os
import json
import urllib.request
import urllib.error

# Load .env
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
with open(dotenv_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

token = os.environ.get('VERCEL_TOKEN', '')
team_id = os.environ.get('VERCEL_TEAM_ID', '')

print("=" * 60)
print("STEP 1: Verify Vercel token account")
print("=" * 60)
if not token:
    print("RESULT: VERCEL_TOKEN NOT CONFIGURED")
else:
    req = urllib.request.Request('https://api.vercel.com/v2/user', headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            print("  User ID:", data.get('id'))
            print("  Username:", data.get('username'))
            print("  Email:", data.get('email'))
            print("  Name:", data.get('name'))
    except urllib.error.HTTPError as exc:
        print("  ERROR: HTTP", exc.code)
        print("  ", exc.read().decode()[:500])

print()
print("=" * 60)
print("STEP 2: Check VERCEL_TEAM_ID configuration")
print("=" * 60)
print("  VERCEL_TEAM_ID from .env:", repr(team_id))
if team_id:
    # Try to get team info
    url = 'https://api.vercel.com/v2/teams/' + team_id
    req = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            print("  Team name:", data.get('name'))
            print("  Team slug:", data.get('slug'))
    except urllib.error.HTTPError as exc:
        print("  ERROR: HTTP", exc.code)
        print("  ", exc.read().decode()[:500])
else:
    print("  No team ID configured. Using personal account scope.")

print()
print("=" * 60)
print("STEP 3: List Vercel projects")
print("=" * 60)
url = 'https://api.vercel.com/v9/projects?limit=20'
if team_id:
    url += '&teamId=' + team_id
req = urllib.request.Request(url, headers={
    'Authorization': 'Bearer ' + token,
    'Accept': 'application/json',
})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        projects = data.get('projects', [])
        print("  Found", len(projects), "projects:")
        for p in projects:
            print("  -", p.get('name'), "| ID:", p.get('id'))
            git_repo = p.get('link', {}).get('repo')
            if git_repo:
                print("    Linked repo:", git_repo)
            else:
                print("    Linked repo: NONE")
except urllib.error.HTTPError as exc:
    print("  ERROR: HTTP", exc.code)
    print("  ", exc.read().decode()[:500])

print()
print("=" * 60)
print("STEP 4: List Vercel GitHub integrations/installations")
print("=" * 60)
url = 'https://api.vercel.com/v1/integrations/configuration'
if team_id:
    url += '?teamId=' + team_id
req = urllib.request.Request(url, headers={
    'Authorization': 'Bearer ' + token,
    'Accept': 'application/json',
})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        configs = data.get('configurations', [])
        print("  Found", len(configs), "integration configurations:")
        for c in configs:
            print("  -", c.get('type'), "| slug:", c.get('slug'), "| id:", c.get('id'))
except urllib.error.HTTPError as exc:
    print("  ERROR: HTTP", exc.code)
    print("  ", exc.read().decode()[:500])
