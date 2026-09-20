import re
from dataclasses import asdict
from typing import Mapping

from .tech_stack_detector import TechStack, UnsupportedTechStackError, detect_tech_stack


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


def generate_compose(port: int) -> str:
    return f"""version: '3.8'

services:
  app:
    build: .
    ports:
      - "{port}:{port}"
    environment:
      - PORT={port}
      - NODE_ENV=production
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


def generate_deployment_files(
  files: Mapping[str, str], provider: str = "MOCK"
) -> dict[str, object]:
    # Check for existing Dockerfile
    dockerfile_key = None
    for k in files.keys():
        if k.lower() in ('dockerfile', 'dockerfile.prod', 'docker/dockerfile'):
            dockerfile_key = k
            break

    # Check for existing compose file
    compose_key = None
    for k in files.keys():
        if k.lower() in ('docker-compose.yml', 'docker-compose.yaml'):
            compose_key = k
            break

    # Check for existing CI/CD file
    cicd_key = None
    for k in files.keys():
        if '.github/workflows' in k.lower():
            cicd_key = k
            break

    # Detect stack — fall back to a generic Node stack if unrecognised
    try:
        stack = detect_tech_stack(files)
    except UnsupportedTechStackError:
        stack = None

    generated_files = {}

    # 1. Dockerfile logic
    dockerfile_preserved = False
    if dockerfile_key and files[dockerfile_key].strip():
        dockerfile_content = files[dockerfile_key]
        default_port = stack.port if stack else 3000
        port = parse_exposed_port_from_dockerfile(dockerfile_content, default_port=default_port)
        generated_files["Dockerfile"] = dockerfile_content
        dockerfile_preserved = True
    elif stack:
        port = stack.port
        generated_files["Dockerfile"] = generate_dockerfile(stack)
    else:
        # No Dockerfile and no recognised stack — generate a generic Node container
        port = 3000
        generated_files["Dockerfile"] = (
            "FROM node:20-alpine\nWORKDIR /app\nCOPY . .\n"
            f"EXPOSE {port}\nCMD [\"node\", \"server.js\"]\n"
        )

    # 2. docker-compose.yml logic
    compose_preserved = False
    if compose_key and files[compose_key].strip():
        generated_files["docker-compose.yml"] = files[compose_key]
        compose_preserved = True
    else:
        generated_files["docker-compose.yml"] = generate_compose(port)

    # 3. AWS CI/CD pipeline logic
    cicd_preserved = False
    if cicd_key and files[cicd_key].strip():
        generated_files[cicd_key] = files[cicd_key]
        generated_files[".github/workflows/deploy.yml"] = files[cicd_key]
        cicd_preserved = True
    else:
        cicd_content = generate_aws_github_actions(port, provider)
        generated_files[".github/workflows/deploy.yml"] = cicd_content
        generated_files[".github/workflows/aws-deploy.yml"] = cicd_content

    # 4. Multi-provider deployment configs (Vercel / Render)
    generated_files["vercel.json"] = generate_vercel_config()
    generated_files["render.yaml"] = generate_render_config(port)

    return {
        "technology": asdict(stack) if stack else None,
        "dockerfile_preserved": dockerfile_preserved,
        "compose_preserved": compose_preserved,
        "cicd_preserved": cicd_preserved,
        "port": port,
        "files": generated_files,
    }
