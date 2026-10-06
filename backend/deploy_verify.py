import sys
sys.path.insert(0, r'T:\D-drive\Sem - 5\sgp - 2\backend')
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
import django
django.setup()
from api.services.deployment.deployment_file_generator import generate_deployment_files
print('OK imported')