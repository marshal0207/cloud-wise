import base64
from unittest.mock import patch

from django.test import SimpleTestCase

from api.services.github_repository_service import (
    inspect_repository,
)


import base64
from unittest.mock import patch

from django.test import SimpleTestCase

from api.services.github_repository_service import (
    inspect_repository,
)


class GitHubRepositoryInspectionTests(SimpleTestCase):
    @patch('api.services.github_repository_service._request_json')
    def test_fetches_and_decodes_supported_manifest_files(self, request_json):
        def response_for(url, token=None, **kwargs):
            if url.endswith('/repos/owner/repository'):
                return {'default_branch': 'main', 'name': 'repository', 'owner': {'login': 'owner'}}
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

        self.assertEqual(result['repository']['full_name'], 'owner/repository')
        self.assertEqual(result['branch'], 'main')
        self.assertEqual(
            result['files']['package.json'],
            '{"dependencies":{"react":"18.3.1"}}',
        )

    @patch('api.services.github_repository_service._request_json')
    def test_ignores_directories(self, request_json):
        def response_for(url, token=None, **kwargs):
            if url.endswith('/repos/owner/repository'):
                return {'default_branch': 'main', 'name': 'repository', 'owner': {'login': 'owner'}}
            if 'git/trees' in url:
                return {'tree': [{'path': 'src', 'type': 'tree'}]}
            return {'type': 'dir'}

        request_json.side_effect = response_for

        result = inspect_repository(
            'github-token',
            {'full_name': 'owner/repository', 'default_branch': 'main'},
        )

        self.assertEqual(result['files'], {})

    def test_rejects_invalid_repository_name(self):
        with self.assertRaisesRegex(ValueError, 'GitHub repository'):
            inspect_repository('github-token', {'full_name': 'repository'})

    @patch('api.services.github_repository_service._request_json')
    def test_fetches_env_templates_but_never_sensitive_env_files(self, request_json):
        def response_for(url, token=None, **kwargs):
            if url.endswith('/repos/owner/repository'):
                return {'default_branch': 'main', 'name': 'repository', 'owner': {'login': 'owner'}}
            if 'git/trees' in url:
                return {'tree': [
                    {'path': 'package.json', 'type': 'blob', 'size': 40, 'sha': 'a'},
                    {'path': '.env.example', 'type': 'blob', 'size': 25, 'sha': 'b'},
                    {'path': '.env', 'type': 'blob', 'size': 30, 'sha': 'c'},
                ]}
            if '.env.example' in url:
                content = base64.b64encode(b'DATABASE_URL=\nJWT_SECRET=\n').decode()
                return {'type': 'file', 'content': content}
            if '/contents/.env?' in url:
                content = base64.b64encode(b'SECRET=hunter2\n').decode()
                return {'type': 'file', 'content': content}
            if 'package.json' in url:
                content = base64.b64encode(b'{"dependencies":{"react":"18.3.1"}}').decode()
                return {'type': 'file', 'content': content}
            return None

        request_json.side_effect = response_for

        result = inspect_repository(
            'github-token',
            {'full_name': 'owner/repository', 'default_branch': 'main'},
        )

        self.assertIn('.env.example', result['files'])
        self.assertNotIn('.env', result['files'])
        self.assertNotIn('hunter2', str(result['files']))

    @patch('api.services.github_repository_service._request_json')
    def test_returns_repository_size_metadata(self, request_json):
        def response_for(url, token=None, **kwargs):
            if url.endswith('/repos/owner/repository'):
                return {'default_branch': 'main', 'name': 'repository', 'owner': {'login': 'owner'}}
            if 'git/trees' in url:
                return {'tree': [
                    {'path': 'package.json', 'type': 'blob', 'size': 1024, 'sha': 'a'},
                    {'path': 'src/index.js', 'type': 'blob', 'size': 2048, 'sha': 'b'},
                    {'path': 'src', 'type': 'tree', 'sha': 'c'},
                ]}
            if 'package.json' in url:
                content = base64.b64encode(b'{"dependencies":{"react":"18.3.1"}}').decode()
                return {'type': 'file', 'content': content}
            return None

        request_json.side_effect = response_for

        result = inspect_repository(
            'github-token',
            {'full_name': 'owner/repository', 'default_branch': 'main'},
        )

        self.assertEqual(result['repositorySize']['totalBytes'], 3072)
        self.assertEqual(result['repositorySize']['fileCount'], 2)
        self.assertEqual(result['repositorySize']['largestFileBytes'], 2048)
        self.assertEqual(result['totalFiles'], 2)

    @patch('api.services.github_repository_service._request_json')
    def test_raises_platform_limit_error_for_oversized_repository(self, request_json):
        from django.test import override_settings

        from api.services.github_repository_service import RepositoryLimitError

        def response_for(url, token=None, **kwargs):
            if url.endswith('/repos/owner/repository'):
                return {'default_branch': 'main', 'name': 'repository', 'owner': {'login': 'owner'}}
            if 'git/trees' in url:
                return {'tree': [
                    {'path': f'file-{i}.bin', 'type': 'blob', 'size': 1024, 'sha': str(i)}
                    for i in range(50)
                ]}
            return None

        request_json.side_effect = response_for

        with override_settings(MAX_FILES=10):
            with self.assertRaises(RepositoryLimitError) as ctx:
                inspect_repository(
                    'github-token',
                    {'full_name': 'owner/repository', 'default_branch': 'main'},
                )

        message = str(ctx.exception)
        self.assertIn('Repository analysis limit reached.', message)
        self.assertNotIn('GitHub', message)


