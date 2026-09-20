import base64
from unittest.mock import patch

from django.test import SimpleTestCase

from api.services.github_repository_service import (
    inspect_repository,
)


class GitHubRepositoryInspectionTests(SimpleTestCase):
    @patch('api.services.github_repository_service._request_json')
    def test_fetches_and_decodes_supported_manifest_files(self, request_json):
        def response_for(url, token):
            if 'git/trees' in url:
                return {'tree': [{'path': 'package.json', 'type': 'blob'}]}
            if 'package.json' in url:
                content = base64.b64encode(b'{"dependencies":{"react":"18.3.1"}}').decode()
                return {'type': 'file', 'content': content}
            return None

        request_json.side_effect = response_for

        result = inspect_repository(
            'github-token',
            {'full_name': 'owner/repository', 'default_branch': 'main'},
        )

        self.assertEqual(result['repository'], 'owner/repository')
        self.assertEqual(result['branch'], 'main')
        self.assertEqual(
            result['files']['package.json'],
            '{"dependencies":{"react":"18.3.1"}}',
        )

    @patch('api.services.github_repository_service._request_json')
    def test_ignores_directories(self, request_json):
        request_json.return_value = {'type': 'dir'}

        result = inspect_repository(
            'github-token',
            {'full_name': 'owner/repository', 'default_branch': 'main'},
        )

        self.assertEqual(result['files'], {})

    def test_rejects_invalid_repository_name(self):
        with self.assertRaisesRegex(ValueError, 'owner/name'):
            inspect_repository('github-token', {'full_name': 'repository'})
