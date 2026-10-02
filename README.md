# CloudWise — Multi-Cloud Resource Intelligence & Automated Deployment Platform

CloudWise is a full-stack cloud infrastructure advisory and deployment platform. It analyzes a GitHub repository, estimates infrastructure costs across AWS, GCP, Azure, and DigitalOcean, generates production-ready deployment artifacts, and provisions and deploys the application to AWS EC2 — automatically, end to end.

---

## What It Does

A user connects their GitHub repository, describes their workload, and CloudWise handles everything from cost estimation to a live running application on AWS. The entire workflow is driven by real data: real GitHub repository analysis, real AWS pricing API calls, real EC2 provisioning via STS AssumeRole, and real deployment logs streamed from the instance.

The six-step pipeline is:

**Connect Repository → Estimate Workload → Compare Cloud Costs → Generate Artifacts → Provision & Deploy → Monitor & Optimize**

---

## Core Features

**Workload Estimation Engine**
Accepts application type, vCPU, RAM, storage, traffic, region, and performance tier. Computes min/max monthly cost in INR with region-specific multipliers. Persists every estimation to the database.

**Multi-Cloud Recommendation**
Generates side-by-side recommendations for AWS (c6i), GCP (n2-standard), Azure (Dsv5), and DigitalOcean (CPU-Optimized) from the same estimation inputs. All costs are derived dynamically — no hardcoded values.

**GitHub OAuth Integration**
Full OAuth 2.0 flow with GitHub. Stores encrypted access tokens using Fernet symmetric encryption. Fetches the user's repositories, links a selected repository to the active project, and recursively inspects the full repository tree via the GitHub Git Trees API.

**Repository Analysis & Artifact Generation**
Detects the technology stack (Spring Boot/Maven, Spring Boot/Gradle, React/Vite, Node.js, Python/Django, Python/FastAPI) from actual repository files. If a Dockerfile already exists it is preserved. Missing deployment files are generated: `Dockerfile`, `docker-compose.yml`, `.github/workflows/aws-deploy.yml`. Files can be committed back to the repository via the GitHub Contents API.

**AWS EC2 Deployment**
Connects to the user's own AWS account via IAM Role + STS AssumeRole (no long-lived keys stored). Provisions an EC2 instance with a security group, installs Docker via SSM, uploads the application, runs `docker compose up`, and performs a real HTTP health check. The live URL is the EC2 public IP/DNS. Deployment status progresses through `QUEUED → PREPARING → BUILDING → DEPLOYING → HEALTH_CHECK → RUNNING` with structured logs streamed in real time.

**MongoDB Atlas Integration**
Connects to MongoDB Atlas via the Atlas Administration API (OAuth2 Client Credentials). Automatically adds the EC2 instance's public IP to the Atlas Project Network Access list on every deployment so the application can reach its database.

**Cost Optimization Engine**
Generates four optimization recommendations (rightsize compute, delete unattached storage, purchase savings plan, automate off-peak shutdown) derived from the selected recommendation's actual cost and specs. Savings are calculated as percentages of real costs, not hardcoded numbers.

**Live Monitoring**
Queries the latest deployment record for uptime, IP address, and endpoint URL. CPU, memory, and storage metrics are shown as "Not collected" when no agent is running — no fabricated numbers.

**Role-Based Access Control**
Four roles: Owner, Editor, Viewer, Admin. Viewer role is blocked from creating projects, modifying settings, linking repositories, applying optimizations, and deploying. All project endpoints enforce strict user ownership — cross-user access returns 403 with no existence leak.

**JWT Authentication**
SimpleJWT with 7-day access tokens and 30-day rotating refresh tokens. All project, deployment, and GitHub endpoints require a valid Bearer token.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend framework | React 18 + TypeScript + Vite 6 |
| Frontend styling | Tailwind CSS 3 + Framer Motion |
| Frontend routing | React Router v6 |
| Frontend icons | Lucide React |
| Backend framework | Django 5 + Django REST Framework |
| Authentication | SimpleJWT (JWT) |
| Database (local) | SQLite |
| Database (production) | Neon PostgreSQL via `dj-database-url` |
| AWS SDK | boto3 |
| Token encryption | cryptography (Fernet) |
| CORS | django-cors-headers |
| HTTP client (backend) | urllib (stdlib, no extra dependency) |

---

## Getting Started

### Prerequisites

- Python 3.11 or later
- Node.js 18 or later
- A GitHub OAuth App (for repository integration)
- An AWS account with an IAM role (for EC2 deployment)

### Backend Setup

```bash
cd backend
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials (see Environment Variables section)
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

The API is available at `http://127.0.0.1:8000/api/`.
The Django admin panel is at `http://127.0.0.1:8000/admin/`.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend starts at `http://localhost:5173` and proxies all `/api/*` requests to the Django backend on port 8000 via the Vite dev server proxy.

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in the values.

### Required for GitHub OAuth

```dotenv
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_REDIRECT_URI=http://127.0.0.1:8000/api/github/oauth/callback
FRONTEND_URL=http://localhost:5173
```

Create a GitHub OAuth App at **GitHub → Settings → Developer settings → OAuth Apps → New OAuth App**. Set the Authorization callback URL to `http://127.0.0.1:8000/api/github/oauth/callback`.

### Required for Token Encryption

```dotenv
GITHUB_TOKEN_ENCRYPTION_KEY=
```

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Required for AWS Deployment

```dotenv
AWS_TRUSTED_ACCOUNT_ID=        # The AWS account ID that owns the CloudWise backend
AWS_DEFAULT_REGION=ap-south-1
AWS_ROLE_SESSION_NAME=cloudwise-deploy
AWS_ROLE_DURATION_SECONDS=3600
```

Optional static-key fallback (only if the host has no instance profile):

```dotenv
AWS_DEPLOYER_ACCESS_KEY_ID=
AWS_DEPLOYER_SECRET_ACCESS_KEY=
```

### Optional for MongoDB Atlas

```dotenv
MONGODB_ATLAS_PUBLIC_KEY=
MONGODB_ATLAS_PRIVATE_KEY=
MONGODB_ATLAS_PROJECT_ID=
```

### Database

```dotenv
# Leave empty to use SQLite locally
DATABASE_URL=postgres://user:password@host:5432/cloudwisedb
```

Tests always use SQLite regardless of `DATABASE_URL`.

### Django Core

```dotenv
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

---

## AWS IAM Setup

CloudWise never stores AWS access keys. Each user creates an IAM role in their own AWS account and gives CloudWise the role ARN. CloudWise assumes it with STS using a per-user external ID (confused-deputy protection).

**Step 1** — In the CloudWise UI, go to **Connect AWS** and click **Start AWS Setup**. Copy the External ID and Trust Policy shown.

**Step 2** — In your AWS console: IAM → Roles → Create role → AWS account → Another AWS account. Enter the CloudWise trusted account ID and the External ID condition from the Trust Policy.

**Step 3** — Create a new IAM policy named `CloudWiseDeployPolicy` using the Permissions Policy JSON shown in the UI. Attach it to the role.

**Step 4** — Copy the role ARN and paste it into CloudWise → **Verify & Connect AWS**. CloudWise performs a real STS AssumeRole + permission probe before saving the connection.

Permissions granted (least privilege, no `*` admin):

- `ec2:Describe*`, `ec2:RunInstances`, `ec2:Start/Stop/Reboot/TerminateInstances`
- `ec2:CreateTags`, `ec2:CreateSecurityGroup`, `ec2:Authorize/RevokeSecurityGroupIngress`
- `ec2:AllocateAddress`, `ec2:AssociateAddress`
- `ssm:SendCommand`, `ssm:GetCommandInvocation`, `ssm:Describe*`
- `iam:PassRole` scoped to `arn:aws:iam::*:role/cloudwise-ec2-*`

---

## API Reference

All endpoints are prefixed with `/api/`. Endpoints marked **Auth** require `Authorization: Bearer <JWT>`.

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/signup` | Register a new user |
| `POST` | `/auth/login` | Sign in, receive JWT |

### Projects — Auth required

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/projects` | List projects owned by the authenticated user |
| `POST` | `/projects` | Create a new project |
| `GET` | `/projects/<id>` | Get project detail |
| `PUT` | `/projects/<id>` | Update project (name, step, estimation, recommendation, deployment, optimizations) |
| `DELETE` | `/projects/<id>` | Delete project (owner/admin only) |
| `POST` | `/projects/<id>/github` | Link a GitHub repository to the project |
| `POST` | `/projects/<id>/github/inspect` | Recursively inspect the linked repository |
| `POST` | `/projects/<id>/github/push` | Commit generated files to the repository |

### Deployment — Auth required

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/deploy` | Start a real deployment to AWS EC2 |
| `POST` | `/deploy/preflight` | Validate all prerequisites without creating a record |
| `GET` | `/deployments` | List the authenticated user's deployments |
| `GET` | `/deployments/<id>` | Full deployment detail including logs |
| `GET` | `/deployments/<id>/status` | Current status + live EC2 state |
| `GET` | `/deployments/<id>/logs` | Structured deployment logs |
| `POST` | `/deployments/<id>/health` | Real HTTP health check against the live URL |
| `POST` | `/deployments/<id>/retry` | Re-run a failed deployment |
| `POST` | `/deployments/<id>/stop` | Stop the EC2 instance (instance retained) |
| `POST` | `/deployments/<id>/start` | Start a stopped EC2 instance |
| `POST` | `/deployments/<id>/terminate` | Terminate the EC2 instance |
| `POST` | `/deployments/<id>/rollback` | Stop containers, keep instance |

### AWS Connection — Auth required

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/aws/connect-info` | Get External ID, Trust Policy, and Permissions Policy |
| `POST` | `/aws/verify` | Probe IAM role (identity, permissions, region) |
| `POST` | `/aws/connect` | Save verified AWS connection |
| `GET` | `/aws/connection` | Get current AWS connection status |
| `POST` | `/aws/disconnect` | Remove AWS connection |

### MongoDB Atlas — Auth required

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/atlas/connection` | Get Atlas connection status |
| `POST` | `/atlas/connect` | Connect Atlas (server config or manual API key) |
| `POST` | `/atlas/disconnect` | Remove Atlas connection |

### GitHub OAuth

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/github/oauth/start` | Begin OAuth flow, returns authorization URL |
| `GET` | `/github/oauth/callback` | OAuth callback, stores token, redirects to frontend |
| `GET` | `/github/repos` | List authenticated user's GitHub repositories |

### Other

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/estimate` | Calculate infrastructure cost estimate |
| `POST` | `/deployment/generate-files` | Generate Dockerfile, compose, and CI/CD files |
| `GET` | `/monitoring` | Live monitoring data for the latest deployment |
| `GET` | `/pricing/aws` | AWS instance pricing snapshot |
| `POST` | `/contact` | Submit a contact inquiry |
| `POST` | `/waitlist` | Subscribe to the waitlist |
| `GET` | `/health` | API health check |

---

## Deployment Status Lifecycle

```
QUEUED → PREPARING → BUILDING → DEPLOYING → HEALTH_CHECK → RUNNING
```

Terminal states: `FAILED`, `ROLLING_BACK`, `ROLLED_BACK`, `TERMINATED`

All transitions are validated by a state machine. Progress percentage is derived deterministically from status — never animated by a client-side timer.

---

## Database Models

| Model | Purpose |
|---|---|
| `CustomUser` | Extended Django user with `company` and `role` fields |
| `Project` | User-owned project with JSON fields for estimation, recommendation, deployment, and optimizations |
| `EstimationRecord` | Persisted estimation inputs and calculated results |
| `DeploymentRecord` | Full deployment record with FKs to user, project, GitHub connection, AWS connection, and EC2 instance |
| `GitHubConnection` | One-to-one GitHub OAuth connection per user with encrypted access token |
| `AWSConnection` | One-to-one AWS IAM role connection per user (no keys stored) |
| `EC2Instance` | CloudWise-managed EC2 instance, reused across deployments |
| `MongoDBAtlasConnection` | Atlas API credentials per user with encrypted client secret |
| `WaitlistSubscriber` | Email waitlist |
| `ContactInquiry` | Contact form submissions |

---

## Running Tests

```bash
cd backend
python manage.py test api
```

Tests always use SQLite regardless of the `DATABASE_URL` environment variable. The test suite covers authentication, project CRUD, user isolation, RBAC enforcement, GitHub OAuth flow, repository inspection, deployment file generation, tech stack detection, AWS connection service, EC2 lifecycle, deployment state machine, and free-tier policy.

---

## Frontend Build

```bash
cd frontend
npm run build   # TypeScript check + Vite production build
```

---

## Security Notes

- GitHub OAuth tokens are encrypted at rest using Fernet symmetric encryption. The encryption key is stored only in `backend/.env` and never sent to the browser.
- AWS access keys are never stored. CloudWise uses STS AssumeRole with a per-user External ID. Temporary credentials are held in memory only and expire automatically.
- MongoDB Atlas API keys are encrypted at rest using the same Fernet key.
- JWT tokens are issued with a 7-day lifetime. Refresh tokens rotate on use.
- All project and deployment endpoints enforce strict user ownership. A record owned by another user returns 404 — no existence leak.
- `CORS_ALLOW_ALL_ORIGINS = True` is set for local development. In production, set `CORS_ALLOWED_ORIGINS` to the actual frontend domain.
- No secrets are ever included in API responses, logs, or frontend state.

---

## Pages & Routes

| Route | Page | Description |
|---|---|---|
| `/` | Home | Landing page with pipeline overview and waitlist |
| `/auth` | Auth | Sign in / create account |
| `/projects` | Projects | Project list with live deployment links |
| `/estimation` | Estimation | Workload sizing form |
| `/recommendation` | Recommendation | Multi-cloud cost comparison |
| `/generate` | GenerateFiles | Repository inspection and artifact generation |
| `/connect-aws` | ConnectAws | AWS IAM role setup and verification |
| `/connect-atlas` | ConnectAtlas | MongoDB Atlas API key connection |
| `/deployment` | Deployment | Deploy to AWS EC2 with real-time log stream |
| `/deployment/:id` | DeploymentDetails | Full deployment record, logs, health check, lifecycle actions |
| `/monitoring` | Monitoring | Live metrics for the active deployment |
| `/optimization` | Optimization | Cost optimization recommendations |
| `/about` | About | Platform information |
| `/contact` | Contact | Contact form |
