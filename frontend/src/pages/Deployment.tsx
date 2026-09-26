import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Rocket,
  CheckCircle2,
  Clock,
  Terminal,
  Server,
  ShieldCheck,
  Globe,
  Activity,
  RefreshCw,
  Cloud,
  AlertTriangle,
  Eye,
  EyeOff,
  FileCode2,
  Database,
  GitBranch,
  ListChecks,
  ExternalLink,
} from 'lucide-react';
import { useCloudWise, formatINR } from '@/context/CloudWiseContext';

type PipelinePhase =
  | 'idle'
  | 'preparing'
  | 'provisioning'
  | 'configuring'
  | 'deployed'
  | 'failed';

interface EnvVarRow {
  key: string;
  value: string;
  required: boolean;
}

interface DetectionInfo {
  technology?: string;
  frontend?: string;
  backend?: string;
  database?: string;
  applicationType?: string;
}

interface DeploymentPlanInfo {
  target?: string;
  containers?: string[];
  generatedFiles?: string[];
  requiredEnvVars?: string[];
  ports?: number[];
  requiresNginx?: boolean;
}

const authHeaders = (): Record<string, string> => {
  const token = localStorage.getItem('cloudwise_token');
  return { Authorization: token ? `Bearer ${token}` : '' };
};

const NINE_STEPS = [
  { key: 'analyze', label: '1. Analyze Repository', desc: 'Inspect stack, frameworks, database' },
  { key: 'generate', label: '2. Generate Docker Files', desc: 'Dockerfile, compose, nginx' },
  { key: 'env', label: '3. Configure Env Vars', desc: 'Upload .env or enter manually' },
  { key: 'connect', label: '4. Connect AWS Account', desc: 'IAM role ARN + external ID' },
  { key: 'sts', label: '5. Assume IAM Role / STS', desc: 'Temporary credentials only' },
  { key: 'sg', label: '6. Security Group & AMI', desc: 'Ports 80/443/22 · resolve AMI' },
  { key: 'launch', label: '7. Launch / Reuse EC2', desc: 'Create or reuse free-tier instance' },
  { key: 'compose', label: '8. Upload & Compose Up', desc: 'SSM upload · docker compose up' },
  { key: 'health', label: '9. Health Check & Live URL', desc: 'Verify HTTP · expose endpoint' },
];

// Four user-facing gates. Backend stage codes map onto these directly:
//   PROJECT / GITHUB → Repository / GitHub, ENVIRONMENT → Deployment,
//   AWS → AWS, and the pipeline's own failureStage → Deployment.
const CHECKLIST_STAGES = [
  { key: 'GITHUB', label: 'GitHub', desc: 'OAuth authorization accepted, token readable' },
  { key: 'REPOSITORY', label: 'Repository', desc: 'Repository linked, files readable, commit resolved' },
  { key: 'AWS', label: 'AWS', desc: 'IAM role assumed via STS, account validated' },
  { key: 'DEPLOYMENT', label: 'Deployment', desc: 'EC2 provisioned · containers up · health check · live URL' },
] as const;

type ChecklistStatus = 'pending' | 'active' | 'done' | 'failed';
type ChecklistKey = (typeof CHECKLIST_STAGES)[number]['key'];

const stageKeyFromBackendStage = (stage?: string, message?: string): ChecklistKey => {
  const s = (stage || '').toUpperCase();
  const m = (message || '').trim();
  if (s === 'GITHUB') return 'GITHUB';
  if (s === 'PROJECT') return 'REPOSITORY';
  if (s === 'AWS' || m.startsWith('AWS:') || m.startsWith('BLOCKED')) return 'AWS';
  return 'DEPLOYMENT';
};

const PHASE_TO_STEP: Record<PipelinePhase, number> = {
  idle: -1,
  preparing: 3,
  provisioning: 6,
  configuring: 7,
  deployed: 8,
  failed: -2,
};

export const Deployment: React.FC = () => {
  const navigate = useNavigate();
  const {
    selectedRecommendation,
    estimation,
    deployment: contextDeployment,
    updateActiveProject,
    activeProject,
    showToast,
  } = useCloudWise();

  const provider = 'AWS' as const;

  const [envName, setEnvName] = useState(
    activeProject?.name
      ? activeProject.name.toLowerCase().replace(/\s+/g, '-') + '-prod'
      : contextDeployment.environmentName || 'cloudwise-prod-cluster'
  );

  const [showDeployConfirmation, setShowDeployConfirmation] = useState(false);

  const [deploymentId, setDeploymentId] = useState<string | null>(
    () => activeProject?.deployment?.providerDeploymentId || null
  );

  const [liveDeployment, setLiveDeployment] = useState(() => {
    const saved = activeProject?.deployment;
    if (saved && saved.status !== 'idle') return saved;
    return contextDeployment;
  });
  const [showLogs, setShowLogs] = useState(false);
  const [polling, setPolling] = useState(false);

  const [awsConnection, setAwsConnection] = useState<{
    connected: boolean;
    accountId?: string;
    region?: string;
    roleArn?: string;
  } | null>(null);

  // Analysis panel (from Generate Files step / inspect)
  const [detection, setDetection] = useState<DetectionInfo | null>(null);
  const [deploymentPlan, setDeploymentPlan] = useState<DeploymentPlanInfo | null>(null);
  const [generatedFileList, setGeneratedFileList] = useState<string[]>([]);

  // Env configuration
  const [envRows, setEnvRows] = useState<EnvVarRow[]>([]);
  const [envMasked, setEnvMasked] = useState(true);
  const [envSource, setEnvSource] = useState<'manual' | 'upload' | null>(null);
   const [activeStepIndex, setActiveStepIndex] = useState(-1);
   const [scanProgress, setScanProgress] = useState<Array<{stage: string; message: string; progress: number}>>([]);
   const [tokenExpired, setTokenExpired] = useState(false);
   const [rateLimited, setRateLimited] = useState(false);

   const repoName = activeProject?.githubRepo?.name;
  const missingRepo = !repoName;

  // Stage-tagged failure returned by POST /api/deploy or by the pipeline
  const [stageError, setStageError] = useState<{ stage: string; message: string } | null>(null);
  const [pipelineFailure, setPipelineFailure] = useState<{ stage: string; message: string } | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [lastDeploymentId, setLastDeploymentId] = useState<string | null>(null);

  const refreshAwsConnection = async () => {
    try {
      const res = await fetch('/api/aws/connection', { headers: authHeaders() });
      const data = await res.json();
      if (data.success) setAwsConnection(data.data);
    } catch {
      // banner shows "not connected"
    }
  };

  useEffect(() => {
    void refreshAwsConnection();
  }, []);

  // Restore analysis info from context if available
  useEffect(() => {
    const anyProject = activeProject as any;
    if (anyProject?.detectedInfo) {
      setDetection(anyProject.detectedInfo.detection || null);
      setDeploymentPlan(anyProject.detectedInfo.deploymentPlan || null);
      setGeneratedFileList(anyProject.detectedInfo.generatedFiles || []);
    }
  }, [activeProject]);

  const handleRetryAnalysis = async () => {
    setScanProgress([]);
    setActiveStepIndex(0);
    await runAnalysis();
  };

  // Step 1: Analyze repository (inspect via backend)
  const runAnalysis = async () => {
    if (missingRepo) {
      showToast('Link a GitHub repository in Files & GitHub first.', 'error');
      return;
    }
    setActiveStepIndex(0);
    setScanProgress([]);
    setLiveDeployment(prev => ({
      ...prev,
      status: 'preparing' as PipelinePhase,
      progress: 5,
      logs: [...prev.logs, `[CloudWise] Analyzing repository ${repoName}...`],
    }));
    try {
      const res = await fetch(`/api/github/repos/${encodeURIComponent(repoName!)}/inspect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ repoName }),
      });
      const data = await res.json().catch(() => null);

      // Show progress stages from the server
      if (data?.progress && Array.isArray(data.progress)) {
        setScanProgress(data.progress);
      }

      if (data?.token_expired) setTokenExpired(true);
      if (data?.rate_limited) setRateLimited(true);

      if (!res.ok || !data?.success) {
        throw new Error(
          data?.error || data?.message || data?.detail ||
          (res.status === 401
            ? 'Your CloudWise session has expired. Please sign in again.'
            : 'Repository analysis failed.')
        );
      }
      const detected = data.data.technology || {};
      setDetection({
        technology: detected.technology,
        frontend: data.data.detection?.frontend,
        backend: data.data.detection?.backend,
        database: data.data.detection?.database,
        applicationType: data.data.detection?.applicationType,
      });
      setScanProgress(data.progress || []);
      setLiveDeployment(prev => ({
        ...prev,
        progress: 15,
        logs: [
          ...prev.logs,
          `[CloudWise] Stack: ${detected.technology || 'unknown'}` +
            (data.data.detection?.frontend ? ` · FE: ${data.data.detection.frontend}` : '') +
            (data.data.detection?.backend ? ` · BE: ${data.data.detection.backend}` : '') +
            (data.data.detection?.database ? ` · DB: ${data.data.detection.database}` : ''),
        ],
      }));
      showToast('Repository analysis complete.', 'success');
      setActiveStepIndex(1);
    } catch (err: any) {
      setLiveDeployment(prev => ({
        ...prev,
        status: 'failed',
        failureReason: err.message,
        logs: [...prev.logs, `ERROR: ${err.message}`],
      }));
      showToast(err.message, 'error');
      setActiveStepIndex(-1);
    }
  };

  // Step 2: Generate Docker files
  const runGenerateFiles = async () => {
    if (missingRepo) return;
    setActiveStepIndex(1);
    try {
      const inspectRes = await fetch(`/api/github/repos/${encodeURIComponent(repoName!)}/inspect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ repoName }),
      });
      const inspectData = await inspectRes.json().catch(() => null);
      if (inspectData?.progress && Array.isArray(inspectData.progress)) {
        setScanProgress(inspectData.progress);
      }
      if (inspectData?.token_expired) setTokenExpired(true);
      if (inspectData?.rate_limited) setRateLimited(true);
      if (!inspectRes.ok || !inspectData?.success) {
        throw new Error(
          inspectData?.error || inspectData?.message || inspectData?.detail ||
          (inspectRes.status === 401
            ? 'Your CloudWise session has expired. Please sign in again.'
            : 'Repository inspection failed.')
        );
      }
      const genRes = await fetch('/api/deployment/generate-files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          provider: 'AWS',
          files: inspectData.data.files || {},
          tree: inspectData.data.tree || [],
        }),
      });
      const genData = await genRes.json();
      if (!genRes.ok || !genData.success) {
        throw new Error(genData.error || 'Deployment file generation failed.');
      }
      const plan = genData.data.deploymentPlan;
      setDeploymentPlan(plan);
      setDetection(genData.data.detection || detection);
      setGeneratedFileList(Object.keys(genData.data.files || {}));
      // Seed required env vars
      const required: string[] = plan?.requiredEnvVars || [];
      setEnvRows(prev => {
        const existing = new Set(prev.map(r => r.key));
        const merged = [...prev];
        for (const key of required) {
          if (!existing.has(key)) merged.push({ key, value: '', required: true });
        }
        return merged;
      });
      setLiveDeployment(prev => ({
        ...prev,
        progress: 25,
        logs: [
          ...prev.logs,
          `[CloudWise] Generated: ${Object.keys(genData.data.files || {}).join(', ')}`,
          `[CloudWise] Target: ${plan?.target || 'AWS_EC2'} · containers: ${(plan?.containers || []).join(', ')}`,
        ],
      }));
      showToast('Docker deployment files generated.', 'success');
      setActiveStepIndex(2);
    } catch (err: any) {
      setLiveDeployment(prev => ({
        ...prev,
        status: 'failed',
        failureReason: err.message,
        logs: [...prev.logs, `ERROR: ${err.message}`],
      }));
      showToast(err.message, 'error');
    }
  };

  // Step 3: Env configuration
  const handleEnvFileUpload = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || '');
      const rows: EnvVarRow[] = [];
      for (const line of text.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const eq = trimmed.indexOf('=');
        if (eq <= 0) continue;
        rows.push({ key: trimmed.slice(0, eq).trim(), value: trimmed.slice(eq + 1).trim(), required: false });
      }
      setEnvRows(rows);
      setEnvSource('upload');
      setActiveStepIndex(3);
      showToast(`Loaded ${rows.length} variables from ${file.name}.`, 'success');
    };
    reader.readAsText(file);
  };

  const addEnvRow = () => {
    setEnvRows(prev => [...prev, { key: '', value: '', required: false }]);
  };

  const updateEnvRow = (index: number, field: keyof EnvVarRow, value: string | boolean) => {
    setEnvRows(prev => prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  };

  const removeEnvRow = (index: number) => {
    setEnvRows(prev => prev.filter((_, i) => i !== index));
  };

  const envVarsReady = useMemo(() => {
    const required = deploymentPlan?.requiredEnvVars || [];
    const map = new Map(envRows.map(r => [r.key, r.value]));
    return required.every(k => (map.get(k) || '').length > 0);
  }, [envRows, deploymentPlan]);

  // Derived from real signals only: what the user actually linked, what
  // the backend actually accepted, and the record's own deployment status.
  const checklist = useMemo(() => {
    const failedKey: ChecklistKey | null = stageError
      ? stageKeyFromBackendStage(stageError.stage, stageError.message)
      : liveDeployment.status === 'failed' && pipelineFailure
      ? stageKeyFromBackendStage(pipelineFailure.stage, pipelineFailure.message)
      : null;

    const githubStatus: ChecklistStatus = failedKey === 'GITHUB'
      ? 'failed'
      : repoName
      ? 'done'
      : 'pending';

    const repositoryStatus: ChecklistStatus = failedKey === 'REPOSITORY'
      ? 'failed'
      : repoName && detection
      ? 'done'
      : repoName
      ? 'active'
      : 'pending';

    const awsStatus: ChecklistStatus = failedKey === 'AWS'
      ? 'failed'
      : awsConnection?.connected
      ? 'done'
      : 'pending';

    let deploymentStatus: ChecklistStatus = 'pending';
    if (failedKey === 'DEPLOYMENT' || (failedKey !== 'GITHUB' && failedKey !== 'REPOSITORY' && failedKey !== 'AWS' && liveDeployment.status === 'failed')) {
      deploymentStatus = 'failed';
    } else if (liveDeployment.status === 'deployed') {
      deploymentStatus = 'done';
    } else if (liveDeployment.status !== 'idle') {
      deploymentStatus = 'active';
    }

    const deploymentLabel = (() => {
      switch (liveDeployment.status) {
        case 'preparing':
          return 'Validating repository and environment';
        case 'provisioning':
          return 'Provisioning EC2 capacity';
        case 'configuring':
          return 'Uploading files and starting containers';
        case 'deployed':
          return `Live at ${liveDeployment.endpointUrl || 'health-checked URL'}`;
        case 'failed':
          return 'Failed — inspect the error and retry';
        default:
          return 'Queued for deployment';
      }
    })();

    return [
      { ...CHECKLIST_STAGES[0], status: githubStatus, detail: githubStatus === 'done' ? (repoName || '') : (missingRepo ? 'No repository linked yet' : '') },
      { ...CHECKLIST_STAGES[1], status: repositoryStatus, detail: detection?.technology || (repositoryStatus === 'active' ? 'Awaiting analysis' : '') },
      { ...CHECKLIST_STAGES[2], status: awsStatus, detail: awsConnection?.connected ? `Account ${awsConnection.accountId || 'connected'} · ${awsConnection.region || estimation.region}` : 'IAM role not connected' },
      { ...CHECKLIST_STAGES[3], status: deploymentStatus, detail: deploymentLabel },
    ];
  }, [
    stageError,
    pipelineFailure,
    liveDeployment.status,
    liveDeployment.endpointUrl,
    repoName,
    detection,
    awsConnection,
    missingRepo,
    estimation.region,
  ]);

  const markEnvComplete = () => {
    if (!envVarsReady) {
      showToast('Fill all required environment variables first.', 'error');
      return;
    }
    setActiveStepIndex(3);
    setLiveDeployment(prev => ({
      ...prev,
      progress: 30,
      logs: [...prev.logs, `[CloudWise] ${envRows.length} environment variables configured.`],
    }));
    showToast('Environment variables ready.', 'success');
  };

  // Full deploy (steps 4–9 orchestrated by backend deploy_view)
  const handleDeploy = async () => {
    if (missingRepo) return;
    if (!awsConnection?.connected) {
      showToast('Connect your AWS account first.', 'error');
      navigate('/connect-aws');
      return;
    }

    setActiveStepIndex(4);
    setLiveDeployment(prev => ({
      ...prev,
      status: 'preparing' as PipelinePhase,
      progress: 35,
      logs: [
        ...prev.logs,
        '[CloudWise] Assuming IAM role via STS...',
        `[CloudWise] Environment: ${envName}`,
      ],
    }));

    const envMap: Record<string, string> = {};
    for (const row of envRows) {
      if (row.key) envMap[row.key] = row.value;
    }

    try {
      const res = await fetch('/api/deploy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          projectId: activeProject?.id,
          environmentName: envName,
          provider: 'AWS',
          monthlyCost: selectedRecommendation.monthlyCost,
          specs: selectedRecommendation.specs,
          region: estimation.region,
          envVars: envMap,
        }),
      });
      const data = await res.json();

      if (res.status === 503 && data.status === 'BLOCKED') {
        setStageError({ stage: data.stage || 'AWS', message: data.error || '' });
        setLiveDeployment(prev => ({
          ...prev,
          status: 'failed',
          progress: 0,
          failureReason: data.error,
          logs: [`[BLOCKED] ${data.error}`, ...(data.required || []).map((k: string) => `  → Missing: ${k}`)],
        }));
        showToast(data.error, 'error');
        return;
      }

      if (res.status === 400 && data.status === 'RETIRED') {
        setStageError({ stage: data.stage || 'PROJECT', message: data.error || '' });
        showToast(data.error || 'Provider retired. AWS only.', 'error');
        return;
      }

      if (!res.ok && data.code === 'MISSING_ENV_VARS') {
        setStageError({ stage: data.stage || 'ENVIRONMENT', message: data.error || '' });
        setLiveDeployment(prev => ({
          ...prev,
          status: 'failed',
          failureReason: data.error,
          logs: [...prev.logs, `[ENV] ${data.error}`, ...(data.missing || []).map((k: string) => `  → missing: ${k}`)],
        }));
        showToast(data.error, 'error');
        setActiveStepIndex(2);
        return;
      }

      if (!res.ok && data.code === 'INVALID_DATABASE_URL') {
        setStageError({ stage: data.stage || 'ENVIRONMENT', message: data.error || '' });
        setLiveDeployment(prev => ({
          ...prev,
          status: 'failed',
          failureReason: data.error,
          logs: [...prev.logs, `[ENV] ${data.error}`],
        }));
        showToast(data.error, 'error');
        setActiveStepIndex(2);
        return;
      }

      if (res.ok && data.success && (data.deployment_id || data.data?.id)) {
        const record = data.data || {};
        const id: string = data.deployment_id || record.id;
        const initialLogs: string[] = Array.isArray(record.logs)
          ? record.logs.map((l: any) => `[${l.timestamp}] [${l.level}] ${l.message}`)
          : liveDeployment.logs;

        setDeploymentId(id);
        setLastDeploymentId(id);
        setStageError(null);
        setPipelineFailure(null);
        setActiveStepIndex(4);
        setLiveDeployment(prev => ({
          ...prev,
          status: 'preparing',
          progress: 5,
          failureReason: null,
          endpointUrl: record.liveUrl || null,
          ipAddress: record.ipAddress || prev.ipAddress,
          logs: initialLogs,
        }));
        setPolling(true);
        showToast(
          `Deployment ${id} queued for ${record.repository || repoName} in ${record.region || estimation.region}.`,
          'success'
        );
        return;
      }

      if (!res.ok) {
        setStageError({ stage: data.stage || 'PROJECT', message: data.error || 'Deployment failed to initialize.' });
        setLiveDeployment(prev => ({
          ...prev,
          status: 'failed',
          failureReason: data.error || 'Deployment failed to initialize.',
          logs: [...prev.logs, `ERROR: ${data.error}`],
        }));
      }
    } catch (err: any) {
      setLiveDeployment(prev => ({
        ...prev,
        status: 'failed',
        failureReason: err.message,
        logs: [...prev.logs, `ERROR: ${err.message}`],
      }));
    }
  };

  // Re-run a failed deployment on the same record. CloudWise never stores
  // secret values, so env vars are re-submitted with the retry request.
  const handleRetryDeployment = async () => {
    const id = deploymentId || lastDeploymentId;
    if (!id) {
      void handleDeploy();
      return;
    }

    const envMap: Record<string, string> = {};
    for (const row of envRows) {
      if (row.key) envMap[row.key] = row.value;
    }

    try {
      setRetrying(true);
      const res = await fetch(`/api/deployments/${id}/retry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ envVars: envMap, environmentName: envName }),
      });
      const data = await res.json();

      if (res.status === 409) {
        showToast(data.error || 'Only a failed deployment can be retried.', 'error');
        return;
      }
      if (!res.ok || !data.success) {
        setStageError({ stage: data.stage || 'DEPLOYMENT', message: data.error || 'Retry failed.' });
        showToast(data.error || 'Retry failed.', 'error');
        return;
      }

      const record = data.data || {};
      setDeploymentId(id);
      setLastDeploymentId(id);
      setStageError(null);
      setPipelineFailure(null);
      setActiveStepIndex(4);
      setLiveDeployment(prev => ({
        ...prev,
        status: 'preparing',
        progress: 5,
        failureReason: null,
        endpointUrl: null,
        logs: Array.isArray(record.logs)
          ? record.logs.map((l: any) => `[${l.timestamp}] [${l.level}] ${l.message}`)
          : [...prev.logs, `[CloudWise] Retry requested for ${record.repository || repoName}.`],
      }));
      setPolling(true);
      showToast(`Retry queued for deployment ${id}.`, 'success');
    } catch (err: any) {
      showToast(err.message || 'Retry failed.', 'error');
    } finally {
      setRetrying(false);
    }
  };

  useEffect(() => {
    if (!polling || !deploymentId) return;

    const interval = setInterval(async () => {
      try {
        const headers = authHeaders();
        const [statusRes, logsRes] = await Promise.all([
          fetch(`/api/deployments/${deploymentId}/status`, { headers }),
          fetch(`/api/deployments/${deploymentId}/logs`, { headers }),
        ]);

        const statusData = await statusRes.json();
        const logsData = await logsRes.json();

        if (statusData.success && logsData.success) {
          const rawStatus: string = String(statusData.data.deploymentStatus || '').toUpperCase();

          const statusMap: Record<string, string> = {
            QUEUED: 'preparing',
            PREPARING: 'preparing',
            BUILDING: 'provisioning',
            DEPLOYING: 'configuring',
            HEALTH_CHECK: 'configuring',
            RUNNING: 'deployed',
            FAILED: 'failed',
            ROLLING_BACK: 'failed',
            ROLLED_BACK: 'idle',
            TERMINATED: 'failed',
            // legacy lowercase records created before migration 0007
            DEPLOYED: 'deployed',
            DONE: 'deployed',
          };
          const uiStatus = statusMap[rawStatus] ?? 'preparing';

          const serverProgress = Number(statusData.data.progress);
          const progressMap: Record<string, number> = {
            preparing: Number.isFinite(serverProgress) ? serverProgress : 15,
            provisioning: Number.isFinite(serverProgress) ? serverProgress : 45,
            configuring: Number.isFinite(serverProgress) ? serverProgress : 70,
            deployed: 100,
            failed: Number.isFinite(serverProgress) ? serverProgress : 60,
            idle: 0,
          };

          const formattedLogs = logsData.data.map((l: any) => `[${l.timestamp}] [${l.level}] ${l.message}`);

          if (uiStatus === 'failed') {
            const lastError = [...logsData.data].reverse().find((l: any) => l.level === 'ERROR');
            setPipelineFailure(
              lastError ? { stage: String(lastError.stage || ''), message: String(lastError.message || '') } : null
            );
            setActiveStepIndex(-2);
          }

          setLiveDeployment(prev => ({
            ...prev,
            status: uiStatus as any,
            progress: progressMap[uiStatus] ?? prev.progress,
            logs: formattedLogs,
            ipAddress: statusData.data.ipAddress || prev.ipAddress,
            endpointUrl: statusData.data.liveUrl || prev.endpointUrl,
            failureReason:
              uiStatus === 'failed'
                ? (logsData.data.filter((l: any) => l.level === 'ERROR').pop()?.message ?? prev.failureReason)
                : prev.failureReason,
          }));

          if (['deployed', 'failed', 'idle'].includes(uiStatus)) {
            setPolling(false);
            if (uiStatus === 'deployed') {
              setActiveStepIndex(8);
              setPipelineFailure(null);
              updateActiveProject({
                currentStep: 'deployment',
                deployment: {
                  status: 'deployed',
                  progress: 100,
                  logs: formattedLogs,
                  deployedAt: new Date().toISOString(),
                  endpointUrl: statusData.data.liveUrl || null,
                  providerDeploymentId: deploymentId,
                  ipAddress: statusData.data.ipAddress || null,
                  environmentName: envName,
                  failureReason: null,
                },
              });
              showToast('Deployment live on AWS EC2!', 'success');
            }
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 1800);

    return () => clearInterval(interval);
  }, [polling, deploymentId]);

  const handleRollback = async () => {
    if (!deploymentId) {
      setLiveDeployment({ ...contextDeployment, status: 'idle', progress: 0, logs: [] });
      return;
    }
    try {
      setLiveDeployment(prev => ({ ...prev, status: 'failed', progress: 20, logs: [...prev.logs, 'Rollback initiated...'] }));
      const res = await fetch(`/api/deployments/${deploymentId}/rollback`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = await res.json();
      if (data.success) {
        const rollbackLogs = (data.data.logs ?? []).map((l: any) => `[${l.timestamp}] [${l.level}] ${l.message}`);
        setStageError(null);
        setPipelineFailure(null);
        setLiveDeployment(prev => ({
          ...prev,
          status: 'idle',
          progress: 0,
          logs: rollbackLogs,
          failureReason: null,
        }));
        setDeploymentId(null);
        setPolling(false);
        setActiveStepIndex(-1);
        showToast('Deployment rolled back. EC2 instance retained.', 'info');
      }
    } catch (err) {
      console.error('Rollback failed:', err);
    }
  };

  const handleHealthCheck = async () => {
    if (!deploymentId) return;
    try {
      const res = await fetch(`/api/deployments/${deploymentId}/health`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const healthData = await res.json();
      const logsRes = await fetch(`/api/deployments/${deploymentId}/logs`, { headers: authHeaders() });
      const logsData = await logsRes.json();
      if (logsData.success) {
        setLiveDeployment(prev => ({
          ...prev,
          logs: logsData.data.map((l: any) => `[${l.timestamp}] ${l.message}`),
        }));
      }
      if (healthData.data?.healthy) {
        showToast('Health check passed! HTTP endpoint responding.', 'success');
      } else {
        showToast(healthData.data?.detail?.error || 'Health check failed.', 'error');
      }
    } catch (err) {
      console.error('Health check failed:', err);
    }
  };

  const handleRefreshUrl = async () => {
    if (!deploymentId) return;
    try {
      showToast('Fetching live URL from AWS...', 'info');
      const headers = authHeaders();
      const [statusRes, logsRes] = await Promise.all([
        fetch(`/api/deployments/${deploymentId}/status`, { headers }),
        fetch(`/api/deployments/${deploymentId}/logs`, { headers }),
      ]);
      const statusData = await statusRes.json();
      const logsData = await logsRes.json();

      if (statusData.success) {
        const newUrl = statusData.data.liveUrl;
        setLiveDeployment(prev => ({
          ...prev,
          endpointUrl: newUrl || prev.endpointUrl,
          logs: logsData.success
            ? logsData.data.map((l: any) => `[${l.timestamp}] [${l.level}] ${l.message}`)
            : prev.logs,
        }));
        if (newUrl) {
          updateActiveProject({
            deployment: {
              ...activeProject?.deployment,
              endpointUrl: newUrl,
              status: 'deployed',
              providerDeploymentId: deploymentId,
            },
          });
          showToast(`Live URL: ${newUrl}`, 'success');
        } else {
          showToast('URL not available yet. Try again in a moment.', 'info');
        }
      }
    } catch (err) {
      console.error('Refresh URL failed:', err);
    }
  };

  const handleReset = () => {
    setDeploymentId(null);
    setStageError(null);
    setPipelineFailure(null);
    setLiveDeployment({ ...contextDeployment, status: 'idle', progress: 0, logs: [] });
    setActiveStepIndex(-1);
    setPolling(false);
  };

  const getStepVisual = (stepIndex: number) => {
    if (liveDeployment.status === 'failed') {
      if (stepIndex < activeStepIndex) return 'complete';
      if (stepIndex === activeStepIndex) return 'failed';
      if (activeStepIndex === -2 && stepIndex <= 7) return 'failed';
      return 'pending';
    }
    if (liveDeployment.status === 'deployed') return 'complete';
    if (liveDeployment.status === 'idle') {
      return stepIndex < activeStepIndex ? 'complete' : stepIndex === activeStepIndex ? 'active' : 'pending';
    }
    // in-progress phases
    const phaseBase = PHASE_TO_STEP[liveDeployment.status as PipelinePhase] ?? 0;
    if (stepIndex < phaseBase) return 'complete';
    if (stepIndex <= phaseBase + 1) return 'active';
    return 'pending';
  };

  const handleProceedToMonitoring = () => {
    updateActiveProject({ currentStep: 'monitoring' });
    navigate('/monitoring');
  };

  const handleProceedToOptimization = () => {
    updateActiveProject({ currentStep: 'optimization' });
    navigate('/optimization');
  };

  const canDeploy = !missingRepo && !!awsConnection?.connected && activeStepIndex >= 3;

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      {/* Header */}
      <div className="text-center space-y-3 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold">
          <Rocket className="w-3.5 h-3.5" />
          <span>Step 4: AWS EC2 Deployment Pipeline</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white">Deploy to Your AWS Account</h1>
        <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
          Nine-step pipeline: analyze → generate Docker files → configure env → assume IAM role →
          provision EC2 → compose up → health check. Vercel and Render are retired targets.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column */}
        <div className="space-y-6 lg:col-span-1">
          {/* AWS connection */}
          <div className="glass-panel p-6 rounded-3xl space-y-4 border border-slate-800">
            <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
              <Cloud className="w-4 h-4 text-cyan-400" />
              <span>Target Platform</span>
            </label>
            <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs flex items-center gap-2">
              <ShieldCheck size={16} className="shrink-0" />
              <span>
                <strong>AWS EC2 Free Tier</strong> — deploy in your own account via IAM role (no access keys).
              </span>
            </div>

            {awsConnection?.connected ? (
              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
                <ShieldCheck size={16} className="shrink-0" />
                <span className="flex-1">
                  Account <strong className="font-mono">{awsConnection.accountId || ''}</strong> ·{' '}
                  {awsConnection.region || estimation.region}
                </span>
                <button
                  onClick={() => navigate('/connect-aws')}
                  className="underline font-semibold hover:text-emerald-200 shrink-0"
                >
                  Manage
                </button>
              </div>
            ) : (
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-center gap-2">
                <AlertTriangle size={16} className="shrink-0" />
                <span className="flex-1">Connect your AWS account (IAM role — no access keys).</span>
                <button
                  onClick={() => navigate('/connect-aws')}
                  className="px-2.5 py-1 rounded-lg bg-amber-400 text-slate-950 font-bold hover:bg-amber-300 shrink-0"
                >
                  Connect AWS
                </button>
              </div>
            )}
          </div>

          {/* Analysis panel */}
          <div className="glass-panel p-6 rounded-3xl space-y-4 border border-slate-800">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-cyan-400" />
                Repository Analysis
              </h4>
              <button
                onClick={runAnalysis}
                disabled={missingRepo}
                className="text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 disabled:opacity-40"
              >
                {detection ? 'Re-analyze' : 'Analyze'}
              </button>
            </div>
            {missingRepo ? (
              <p className="text-amber-300 text-xs">
                No GitHub repository linked. Go to <strong>Files &amp; GitHub</strong> first.
              </p>
            ) : detection ? (
              <div className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-400">Stack</span>
                  <span className="font-bold text-cyan-300">{detection.technology || '—'}</span>
                </div>
                {detection.frontend && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Frontend</span>
                    <span className="font-semibold">{detection.frontend}</span>
                  </div>
                )}
                {detection.backend && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Backend</span>
                    <span className="font-semibold">{detection.backend}</span>
                  </div>
                )}
                {detection.database && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Database</span>
                    <span className="font-semibold">{detection.database}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-slate-400">Type</span>
                  <span className="font-semibold">{detection.applicationType || '—'}</span>
                </div>
              </div>
            ) : (
              <p className="text-slate-500 text-xs">Run analysis to detect stack before generating files.</p>
            )}
          </div>

          {/* Generated files panel */}
          <div className="glass-panel p-6 rounded-3xl space-y-4 border border-slate-800">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <FileCode2 className="w-4 h-4 text-cyan-400" />
                Generated Files
              </h4>
              <button
                onClick={runGenerateFiles}
                disabled={missingRepo}
                className="text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 disabled:opacity-40"
              >
                {generatedFileList.length ? 'Regenerate' : 'Generate'}
              </button>
            </div>
            {generatedFileList.length ? (
              <ul className="space-y-1 text-xs font-mono text-slate-300">
                {generatedFileList.map(f => (
                  <li key={f} className="flex items-center gap-1.5">
                    <CheckCircle2 size={12} className="text-emerald-400 shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-slate-500 text-xs">No files generated yet.</p>
            )}
            {deploymentPlan && (
              <div className="pt-2 border-t border-slate-800 space-y-1 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-400">Target</span>
                  <span className="font-bold text-cyan-300">{deploymentPlan.target}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Containers</span>
                  <span className="font-semibold">{(deploymentPlan.containers || []).join(', ')}</span>
                </div>
                {deploymentPlan.requiresNginx && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">Nginx</span>
                    <span className="font-semibold">Required (port 80)</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Env vars panel */}
          <div className="glass-panel p-6 rounded-3xl space-y-4 border border-slate-800">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <Database className="w-4 h-4 text-cyan-400" />
                Environment Variables
              </h4>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setEnvMasked(!envMasked)}
                  className="text-slate-400 hover:text-white"
                  title={envMasked ? 'Show values' : 'Hide values'}
                >
                  {envMasked ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
                <label className="text-[11px] font-semibold text-cyan-400 hover:text-cyan-300 cursor-pointer">
                  Upload .env
                  <input
                    type="file"
                    accept=".env,.env.example,.txt"
                    className="hidden"
                    onChange={e => {
                      const f = e.target.files?.[0];
                      if (f) handleEnvFileUpload(f);
                    }}
                  />
                </label>
              </div>
            </div>

            {(deploymentPlan?.requiredEnvVars?.length ?? 0) > 0 && (
              <p className="text-[11px] text-amber-300">
                Required: {(deploymentPlan!.requiredEnvVars || []).join(', ')}
              </p>
            )}

            <div className="space-y-2 max-h-48 overflow-y-auto">
              {envRows.length === 0 && (
                <p className="text-slate-500 text-xs">Upload a .env file or add variables manually.</p>
              )}
              {envRows.map((row, idx) => (
                <div key={idx} className="flex gap-1.5 items-center">
                  <input
                    type="text"
                    value={row.key}
                    placeholder="KEY"
                    onChange={e => updateEnvRow(idx, 'key', e.target.value)}
                    className="w-1/3 bg-slate-900 border border-slate-700/80 rounded-lg px-2 py-1.5 text-[11px] font-mono text-white focus:border-cyan-400 focus:outline-none"
                  />
                  <input
                    type={envMasked ? 'password' : 'text'}
                    value={row.value}
                    placeholder="value"
                    onChange={e => updateEnvRow(idx, 'value', e.target.value)}
                    className="flex-1 bg-slate-900 border border-slate-700/80 rounded-lg px-2 py-1.5 text-[11px] font-mono text-white focus:border-cyan-400 focus:outline-none"
                  />
                  <button
                    onClick={() => removeEnvRow(idx)}
                    className="text-rose-400 hover:text-rose-300 text-xs px-1"
                    aria-label="Remove variable"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>

            <div className="flex gap-2">
              <button
                onClick={addEnvRow}
                className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 text-[11px] font-semibold"
              >
                + Add Variable
              </button>
              <button
                onClick={markEnvComplete}
                className="px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/40 text-cyan-300 text-[11px] font-semibold"
              >
                Confirm Env ({envSource === 'upload' ? 'uploaded' : 'manual'})
              </button>
            </div>
          </div>

          {/* Config summary */}
          <div className="glass-panel p-6 rounded-3xl space-y-4 border border-slate-800">
            <div className="bg-slate-900/80 p-3.5 rounded-xl border border-slate-800 space-y-1 text-xs">
              <span className="text-slate-400 block text-[10px]">Active Project</span>
              <p className="font-bold text-white text-sm">{activeProject?.name || 'CloudWise App'}</p>
              <span className="text-cyan-400 font-bold block pt-1">
                {formatINR(selectedRecommendation.monthlyCost)} / mo
              </span>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">Provider</span>
                <span className="font-bold text-cyan-300">AWS EC2</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Region</span>
                <span className="font-bold">{estimation.region}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">vCPU</span>
                <span className="font-bold">{selectedRecommendation.specs.vcpu} Cores</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">RAM</span>
                <span className="font-bold">{selectedRecommendation.specs.ram} GB</span>
              </div>
            </div>

            <div className="space-y-1.5 pt-2 border-t border-slate-800">
              <label className="text-[11px] font-semibold text-slate-400">Environment Identifier</label>
              <input
                type="text"
                disabled={liveDeployment.status !== 'idle'}
                value={envName}
                onChange={e => setEnvName(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-white focus:border-cyan-400 focus:outline-none disabled:opacity-60"
              />
            </div>

            {liveDeployment.status === 'idle' && (
              <div className="space-y-2 pt-2">
                {missingRepo && (
                  <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs">
                    No GitHub repository linked. Go to <strong>Files &amp; GitHub</strong> first.
                  </div>
                )}
                {!awsConnection?.connected && !missingRepo && (
                  <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs">
                    AWS account not connected.{' '}
                    <button onClick={() => navigate('/connect-aws')} className="underline font-bold hover:text-amber-200">
                      Connect AWS
                    </button>{' '}
                    first (IAM role — no access keys).
                  </div>
                )}
                {!canDeploy && !missingRepo && awsConnection?.connected && activeStepIndex < 3 && (
                  <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-slate-400 text-xs">
                    Complete steps 1–3 (analyze → generate files → configure env) before deploying.
                  </div>
                )}
                <button
                  onClick={handleDeploy}
                  disabled={!canDeploy}
                  className="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-400 via-cyan-500 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-sm transition-all shadow-xl shadow-cyan-500/25 flex items-center justify-center gap-2 active:scale-98 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Rocket className="w-5 h-5" />
                  <span>Deploy {repoName ? `"${repoName.split('/')[1]}"` : 'Project'} to AWS EC2</span>
                </button>
              </div>
            )}

            {liveDeployment.status !== 'idle' && (
              <div className="space-y-2 pt-2">
                <button
                  onClick={handleReset}
                  className="w-full py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 font-semibold text-xs transition-colors flex items-center justify-center gap-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Reset Pipeline State</span>
                </button>
                {liveDeployment.status === 'deployed' && (
                  <button
                    onClick={handleHealthCheck}
                    className="w-full py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-emerald-400 font-semibold text-xs transition-colors flex items-center justify-center gap-1.5"
                  >
                    <Activity className="w-3.5 h-3.5" />
                    <span>Run Health Check</span>
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: 9-step pipeline + logs */}
        <div className="space-y-6 lg:col-span-2">
          {/* Readiness checklist — every row reflects a real signal */}
          <div className="glass-panel p-6 rounded-3xl space-y-4 border border-slate-800">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <ListChecks className="w-5 h-5 text-cyan-400" />
                <span>Deployment Readiness</span>
              </h3>
              {(deploymentId || lastDeploymentId) && (
                <button
                  onClick={() => navigate(`/deployment/${deploymentId || lastDeploymentId}`)}
                  className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-cyan-300 text-[11px] font-bold transition-colors flex items-center gap-1.5"
                >
                  <ExternalLink size={12} />
                  <span>Deployment Details</span>
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {checklist.map(item => (
                <div
                  key={item.key}
                  className={`p-3.5 rounded-2xl border transition-all ${
                    item.status === 'done'
                      ? 'bg-emerald-950/20 border-emerald-500/40 text-emerald-300'
                      : item.status === 'active'
                      ? 'bg-cyan-950/30 border-cyan-400 text-white shadow-lg shadow-cyan-950/50'
                      : item.status === 'failed'
                      ? 'bg-rose-950/20 border-rose-500/40 text-rose-300'
                      : 'bg-slate-900/40 border-slate-800 text-slate-500'
                  }`}
                >
                  <div className="flex items-center gap-2 font-bold text-xs">
                    {item.status === 'done' && <CheckCircle2 size={15} className="text-emerald-400 shrink-0" />}
                    {item.status === 'active' && <RefreshCw size={15} className="text-cyan-400 animate-spin shrink-0" />}
                    {item.status === 'failed' && <AlertTriangle size={15} className="text-rose-400 shrink-0" />}
                    {item.status === 'pending' && <Clock size={15} className="shrink-0" />}
                    <span>{item.label}</span>
                    <span className="ml-auto text-[10px] uppercase tracking-wider font-extrabold opacity-80">
                      {item.status === 'done'
                        ? '✓'
                        : item.status === 'active'
                        ? 'in progress'
                        : item.status === 'failed'
                        ? 'failed'
                        : 'waiting'}
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-400 pt-1 leading-snug">{item.desc}</p>
                  {item.detail && (
                    <p className="text-[10px] text-slate-300/80 pt-1 font-mono truncate">{item.detail}</p>
                  )}
                </div>
              ))}
            </div>

            {stageError && (
              <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 space-y-2 text-xs text-rose-300">
                <div className="flex items-center gap-2 font-bold text-rose-400">
                  <AlertTriangle size={15} />
                  <span>{stageError.stage} stage failed</span>
                </div>
                <p className="whitespace-pre-wrap bg-slate-900/60 rounded-xl p-3 border border-rose-500/20 text-slate-300">
                  {stageError.message}
                </p>
                <div className="flex items-center gap-2 flex-wrap pt-1">
                  <button
                    onClick={() => (stageKeyFromBackendStage(stageError.stage) === 'GITHUB' ? navigate('/files') : handleRetryDeployment())}
                    className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 border border-rose-500/40 text-[11px] font-bold transition-colors flex items-center gap-1.5"
                  >
                    <RefreshCw size={12} />
                    <span>
                      {stageKeyFromBackendStage(stageError.stage) === 'GITHUB' ? 'Fix GitHub Connection' : 'Retry'}
                    </span>
                  </button>
                  <button
                    onClick={() => setStageError(null)}
                    className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 text-[11px] font-bold transition-colors"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="glass-panel p-6 rounded-3xl space-y-6 border border-slate-800">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-cyan-400" />
                <span>AWS EC2 Deployment Pipeline (9 Steps)</span>
              </h3>
              <span
                className={`px-3 py-1 rounded-full text-xs font-bold border ${
                  liveDeployment.status === 'deployed'
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    : liveDeployment.status === 'failed'
                    ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                    : liveDeployment.status === 'idle'
                    ? 'bg-slate-800 text-slate-400 border-slate-700'
                    : 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 animate-pulse'
                }`}
              >
                {liveDeployment.status.toUpperCase()}
              </span>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-xs font-semibold text-slate-400">
                <span>Progress</span>
                <span className="text-cyan-400">{liveDeployment.progress}%</span>
              </div>
              <div className="w-full h-3 rounded-full bg-slate-900 overflow-hidden p-0.5 border border-slate-800">
                <motion.div
                  className={`h-full rounded-full transition-all duration-500 ${
                    liveDeployment.status === 'failed'
                      ? 'bg-rose-500'
                      : liveDeployment.status === 'deployed'
                      ? 'bg-emerald-400'
                      : 'bg-gradient-to-r from-cyan-500 to-blue-500'
                  }`}
                  style={{ width: `${liveDeployment.progress}%` }}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-2">
              {NINE_STEPS.map((step, idx) => {
                const st = getStepVisual(idx);
                return (
                  <div
                    key={step.key}
                    className={`p-3 rounded-2xl border transition-all ${
                      st === 'complete'
                        ? 'bg-emerald-950/20 border-emerald-500/40 text-emerald-300'
                        : st === 'active'
                        ? 'bg-cyan-950/30 border-cyan-400 text-white shadow-lg shadow-cyan-950/50'
                        : st === 'failed'
                        ? 'bg-rose-950/20 border-rose-500/40 text-rose-300'
                        : 'bg-slate-900/40 border-slate-800 text-slate-500'
                    }`}
                  >
                    <div className="flex items-center gap-2 font-bold text-[11px]">
                      {st === 'complete' && <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />}
                      {st === 'active' && <RefreshCw size={14} className="text-cyan-400 animate-spin shrink-0" />}
                      {st === 'failed' && <AlertTriangle size={14} className="text-rose-400 shrink-0" />}
                      {st === 'pending' ? <Clock size={14} className="shrink-0" /> : null}
                      <span className="truncate">{step.label}</span>
                    </div>
                    <p className="text-[10px] text-slate-400 pt-1 leading-snug">{step.desc}</p>
                  </div>
                );
              })}
            </div>

            {liveDeployment.status === 'deployed' && (
              <div className="p-5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 space-y-3">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div>
                    <span className="text-[10px] font-extrabold uppercase tracking-wider text-emerald-400">
                      Live Application
                    </span>
                    <a
                      href={liveDeployment.endpointUrl || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-lg font-extrabold text-white hover:text-cyan-300 flex items-center gap-2 underline underline-offset-4"
                    >
                      <Globe size={18} className="text-cyan-400" />
                      <span>{liveDeployment.endpointUrl || 'No URL available yet'}</span>
                    </a>
                    {liveDeployment.ipAddress && (
                      <p className="text-xs text-emerald-300/80 font-mono pt-1">
                        EC2: {liveDeployment.ipAddress} · {estimation.region}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {!liveDeployment.endpointUrl && (
                      <button
                        onClick={handleRefreshUrl}
                        className="px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition-all shadow flex items-center gap-1.5"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        <span>Fetch Live URL</span>
                      </button>
                    )}
                    {liveDeployment.endpointUrl && (
                      <a
                        href={liveDeployment.endpointUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs transition-all shadow flex items-center gap-1.5"
                      >
                        <Globe className="w-3.5 h-3.5" />
                        <span>Open Live Website</span>
                      </a>
                    )}
                    <button
                      onClick={() => navigate(`/deployment/${deploymentId || lastDeploymentId || ''}`)}
                      className="px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-cyan-300 font-bold text-xs transition-all flex items-center gap-1.5"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      <span>Deployment Details</span>
                    </button>
                    <button
                      onClick={handleProceedToMonitoring}
                      className="px-4 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs transition-all shadow"
                    >
                      View Live Metrics
                    </button>
                    <button
                      onClick={handleProceedToOptimization}
                      className="px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs transition-all shadow"
                    >
                      Cost Tuning
                    </button>
                  </div>
                </div>
              </div>
            )}

            {liveDeployment.status === 'failed' && (
              <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 space-y-3 text-xs text-rose-300">
                <div className="flex items-center gap-2 font-bold text-sm text-rose-400">
                  <AlertTriangle size={18} />
                  <span>
                    {liveDeployment.failureReason?.startsWith('BLOCKED')
                      ? liveDeployment.failureReason?.includes('AWS account not connected')
                        ? 'Deployment Blocked — Connect AWS Account'
                        : 'Deployment Blocked — AWS Connection Required'
                      : 'Deployment Failed'}
                  </span>
                </div>

                {liveDeployment.failureReason && (
                  <div className="space-y-2">
                    <span className="font-semibold text-rose-400">Error:</span>
                    <p className="text-slate-300 whitespace-pre-wrap bg-slate-900/60 rounded-xl p-3 border border-rose-500/20 text-xs">
                      {liveDeployment.failureReason}
                    </p>
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        onClick={handleRetryAnalysis}
                        className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 border border-rose-500/40 text-[11px] font-bold transition-colors flex items-center gap-1.5"
                      >
                        <RefreshCw size={12} />
                        <span>Retry Analysis</span>
                      </button>
                      {tokenExpired && (
                        <button
                          onClick={handleRetryAnalysis}
                          className="px-3 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 border border-amber-500/40 text-[11px] font-bold transition-colors flex items-center gap-1.5"
                        >
                          <span>Re-authenticate GitHub</span>
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* Scan progress steps */}
                {scanProgress.length > 0 && (
                  <div className="space-y-1 mt-2">
                    <span className="font-semibold text-cyan-400 text-xs">Scan Progress:</span>
                    {scanProgress.map((step, i) => (
                      <div key={i} className={`flex items-center gap-1.5 text-[11px] ${i === scanProgress.length - 1 ? 'text-cyan-300' : 'text-slate-400'}`}>
                        {i < scanProgress.length - 1 ? <CheckCircle2 size={12} className="text-green-400 shrink-0" /> : <RefreshCw size={12} className="animate-spin shrink-0" />}
                        <span>{step.message}</span>
                      </div>
                    ))}
                  </div>
                )}

                {liveDeployment.logs.length > 0 && (
                  <div className="pt-1">
                    <button
                      onClick={() => setShowLogs(!showLogs)}
                      className="flex items-center gap-2 text-[11px] font-semibold text-slate-400 hover:text-white transition-colors"
                    >
                      <span className={`transform transition-transform ${showLogs ? 'rotate-90' : ''}`}>▶</span>
                      <span>View deployment logs ({liveDeployment.logs.length} lines)</span>
                    </button>
                    {showLogs && (
                      <div className="mt-2 bg-slate-950 rounded-xl p-3 border border-slate-800 max-h-48 overflow-y-auto font-mono text-[10px] leading-relaxed space-y-0.5">
                        {liveDeployment.logs.map((log, idx) => (
                          <div
                            key={idx}
                            className={`flex gap-2 ${log.includes('ERROR') || log.includes('failed') ? 'text-rose-400' : 'text-slate-400'}`}
                          >
                            <span className="text-slate-600 select-none">&gt;</span>
                            <span>{log}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="pt-2 flex items-center gap-2 flex-wrap">
                  <button
                    onClick={handleRetryDeployment}
                    disabled={retrying}
                    className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs transition-colors disabled:opacity-50 flex items-center gap-1.5"
                  >
                    <RefreshCw size={13} className={retrying ? 'animate-spin' : ''} />
                    <span>{retrying ? 'Retrying…' : 'Retry Failed Deployment'}</span>
                  </button>
                  <button
                    onClick={handleRollback}
                    className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs transition-colors"
                  >
                    Initiate Instant Rollback
                  </button>
                  {(deploymentId || lastDeploymentId) && (
                    <button
                      onClick={() => navigate(`/deployment/${deploymentId || lastDeploymentId}`)}
                      className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs border border-slate-700 transition-colors"
                    >
                      Deployment Details
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Terminal */}
          <div className="glass-panel rounded-3xl border border-slate-800 overflow-hidden">
            <div className="bg-slate-900/90 px-6 py-3 border-b border-slate-800 flex items-center justify-between">
              <h4 className="text-xs font-bold text-white flex items-center gap-2">
                <Terminal className="w-4 h-4 text-cyan-400" />
                <span>Live Provisioning Console Logs</span>
              </h4>
              <span className="text-[10px] text-slate-400 font-mono">{liveDeployment.logs.length} lines logged</span>
            </div>

            <div className="p-5 bg-slate-950 font-mono text-xs text-slate-300 leading-relaxed max-h-72 overflow-y-auto space-y-1">
              {liveDeployment.logs.length === 0 ? (
                <p className="text-slate-600 text-center py-8">
                  Console idle. Run analysis, generate files, configure env, then deploy to AWS EC2.
                </p>
              ) : (
                liveDeployment.logs.map((log, idx) => (
                  <div key={idx} className="flex gap-2">
                    <span className="text-slate-600 select-none">&gt;</span>
                    <span
                      className={
                        log.includes('ERROR') || log.includes('failed')
                          ? 'text-rose-400 font-bold'
                          : log.includes('complete') || log.includes('live') || log.includes('200')
                          ? 'text-emerald-400'
                          : 'text-slate-300'
                      }
                    >
                      {log}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
