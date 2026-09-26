# CloudWise - Multi-Cloud Resource Intelligence & Cost Sizing Platform

CloudWise is a cloud infrastructure resource intelligence, estimation, deployment advisory, and cost tuning platform built with **React (TypeScript + Vite)** on the frontend and **Django + Django REST Framework** on the backend.

---

## 📁 Repository Structure

```
Cloudwise-try/
├── frontend/               # React + TypeScript + Vite + Tailwind CSS Frontend
│   ├── src/                # Pages, Components, Context, and Styles
│   ├── package.json
│   ├── vite.config.ts      # Configured with proxy to http://127.0.0.1:8000
│   └── README.md
├── backend/                # Django + Django REST Framework Backend
│   ├── backend/            # Django Settings, URLs, WSGI, ASGI
│   ├── api/                # Models, Serializers, Views, Permissions, Admin
│   ├── manage.py
│   ├── requirements.txt
│   └── .env.example
└── README.md
```

---

## 🚀 Quick Start Guide

### 1. Start Django Backend

```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Run database migrations
python manage.py migrate

# Start Django development server (runs on http://127.0.0.1:8000)
python manage.py runserver 127.0.0.1:8000
```

- **API Base URL**: `http://127.0.0.1:8000/api/`
- **Django Admin Panel**: `http://127.0.0.1:8000/admin/`

---

### 2. Start React Frontend

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start Vite development server (runs on http://localhost:5173)
npm run dev
```

The frontend will start at `http://localhost:5173` and automatically proxy `/api/*` requests to the Django backend on port `8000`.

---

## 🛠️ Tech Stack

### Frontend
- **Framework**: React 18 + TypeScript + Vite
- **Styling**: Tailwind CSS + Framer Motion
- **Icons**: Lucide React
- **Routing**: React Router v6

### Backend
- **Framework**: Python 3 + Django 5 + Django REST Framework
- **Authentication**: SimpleJWT (JWT Authentication)
- **Database**: Django ORM + SQLite (Local Dev) / PostgreSQL (Production)
- **CORS**: `django-cors-headers`

---

## 🔐 Features Implemented
- User Registration & Sign In (JWT Authentication)
- Role-Based Access Control (RBAC: Owner, Editor, Viewer, Admin)
- INR ₹ Resource Cost Sizing Engine
- Multi-Cloud Comparison (AWS, GCP, Azure, DigitalOcean)
- GitHub Repository Integration & Manifest Generation
- Infrastructure Deployment Simulator & Logging
- Dynamic Cost Optimization Tuning
- Django Admin Control Panel for Data Management

# Django setup
```
    .\.venv\Scripts\Activate.ps1 
    python manage.py runserver
```
- cd backend
- python -m venv .venv
- .\.venv\Scripts\Activate.ps1
- pip install -r requirements.txt
- cp .env.example .env
#### Edit the .env file with your credentials if necessary
- python manage.py migrate
- python manage.py runserver

```bash
    .\.venv\Scripts\Activate.ps1
    .\.venv\Scripts\pip.exe install -r requirements.txt
    .\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000


    .\.venv\Scripts\Activate.ps1
    python manage.py migrate
    python manage.py runserver
```

---

# CloudWise Deployment Pipeline — Implementation Report

The end-to-end deploy flow is now **GitHub OAuth → repository scan → project
detection → AWS IAM/STS → EC2 provision → container deploy → health check →
real live URL**, scoped to the signed-in user on every endpoint. There is no
mock, simulated, or timer-driven data anywhere in the production path.

---

## 1. Architecture

```
Browser
  │  POST /api/deploy  (projectId, environmentName, envVars, region, specs)
  ▼
deploy_view  ── fast, synchronous validation (stage-tagged errors)
  │   PROJECT      project exists and belongs to caller
  │   GITHUB       repo linked, OAuth token readable, files readable
  │   ENVIRONMENT  required env vars present, DATABASE_URL scheme allowed
  │   AWS          caller has an active AWS connection (STS-assumable role)
  │
  ├─► DeploymentRecord(id=dep_…, user, github_connection, aws_connection,
  │                    repository, commit_sha, project_type, aws_account_id,
  │                    region, instance_id, instance_type,
  │                    deployment_status=QUEUED, live_url=NULL)
  │
  └─► start_pipeline()  ── daemon thread (DEPLOYMENT_RUN_INLINE=1 in tests)
         1. assume_role_credentials()      STS AssumeRole + external id
         2. AwsEc2Provider.start()         security group, AMI, RunInstances
         3. AwsEc2Provider.deploy()        upload, docker compose up, health
         4. record → RUNNING + live_url    structured logs streamed in-band
  ▲
  └── GET /api/deployments/<id>/status    record state, then live EC2 query
      GET /api/deployments/<id>/logs      structured logs
      POST /api/deployments/<id>/health   real HTTP GET against live_url
```

Status vocabulary (`backend/api/services/deployment/status.py`):

`QUEUED → PREPARING → BUILDING → DEPLOYING → HEALTH_CHECK → RUNNING`,
with `FAILED`, `ROLLING_BACK`, `ROLLED_BACK`, `TERMINATED` as terminal or
recovery states. Transitions are validated by `is_valid_transition()`.

Progress is derived deterministically from the status (`_STATUS_PROGRESS` in
`backend/api/views.py`) — never animated by a client-side timer.

---

## 2. Files changed

### Backend

| File | Change |
|---|---|
| `backend/api/models.py` | `DeploymentRecord` rewritten: FKs to `project`/`github_connection`/`aws_connection`/`user`, plus `repository`, `commit_sha`, `project_type`, `aws_account_id`, `instance_id`, `instance_type`, `deployment_status`, `live_url`, `updated_at`. `status`/`endpoint_url` kept as Python `@property` aliases (not DB columns). Added `failure_stage` property. |
| `backend/api/serializers.py` | `DeploymentRecordSerializer` emits canonical camelCase fields (`deploymentStatus`, `liveUrl`, `repository`, `commitSha`, `projectType`, `awsAccountId`, `instanceId`, `failureStage`, …). |
| `backend/api/admin.py` | Admin list/filter switched to `deployment_status`. |
| `backend/api/urls.py` | Deployment routes (list/detail/status/logs/health/retry/terminate/rollback); `/api/deployments/<id>/fail` removed. |
| `backend/api/views.py` | `deploy_view` → create-then-observe (201 + `QUEUED`); shared `_prepare_repository_payload()`; `_project_type_label()`; `monitoring_view` → authenticated, user-scoped, real data; `_find_deployment_record()` (owner-enforced, accepts `dep_…` or instance id); `_deployment_payload()`, `_stored_status_payload()`; `deployments_list_view`, `deployment_detail_view`, `deployment_status_view`, `deployment_logs_view`, `deployment_health_view`, `deployment_retry_view`, `deployment_terminate_view`, `deployment_rollback_view`. |
| `backend/api/services/deployment/pipeline.py` **(new)** | `start_pipeline()` / `run_pipeline()` / `append_log()` / `fail_deployment()` / `RecordLogStream` — STS → provision → deploy → finalize, streaming log + status updates. |
| `backend/api/services/deployment/aws_ec2_provider.py` | `set_log_listener()` + `_new_log()` for streaming; new `terminate_instance()` (verifies tag `ManagedBy=CloudWise` before `ec2:TerminateInstances`). |
| `backend/api/services/deployment/log_service.py` | Optional `listener` callback so log entries reach the record in-band. |
| `backend/api/services/deployment/status.py` | Added `TERMINATED` status + transition rules. |
| `backend/api/services/deployment_file_generator.py` | Default provider `MOCK` → `AWS`; dead `generate_vercel_config()` / `generate_render_config()` removed. |
| `backend/api/migrations/0007_deployment_record_ownership_and_pipeline_fields.py` **(new)** | See §3. |
| `backend/backend/settings.py` | `VERCEL_*` / `RENDER_*` removed; added `DEPLOYMENT_RUN_INLINE`. |

**Deleted** (retired / mock / dead):

```
backend/api/services/deployment/mock_provider.py
backend/api/services/deployment/vercel_provider.py
backend/api/services/deployment/render_provider.py
backend/api/services/deployment/health_check.py
backend/api/services/deployment/rollback.py
backend/debug_vercel.py
backend/diagnose_vercel.py
backend/api/services/tests/test_mock_deployment.py
```

### Frontend

| File | Change |
|---|---|
| `frontend/src/pages/Deployment.tsx` | Reads new response contract (`deploymentStatus` / `liveUrl` / `ipAddress`); **Deployment Readiness checklist** (GitHub · Repository · AWS · Deployment) driven by real signals with per-stage errors, Dismiss and Retry; `handleRetryDeployment()` → `POST /retry`; "Open Live Website" + "Deployment Details" buttons. |
| `frontend/src/pages/DeploymentDetails.tsx` **(new)** | Route `/deployment/:id` — Repository, Commit, Project type, AWS account, AWS region, Instance ID, Instance type, Instance state, Public IP, Deployment status, Failure stage, Created/Updated time, Deployment logs, Live URL, **Open Live Website**; actions: health check, refresh, retry, rollback, terminate; polls only while in-flight. |
| `frontend/src/pages/Monitoring.tsx` | Fabricated data removed: no random CPU/mem/storage, no "99.99% SLA", no fake anomaly alerts, no "Simulate Traffic Load Spike". Unmeasured metrics render an explicit "Not collected" state. |
| `frontend/src/context/CloudWiseContext.tsx` | `MonitoringData` fields nullable + `metricsCollected`; initial state is "not measured"; `/api/monitoring` now fetched with the JWT; exposes `refreshMonitoring()`. |
| `frontend/src/App.tsx` | Added route `/deployment/:id`. |

---

## 3. Database migration

```bash
python manage.py makemigrations api   # 0007_...
python manage.py migrate
```

`0007_deployment_record_ownership_and_pipeline_fields.py`:

1. `RenameField status → deployment_status` (data preserved)
2. `RenameField endpoint_url → live_url` (data preserved)
3. `AlterField deployment_status` default `'QUEUED'`
4. `AddField`: `aws_account_id`, `aws_connection` (FK), `commit_sha`,
   `github_connection` (FK), `instance_id`, `instance_type`, `project` (FK),
   `project_type`, `repository`, `updated_at`
5. `RunPython` — normalises legacy lowercase statuses
   (`deployed→RUNNING`, `deploying→DEPLOYING`, `building→BUILDING`,
   `preparing→PREPARING`, `failed→FAILED`, `rollback→ROLLED_BACK`, …)
6. `RunPython` — backfills `instance_id` from `provider_deployment_id`
   when it looks like `i-…`

Rollback: the `RunPython` steps are no-ops in reverse; the renames reverse cleanly.

---

## 4. Environment variables

Copy `backend/.env.example` → `backend/.env` (`.env` is gitignored).

**Required for GitHub**

```dotenv
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_REDIRECT_URI=http://localhost:8000/api/github/oauth/callback
FRONTEND_URL=http://localhost:5173
GITHUB_OAUTH_SCOPES=repo workflow
GITHUB_OAUTH_STATE_MAX_AGE=600
GITHUB_TOKEN_ENCRYPTION_KEY=      # Fernet key; encrypts stored OAuth tokens
```

**Required for AWS (STS assume-role — no long-lived keys needed)**

```dotenv
AWS_TRUSTED_ACCOUNT_ID=           # the account that owns the CloudWise backend
AWS_DEFAULT_REGION=ap-south-1
AWS_ROLE_SESSION_NAME=cloudwise-deploy
AWS_ROLE_DURATION_SECONDS=3600
```

Optional static-key fallback (only if the host has no instance profile):

```dotenv
AWS_DEPLOYER_ACCESS_KEY_ID=
AWS_DEPLOYER_SECRET_ACCESS_KEY=
```

**Deployment behaviour**

```dotenv
DEPLOYMENT_RUN_INLINE=            # leave empty in production (background thread)
```

**Removed:** `VERCEL_TOKEN`, `VERCEL_TEAM_ID`, `RENDER_API_KEY`,
`RENDER_OWNER_ID` and every other Vercel/Render variable.

> The repository previously carried a real `VERCEL_TOKEN` in `backend/.env`.
> It has been deleted from the file. **Revoke it in the Vercel dashboard**
> (Settings → Tokens) — it is not needed by CloudWise.

Other: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
`AWS_EC2_*`, `AWS_SECURITY_GROUP_*`, `AWS_HEALTH_CHECK_*`, `AWS_SSM_*`,
`AWS_PRICING_API_REGION`, `USD_TO_INR_RATE`.

---

## 5. GitHub setup

1. GitHub → Settings → Developer settings → **OAuth Apps → New OAuth App**
   - Homepage URL: `http://localhost:5173`
   - Authorization callback URL: `http://localhost:8000/api/github/oauth/callback`
2. Put the client id/secret in `backend/.env`.
3. `GITHUB_TOKEN_ENCRYPTION_KEY` must be a valid Fernet key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
4. Flow: **Files & GitHub → Connect GitHub** → `/api/github/oauth/start` →
   GitHub → `/api/github/oauth/callback` → JWT issued, `GitHubConnection`
   row created with encrypted token + scopes.

---

## 6. AWS / IAM setup

CloudWise never stores AWS keys. Each user creates (or reuses) an IAM role in
**their own** account and gives CloudWise the role ARN; CloudWise assumes it
with STS using a per-user **external id** (confused-deputy protection).

1. **Connect AWS → GET `/api/aws/connect-info`** returns
   - `externalId` (unique per user)
   - `trustPolicy` (role trust with `sts:ExternalId` condition)
   - `permissionsPolicy` (least-privilege, see below)
2. In the user's AWS console: IAM → Roles → Create role → **AWS account →
   Another AWS account** → paste `AWS_TRUSTED_ACCOUNT_ID` and the
   `trustPolicy` condition → attach the returned `permissionsPolicy`.
3. Paste the role ARN into CloudWise → **POST `/api/aws/connect`** →
   `sts:AssumeRole` is called immediately to validate it; only
   `role_arn`, `external_id`, `account_id`, `region`, `status` are stored.

Permissions granted (no `*`, no `AdministratorAccess`):

```
ec2:Describe*  |  ec2:RunInstances  ec2:Start/Stop/Reboot/TerminateInstances
ec2:CreateTags |  ec2:CreateSecurityGroup  ec2:Authorize/RevokeSecurityGroup*
ec2:ModifyInstanceAttribute
ssm:SendCommand, ssm:GetCommandInvocation, ssm:Describe*      (file upload + compose)
iam:PassRole → arn:aws:iam::*:role/cloudwise-ec2-*            (only to EC2)
```

Instances are tagged `ManagedBy=CloudWise` (plus `CloudWiseUser`,
`CloudWiseDeployment`, `Environment`); `terminate_instance()` refuses to
terminate anything not carrying that tag.

---

## 7. API endpoints

All deployment endpoints require `Authorization: Bearer <JWT>` and are scoped
to `request.user` — a record owned by anyone else returns **404** (no
existence leak).

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/deploy` | Validate (PROJECT/GITHUB/ENVIRONMENT/AWS) → create record → **201** with `deployment_id`, `stage: QUEUED` |
| `GET` | `/api/deployments` | My deployments, newest first (`?limit=`) — no log payload |
| `GET` | `/api/deployments/<id>` | Full details incl. logs, `progress`, `openUrl` |
| `GET` | `/api/deployments/<id>/status` | Record state while in-flight; live `ec2:DescribeInstances` once running |
| `GET` | `/api/deployments/<id>/logs` | Structured logs (`timestamp`, `level`, `stage`, `message`) |
| `POST` | `/api/deployments/<id>/health` | Real `GET` against `live_url` → `detail.httpStatus`, `detail.latencyMs` |
| `POST` | `/api/deployments/<id>/retry` | Re-run from `FAILED`/`ROLLED_BACK` (**409** otherwise); `envVars` must be re-sent |
| `POST` | `/api/deployments/<id>/terminate` | Terminate my EC2 instance → `TERMINATED` |
| `POST` | `/api/deployments/<id>/rollback` | Stop app containers, keep instance → `ROLLED_BACK` |
| `GET` | `/api/monitoring` | My latest deployment's real telemetry; unmeasured metrics are `null` + `metricsCollected: false` |

Retired (`400 status=RETIRED`, `supported: ["AWS"]`): any deploy request with
`provider: Vercel` or `provider: Render`, and
`POST /api/deployment/generate-files` with a non-AWS provider.

Canonical response fields:
`deploymentId, deploymentStatus, progress, providerType, repository, commitSha,
projectType, awsAccountId, region, instanceId, instanceType, ipAddress,
liveUrl, openUrl, failureStage, logs, createdAt, updatedAt, pipelineInFlight`.

---

## 8. Commands

```bash
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\pip.exe install -r requirements.txt
cp .env.example .env                    # then fill in credentials
python manage.py migrate
python manage.py runserver 127.0.0.1:8000

# Tests (248)
python manage.py test api

# Frontend
cd ..\frontend
npm install
npm run dev                             # http://localhost:5173
npm run build                           # tsc + vite build
```

---

## 9. Manual end-to-end test procedure

Setup: backend on `:8000`, frontend on `:5173`, `.env` filled in.

1. **Auth** — Sign up at `/auth`. Refresh: you stay signed in (JWT).
2. **GitHub** — *Files & GitHub → Connect GitHub*, authorize, pick a repo.
   Repository appears; analysis shows detected stack.
3. **Generate files** — *Generate* → Dockerfile / docker-compose / nginx
   listed. No `vercel.json`, no `render.yaml`.
4. **Estimate → Recommend** — choose a spec; note the region.
5. **Connect AWS** — *Connect AWS* → copy the external id + policies →
   create the role in **your** AWS account → paste the role ARN → Connect.
   Banner shows account id + region; **no access keys stored**.
6. **Configure env vars** — upload `.env` or add keys manually → *Confirm Env*.
7. **Deploy** — click *Deploy to AWS EC2*.
   201 returned; readiness checklist moves through
   `GitHub → Repository → AWS → Deployment (provisioning → deploying →
   health check → live)`, and the terminal prints real log lines
   (`assuming IAM role via STS …`, `Provisioning EC2 capacity …`,
   `Containers live at http://…`).
8. **Verify in AWS console** — an EC2 instance appears, tagged
   `ManagedBy=CloudWise`, with a security group opening the app port.
9. **Live URL** — when the checklist reaches *Live*, click **Open Live
   Website**. Your app loads from the EC2 public IP/DNS.
10. **Deployment details** — *Deployment Details* → `/deployment/<id>`.
    Repository, Commit, Project type, AWS account, Region, Instance ID,
    Instance type, Deployment status, Logs, Live URL, Created time.
11. **Health check** — *Run Health Check* → returns the real HTTP status code
    and latency.
12. **Refresh / Monitoring** — *View Live Metrics* → health, burn rate,
    instance id/type/region, uptime. CPU/memory/storage show
    **"Not collected"** (no agent). *Probe live URL now* returns a real result.
13. **Failure path** — remove an IAM permission (e.g. `ec2:RunInstances`) and
    deploy again → checklist **AWS/Deployment** turns red with the STS/EC2
    message, record → `FAILED`. Re-grant, click **Retry Failed Deployment**
    (re-enter env vars) → pipeline restarts on the same record.
14. **Isolation** — sign in as a second account and open the first account's
    `/deployment/<id>` → **404** for detail, status, logs, health, retry,
    terminate and rollback.
15. **Rollback / Terminate** — *Rollback* keeps the instance
    (`ROLLED_BACK`); *Terminate Instance* removes it (`TERMINATED`) and the
    record stays queryable.

---

## 10. Verification

```text
backend : python manage.py test api   ->  248 tests, OK
frontend: npm run build               ->  tsc + vite build, built in 20.46s
```

