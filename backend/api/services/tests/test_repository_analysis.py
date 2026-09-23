from django.test import SimpleTestCase, override_settings

from api.services.github_repository_service import (
    RepositoryLimitError,
    check_repository_limits,
    compute_repository_size,
)
from api.services.tech_stack_detector import (
    analyze_repository,
    detect_application_type,
    detect_backend,
    detect_database,
    detect_environment_variables,
    detect_frontend,
    detect_package_managers,
)


class ReactSpringBootPostgresTests(SimpleTestCase):
    """Scenario 1: React + Spring Boot + PostgreSQL."""

    FILES = {
        'package.json': (
            '{"name":"web","dependencies":{"react":"18.3.1"},'
            '"devDependencies":{"vite":"5.4.0","@vitejs/plugin-react":"4.3.0"}}'
        ),
        'vite.config.ts': 'import react from "@vitejs/plugin-react";',
        'pom.xml': (
            '<project><dependencies>'
            '<dependency><groupId>org.springframework.boot</groupId>'
            '<artifactId>spring-boot-starter-web</artifactId></dependency>'
            '<dependency><groupId>org.postgresql</groupId>'
            '<artifactId>postgresql</artifactId></dependency>'
            '</dependencies></project>'
        ),
    }

    def test_detects_frontend_backend_database_and_type(self):
        analysis = analyze_repository(self.FILES)

        self.assertEqual(analysis['frontend'], {'technology': 'React', 'framework': 'Vite'})
        self.assertEqual(analysis['backend'], {'technology': 'Java', 'framework': 'Spring Boot'})
        self.assertEqual(analysis['database'], {'type': 'PostgreSQL', 'detected': True})
        self.assertEqual(analysis['packageManagers'], ['npm', 'maven'])
        self.assertEqual(analysis['applicationType'], 'full-stack')
        self.assertEqual(analysis['deploymentRequirements']['port'], 8080)


class ReactNodeMongoTests(SimpleTestCase):
    """Scenario 2: React + Node + MongoDB."""

    FILES = {
        'client/package.json': (
            '{"dependencies":{"react":"18.3.1"},'
            '"devDependencies":{"vite":"5.4.0","@vitejs/plugin-react":"4.3.0"}}'
        ),
        'server/package.json': (
            '{"dependencies":{"express":"4.19.2","mongoose":"8.4.0"}}'
        ),
    }

    def test_detects_frontend_backend_database_and_type(self):
        analysis = analyze_repository(self.FILES)

        self.assertEqual(analysis['frontend'], {'technology': 'React', 'framework': 'Vite'})
        self.assertEqual(analysis['backend'], {'technology': 'Node.js', 'framework': 'Express'})
        self.assertEqual(analysis['database'], {'type': 'MongoDB', 'detected': True})
        self.assertEqual(analysis['packageManagers'], ['npm'])
        self.assertEqual(analysis['applicationType'], 'full-stack')
        self.assertEqual(analysis['deploymentRequirements']['port'], 3000)


class NextNodeMysqlTests(SimpleTestCase):
    """Scenario 3: Next.js + Node + MySQL."""

    FILES = {
        'package.json': '{"dependencies":{"next":"14.2.0","react":"18.3.1"}}',
        'server/package.json': (
            '{"dependencies":{"express":"4.19.2","mysql2":"3.9.0"}}'
        ),
    }

    def test_detects_frontend_backend_database_and_type(self):
        analysis = analyze_repository(self.FILES)

        self.assertEqual(analysis['frontend'], {'technology': 'React', 'framework': 'Next.js'})
        self.assertEqual(analysis['backend'], {'technology': 'Node.js', 'framework': 'Express'})
        self.assertEqual(analysis['database'], {'type': 'MySQL', 'detected': True})
        self.assertEqual(analysis['packageManagers'], ['npm'])
        self.assertEqual(analysis['applicationType'], 'full-stack')


class SpringBootOnlyTests(SimpleTestCase):
    """Scenario 4: Spring Boot only."""

    FILES = {
        'pom.xml': (
            '<project><parent><groupId>org.springframework.boot</groupId>'
            '<artifactId>spring-boot-starter-parent</artifactId></parent></project>'
        ),
    }

    def test_detects_backend_only(self):
        analysis = analyze_repository(self.FILES)

        self.assertEqual(analysis['frontend'], {})
        self.assertEqual(analysis['backend'], {'technology': 'Java', 'framework': 'Spring Boot'})
        self.assertEqual(analysis['applicationType'], 'backend-only')
        self.assertEqual(analysis['packageManagers'], ['maven'])
        self.assertEqual(analysis['database'], {'type': None, 'detected': False})
        self.assertEqual(analysis['deploymentRequirements']['port'], 8080)


class ReactOnlyTests(SimpleTestCase):
    """Scenario 5: React only."""

    FILES = {
        'package.json': (
            '{"dependencies":{"react":"18.3.1"},'
            '"devDependencies":{"vite":"5.4.0","@vitejs/plugin-react":"4.3.0"}}'
        ),
        'vite.config.ts': 'export default {}',
    }

    def test_detects_frontend_only(self):
        analysis = analyze_repository(self.FILES)

        self.assertEqual(analysis['frontend'], {'technology': 'React', 'framework': 'Vite'})
        self.assertEqual(analysis['backend'], {})
        self.assertEqual(analysis['applicationType'], 'frontend-only')
        self.assertEqual(analysis['packageManagers'], ['npm'])

    def test_detects_cra_variant(self):
        files = {'package.json': '{"dependencies":{"react":"18.3.1","react-scripts":"5.0.1"}}'}

        self.assertEqual(
            detect_frontend(files),
            {'technology': 'React', 'framework': 'CRA'},
        )

    def test_detects_vue_and_angular(self):
        self.assertEqual(
            detect_frontend({'package.json': '{"dependencies":{"vue":"3.4.0"}}'}),
            {'technology': 'Vue', 'framework': None},
        )
        self.assertEqual(
            detect_frontend({'package.json': '{"dependencies":{"@angular/core":"17.0.0"}}'}),
            {'technology': 'Angular', 'framework': None},
        )


class PythonApplicationTests(SimpleTestCase):
    """Scenario 6: Python application."""

    def test_detects_flask_backend_only(self):
        analysis = analyze_repository({'requirements.txt': 'flask==3.0.3\ngunicorn==22.0.0'})

        self.assertEqual(analysis['frontend'], {})
        self.assertEqual(analysis['backend'], {'technology': 'Python', 'framework': 'Flask'})
        self.assertEqual(analysis['applicationType'], 'backend-only')
        self.assertEqual(analysis['packageManagers'], ['pip'])
        self.assertEqual(analysis['deploymentRequirements']['port'], 5000)

    def test_detects_django_backend_only(self):
        analysis = analyze_repository({
            'manage.py': 'import django',
            'requirements.txt': 'Django>=5.0',
        })

        self.assertEqual(analysis['backend'], {'technology': 'Python', 'framework': 'Django'})
        self.assertEqual(analysis['applicationType'], 'backend-only')

    def test_detects_plain_python(self):
        self.assertEqual(
            detect_backend({'requirements.txt': 'requests==2.32.0'}),
            {'technology': 'Python', 'framework': None},
        )


class EnvironmentVariableTests(SimpleTestCase):
    """Scenario 7: repository containing .env.example."""

    FILES = {
        '.env.example': (
            'DATABASE_URL=\n'
            'JWT_SECRET=s3cr3t-value-do-not-leak\n'
            'API_KEY=\n'
            'PORT=3000\n'
            '# commented=\n'
            'export REDIS_URL=\n'
        ),
    }

    def test_returns_names_only(self):
        env_vars = detect_environment_variables(self.FILES)

        self.assertEqual(env_vars, ['DATABASE_URL', 'JWT_SECRET', 'API_KEY', 'PORT', 'REDIS_URL'])
        self.assertNotIn('s3cr3t-value-do-not-leak', str(env_vars))

    def test_analysis_never_exposes_values(self):
        analysis = analyze_repository(self.FILES)

        self.assertEqual(
            analysis['environmentVariables'],
            ['DATABASE_URL', 'JWT_SECRET', 'API_KEY', 'PORT', 'REDIS_URL'],
        )
        self.assertNotIn('s3cr3t-value-do-not-leak', str(analysis))
        self.assertEqual(
            analysis['deploymentRequirements']['environmentVariables'],
            analysis['environmentVariables'],
        )

    def test_sensitive_env_file_is_never_parsed(self):
        env_vars = detect_environment_variables({
            '.env': 'SECRET=hunter2\n',
            '.env.example': 'DATABASE_URL=\n',
        })

        self.assertEqual(env_vars, ['DATABASE_URL'])
        self.assertNotIn('hunter2', str(env_vars))

    def test_supports_sample_and_template_names(self):
        env_vars = detect_environment_variables({
            '.env.sample': 'API_KEY=\n',
            '.env.template': 'DB_PASSWORD=\n',
        })

        self.assertEqual(env_vars, ['API_KEY', 'DB_PASSWORD'])


class EnvironmentVariableAbsenceTests(SimpleTestCase):
    """Scenario 8: repository without .env.example."""

    def test_returns_empty_list(self):
        analysis = analyze_repository({'package.json': '{"dependencies":{"react":"18.3.1"}}'})

        self.assertEqual(analysis['environmentVariables'], [])
        self.assertEqual(analysis['deploymentRequirements']['environmentVariables'], [])


class RepositoryLimitTests(SimpleTestCase):
    """Scenario 9: large repository platform limits."""

    @override_settings(MAX_FILES=100)
    def test_file_count_limit(self):
        tree = [
            {'path': f'file-{i}.txt', 'type': 'file', 'size': 1}
            for i in range(150)
        ]

        with self.assertRaises(RepositoryLimitError) as ctx:
            check_repository_limits(tree)

        message = str(ctx.exception)
        self.assertIn('Repository analysis limit reached.', message)
        self.assertIn('Repository files: 150', message)
        self.assertIn('Maximum supported files: 100', message)
        self.assertNotIn('GitHub', message)

    @override_settings(MAX_REPOSITORY_SIZE_MB=1)
    def test_repository_size_limit(self):
        tree = [
            {'path': 'large.bin', 'type': 'file', 'size': 2 * 1024 * 1024},
            {'path': 'small.txt', 'type': 'file', 'size': 10},
        ]

        with self.assertRaises(RepositoryLimitError) as ctx:
            check_repository_limits(tree)

        message = str(ctx.exception)
        self.assertIn('Repository analysis limit reached.', message)
        self.assertIn('Repository size: 2.0 MB', message)
        self.assertIn('Maximum supported size: 1 MB', message)
        self.assertNotIn('GitHub', message)

    @override_settings(MAX_REPOSITORY_SIZE_MB=500)
    def test_size_limit_example_message_shape(self):
        tree = [
            {'path': 'huge.bin', 'type': 'file', 'size': int(1.2 * 1024 ** 3)},
        ]

        with self.assertRaises(RepositoryLimitError) as ctx:
            check_repository_limits(tree)

        message = str(ctx.exception)
        self.assertIn('Repository size: 1.2 GB', message)
        self.assertIn('Maximum supported size: 500 MB', message)

    @override_settings(MAX_SINGLE_FILE_MB=10)
    def test_single_file_limit(self):
        tree = [
            {'path': 'dist/video.mp4', 'type': 'file', 'size': 25 * 1024 * 1024},
            {'path': 'src/index.js', 'type': 'file', 'size': 100},
        ]

        with self.assertRaises(RepositoryLimitError) as ctx:
            check_repository_limits(tree)

        message = str(ctx.exception)
        self.assertIn('File size: 25.0 MB (dist/video.mp4)', message)
        self.assertIn('Maximum supported single file size: 10 MB', message)
        self.assertNotIn('GitHub', message)

    @override_settings(MAX_ANALYSIS_TIME_MINUTES=5)
    def test_analysis_time_limit(self):
        with self.assertRaises(RepositoryLimitError) as ctx:
            check_repository_limits([], elapsed_seconds=5 * 60 + 1)

        message = str(ctx.exception)
        self.assertIn('Analysis time: 5.0 minutes', message)
        self.assertIn('Maximum analysis time: 5 minutes', message)
        self.assertNotIn('GitHub', message)

    @override_settings(MAX_FILES=10000, MAX_REPOSITORY_SIZE_MB=500)
    def test_within_limits_does_not_raise(self):
        tree = [{'path': 'app.py', 'type': 'file', 'size': 1000}]

        check_repository_limits(tree, elapsed_seconds=1.0)

    def test_default_limits_are_configurable(self):
        from api.services.github_repository_service import get_repository_limits

        limits = get_repository_limits()
        self.assertEqual(limits['max_repository_size_mb'], 500)
        self.assertEqual(limits['max_files'], 10000)
        self.assertEqual(limits['max_single_file_mb'], 10)
        self.assertEqual(limits['max_analysis_time_minutes'], 5)

        with override_settings(MAX_FILES=42):
            self.assertEqual(get_repository_limits()['max_files'], 42)

    def test_compute_repository_size(self):
        size = compute_repository_size([
            {'path': 'a.txt', 'type': 'file', 'size': 1024},
            {'path': 'b.txt', 'type': 'file', 'size': 2048},
            {'path': 'dir', 'type': 'directory', 'size': 0},
        ])

        self.assertEqual(size['totalBytes'], 3072)
        self.assertEqual(size['fileCount'], 2)
        self.assertEqual(size['largestFileBytes'], 2048)


class FullStackStructureTests(SimpleTestCase):
    def test_frontend_backend_directories(self):
        files = {
            'frontend/package.json': '{"dependencies":{"react":"18.3.1"}}',
            'backend/pom.xml': '<project></project>',
        }

        self.assertEqual(detect_application_type(files), 'full-stack')

    def test_client_server_directories(self):
        files = {
            'client/package.json': '{"dependencies":{"react":"18.3.1"}}',
            'server/package.json': '{"dependencies":{"express":"4.19.2"}}',
        }

        self.assertEqual(detect_application_type(files), 'full-stack')

    def test_unknown_repository_returns_empty_type(self):
        self.assertEqual(detect_application_type({'README.md': '# hello'}), '')
        self.assertEqual(analyze_repository({'README.md': '# hello'})['applicationType'], '')


class PackageManagerTests(SimpleTestCase):
    def test_defaults_to_npm_for_package_json(self):
        self.assertEqual(detect_package_managers({'package.json': '{}'}), ['npm'])

    def test_detects_alternate_js_managers_from_lockfiles(self):
        tree = [{'path': 'pnpm-lock.yaml', 'type': 'file', 'size': 1}]
        self.assertEqual(detect_package_managers({'package.json': '{}'}, tree=tree), ['pnpm'])
        self.assertEqual(
            detect_package_managers({'package.json': '{}', 'yarn.lock': ''}),
            ['yarn'],
        )
        self.assertEqual(
            detect_package_managers({'package.json': '{}', 'bun.lockb': ''}),
            ['bun'],
        )

    def test_detects_backend_managers(self):
        self.assertEqual(detect_package_managers({'pom.xml': ''}), ['maven'])
        self.assertEqual(detect_package_managers({'build.gradle': ''}), ['gradle'])
        self.assertEqual(detect_package_managers({'requirements.txt': ''}), ['pip'])
        self.assertEqual(
            detect_package_managers({'package.json': '{}', 'pom.xml': ''}),
            ['npm', 'maven'],
        )


class DatabaseDetectionTests(SimpleTestCase):
    def test_postgres_from_python_driver(self):
        self.assertEqual(
            detect_database({'requirements.txt': 'psycopg2-binary==2.9.9'}),
            {'type': 'PostgreSQL', 'detected': True},
        )
        self.assertEqual(
            detect_database({'requirements.txt': 'asyncpg==0.29.0'}),
            {'type': 'PostgreSQL', 'detected': True},
        )

    def test_postgres_from_prisma_schema(self):
        files = {'prisma/schema.prisma': 'generator client {\n}\ndata_source db {\n provider = "postgresql"\n}'}

        self.assertEqual(detect_database(files), {'type': 'PostgreSQL', 'detected': True})

    def test_postgres_from_drizzle_config(self):
        files = {'drizzle.config.ts': "export default { dialect: 'postgresql', schema: './schema.ts' }"}

        self.assertEqual(detect_database(files), {'type': 'PostgreSQL', 'detected': True})

    def test_postgres_from_env_connection_string(self):
        files = {'.env.example': 'DATABASE_URL=postgres://user:pass@host/db\n'}

        self.assertEqual(detect_database(files), {'type': 'PostgreSQL', 'detected': True})

    def test_mysql_from_node_driver(self):
        self.assertEqual(
            detect_database({'package.json': '{"dependencies":{"mysql2":"3.9.0"}}'}),
            {'type': 'MySQL', 'detected': True},
        )

    def test_mysql_from_python_driver(self):
        self.assertEqual(
            detect_database({'requirements.txt': 'PyMySQL==1.1.0'}),
            {'type': 'MySQL', 'detected': True},
        )
        self.assertEqual(
            detect_database({'requirements.txt': 'mysqlclient==2.2.0'}),
            {'type': 'MySQL', 'detected': True},
        )

    def test_mysql_from_jdbc(self):
        files = {'pom.xml': '<dependency><groupId>com.mysql</groupId><artifactId>mysql-connector-j</artifactId></dependency>'}

        self.assertEqual(detect_database(files), {'type': 'MySQL', 'detected': True})

    def test_mongodb_from_node_driver(self):
        self.assertEqual(
            detect_database({'package.json': '{"dependencies":{"mongoose":"8.4.0"}}'}),
            {'type': 'MongoDB', 'detected': True},
        )
        self.assertEqual(
            detect_database({'package.json': '{"dependencies":{"mongodb":"6.6.0"}}'}),
            {'type': 'MongoDB', 'detected': True},
        )

    def test_mongodb_from_python_driver(self):
        self.assertEqual(
            detect_database({'requirements.txt': 'pymongo==4.7.0'}),
            {'type': 'MongoDB', 'detected': True},
        )

    def test_mongodb_from_env_var_names(self):
        files = {'.env.example': 'MONGO_URI=\n'}

        self.assertEqual(detect_database(files), {'type': 'MongoDB', 'detected': True})

    def test_not_detected(self):
        self.assertEqual(
            detect_database({'package.json': '{"dependencies":{"react":"18.3.1"}}'}),
            {'type': None, 'detected': False},
        )


class AnalyzeRepositoryShapeTests(SimpleTestCase):
    def test_returns_all_api_fields(self):
        analysis = analyze_repository({}, repository_size={'totalBytes': 10})

        for key in (
            'frontend',
            'backend',
            'database',
            'packageManagers',
            'environmentVariables',
            'applicationType',
            'repositorySize',
            'deploymentRequirements',
        ):
            self.assertIn(key, analysis)

        self.assertEqual(analysis['frontend'], {})
        self.assertEqual(analysis['backend'], {})
        self.assertEqual(analysis['packageManagers'], [])
        self.assertEqual(analysis['environmentVariables'], [])
        self.assertEqual(analysis['applicationType'], '')
        self.assertEqual(analysis['repositorySize'], {'totalBytes': 10})
