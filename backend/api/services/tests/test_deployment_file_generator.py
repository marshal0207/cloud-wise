from django.test import SimpleTestCase

from api.services.deployment_file_generator import generate_deployment_files


class DeploymentFileGeneratorTests(SimpleTestCase):
    def test_generates_spring_boot_files(self):
        result = generate_deployment_files(
            {"pom.xml": "<project></project>"}, provider="AWS"
        )

        self.assertEqual(result["technology"]["technology"], "SPRING_BOOT")
        self.assertIn("Dockerfile", result["files"])
        self.assertIn("docker-compose.yml", result["files"])
        self.assertIn(".github/workflows/deploy.yml", result["files"])
        self.assertIn("eclipse-temurin", result["files"]["Dockerfile"])
        self.assertIn("8080:8080", result["files"]["docker-compose.yml"])

    def test_generates_node_files(self):
        result = generate_deployment_files(
            {"package.json": '{"dependencies":{"express":"4.21.2"}}'},
            provider="AWS",
        )

        self.assertEqual(result["technology"]["technology"], "NODE_JS")
        self.assertIn("node:20-alpine", result["files"]["Dockerfile"])
        self.assertIn("3000:3000", result["files"]["docker-compose.yml"])

    def test_generates_python_files(self):
        result = generate_deployment_files(
            {"requirements.txt": "Django>=5.0"}, provider="AWS"
        )

        self.assertEqual(result["technology"]["technology"], "PYTHON")
        self.assertIn("python:3.13-slim", result["files"]["Dockerfile"])
        self.assertIn("8000:8000", result["files"]["docker-compose.yml"])

    def test_generates_react_files_and_build_only_workflow(self):
        result = generate_deployment_files(
            {"package.json": '{"dependencies":{"react":"18.3.1"}}'},
            provider="GCP",
        )

        self.assertEqual(result["technology"]["technology"], "REACT")
        self.assertIn("nginx:alpine", result["files"]["Dockerfile"])
        workflow = result["files"][".github/workflows/deploy.yml"]
        self.assertIn("Build Docker image", workflow)
        self.assertIn("Validate Docker image", workflow)
        self.assertNotIn("aws-actions", workflow)
        self.assertNotIn("gcloud", workflow)
        self.assertNotIn("azure/login", workflow)
        self.assertNotIn("digitalocean", workflow.lower())


class VercelRenderRemovalTests(SimpleTestCase):
    """Vercel/Render configs must not be part of the default AWS flow."""

    FILES = {"package.json": '{"dependencies":{"react":"18.3.1"}}'}

    def test_vercel_and_render_configs_not_generated(self):
        result = generate_deployment_files(self.FILES, provider="AWS")

        self.assertNotIn("vercel.json", result["files"])
        self.assertNotIn("render.yaml", result["files"])

    def test_not_generated_for_backend_repositories(self):
        result = generate_deployment_files({"pom.xml": "<project></project>"})

        self.assertNotIn("vercel.json", result["files"])
        self.assertNotIn("render.yaml", result["files"])


class FrontendOnlyGenerationTests(SimpleTestCase):
    def test_react_vite_frontend_only(self):
        files = {
            "package.json": (
                '{"dependencies":{"react":"18.3.1"},'
                '"devDependencies":{"vite":"5.4.0","@vitejs/plugin-react":"4.3.0"}}'
            ),
            "vite.config.ts": "export default {}",
        }
        result = generate_deployment_files(files, provider="AWS")

        self.assertIn("Dockerfile", result["files"])
        self.assertIn("nginx:alpine", result["files"]["Dockerfile"])
        self.assertIn("/app/dist", result["files"]["Dockerfile"])
        self.assertIn("docker-compose.yml", result["files"])
        self.assertNotIn("nginx.conf", result["files"])
        self.assertFalse(result["deploymentPlan"]["requiresNginx"])
        self.assertEqual(result["deploymentPlan"]["containers"], ["app"])
        self.assertEqual(result["detection"]["frontend"], "React + Vite")
        self.assertEqual(result["detection"]["applicationType"], "frontend-only")

    def test_next_js_frontend_only(self):
        files = {"package.json": '{"dependencies":{"next":"14.2.0","react":"18.3.1"}}'}
        result = generate_deployment_files(files, provider="AWS")

        dockerfile = result["files"]["Dockerfile"]
        self.assertIn("node:20-alpine", dockerfile)
        self.assertIn("npm run build", dockerfile)
        self.assertIn("EXPOSE 3000", dockerfile)
        self.assertNotIn("nginx.conf", result["files"])
        self.assertFalse(result["deploymentPlan"]["requiresNginx"])
        self.assertEqual(result["detection"]["frontend"], "React + Next.js")


class BackendOnlyGenerationTests(SimpleTestCase):
    def test_spring_boot_backend_only(self):
        result = generate_deployment_files({
            "pom.xml": (
                "<project><dependency>"
                "<groupId>org.springframework.boot</groupId>"
                "<artifactId>spring-boot-starter-web</artifactId>"
                "</dependency></project>"
            ),
        })

        self.assertNotIn("nginx.conf", result["files"])
        self.assertFalse(result["deploymentPlan"]["requiresNginx"])
        self.assertEqual(result["deploymentPlan"]["containers"], ["app"])
        self.assertEqual(result["deploymentPlan"]["ports"], [8080])
        self.assertEqual(result["detection"]["backend"], "Spring Boot")
        self.assertEqual(result["detection"]["applicationType"], "backend-only")

    def test_node_express_backend_only(self):
        result = generate_deployment_files(
            {"package.json": '{"dependencies":{"express":"4.19.2"}}'}
        )

        self.assertIn("node:20-alpine", result["files"]["Dockerfile"])
        self.assertIn("3000:3000", result["files"]["docker-compose.yml"])
        self.assertEqual(result["detection"]["backend"], "Express")
        self.assertNotIn("nginx.conf", result["files"])

    def test_django_backend_only(self):
        result = generate_deployment_files({
            "manage.py": "import django",
            "requirements.txt": "Django>=5.0",
        })

        self.assertIn("python:3.13-slim", result["files"]["Dockerfile"])
        self.assertIn("manage.py", result["files"]["Dockerfile"])
        self.assertIn("8000:8000", result["files"]["docker-compose.yml"])
        self.assertEqual(result["detection"]["backend"], "Django")

    def test_flask_backend_only(self):
        result = generate_deployment_files({"requirements.txt": "flask==3.0.3"})

        dockerfile = result["files"]["Dockerfile"]
        self.assertIn("python:3.13-slim", dockerfile)
        self.assertIn("gunicorn", dockerfile)
        self.assertIn("EXPOSE 5000", dockerfile)
        self.assertIn("5000:5000", result["files"]["docker-compose.yml"])
        self.assertEqual(result["detection"]["backend"], "Flask")


class FullStackGenerationTests(SimpleTestCase):
    FILES = {
        "frontend/package.json": (
            '{"dependencies":{"react":"18.3.1"},'
            '"devDependencies":{"vite":"5.4.0","@vitejs/plugin-react":"4.3.0"}}'
        ),
        "backend/pom.xml": (
            "<project><dependency><groupId>org.springframework.boot</groupId>"
            "<artifactId>spring-boot-starter-web</artifactId></dependency>"
            "<dependency><groupId>org.postgresql</groupId>"
            "<artifactId>postgresql</artifactId></dependency></project>"
        ),
        ".env.example": "DATABASE_URL=\nJWT_SECRET=\n",
    }

    def test_generates_required_full_stack_files(self):
        result = generate_deployment_files(self.FILES, provider="AWS")
        generated = result["files"]

        self.assertIn("frontend/Dockerfile", generated)
        self.assertIn("backend/Dockerfile", generated)
        self.assertIn("docker-compose.yml", generated)
        self.assertIn("nginx.conf", generated)
        self.assertNotIn("Dockerfile", generated)  # root Dockerfile not required
        self.assertNotIn("vercel.json", generated)
        self.assertNotIn("render.yaml", generated)

        # Preview order matches spec
        self.assertEqual(
            list(generated.keys())[:4],
            ["frontend/Dockerfile", "backend/Dockerfile", "docker-compose.yml", "nginx.conf"],
        )

    def test_deployment_plan_structure(self):
        result = generate_deployment_files(self.FILES, provider="AWS")
        plan = result["deploymentPlan"]

        self.assertEqual(plan["target"], "AWS_EC2")
        self.assertEqual(plan["containers"], ["frontend", "backend", "nginx"])
        self.assertEqual(
            plan["generatedFiles"][:4],
            ["frontend/Dockerfile", "backend/Dockerfile", "docker-compose.yml", "nginx.conf"],
        )
        self.assertEqual(plan["database"], {"type": "PostgreSQL", "detected": True})
        self.assertIn("DATABASE_URL", plan["requiredEnvVars"])
        self.assertIn("JWT_SECRET", plan["requiredEnvVars"])
        self.assertEqual(plan["ports"], [80])
        self.assertTrue(plan["requiresNginx"])

    def test_detection_summary_for_preview(self):
        result = generate_deployment_files(self.FILES, provider="AWS")
        detection = result["detection"]

        self.assertEqual(detection["frontend"], "React + Vite")
        self.assertEqual(detection["backend"], "Spring Boot")
        self.assertEqual(detection["database"], "PostgreSQL")
        self.assertEqual(detection["applicationType"], "full-stack")

    def test_nginx_routes_frontend_and_backend(self):
        result = generate_deployment_files(self.FILES, provider="AWS")
        nginx = result["files"]["nginx.conf"]

        self.assertIn("location /", nginx)
        self.assertIn("location /api/", nginx)
        self.assertIn("proxy_pass http://frontend:80;", nginx)
        self.assertIn("proxy_pass http://backend:8080;", nginx)

    def test_backend_port_not_published_to_host(self):
        result = generate_deployment_files(self.FILES, provider="AWS")
        compose = result["files"]["docker-compose.yml"]

        self.assertIn('"80:80"', compose)
        self.assertNotIn('"8080:8080"', compose)
        self.assertIn("services:", compose)
        self.assertIn("frontend:", compose)
        self.assertIn("backend:", compose)
        self.assertIn("nginx:", compose)

    def test_compose_contains_no_database_containers(self):
        result = generate_deployment_files(self.FILES, provider="AWS")
        compose = result["files"]["docker-compose.yml"].lower()

        self.assertNotIn("postgres", compose)
        self.assertNotIn("mysql", compose)
        self.assertNotIn("mongo", compose)
        self.assertNotIn("database:", compose)

    def test_client_server_layout(self):
        files = {
            "client/package.json": (
                '{"dependencies":{"react":"18.3.1"},"devDependencies":{"vite":"5.4.0"}}'
            ),
            "server/package.json": '{"dependencies":{"express":"4.19.2"}}',
        }
        result = generate_deployment_files(files, provider="AWS")

        self.assertIn("client/Dockerfile", result["files"])
        self.assertIn("server/Dockerfile", result["files"])
        self.assertIn("nginx.conf", result["files"])
        self.assertTrue(result["deploymentPlan"]["requiresNginx"])
        self.assertIn("proxy_pass http://backend:3000;", result["files"]["nginx.conf"])


class ExistingDockerfileTests(SimpleTestCase):
    def test_root_dockerfile_is_preserved_not_overwritten(self):
        custom = "FROM my-custom-image:1.2.3\nEXPOSE 9999\nCMD [\"run\"]\n"
        result = generate_deployment_files({
            "Dockerfile": custom,
            "package.json": '{"dependencies":{"react":"18.3.1"}}',
        })

        self.assertEqual(result["files"]["Dockerfile"], custom)
        self.assertTrue(result["dockerfile_preserved"])
        self.assertIn('"9999:9999"', result["files"]["docker-compose.yml"])

    def test_split_layout_preserves_existing_service_dockerfiles(self):
        custom_frontend = "FROM custom-fe:1\nEXPOSE 8081\n"
        files = {
            "frontend/package.json": '{"dependencies":{"react":"18.3.1"}}',
            "frontend/Dockerfile": custom_frontend,
            "backend/pom.xml": "<project><dependency><groupId>org.springframework.boot</groupId></dependency></project>",
        }
        result = generate_deployment_files(files)

        self.assertEqual(result["files"]["frontend/Dockerfile"], custom_frontend)
        self.assertIn("eclipse-temurin", result["files"]["backend/Dockerfile"])
        self.assertTrue(result["dockerfile_preserved"])
        self.assertIn("nginx.conf", result["files"])

    def test_existing_compose_is_preserved(self):
        custom_compose = "services:\n  app:\n    image: my-image\n"
        result = generate_deployment_files({
            "pom.xml": "<project></project>",
            "docker-compose.yml": custom_compose,
        })

        self.assertEqual(result["files"]["docker-compose.yml"], custom_compose)
        self.assertTrue(result["compose_preserved"])


class DatabasePlanTests(SimpleTestCase):
    def test_postgresql_plan_without_database_container(self):
        files = {
            "package.json": '{"dependencies":{"react":"18.3.1"},"devDependencies":{"vite":"5.4.0","@vitejs/plugin-react":"4.3.0"}}',
            "pom.xml": "<project><dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId></dependency></project>",
            ".env.example": "DATABASE_URL=\n",
        }
        result = generate_deployment_files(files)
        plan = result["deploymentPlan"]

        self.assertEqual(plan["database"], {"type": "PostgreSQL", "detected": True})
        self.assertIn("DATABASE_URL", plan["requiredEnvVars"])
        compose = result["files"]["docker-compose.yml"].lower()
        self.assertNotIn("image: postgres", compose)
        self.assertNotRegex(compose, r"(?m)^\s{2}(postgres|db|database):")

    def test_mongodb_plan_without_database_container(self):
        files = {
            "package.json": '{"dependencies":{"express":"4.19.2","mongoose":"8.4.0"}}',
            ".env.example": "MONGO_URI=\n",
        }
        result = generate_deployment_files(files)
        plan = result["deploymentPlan"]

        self.assertEqual(plan["database"], {"type": "MongoDB", "detected": True})
        self.assertIn("MONGO_URI", plan["requiredEnvVars"])
        compose = result["files"]["docker-compose.yml"].lower()
        self.assertNotIn("image: mongo", compose)
        self.assertNotRegex(compose, r"(?m)^\s{2}mongo:")

    def test_mysql_plan_without_database_container(self):
        files = {
            "package.json": '{"dependencies":{"express":"4.19.2","mysql2":"3.9.0"}}',
        }
        result = generate_deployment_files(files)
        plan = result["deploymentPlan"]

        self.assertEqual(plan["database"], {"type": "MySQL", "detected": True})
        compose = result["files"]["docker-compose.yml"].lower()
        self.assertNotIn("image: mysql", compose)
        self.assertNotRegex(compose, r"(?m)^\s{2}(mysql|db|database):")


class NginxRequirementTests(SimpleTestCase):
    def test_full_stack_requires_nginx(self):
        files = {
            "frontend/package.json": '{"dependencies":{"react":"18.3.1"}}',
            "backend/requirements.txt": "Django>=5.0",
        }
        result = generate_deployment_files(files)

        self.assertTrue(result["deploymentPlan"]["requiresNginx"])
        self.assertIn("nginx.conf", result["files"])
        self.assertIn("nginx:", result["files"]["docker-compose.yml"])

    def test_single_service_does_not_require_nginx(self):
        for files in (
            {"package.json": '{"dependencies":{"react":"18.3.1"}}'},
            {"pom.xml": "<project></project>"},
            {"requirements.txt": "flask==3.0.3"},
            {"package.json": '{"dependencies":{"express":"4.19.2"}}'},
        ):
            result = generate_deployment_files(files)
            self.assertFalse(result["deploymentPlan"]["requiresNginx"])
            self.assertNotIn("nginx.conf", result["files"])
