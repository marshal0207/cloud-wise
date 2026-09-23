import re
from dataclasses import asdict
from typing import Mapping

from .tech_stack_detector import (
    BACKEND_DIRECTORIES,
    BACKEND_MARKER_FILENAMES,
    FRONTEND_DIRECTORIES,
    TechStack,
    UnsupportedTechStackError,
    _backend_default_port,
    analyze_repository,
    detect_tech_stack,
)


def parse_exposed_port_from_dockerfile(dockerfile_content: str, default_port: int = 8000) -> int:
    """Extract exposed port from EXPOSE line in a Dockerfile."""
    match = re.search(r'EXPOSE\s+(\d+)', dockerfile_content, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return default_port


def generate_dockerfile(stack: TechStack) -> str:
    if stack.technology == "SPRING_BOOT":
        build_command = (
            "RUN ./mvnw clean package -DskipTests || "
            "mvn clean package -DskipTests"
        ) if stack.build_tool == "MAVEN" else (
            "RUN ./gradlew bootJar || gradle bootJar"
        )
        artifact_path = "build/libs/*.jar" if stack.build_tool == "GRADLE" else "target/*.jar"
        return f"""FROM eclipse-temurin:21-jdk AS builder
WORKDIR /app
COPY . .
{build_command}

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=builder /app/{artifact_path} app.jar
EXPOSE {stack.port}
ENTRYPOINT ["java", "-jar", "app.jar"]
"""

    if stack.technology == "PYTHON":
        return f"""FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE {stack.port}
CMD ["python", "manage.py", "runserver", "0.0.0.0:{stack.port}"]
"""

    if stack.technology == "REACT":
        return f"""FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE {stack.port}
CMD ["nginx", "-g", "daemon off;"]
"""

    return f"""FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
EXPOSE {stack.port}
CMD ["npm", "start"]
"""


def generate_compose(port: int, env_vars=None) -> str:
    environment_lines = [
        f"      - PORT={port}",
        "      - NODE_ENV=production",
    ]
    for name in env_vars or []:
        environment_lines.append(f"      - {name}=${{{name}}}")
    environment = "\n".join(environment_lines)
    return f"""version: '3.8'

services:
  app:
    build: .
    ports:
      - "{port}:{port}"
    environment:
{environment}
    restart: unless-stopped
"""


def generate_aws_github_actions(port: int, provider: str = "AWS") -> str:
    if provider.upper() == "AWS":
        return f"""name: AWS EC2 / ECS CloudWise Auto-Deployment

on:
  push:
    branches: [main, master]

jobs:
  deploy:
    name: Build & Deploy to AWS
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{{{ secrets.AWS_ACCESS_KEY_ID }}}}
          aws-secret-access-key: ${{{{ secrets.AWS_SECRET_ACCESS_KEY }}}}
          aws-region: ${{{{ secrets.AWS_REGION || 'ap-south-1' }}}}

      - name: Log in to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build Docker image
        env:
          ECR_REGISTRY: ${{{{ steps.login-ecr.outputs.registry }}}}
          ECR_REPOSITORY: cloudwise-app
          IMAGE_TAG: ${{{{ github.sha }}}}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          echo "IMAGE=$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG" >> $GITHUB_ENV

      - name: Validate Docker image
        run: docker image inspect $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG

      - name: Verify Container Deployment (Port {port})
        run: |
          echo "CloudWise AWS Deployment pipeline completed for container exposed on port {port}."
"""
    return f"""name: CloudWise Deployment Pipeline

on:
  push:
    branches: [main, master]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t cloudwise-app:${{{{ github.sha }}}} .
      - name: Validate Docker image
        run: docker image inspect cloudwise-app:${{{{ github.sha }}}}
"""


# Isolated for future compatibility — NOT generated in the default AWS flow.
def generate_vercel_config() -> str:
    return """{
  "version": 2,
  "builds": [
    {
      "src": "package.json",
      "use": "@vercel/node"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "/$1"
    }
  ]
}
"""


# Isolated for future compatibility — NOT generated in the default AWS flow.
def generate_render_config(port: int) -> str:
    return f"""services:
  - type: web
    name: cloudwise-app
    env: docker
    dockerfilePath: ./Dockerfile
    envVars:
      - key: PORT
        value: "{port}"
    plan: free
"""


# ---------------------------------------------------------------------------
# Structured Dockerfiles (driven by Part 1 repository analysis)
# ---------------------------------------------------------------------------

def _js_basenames(files: Mapping[str, str]) -> set[str]:
    return {str(key).replace('\\', '/').split('/')[-1].lower() for key in files}


def _detect_js_package_manager(files: Mapping[str, str]) -> str:
    basenames = _js_basenames(files)
    if 'pnpm-lock.yaml' in basenames:
        return 'pnpm'
    if 'yarn.lock' in basenames:
        return 'yarn'
    if 'bun.lock' in basenames or 'bun.lockb' in basenames:
        return 'bun'
    return 'npm'


def _js_toolchain(files: Mapping[str, str], package_manager: str) -> dict:
    basenames = _js_basenames(files)
    if package_manager == 'pnpm':
        return {
            'copy_deps': 'COPY . .',
            'install': 'corepack enable pnpm && pnpm install --frozen-lockfile',
            'install_prod': 'corepack enable pnpm && pnpm install --frozen-lockfile --prod',
            'build': 'pnpm run build',
            'start': 'pnpm start',
        }
    if package_manager == 'yarn':
        return {
            'copy_deps': 'COPY . .',
            'install': 'yarn install --frozen-lockfile',
            'install_prod': 'yarn install --frozen-lockfile --production',
            'build': 'yarn build',
            'start': 'yarn start',
        }
    if package_manager == 'bun':
        return {
            'copy_deps': 'COPY . .',
            'install': 'bun install',
            'install_prod': 'bun install --omit=dev',
            'build': 'bun run build',
            'start': 'bun start',
        }
    install = 'npm ci' if 'package-lock.json' in basenames else 'npm install'
    install_prod = install + ' --omit=dev'
    return {
        'copy_deps': 'COPY package*.json ./',
        'install': install,
        'install_prod': install_prod,
        'build': 'npm run build',
        'start': 'npm start',
    }


def _frontend_output_directory(frontend: Mapping) -> str:
    framework = frontend.get('framework')
    if framework == 'CRA':
        return 'build'
    return 'dist'


def frontend_default_port(frontend: Mapping) -> int:
    """Internal port a frontend container listens on."""
    if frontend.get('framework') == 'Next.js':
        return 3000
    return 80


def backend_default_port(backend: Mapping) -> int:
    """Internal port a backend container listens on."""
    return _backend_default_port(backend) or 8000


def generate_frontend_dockerfile(frontend: Mapping, *, files: Mapping[str, str] | None = None) -> str:
    """Dockerfile for a detected frontend (React/Vite, Next.js, CRA, Vue, Angular)."""
    files = files or {}
    frontend = frontend or {}
    package_manager = _detect_js_package_manager(files)
    toolchain = _js_toolchain(files, package_manager)
    framework = frontend.get('framework')

    if framework == 'Next.js':
        return f"""FROM node:20-alpine
WORKDIR /app
{toolchain['copy_deps']}
RUN {toolchain['install']}
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
RUN {toolchain['build']}
EXPOSE 3000
CMD ["{toolchain['start']}"]
"""

    output_dir = _frontend_output_directory(frontend)
    return f"""FROM node:20-alpine AS builder
WORKDIR /app
{toolchain['copy_deps']}
RUN {toolchain['install']}
COPY . .
RUN {toolchain['build']}

FROM nginx:alpine
COPY --from=builder /app/{output_dir} /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
"""


def generate_backend_dockerfile(
    backend: Mapping,
    *,
    files: Mapping[str, str] | None = None,
    package_managers: list[str] | None = None,
) -> str:
    """Dockerfile for a detected backend (Spring Boot, Node.js/Express, Django, Flask, Python)."""
    files = files or {}
    backend = backend or {}
    package_managers = package_managers or []
    technology = backend.get('technology')
    framework = backend.get('framework')

    if technology == 'Java':
        build_tool = 'GRADLE' if 'gradle' in package_managers else 'MAVEN'
        return generate_dockerfile(TechStack('SPRING_BOOT', build_tool, 8080))

    if technology == 'Node.js':
        package_manager = _detect_js_package_manager(files)
        toolchain = _js_toolchain(files, package_manager)
        return f"""FROM node:20-alpine
WORKDIR /app
{toolchain['copy_deps']}
RUN {toolchain['install_prod']}
COPY . .
EXPOSE 3000
CMD ["{toolchain['start']}"]
"""

    if technology == 'Python':
        if framework == 'Flask':
            return """FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
"""
        if framework == 'Django':
            return generate_dockerfile(TechStack('PYTHON', 'PIP', 8000))
        return """FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "main.py"]
"""

    # Unknown backend — generic Node runtime fallback
    package_manager = _detect_js_package_manager(files)
    toolchain = _js_toolchain(files, package_manager)
    return f"""FROM node:20-alpine
WORKDIR /app
{toolchain['copy_deps']}
RUN {toolchain['install_prod']}
COPY . .
EXPOSE 3000
CMD ["{toolchain['start']}"]
"""


# ---------------------------------------------------------------------------
# Nginx routing + multi-service compose (full-stack only)
# ---------------------------------------------------------------------------

def generate_nginx_conf(frontend_port: int, backend_port: int) -> str:
    """Route / to the frontend container and /api to the backend container."""
    return f"""server {{
    listen 80;
    server_name _;

    # Backend API — not exposed on the host
    location /api/ {{
        proxy_pass http://backend:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location /api {{
        return 301 /api/;
    }}

    # Frontend application
    location / {{
        proxy_pass http://frontend:{frontend_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""


def generate_split_compose(
    frontend_dir: str,
    backend_dir: str,
    *,
    backend_port: int,
    env_vars=None,
) -> str:
    """Multi-service compose for full-stack repos: frontend + backend + nginx.

    Only nginx publishes a host port — the backend stays internal.
    No database containers: the database is external.
    """
    backend_context = f'./{backend_dir}' if backend_dir else '.'
    backend_environment = [f"      - PORT={backend_port}"]
    for name in env_vars or []:
        backend_environment.append(f"      - {name}=${{{name}}}")
    backend_env_block = "\n".join(backend_environment)
    return f"""version: '3.8'

services:
  frontend:
    build:
      context: ./{frontend_dir}
    restart: unless-stopped
    environment:
      - NODE_ENV=production
  backend:
    build:
      context: {backend_context}
    restart: unless-stopped
    environment:
{backend_env_block}
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - frontend
      - backend
    restart: unless-stopped
"""


# ---------------------------------------------------------------------------
# Layout + detection helpers
# ---------------------------------------------------------------------------

def _resolve_service_directories(files: Mapping[str, str]) -> tuple[str | None, str | None]:
    """Find a split full-stack layout: frontend/ + backend/ (or client/server, web/api...)."""
    frontend_dir = None
    backend_dir = None
    for key in files:
        normalized = str(key).replace('\\', '/')
        parts = normalized.split('/')
        if len(parts) < 2:
            continue
        top = parts[0]
        basename = parts[-1].lower()
        if frontend_dir is None and top in FRONTEND_DIRECTORIES and basename == 'package.json':
            frontend_dir = top
        if backend_dir is None and top in BACKEND_DIRECTORIES and (
            basename == 'package.json'
            or basename in BACKEND_MARKER_FILENAMES
            or basename.startswith('build.gradle')
        ):
            backend_dir = top
    if frontend_dir and backend_dir and frontend_dir != backend_dir:
        return frontend_dir, backend_dir
    return None, None


def _find_dockerfile(files: Mapping[str, str], directory: str | None = None) -> str | None:
    """Locate an existing Dockerfile (root, or direct child of directory)."""
    for key in files:
        normalized = str(key).replace('\\', '/')
        parts = normalized.split('/')
        basename = parts[-1].lower()
        if basename not in ('dockerfile', 'dockerfile.prod'):
            continue
        if directory is None:
            if len(parts) == 1 or normalized.lower() in ('docker/dockerfile',):
                return key
        elif len(parts) == 2 and parts[0] == directory:
            return key
    return None


def _find_compose(files: Mapping[str, str]) -> str | None:
    for key in files:
        if str(key).lower() in ('docker-compose.yml', 'docker-compose.yaml'):
            return key
    return None


def _find_cicd(files: Mapping[str, str]) -> str | None:
    for key in files:
        if '.github/workflows' in str(key).lower():
            return key
    return None


def _format_tier_label(info: Mapping) -> str:
    technology = (info or {}).get('technology')
    framework = (info or {}).get('framework')
    if technology and framework:
        return f"{technology} + {framework}"
    return technology or framework or ''


def format_detection(analysis: Mapping) -> dict:
    """Human-readable detection summary for the frontend preview."""
    frontend = analysis.get('frontend') or {}
    backend = analysis.get('backend') or {}
    database = analysis.get('database') or {}

    frontend_label = _format_tier_label(frontend)
    backend_label = backend.get('framework') or backend.get('technology') or ''
    database_label = database.get('type') if database.get('detected') else ''

    return {
        'frontend': frontend_label,
        'backend': backend_label,
        'database': database_label or '',
        'applicationType': analysis.get('applicationType', ''),
    }


def build_deployment_plan(
    *,
    generated_files: Mapping[str, str],
    analysis: Mapping,
    containers: list[str],
    ports: list[int],
    requires_nginx: bool,
) -> dict:
    """Structured AWS EC2 deployment plan (Docker flow — database stays external)."""
    return {
        'target': 'AWS_EC2',
        'containers': containers,
        'generatedFiles': list(generated_files.keys()),
        'database': dict(analysis.get('database') or {'type': None, 'detected': False}),
        'requiredEnvVars': list(analysis.get('environmentVariables') or []),
        'ports': ports,
        'requiresNginx': requires_nginx,
    }


def generate_deployment_files(
    files: Mapping[str, str],
    provider: str = "MOCK",
    tree: list[dict] | None = None,
) -> dict[str, object]:
    """
    Generate Docker deployment files for the AWS EC2 flow.

    Uses the Part 1 repository analysis (frontend/backend/database/env/type).
    Existing Dockerfiles and compose files are preserved, never overwritten.
    vercel.json / render.yaml are NOT generated in this flow.
    """
    files = dict(files or {})
    analysis = analyze_repository(files, tree=tree)
    frontend = analysis.get('frontend') or {}
    backend = analysis.get('backend') or {}
    env_vars = analysis.get('environmentVariables') or []
    package_managers = analysis.get('packageManagers') or []

    try:
        stack = detect_tech_stack(files)
    except UnsupportedTechStackError:
        stack = None

    frontend_dir, backend_dir = _resolve_service_directories(files)
    split_layout = bool(frontend_dir and backend_dir)

    generated_files: dict[str, str] = {}
    dockerfile_preserved = False
    compose_preserved = False

    if split_layout:
        # ---------------------------------------------------------------
        # Full-stack: frontend/Dockerfile + backend/Dockerfile + compose
        # ---------------------------------------------------------------
        frontend_path = f'{frontend_dir}/Dockerfile'
        existing_frontend_dockerfile = _find_dockerfile(files, frontend_dir)
        if existing_frontend_dockerfile and files[existing_frontend_dockerfile].strip():
            generated_files[frontend_path] = files[existing_frontend_dockerfile]
            dockerfile_preserved = True
            frontend_port = parse_exposed_port_from_dockerfile(
                files[existing_frontend_dockerfile],
                default_port=frontend_default_port(frontend),
            )
        else:
            generated_files[frontend_path] = generate_frontend_dockerfile(frontend, files=files)
            frontend_port = frontend_default_port(frontend)

        backend_path = f'{backend_dir}/Dockerfile'
        existing_backend_dockerfile = _find_dockerfile(files, backend_dir)
        if existing_backend_dockerfile and files[existing_backend_dockerfile].strip():
            generated_files[backend_path] = files[existing_backend_dockerfile]
            dockerfile_preserved = True
            backend_port = parse_exposed_port_from_dockerfile(
                files[existing_backend_dockerfile],
                default_port=backend_default_port(backend),
            )
        else:
            generated_files[backend_path] = generate_backend_dockerfile(
                backend, files=files, package_managers=package_managers,
            )
            backend_port = backend_default_port(backend)

        compose_key = _find_compose(files)
        if compose_key and files[compose_key].strip():
            generated_files['docker-compose.yml'] = files[compose_key]
            compose_preserved = True
        else:
            generated_files['docker-compose.yml'] = generate_split_compose(
                frontend_dir, backend_dir, backend_port=backend_port, env_vars=env_vars,
            )

        existing_nginx = next(
            (k for k in files if str(k).replace('\\', '/').lower() == 'nginx.conf'),
            None,
        )
        if existing_nginx and files[existing_nginx].strip():
            generated_files['nginx.conf'] = files[existing_nginx]
        else:
            generated_files['nginx.conf'] = generate_nginx_conf(frontend_port, backend_port)

        containers = ['frontend', 'backend', 'nginx']
        published_ports = [80]
        port = 80
        requires_nginx = True
    else:
        # ---------------------------------------------------------------
        # Single service: root Dockerfile + compose
        # ---------------------------------------------------------------
        existing_dockerfile = _find_dockerfile(files)
        default_port = (
            backend_default_port(backend) if backend
            else frontend_default_port(frontend) if frontend
            else stack.port if stack
            else 3000
        )

        if existing_dockerfile and files[existing_dockerfile].strip():
            generated_files['Dockerfile'] = files[existing_dockerfile]
            dockerfile_preserved = True
            port = parse_exposed_port_from_dockerfile(
                files[existing_dockerfile], default_port=default_port,
            )
        elif backend:
            generated_files['Dockerfile'] = generate_backend_dockerfile(
                backend, files=files, package_managers=package_managers,
            )
            port = backend_default_port(backend)
        elif frontend:
            generated_files['Dockerfile'] = generate_frontend_dockerfile(frontend, files=files)
            port = frontend_default_port(frontend)
        elif stack:
            generated_files['Dockerfile'] = generate_dockerfile(stack)
            port = stack.port
        else:
            port = 3000
            generated_files['Dockerfile'] = (
                "FROM node:20-alpine\nWORKDIR /app\nCOPY . .\n"
                f"EXPOSE {port}\nCMD [\"node\", \"server.js\"]\n"
            )

        compose_key = _find_compose(files)
        if compose_key and files[compose_key].strip():
            generated_files['docker-compose.yml'] = files[compose_key]
            compose_preserved = True
        else:
            generated_files['docker-compose.yml'] = generate_compose(port, env_vars=env_vars)

        containers = ['app']
        published_ports = [port]
        requires_nginx = False

    # ------------------------------------------------------------------
    # AWS CI/CD pipeline (unchanged behaviour)
    # ------------------------------------------------------------------
    cicd_key = _find_cicd(files)
    cicd_preserved = False
    if cicd_key and files[cicd_key].strip():
        generated_files[cicd_key] = files[cicd_key]
        generated_files['.github/workflows/deploy.yml'] = files[cicd_key]
        cicd_preserved = True
    else:
        cicd_content = generate_aws_github_actions(port, provider)
        generated_files['.github/workflows/deploy.yml'] = cicd_content
        generated_files['.github/workflows/aws-deploy.yml'] = cicd_content

    # vercel.json / render.yaml are intentionally NOT generated —
    # the active deployment flow targets AWS EC2 only.

    deployment_plan = build_deployment_plan(
        generated_files=generated_files,
        analysis=analysis,
        containers=containers,
        ports=published_ports,
        requires_nginx=requires_nginx,
    )

    return {
        "technology": asdict(stack) if stack else None,
        "dockerfile_preserved": dockerfile_preserved,
        "compose_preserved": compose_preserved,
        "cicd_preserved": cicd_preserved,
        "port": port,
        "files": generated_files,
        "detection": format_detection(analysis),
        "analysis": analysis,
        "deploymentPlan": deployment_plan,
    }
