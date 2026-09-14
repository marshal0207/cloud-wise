import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from api.models import Project
from api.services.github_service import push_files_to_repository


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class GitHubPushServiceTests(APITestCase):
    @patch('api.services.github_service.urllib.request.urlopen')
    def test_creates_new_file_with_encoded_content(self, urlopen):
        urlopen.side_effect = [
            FakeResponse(None),
            FakeResponse({'commit': {'sha': 'new-commit-sha'}}),
        ]

        result = push_files_to_repository(
            'token',
            {'full_name': 'owner/repository', 'default_branch': 'main'},
            {'Dockerfile': 'FROM python:3.13-slim'},
            'Add deployment files',
        )

        self.assertEqual(result['commit'], 'new-commit-sha')
        put_request = urlopen.call_args_list[1].args[0]
        payload = json.loads(put_request.data.decode())
        self.assertEqual(payload['message'], 'Add deployment files')
        self.assertNotIn('sha', payload)

    @patch('api.services.github_service.urllib.request.urlopen')
    def test_updates_existing_file_with_sha(self, urlopen):
        urlopen.side_effect = [
            FakeResponse({'sha': 'existing-sha'}),
            FakeResponse({'commit': {'sha': 'updated-commit-sha'}}),
        ]

        push_files_to_repository(
            'token',
            {'full_name': 'owner/repository', 'default_branch': 'main'},
            {'Dockerfile': 'FROM node:20-alpine'},
            'Update deployment files',
        )

        put_request = urlopen.call_args_list[1].args[0]
        payload = json.loads(put_request.data.decode())
        self.assertEqual(payload['sha'], 'existing-sha')


class GitHubPushApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='push-user',
            email='push@example.com',
            password='Passw0rd',
        )
        self.client.force_authenticate(user=self.user)

    def test_rejects_push_without_selected_repository(self):
        project = Project.objects.create(
            user=self.user,
            user_id_str=str(self.user.id),
            name='Push Test Project',
        )

        response = self.client.post(
            f'/api/projects/{project.id}/github/push',
            {'files': {'Dockerfile': 'FROM alpine'}},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['success'])
