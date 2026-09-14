from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
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

    def test_projects_crud(self):
        # List projects (auto seeds default if empty)
        res = self.client.get('/api/projects')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])

        # Create project
        proj_data = {
            'name': 'New Microservice App',
            'description': 'Test project description',
            'environment': 'Staging'
        }
        res_create = self.client.post('/api/projects', data=proj_data, content_type='application/json')
        self.assertEqual(res_create.status_code, 201)
        proj_id = res_create.json()['data']['id']

        # Get project detail
        res_detail = self.client.get(f'/api/projects/{proj_id}')
        self.assertEqual(res_detail.status_code, 200)
        self.assertEqual(res_detail.json()['data']['name'], 'New Microservice App')

        # Update project
        update_data = {'name': 'Updated Microservice App'}
        res_update = self.client.put(f'/api/projects/{proj_id}', data=update_data, content_type='application/json')
        self.assertEqual(res_update.status_code, 200)
        self.assertEqual(res_update.json()['data']['name'], 'Updated Microservice App')

        # Connect GitHub
        res_github = self.client.post(f'/api/projects/{proj_id}/github', data={'repoName': 'org/repo'}, content_type='application/json')
        self.assertEqual(res_github.status_code, 200)
        self.assertTrue(res_github.json()['data']['githubRepo']['synced'])

        # Delete project
        res_delete = self.client.delete(f'/api/projects/{proj_id}')
        self.assertEqual(res_delete.status_code, 200)

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
        data = {
            'environmentName': 'demo-prod',
            'provider': 'AWS',
            'monthlyCost': 15000,
            'specs': {'vcpu': 2, 'ram': 2, 'storage': '30 GB EBS'}
        }
        res = self.client.post('/api/deploy', data=data, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['success'])

    def test_waitlist(self):
        data = {'email': 'subscriber@example.com', 'source': 'landing_page'}
        res = self.client.post('/api/waitlist', data=data, content_type='application/json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()['success'])

    def test_monitoring(self):
        res = self.client.get('/api/monitoring')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['data']['healthStatus'], 'Healthy')
