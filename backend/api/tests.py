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
        # Authenticated deploy with no GitHub repo linked returns 400.
        user, token = self._create_user_and_token('deployer@cloudwise.io', 'Pass1234', 'Deployer')
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        data = {
            'environmentName': 'demo-prod',
            'provider': 'Vercel',
            'monthlyCost': 0,
            'specs': {'vcpu': 2, 'ram': 2, 'storage': '30 GB EBS'}
        }
        res = self.client.post('/api/deploy', data=data, content_type='application/json', **headers)
        # No project exists for this user — expect 400
        self.assertIn(res.status_code, [400, 503])

    def test_waitlist(self):
        data = {'email': 'subscriber@example.com', 'source': 'landing_page'}
        res = self.client.post('/api/waitlist', data=data, content_type='application/json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.json()['success'])

    def test_monitoring(self):
        res = self.client.get('/api/monitoring')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['data']['healthStatus'], 'Healthy')
        self.assertIn('clusterUptime', res.json()['data'])
        self.assertIn('activeNodes', res.json()['data'])
        self.assertIn('ipAddress', res.json()['data'])
        self.assertIn('endpointUrl', res.json()['data'])

    def test_pricing_compare_exact_tier_match(self):
        from api.models import CloudPricingCache
        from decimal import Decimal

        # Seed Tier 3 cache entries
        CloudPricingCache.objects.create(
            provider='AWS',
            instance_type='c6i.xlarge',
            region='Asia Pacific (Mumbai)',
            price_per_month=Decimal('10300.00'),
            hourly_usd=Decimal('0.1700'),
            specs={'vcpu': 4, 'ramGB': 16, 'storageGB': 100},
            source='AWS Pricing API',
        )
        CloudPricingCache.objects.create(
            provider='Azure',
            instance_type='Standard_D4s_v5',
            region='Asia Pacific (Mumbai)',
            price_per_month=Decimal('11633.00'),
            hourly_usd=Decimal('0.1920'),
            specs={'vcpu': 4, 'ramGB': 16, 'storageGB': 100},
            source='Azure Retail Prices API',
        )
        CloudPricingCache.objects.create(
            provider='GCP',
            instance_type='e2-custom-4-16384',
            region='Asia Pacific (Mumbai)',
            price_per_month=Decimal('8846.00'),
            hourly_usd=Decimal('0.1460'),
            specs={'vcpu': 4, 'ramGB': 16, 'storageGB': 100},
            source='GCP Pricing (Estimated Fallback)',
        )

        res = self.client.get('/api/pricing/compare?vcpu=4&ram=16&region=Asia%20Pacific%20(Mumbai)')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body['success'])
        data = body['data']
        self.assertEqual(data['matchType'], 'EXACT_TIER')
        self.assertEqual(data['matchedTier'], 'Tier 3 (Production Baseline)')
        self.assertIn('AWS', data['providers'])
        self.assertIn('Azure', data['providers'])
        self.assertIn('GCP', data['providers'])
        self.assertEqual(data['providers']['AWS']['monthlyInr'], 10300)
        self.assertEqual(data['providers']['Azure']['monthlyInr'], 11633)
        self.assertEqual(data['providers']['GCP']['monthlyInr'], 8846)

    def test_pricing_compare_closest_match_within_20_percent(self):
        from api.models import CloudPricingCache
        from decimal import Decimal

        # 4 vCPU / 15 GB RAM is within 6.25% of Tier 3 (4 vCPU / 16 GB)
        CloudPricingCache.objects.create(
            provider='AWS',
            instance_type='c6i.xlarge',
            region='Asia Pacific (Mumbai)',
            price_per_month=Decimal('10300.00'),
            hourly_usd=Decimal('0.1700'),
            specs={'vcpu': 4, 'ramGB': 16},
            source='AWS Pricing API',
        )
        CloudPricingCache.objects.create(
            provider='Azure',
            instance_type='Standard_D4s_v5',
            region='Asia Pacific (Mumbai)',
            price_per_month=Decimal('11633.00'),
            hourly_usd=Decimal('0.1920'),
            specs={'vcpu': 4, 'ramGB': 16},
            source='Azure Retail Prices API',
        )
        CloudPricingCache.objects.create(
            provider='GCP',
            instance_type='e2-custom-4-16384',
            region='Asia Pacific (Mumbai)',
            price_per_month=Decimal('8846.00'),
            hourly_usd=Decimal('0.1460'),
            specs={'vcpu': 4, 'ramGB': 16},
            source='GCP Pricing (Estimated Fallback)',
        )

        res = self.client.get('/api/pricing/compare?vcpu=4&ram=15&region=Asia%20Pacific%20(Mumbai)')
        self.assertEqual(res.status_code, 200)
        data = res.json()['data']
        self.assertEqual(data['matchType'], 'CLOSEST_MATCH')
        self.assertEqual(data['matchedTier'], 'Tier 3 (Production Baseline)')
        self.assertEqual(data['providers']['AWS']['matchType'], 'CLOSEST_MATCH')

    def test_pricing_compare_on_demand_lookup_beyond_tiers(self):
        from unittest.mock import patch
        from api.models import CloudPricingCache

        # 32 vCPU / 128 GB RAM exceeds Tier 5 (16 vCPU / 64 GB) -> triggers ON_DEMAND_LOOKUP
        with patch('api.services.pricing_comparison_service.get_aws_price_snapshot') as mock_aws, \
             patch('api.services.pricing_comparison_service.get_azure_price_snapshot') as mock_az, \
             patch('api.services.pricing_comparison_service.get_gcp_price_snapshot') as mock_gcp:

            mock_aws.return_value = {
                'provider': 'AWS',
                'instanceType': 'c6i.8xlarge',
                'region': 'Asia Pacific (Mumbai)',
                'hourlyUsd': 1.36,
                'monthlyUsd': 992.8,
                'usdToInrRate': 83.0,
                'monthlyInr': 82402,
                'source': 'AWS Pricing API',
                'specs': {'vcpu': 32, 'ramGB': 128},
            }
            mock_az.return_value = {
                'provider': 'Azure',
                'instanceType': 'Standard_D32s_v5',
                'region': 'Asia Pacific (Mumbai)',
                'hourlyUsd': 1.536,
                'monthlyUsd': 1121.28,
                'usdToInrRate': 83.0,
                'monthlyInr': 93066,
                'source': 'Azure Retail Prices API',
                'specs': {'vcpu': 32, 'ramGB': 128},
            }
            mock_gcp.return_value = {
                'provider': 'GCP',
                'instanceType': 'e2-custom-32-131072',
                'region': 'Asia Pacific (Mumbai)',
                'hourlyUsd': 1.17,
                'monthlyUsd': 854.1,
                'usdToInrRate': 83.0,
                'monthlyInr': 70890,
                'source': 'GCP Pricing (Estimated Fallback)',
                'specs': {'vcpu': 32, 'ramGB': 128},
            }

            res = self.client.get('/api/pricing/compare?vcpu=32&ram=128')
            self.assertEqual(res.status_code, 200)
            data = res.json()['data']
            self.assertEqual(data['matchType'], 'ON_DEMAND_LOOKUP')
            self.assertIsNone(data['matchedTier'])
            self.assertEqual(data['providers']['AWS']['instanceType'], 'c6i.8xlarge')
            self.assertEqual(data['providers']['Azure']['instanceType'], 'Standard_D32s_v5')
            self.assertEqual(data['providers']['GCP']['instanceType'], 'e2-custom-32-131072')

            # Verify cached in database on the fly
            self.assertTrue(CloudPricingCache.objects.filter(instance_type='c6i.8xlarge').exists())
            self.assertTrue(CloudPricingCache.objects.filter(instance_type='Standard_D32s_v5').exists())
            self.assertTrue(CloudPricingCache.objects.filter(instance_type='e2-custom-32-131072').exists())

    def test_legacy_aws_pricing_endpoint_backward_compatibility(self):
        from unittest.mock import patch

        with patch('api.views.get_aws_price_snapshot') as mock_aws:
            mock_aws.return_value = {
                'provider': 'AWS',
                'instanceType': 'c6i.xlarge',
                'region': 'Asia Pacific (Mumbai)',
                'hourlyUsd': 0.17,
                'monthlyUsd': 124.1,
                'usdToInrRate': 83.0,
                'monthlyInr': 10300,
                'source': 'AWS Pricing API',
            }

            res = self.client.get('/api/pricing/aws?instanceType=c6i.xlarge')
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json()['success'])
            self.assertEqual(res.json()['data']['instanceType'], 'c6i.xlarge')
