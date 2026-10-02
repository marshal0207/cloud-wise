from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from api.models import GitHubConnection, Project
from api.services.tech_stack_detector import TechStack


class GitHubInspectionApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='inspection-user',
            email='inspection@example.com',
            password='Passw0rd',
        )
        self.other_user = get_user_model().objects.create_user(
            username='other-user',
            email='other@example.com',
            password='Passw0rd',
        )
        self.project = Project.objects.create(
            user=self.user,
            user_id_str=str(self.user.id),
            name='Inspection Project',
            github_repo={
                'name': 'owner/repository',
                'default_branch': 'main',
            },
        )
        self.url = f'/api/projects/{self.project.id}/github/inspect'

    def test_requires_project_ownership(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data['success'])

    def test_requires_github_connection(self):
        self.client.force_authenticate(user=self.user)
        self.project.github_repo = None
        self.project.save()

        response = self.client.post(self.url, {}, format='json')

        self.assertIn(response.status_code, (400, 409))
        self.assertFalse(response.data['success'])


    @patch('api.views.detect_tech_stack')
    @patch('api.views.inspect_repository')
    def test_returns_inspection_and_detected_stack(self, inspect, detect):
        self.client.force_authenticate(user=self.user)
        GitHubConnection.objects.create(
            user=self.user,
            access_token='server-token',
            github_user_id='123',
            github_login='owner',
        )
        inspect.return_value = {
            'repository': 'owner/repository',
            'branch': 'main',
            'files': {'package.json': '{"dependencies":{"react":"18.3.1"}}'},
        }
        detect.return_value = TechStack('REACT', 'NPM', 3000)

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['technology']['technology'], 'REACT')
        self.assertEqual(response.data['data']['technology']['port'], 3000)
        inspect.assert_called_once()
        self.assertEqual(inspect.call_args[0], ('server-token', self.project.github_repo))

    @patch('api.views.detect_tech_stack')
    @patch('api.views.inspect_repository')
    def test_returns_unprocessable_for_unsupported_stack(self, inspect, detect):
        from api.services.tech_stack_detector import UnsupportedTechStackError

        self.client.force_authenticate(user=self.user)
        GitHubConnection.objects.create(
            user=self.user,
            access_token='server-token',
            github_user_id='123',
            github_login='owner',
        )
        inspect.return_value = {
            'repository': 'owner/repository',
            'branch': 'main',
            'files': {'README.md': 'unknown'},
            'tree': [],
            'has_dockerfile': False,
            'has_compose': False,
            'has_cicd': False,
        }
        detect.side_effect = UnsupportedTechStackError('Unsupported project.')

        response = self.client.post(self.url, {}, format='json')

        # Unsupported stack now returns 200 with technology=null instead of 422
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertIsNone(response.data['data']['technology'])

    @patch('api.views.detect_tech_stack')
    @patch('api.views.inspect_repository')
    def test_returns_extended_analysis_fields_without_breaking_existing(self, inspect, detect):
        self.client.force_authenticate(user=self.user)
        GitHubConnection.objects.create(
            user=self.user,
            access_token='server-token',
            github_user_id='123',
            github_login='owner',
        )
        inspect.return_value = {
            'repository': {'owner': 'owner', 'name': 'repository', 'full_name': 'owner/repository', 'defaultBranch': 'main'},
            'branch': 'main',
            'commitSha': 'abc1234',
            'tree': [{'path': 'package.json', 'type': 'file', 'size': 100, 'sha': 'a'}],
            'files': {
                'package.json': (
                    '{"dependencies":{"react":"18.3.1"},'
                    '"devDependencies":{"vite":"5.4.0","@vitejs/plugin-react":"4.3.0"}}'
                ),
                'pom.xml': '<project><dependency><groupId>org.springframework.boot</groupId>'
                           '<artifactId>spring-boot-starter-web</artifactId></dependency>'
                           '<dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId></dependency></project>',
                '.env.example': 'DATABASE_URL=\nJWT_SECRET=\nAPI_KEY=\nPORT=\n',
            },
            'totalFiles': 3,
            'totalDirectories': 1,
            'truncated': False,
            'scannedAt': '2026-09-23T00:00:00',
            'repositorySize': {'totalBytes': 2048, 'totalMegabytes': 0.0, 'fileCount': 3, 'largestFileBytes': 1024},
            'has_dockerfile': False,
            'has_compose': False,
            'has_cicd': False,
        }
        detect.return_value = TechStack('REACT', 'NPM', 3000)

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, 200)
        data = response.data['data']

        # Existing consumers keep working — all previous fields preserved
        for key in (
            'repository', 'branch', 'commitSha', 'tree', 'files', 'totalFiles',
            'totalDirectories', 'truncated', 'scannedAt', 'technology',
            'has_dockerfile', 'has_compose', 'has_cicd',
        ):
            self.assertIn(key, data)
        self.assertEqual(data['technology']['technology'], 'REACT')

        # New structured analysis fields
        for key in (
            'frontend', 'backend', 'database', 'packageManagers',
            'environmentVariables', 'applicationType', 'repositorySize',
            'deploymentRequirements',
        ):
            self.assertIn(key, data)

        self.assertEqual(data['frontend'], {'technology': 'React', 'framework': 'Vite'})
        self.assertEqual(data['backend'], {'technology': 'Java', 'framework': 'Spring Boot'})
        self.assertEqual(data['database'], {'type': 'PostgreSQL', 'detected': True})
        self.assertEqual(data['packageManagers'], ['npm', 'maven'])
        self.assertEqual(data['environmentVariables'], ['DATABASE_URL', 'JWT_SECRET', 'API_KEY', 'PORT'])
        self.assertEqual(data['applicationType'], 'full-stack')
        self.assertEqual(data['repositorySize']['totalBytes'], 2048)
        self.assertEqual(data['deploymentRequirements']['port'], 8080)

    @patch('api.views.inspect_repository')
    def test_repository_limit_error_returns_platform_error(self, inspect):
        from api.services.github_repository_service import RepositoryLimitError

        self.client.force_authenticate(user=self.user)
        GitHubConnection.objects.create(
            user=self.user,
            access_token='server-token',
            github_user_id='123',
            github_login='owner',
        )
        inspect.side_effect = RepositoryLimitError(
            'Repository analysis limit reached.\n\n'
            'Repository size: 1.2 GB\n'
            'Maximum supported size: 500 MB'
        )

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.data['code'], 'REPOSITORY_LIMIT_EXCEEDED')
        self.assertFalse(response.data['success'])
        self.assertIn('Repository analysis limit reached.', response.data['error'])
        self.assertNotIn('GitHub limit', response.data['error'])
