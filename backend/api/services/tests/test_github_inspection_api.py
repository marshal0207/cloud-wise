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
        inspect.assert_called_once_with(
            'server-token',
            self.project.github_repo,
        )

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
