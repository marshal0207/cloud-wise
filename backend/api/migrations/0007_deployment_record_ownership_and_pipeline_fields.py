# Deployment pipeline: ownership + required per-deployment fields.
#
# Canonical columns are now ``deployment_status`` and ``live_url``
# (renamed from ``status`` / ``endpoint_url`` so there is exactly one
# source of truth). The remaining fields pin the GitHub connection, the
# AWS connection, the repository, the commit and the EC2 instance that
# were used, so authorization and auditing never have to guess.

import django.db.models.deletion
from django.db import migrations, models

# Legacy lowercase vocabularies written before this migration.
_LEGACY_STATUS_MAP = {
    'deployed': 'RUNNING',
    'deploying': 'DEPLOYING',
    'building': 'BUILDING',
    'preparing': 'PREPARING',
    'queued': 'QUEUED',
    'failed': 'FAILED',
    'rollback': 'ROLLED_BACK',
    'rolled_back': 'ROLLED_BACK',
}


def _normalise_status(apps, schema_editor):
    """Fold legacy lowercase statuses into the DeploymentStatus vocabulary."""
    DeploymentRecord = apps.get_model('api', 'DeploymentRecord')
    for old, new in _LEGACY_STATUS_MAP.items():
        DeploymentRecord.objects.filter(deployment_status=old).update(
            deployment_status=new
        )


def _backfill_instance_id(apps, schema_editor):
    """Recover the EC2 instance id stored in provider_deployment_id."""
    DeploymentRecord = apps.get_model('api', 'DeploymentRecord')
    for record in DeploymentRecord.objects.filter(instance_id=''):
        candidate = record.provider_deployment_id or ''
        if candidate.startswith('i-'):
            DeploymentRecord.objects.filter(pk=record.pk).update(
                instance_id=candidate
            )


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_githubconnection_scopes_githubconnection_status_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='deploymentrecord',
            old_name='status',
            new_name='deployment_status',
        ),
        migrations.RenameField(
            model_name='deploymentrecord',
            old_name='endpoint_url',
            new_name='live_url',
        ),
        migrations.AlterField(
            model_name='deploymentrecord',
            name='deployment_status',
            field=models.CharField(default='QUEUED', max_length=50),
        ),
        migrations.AddField(
            model_name='deploymentrecord',
            name='aws_account_id',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='deploymentrecord',
            name='aws_connection',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='deployment_records',
                to='api.awsconnection',
            ),
        ),
        migrations.AddField(
            model_name='deploymentrecord',
            name='commit_sha',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='deploymentrecord',
            name='github_connection',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='deployment_records',
                to='api.githubconnection',
            ),
        ),
        migrations.AddField(
            model_name='deploymentrecord',
            name='instance_id',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='deploymentrecord',
            name='instance_type',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='deploymentrecord',
            name='project',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='deployment_records',
                to='api.project',
            ),
        ),
        migrations.AddField(
            model_name='deploymentrecord',
            name='project_type',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AddField(
            model_name='deploymentrecord',
            name='repository',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='deploymentrecord',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.RunPython(_normalise_status, _noop),
        migrations.RunPython(_backfill_instance_id, _noop),
    ]
