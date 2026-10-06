from unittest.mock import patch

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from api.models import Project, ContactInquiry, EstimationRecord, DeploymentRecord, WaitlistSubscriber

User = get_user_model()

class BackendApiTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_health_endpoint(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_signup_and_login(self):
        # Signup
        signup_data = {
            'name': 'Test Engineer',
            'email': 'test@cloudwise.io',
            'password': 'Pass1234',
            'company': 'CloudWise Labs'
        }
        res = self.client.post('/api/auth/signup', data=signup_data, content_type='application/json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()['success'])
        self.assertIn('token', res.json())

        # Login
        login_data = {
            'email': 'test@cloudwise.io',
            'password': 'Pass1234'
        }
        res_login = self.client.post('/api/auth/login', data=login_data, content_type='application/json')
        self.assertEqual(res_login.status_code, 200)
        self.assertTrue(res_login.json()['success'])

    def _create_user_and_token(self, email, password, name, role='owner'):
        user = User.objects.create_user(
            username=email.split('@')[0],
            email=email,
            password=password,
            first_name=name,
            role=role
        )
        refresh = RefreshToken.for_user(user)
        return user, str(refresh.access_token)

    def test_unauthenticated_access_rejected(self):
        # 1. Unauthenticated requests must be rejected with 401
        res_list = self.client.get('/api/projects')
        self.assertEqual(res_list.status_code, 401)

        res_post = self.client.post('/api/projects', data={'name': 'Hacker Project'}, content_type='application/json')
        self.assertEqual(res_post.status_code, 401)

        res_detail = self.client.get('/api/projects/proj_fake')
        self.assertEqual(res_detail.status_code, 401)

        res_put = self.client.put('/api/projects/proj_fake', data={'name': 'Hacker'}, content_type='application/json')
        self.assertEqual(res_put.status_code, 401)

        res_del = self.client.delete('/api/projects/proj_fake')
        self.assertEqual(res_del.status_code, 401)

    def test_new_user_empty_state_no_static_projects(self):
        # 2. A new user with no projects must see empty list [] (no static "E-Commerce API Service")
        _, token = self._create_user_and_token('newbie@cloudwise.io', 'Pass1234', 'Newbie User')
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

        res = self.client.get('/api/projects', **headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertEqual(res.json()['data'], [])
        self.assertEqual(Project.objects.count(), 0)

    def test_projects_crud_authenticated(self):
        # 3. Authenticated user can create, read, update, and delete their project
        user, token = self._create_user_and_token('dev@cloudwise.io', 'Pass1234', 'Dev User')
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

        # Create project
        proj_data = {
            'name': 'Real Microservice App',
            'description': 'Real database backed project description',
            'environment': 'Staging',
            'role': 'owner'
        }
        res_create = self.client.post('/api/projects', data=proj_data, content_type='application/json', **headers)
        self.assertEqual(res_create.status_code, 201)
        created = res_create.json()['data']
        proj_id = created['id']
        self.assertEqual(created['name'], 'Real Microservice App')
        self.assertEqual(created['userId'], str(user.id))

        # Verify DB persistence
        db_proj = Project.objects.get(pk=proj_id)
        self.assertEqual(db_proj.name, 'Real Microservice App')
        self.assertEqual(db_proj.user, user)

        # Get project detail
        res_detail = self.client.get(f'/api/projects/{proj_id}', **headers)
        self.assertEqual(res_detail.status_code, 200)
        self.assertEqual(res_detail.json()['data']['name'], 'Real Microservice App')

        # Update project
        update_data = {'name': 'Updated Real Microservice App'}
        res_update = self.client.put(f'/api/projects/{proj_id}', data=update_data, content_type='application/json', **headers)
        self.assertEqual(res_update.status_code, 200)
        self.assertEqual(res_update.json()['data']['name'], 'Updated Real Microservice App')

        # Connect GitHub
        res_github = self.client.post(f'/api/projects/{proj_id}/github', data={'repoName': 'org/repo'}, content_type='application/json', **headers)
        self.assertEqual(res_github.status_code, 200)
        self.assertTrue(res_github.json()['data']['githubRepo']['synced'])

        # Delete project
        res_delete = self.client.delete(f'/api/projects/{proj_id}', **headers)
        self.assertEqual(res_delete.status_code, 200)
        self.assertFalse(Project.objects.filter(pk=proj_id).exists())

    def test_user_isolation(self):
        # 4. User A sees only Project A. User B sees only Project B.
        # Direct API access to the other user's project must fail with 403.
        user_a, token_a = self._create_user_and_token('user_a@cloudwise.io', 'Pass1234', 'User Alpha')
        user_b, token_b = self._create_user_and_token('user_b@cloudwise.io', 'Pass1234', 'User Beta')

        headers_a = {'HTTP_AUTHORIZATION': f'Bearer {token_a}'}
        headers_b = {'HTTP_AUTHORIZATION': f'Bearer {token_b}'}

        # User A creates Project A
        res_a = self.client.post('/api/projects', data={'name': 'Project Alpha'}, content_type='application/json', **headers_a)
        self.assertEqual(res_a.status_code, 201)
        proj_a_id = res_a.json()['data']['id']

        # User B creates Project B
        res_b = self.client.post('/api/projects', data={'name': 'Project Beta'}, content_type='application/json', **headers_b)
        self.assertEqual(res_b.status_code, 201)
        proj_b_id = res_b.json()['data']['id']

        # User A lists projects -> sees ONLY Project Alpha
        list_a = self.client.get('/api/projects', **headers_a)
        self.assertEqual(list_a.status_code, 200)
        list_a_ids = [p['id'] for p in list_a.json()['data']]
        self.assertIn(proj_a_id, list_a_ids)
        self.assertNotIn(proj_b_id, list_a_ids)

        # User B lists projects -> sees ONLY Project Beta
        list_b = self.client.get('/api/projects', **headers_b)
        self.assertEqual(list_b.status_code, 200)
        list_b_ids = [p['id'] for p in list_b.json()['data']]
        self.assertIn(proj_b_id, list_b_ids)
        self.assertNotIn(proj_a_id, list_b_ids)

        # User A attempts to access Project B -> 403 Forbidden
        cross_get = self.client.get(f'/api/projects/{proj_b_id}', **headers_a)
        self.assertEqual(cross_get.status_code, 403)
        self.assertIn('error', cross_get.json())

        # User A attempts to modify Project B -> 403 Forbidden
        cross_put = self.client.put(f'/api/projects/{proj_b_id}', data={'name': 'Tampered by A'}, content_type='application/json', **headers_a)
        self.assertEqual(cross_put.status_code, 403)

        # User A attempts to delete Project B -> 403 Forbidden
        cross_del = self.client.delete(f'/api/projects/{proj_b_id}', **headers_a)
        self.assertEqual(cross_del.status_code, 403)

        # User B attempts to access Project A -> 403 Forbidden
        cross_get_b = self.client.get(f'/api/projects/{proj_a_id}', **headers_b)
        self.assertEqual(cross_get_b.status_code, 403)

        # User B attempts to delete Project A -> 403 Forbidden
        cross_del_b = self.client.delete(f'/api/projects/{proj_a_id}', **headers_b)
        self.assertEqual(cross_del_b.status_code, 403)

        # Both projects still intact in database
        self.assertTrue(Project.objects.filter(pk=proj_a_id).exists())
        self.assertTrue(Project.objects.filter(pk=proj_b_id).exists())

    def test_rbac_viewer_restrictions(self):
        # 5. Viewer role cannot create, modify, or delete projects
        user_viewer, token_viewer = self._create_user_and_token('viewer@cloudwise.io', 'Pass1234', 'Viewer User', role='viewer')
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token_viewer}'}

        # Viewer create rejected
        res = self.client.post('/api/projects', data={'name': 'Viewer Project'}, content_type='application/json', **headers)
        self.assertEqual(res.status_code, 403)

    def test_contact_inquiry(self):
        data = {
            'name': 'Aditya',
            'email': 'aditya@example.com',
            'subject': 'Enterprise Quote',
            'message': 'Need assistance with cloud migration.'
        }
        res = self.client.post('/api/contact', data=data, content_type='application/json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()['success'])

    def test_estimation(self):
        data = {
            'appType': 'Web App',
            'vcpu': 4,
            'ram': 16,
            'storage': 200,
            'region': 'Gujarat (GIFT City / Gandhinagar)'
        }
        res = self.client.post('/api/estimate', data=data, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])
        self.assertIn('minCost', res.json()['data']['calculatedResult'])

    def test_deployment(self):
        # deploy_view now requires authentication and real provider credentials.
        # Without auth it must return 401.
        data = {
            'environmentName': 'demo-prod',
            'provider': 'Vercel',
            'monthlyCost': 0,
            'specs': {'vcpu': 2, 'ram': 2, 'storage': '30 GB EBS'}
        }
        res = self.client.post('/api/deploy', data=data, content_type='application/json')
        self.assertEqual(res.status_code, 401)

    def test_deployment_blocked_without_credentials(self):
        # Authenticated deploy: retired provider OR no project → 400/503.
        user, token = self._create_user_and_token('deployer@cloudwise.io', 'Pass1234', 'Deployer')
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        data = {
            'environmentName': 'demo-prod',
            'provider': 'Vercel',
            'monthlyCost': 0,
            'specs': {'vcpu': 2, 'ram': 2, 'storage': '30 GB EBS'}
        }
        res = self.client.post('/api/deploy', data=data, content_type='application/json', **headers)
        # Vercel is retired (400) or no project exists (400/503)
        self.assertIn(res.status_code, [400, 503])

    def test_waitlist(self):
        data = {'email': 'subscriber@example.com', 'source': 'landing_page'}
        res = self.client.post('/api/waitlist', data=data, content_type='application/json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()['success'])

    def test_monitoring(self):
        # Monitoring is authenticated: anonymous callers get 401.
        self.assertEqual(self.client.get('/api/monitoring').status_code, 401)

        user, token = self._create_user_and_token('ops@cloudwise.io', 'Pass1234', 'Ops')
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}

        # A brand new user has no deployments — reported, not invented.
        res = self.client.get('/api/monitoring', **headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()['data']
        self.assertFalse(data['metricsCollected'])
        self.assertIsNone(data['cpuUsage'])
        self.assertEqual(data['healthStatus'], 'Not deployed')
        self.assertEqual(data['activeNodes'], 0)
        for key in ('clusterUptime', 'activeNodes', 'ipAddress', 'endpointUrl', 'deploymentId'):
            self.assertIn(key, data)

        # Real record → real telemetry derived from it.
        DeploymentRecord.objects.create(
            user=user,
            environment_name='ops-prod',
            provider='AWS',
            provider_deployment_id='i-ops1',
            instance_id='i-ops1',
            instance_type='t3.micro',
            deployment_status='RUNNING',
            live_url='https://ops.example.com',
            ip_address='13.232.1.44',
        )
        with patch('api.views._probe_url', return_value=(True, 200)):
            res = self.client.get('/api/monitoring', **headers)
        data = res.json()['data']
        self.assertEqual(data['deploymentStatus'], 'RUNNING')
        self.assertEqual(data['instanceId'], 'i-ops1')
        self.assertEqual(data['healthStatus'], 'Healthy')
        self.assertEqual(data['activeNodes'], 1)
        self.assertEqual(data['endpointUrl'], 'https://ops.example.com')

    def test_monitoring_is_scoped_to_the_calling_user(self):
        owner, _ = self._create_user_and_token('owner2@cloudwise.io', 'Pass1234', 'Owner')
        DeploymentRecord.objects.create(
            user=owner,
            environment_name='secret-prod',
            provider='AWS',
            provider_deployment_id='i-secret1',
            instance_id='i-secret1',
            deployment_status='RUNNING',
            live_url='https://secret.example.com',
        )
        other, token = self._create_user_and_token('other2@cloudwise.io', 'Pass1234', 'Other')
        res = self.client.get(
            '/api/monitoring', HTTP_AUTHORIZATION=f'Bearer {token}'
        )
        data = res.json()['data']
        self.assertIsNone(data['deploymentId'])
        self.assertEqual(data['healthStatus'], 'Not deployed')
