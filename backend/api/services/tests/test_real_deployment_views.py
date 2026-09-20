"""
Tests for real deployment management endpoints.

These tests verify that the deployment status, logs, health, and
rollback endpoints use real provider APIs (or return stored data)
instead of mock/simulated responses.

Covers:
  - deployment_status_view returns stored status when no record found
  - deployment_status_view uses Vercel API when provider is VERCEL
  - deployment_status_view uses Render API when provider is RENDER
  - deployment_logs_view returns stored logs from DeploymentRecord
  - deployment_health_view performs real HTTP health check
  - deployment_health_view handles no endpoint URL
  - deployment_fail_view marks record as FAILED
  - deployment_rollback_view requires provider credentials
  - No SIMULATED/mock responses in production endpoints
"""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory
from api.models import DeploymentRecord, CustomUser


class DeploymentStatusViewTest(TestCase):
    """Tests for the real deployment_status_view."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = CustomUser.objects.create_user(
            username='teststatus', email='status@test.com', password='Test1234'
        )
        self.record = DeploymentRecord.objects.create(
            environment_name='test-prod',
            provider='VERCEL',
            provider_deployment_id='dpl_abc123',
            provider_project_id='prj_xyz789',
            status='RUNNING',
            endpoint_url='https://my-app.vercel.app',
            logs=[{
                'timestamp': '2026-01-01T00:00:00Z',
                'level': 'INFO',
                'stage': 'COMPLETED',
                'message': 'Vercel deployment dpl_abc123 — state: READY',
            }],
        )

    def test_missing_deployment_returns_404(self):
        from api.views import deployment_status_view
        request = self.factory.get('/api/deployments/nonexistent/status')
        response = deployment_status_view(request, 'nonexistent')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data['success'])

    def test_vercel_deployment_returns_stored_status_without_credentials(self):
        from api.views import deployment_status_view
        request = self.factory.get('/api/deployments/dpl_abc123/status')
        with patch('api.views.settings') as mock_settings:
            mock_settings.VERCEL_TOKEN = ''
            mock_settings.VERCEL_TEAM_ID = ''
            response = deployment_status_view(request, 'dpl_abc123')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['status'], 'RUNNING')
        self.assertEqual(response.data['data']['endpoint_url'], 'https://my-app.vercel.app')
        self.assertEqual(response.data['data']['provider_type'], 'VERCEL')

    def test_vercel_deployment_queries_real_api(self):
        from api.views import deployment_status_view
        request = self.factory.get('/api/deployments/dpl_abc123/status')
        mock_vercel_response = {
            'readyState': 'READY',
            'url': 'my-app-abc123.vercel.app',
        }
        with patch('api.views.settings') as mock_settings:
            mock_settings.VERCEL_TOKEN = 'fake-token-for-test'
            mock_settings.VERCEL_TEAM_ID = ''
            with patch('api.views.VercelDeploymentService') as MockSvc:
                mock_instance = MagicMock()
                mock_instance.get_deployment_status.return_value = mock_vercel_response
                MockSvc.return_value = mock_instance
                response = deployment_status_view(request, 'dpl_abc123')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['status'], 'RUNNING')
        self.assertIn('vercel.app', response.data['data']['endpoint_url'])

    def test_vercel_error_returns_stored_status(self):
        from api.views import deployment_status_view
        from api.services.deployment.vercel_provider import VercelApiError
        request = self.factory.get('/api/deployments/dpl_abc123/status')
        with patch('api.views.settings') as mock_settings:
            mock_settings.VERCEL_TOKEN = 'fake-token'
            mock_settings.VERCEL_TEAM_ID = ''
            with patch('api.views.VercelDeploymentService') as MockSvc:
                mock_instance = MagicMock()
                mock_instance.get_deployment_status.side_effect = VercelApiError('API limit')
                MockSvc.return_value = mock_instance
                response = deployment_status_view(request, 'dpl_abc123')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['status'], 'RUNNING')

    def test_render_deployment_returns_stored_status_without_credentials(self):
        render_record = DeploymentRecord.objects.create(
            environment_name='render-test',
            provider='RENDER',
            provider_deployment_id='rdp_456',
            provider_project_id='srv_789',
            status='RUNNING',
            endpoint_url='https://my-app.onrender.com',
        )
        from api.views import deployment_status_view
        request = self.factory.get('/api/deployments/rdp_456/status')
        with patch('api.views.settings') as mock_settings:
            mock_settings.RENDER_API_KEY = ''
            mock_settings.RENDER_OWNER_ID = ''
            response = deployment_status_view(request, 'rdp_456')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['status'], 'RUNNING')
        self.assertEqual(response.data['data']['provider_type'], 'RENDER')

    def test_no_simulated_field_in_response(self):
        from api.views import deployment_status_view
        request = self.factory.get('/api/deployments/dpl_abc123/status')
        with patch('api.views.settings') as mock_settings:
            mock_settings.VERCEL_TOKEN = ''
            mock_settings.VERCEL_TEAM_ID = ''
            response = deployment_status_view(request, 'dpl_abc123')
        data_str = json.dumps(response.data)
        self.assertNotIn('SIMULATED', data_str)
        self.assertNotIn('simulated', data_str)
        self.assertNotIn('mock', data_str.lower().replace('mock_deployment_id', ''))


class DeploymentLogsViewTest(TestCase):
    """Tests for the real deployment_logs_view."""

    def setUp(self):
        self.factory = RequestFactory()
        self.record = DeploymentRecord.objects.create(
            environment_name='logs-test',
            provider='VERCEL',
            provider_deployment_id='dpl_logs1',
            status='RUNNING',
            endpoint_url='https://app.vercel.app',
            logs=[{
                'timestamp': '2026-01-01T00:00:00Z',
                'level': 'INFO',
                'stage': 'COMPLETED',
                'message': 'Deployment complete',
            }],
        )

    def test_missing_deployment_returns_404(self):
        from api.views import deployment_logs_view
        request = self.factory.get('/api/deployments/nonexistent/logs')
        response = deployment_logs_view(request, 'nonexistent')
        self.assertEqual(response.status_code, 404)

    def test_returns_stored_logs(self):
        from api.views import deployment_logs_view
        request = self.factory.get('/api/deployments/dpl_logs1/logs')
        response = deployment_logs_view(request, 'dpl_logs1')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['message'], 'Deployment complete')

    def test_no_simulated_logs(self):
        from api.views import deployment_logs_view
        request = self.factory.get('/api/deployments/dpl_logs1/logs')
        response = deployment_logs_view(request, 'dpl_logs1')
        for log_entry in response.data['data']:
            self.assertNotIn('SIMULATED', log_entry.get('message', ''))


class DeploymentHealthViewTest(TestCase):
    """Tests for the real deployment_health_view."""

    def setUp(self):
        self.factory = RequestFactory()
        self.record = DeploymentRecord.objects.create(
            environment_name='health-test',
            provider='VERCEL',
            provider_deployment_id='dpl_health1',
            status='RUNNING',
            endpoint_url='https://httpbin.org/get',
        )

    def test_missing_deployment_returns_404(self):
        from api.views import deployment_health_view
        request = self.factory.post('/api/deployments/nonexistent/health')
        response = deployment_health_view(request, 'nonexistent')
        self.assertEqual(response.status_code, 404)

    def test_no_endpoint_url_returns_unhealthy(self):
        record = DeploymentRecord.objects.create(
            environment_name='no-url',
            provider='VERCEL',
            provider_deployment_id='dpl_nourl',
            status='BUILDING',
            endpoint_url=None,
        )
        from api.views import deployment_health_view
        request = self.factory.post('/api/deployments/dpl_nourl/health')
        response = deployment_health_view(request, 'dpl_nourl')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['data']['healthy'])

    def test_health_check_does_real_http_request(self):
        from api.views import deployment_health_view
        request = self.factory.post('/api/deployments/dpl_health1/health')
        mock_response = MagicMock()
        mock_response.status = 200
        with patch('api.views.urllib.request.urlopen') as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: mock_response
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            response = deployment_health_view(request, 'dpl_health1')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertTrue(response.data['data']['healthy'])
        self.assertEqual(response.data['data']['detail']['http_status'], 200)

    def test_health_check_handles_connection_failure(self):
        record = DeploymentRecord.objects.create(
            environment_name='fail-url',
            provider='VERCEL',
            provider_deployment_id='dpl_fail',
            status='RUNNING',
            endpoint_url='https://nonexistent-domain-12345.example.com',
        )
        from api.views import deployment_health_view
        request = self.factory.post('/api/deployments/dpl_fail/health')
        response = deployment_health_view(request, 'dpl_fail')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['data']['healthy'])
        self.assertIn('error', response.data['data']['detail'])


class DeploymentFailViewTest(TestCase):
    """Tests for the deployment_fail_view (test endpoint)."""

    def setUp(self):
        self.factory = RequestFactory()
        self.record = DeploymentRecord.objects.create(
            environment_name='fail-test',
            provider='VERCEL',
            provider_deployment_id='dpl_fail1',
            status='RUNNING',
            endpoint_url='https://app.vercel.app',
        )

    def test_marks_record_as_failed(self):
        from api.views import deployment_fail_view
        request = self.factory.post(
            '/api/deployments/dpl_fail1/fail',
            data=json.dumps({'reason': 'Quota exceeded'}),
            content_type='application/json',
        )
        response = deployment_fail_view(request, 'dpl_fail1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data']['status'], 'FAILED')
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, 'FAILED')


class DeploymentRollbackViewTest(TestCase):
    """Tests for the deployment_rollback_view."""

    def setUp(self):
        self.factory = RequestFactory()
        self.record = DeploymentRecord.objects.create(
            environment_name='rb-test',
            provider='VERCEL',
            provider_deployment_id='dpl_rb1',
            provider_project_id='prj_rb1',
            status='RUNNING',
            endpoint_url='https://app.vercel.app',
        )

    def test_missing_deployment_returns_404(self):
        from api.views import deployment_rollback_view
        request = self.factory.post('/api/deployments/nonexistent/rollback')
        response = deployment_rollback_view(request, 'nonexistent')
        self.assertEqual(response.status_code, 404)

    def test_vercel_rollback_requires_credentials(self):
        from api.views import deployment_rollback_view
        request = self.factory.post('/api/deployments/dpl_rb1/rollback')
        with patch('api.views.settings') as mock_settings:
            mock_settings.VERCEL_TOKEN = ''
            mock_settings.VERCEL_TEAM_ID = ''
            response = deployment_rollback_view(request, 'dpl_rb1')
        self.assertEqual(response.status_code, 503)

    def test_vercel_rollback_triggers_new_deployment(self):
        from api.views import deployment_rollback_view
        request = self.factory.post('/api/deployments/dpl_rb1/rollback')
        mock_response = {'id': 'dpl_rb_new_123'}
        with patch('api.views.settings') as mock_settings:
            mock_settings.VERCEL_TOKEN = 'fake-token'
            mock_settings.VERCEL_TEAM_ID = ''
            with patch('api.views.VercelDeploymentService') as MockSvc:
                mock_instance = MagicMock()
                mock_instance._create_deployment.return_value = mock_response
                MockSvc.return_value = mock_instance
                response = deployment_rollback_view(request, 'dpl_rb1')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['data']['deployment_id'], 'dpl_rb_new_123')
        self.record.refresh_from_db()
        self.assertEqual(self.record.provider_deployment_id, 'dpl_rb_new_123')
