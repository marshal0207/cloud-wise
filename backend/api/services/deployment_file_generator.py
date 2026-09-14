from dataclasses import asdict
from typing import Mapping

from .tech_stack_detector import TechStack, detect_tech_stack


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
ENTRYPOINT [\"java\", \"-jar\", \"app.jar\"]
"""

    if stack.technology == "PYTHON":
        return f"""FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE {stack.port}
CMD [\"python\", \"manage.py\", \"runserver\", \"0.0.0.0:{stack.port}\"]
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
CMD [\"nginx\", \"-g\", \"daemon off;\"]
"""

    return f"""FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
EXPOSE {stack.port}
CMD [\"npm\", \"start\"]
"""


def generate_compose(stack: TechStack) -> str:
    return f"""services:
  app:
    build: .
    ports:
      - \"{stack.port}:{stack.port}\"
    restart: unless-stopped
"""


def generate_github_actions(stack: TechStack, provider: str = "AWS") -> str:
    provider_upper = provider.upper()
    return f"""name: CloudWise Deployment

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t cloudwise-app:${{{{ github.sha }}}} .
      - name: Provider target
        run: echo \"Target provider: {provider_upper}; application port: {stack.port}\"
"""


def generate_deployment_files(
    files: Mapping[str, str], provider: str = "AWS"
) -> dict[str, object]:
    stack = detect_tech_stack(files)
    return {
        "technology": asdict(stack),
        "files": {
            "Dockerfile": generate_dockerfile(stack),
            "docker-compose.yml": generate_compose(stack),
            ".github/workflows/deploy.yml": generate_github_actions(stack, provider),
        },
    }
