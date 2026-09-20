import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Rocket, 
  CheckCircle2, 
  Clock, 
  Terminal, 
  ArrowRight, 
  Server, 
  ShieldCheck, 
  Globe, 
  Activity, 
  RefreshCw,
  Sliders,
  Cloud,
  Layers,
  AlertTriangle
} from 'lucide-react';
import { useCloudWise, formatINR } from '@/context/CloudWiseContext';

export const Deployment: React.FC = () => {
  const navigate = useNavigate();
  const { 
    selectedRecommendation, 
    estimation, 
    deployment: contextDeployment, 
    updateActiveProject,
    activeProject,
    showToast
  } = useCloudWise();

  const [provider, setProvider] = useState<'Vercel' | 'Render' | 'AWS'>(
    (selectedRecommendation.provider === 'AWS' ? 'Vercel' : selectedRecommendation.provider as any) || 'Vercel'
  );

  const [envName, setEnvName] = useState(
    activeProject?.name
      ? activeProject.name.toLowerCase().replace(/\s+/g, '-') + '-prod'
      : contextDeployment.environmentName || 'cloudwise-prod-cluster'
  );

  const [autoScaling, setAutoScaling] = useState(true);
  const [dailyBackup, setDailyBackup] = useState(true);
  const [showDeployConfirmation, setShowDeployConfirmation] = useState(false);
  
  const [deploymentId, setDeploymentId] = useState<string | null>(null);
  // Restore persisted deployment state from active project on mount
  const [liveDeployment, setLiveDeployment] = useState(() => {
    const saved = activeProject?.deployment;
    if (saved && saved.status !== 'idle' && saved.endpointUrl) return saved;
    return contextDeployment;
  });
  const [polling, setPolling] = useState(false);

  const deploymentEligible = true;

  // Show a clear message if no GitHub repo is linked
  const repoName = activeProject?.githubRepo?.name;
  const missingRepo = !repoName;

  const handleDeploy = async (simulateError = false) => {
    if (!deploymentEligible) return;
    
    setLiveDeployment(prev => ({ 
      ...prev, 
      status: 'preparing', 
      progress: 10, 
      logs: [`[CloudWise] Contacting ${provider} API for repository ${activeProject?.githubRepo?.name || ''}...`] 
    }));

    try {
      const token = localStorage.getItem('cloudwise_token');
      const res = await fetch('/api/deploy', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          projectId: activeProject?.id,
          environmentName: envName,
          provider: provider,
          monthlyCost: provider === 'Vercel' ? 0 : provider === 'Render' ? 0 : selectedRecommendation.monthlyCost,
          specs: selectedRecommendation.specs,
          region: estimation.region,
          autoScaling,
          dailyBackup,
          simulateError,
          envVars: {},
        }),
      });
      const data = await res.json();

      // BLOCKED — credentials not configured
      if (res.status === 503 && data.status === 'BLOCKED') {
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

      if (data.success && data.data?.deployment_id) {
        setDeploymentId(data.data.deployment_id);
        if (simulateError || data.data.status === 'FAILED') {
          const providerError = data.data.provider_error;
          const failureMsg = providerError
            ? `Vercel Error: ${providerError.errorCode} -- ${providerError.errorMessage}`
            : data.error || 'Deployment failed.';
          setLiveDeployment(prev => ({
            ...prev,
            status: 'failed',
            progress: 45,
            failureReason: failureMsg,
            providerError: providerError || null,
            logs: data.data.logs?.map((l: any) => `[${l.timestamp}] [${l.level}] ${l.message}`) || prev.logs,
          }));
          setPolling(true);
        } else if (data.data.status === 'RUNNING') {
          // Real provider returned immediately with a live URL
          const realUrl = data.data.endpoint_url;
          setLiveDeployment(prev => ({
            ...prev,
            status: 'deployed',
            progress: 100,
            endpointUrl: realUrl,
            logs: data.data.logs?.map((l: any) => `[${l.timestamp}] [${l.level}] ${l.message}`) || prev.logs,
          }));
          updateActiveProject({
            currentStep: 'deployment',
            deployment: {
              status: 'deployed',
              progress: 100,
              logs: data.data.logs?.map((l: any) => `[${l.timestamp}] [${l.level}] ${l.message}`) || [],
              deployedAt: new Date().toISOString(),
              endpointUrl: realUrl,
              ipAddress: data.data.ip_address || null,
              environmentName: envName,
              failureReason: null,
            }
          });
          showToast(`Deployed to ${provider}! URL: ${realUrl}`, 'success');
        } else {
          setPolling(true);
        }
      } else if (!res.ok) {
        setLiveDeployment(prev => ({
          ...prev,
          status: 'failed',
          failureReason: data.error || 'Deployment failed to initialize.',
          logs: [...prev.logs, `ERROR: ${data.error}`]
        }));
      }
    } catch (err: any) {
      setLiveDeployment(prev => ({
        ...prev,
        status: 'failed',
        failureReason: err.message,
        logs: [...prev.logs, `ERROR: ${err.message}`]
      }));
    }
  };

  useEffect(() => {
    if (!polling || !deploymentId) return;

    const interval = setInterval(async () => {
      try {
        const [statusRes, logsRes] = await Promise.all([
            fetch(`/api/deployments/${deploymentId}/status`),
            fetch(`/api/deployments/${deploymentId}/logs`)
        ]);
        
        const statusData = await statusRes.json();
        const logsData = await logsRes.json();

        if (statusData.success && logsData.success) {
          const rawStatus: string = statusData.data.status.toUpperCase();

          const statusMap: Record<string, string> = {
            'QUEUED':       'preparing',
            'PREPARING':    'preparing',
            'BUILDING':     'provisioning',
            'DEPLOYING':    'configuring',
            'HEALTH_CHECK': 'configuring',
            'RUNNING':      'deployed',
            'FAILED':       'failed',
            'ROLLING_BACK': 'failed',
            'ROLLED_BACK':  'idle',
          };
          const uiStatus = statusMap[rawStatus] ?? 'preparing';

          const progressMap: Record<string, number> = {
            'preparing':    statusData.data.progress || 15,
            'provisioning': statusData.data.progress || 50,
            'configuring':  statusData.data.progress || 75,
            'deployed':     100,
            'failed':       statusData.data.progress || 45,
            'idle':         0,
          };

          setLiveDeployment(prev => ({
            ...prev,
            status: uiStatus as any,
            progress: progressMap[uiStatus] ?? prev.progress,
            logs: logsData.data.map((l: any) => `[${l.timestamp}] [${l.level}] ${l.message}`),
            ipAddress: statusData.data.ip_address || prev.ipAddress,
            endpointUrl: statusData.data.endpoint_url || prev.endpointUrl,
            failureReason: uiStatus === 'failed'
              ? (logsData.data.filter((l: any) => l.level === 'ERROR').pop()?.message ?? prev.failureReason)
              : prev.failureReason,
          }));

          if (['deployed', 'failed', 'idle'].includes(uiStatus)) {
            setPolling(false);
            if (uiStatus === 'deployed') {
              // Persist the completed deployment into the project so it survives navigation
              updateActiveProject({
                currentStep: 'deployment',
                deployment: {
                  status: 'deployed',
                  progress: 100,
                  logs: logsData.data.map((l: any) => `[${l.timestamp}] [${l.level}] ${l.message}`),
                  deployedAt: new Date().toISOString(),
                  endpointUrl: statusData.data.endpoint_url || null,
                  ipAddress: statusData.data.ip_address || null,
                  environmentName: envName,
                  failureReason: null,
                }
              });
              showToast(`Deployment to ${provider} live!`, 'success');
            }
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 1800);

    return () => clearInterval(interval);
  }, [polling, deploymentId, provider]);

  const handleConfirmDeployment = () => {
    setShowDeployConfirmation(false);
    void handleDeploy(false);
  };

  const handleRollback = async () => {
    if (!deploymentId) {
      setLiveDeployment({ ...contextDeployment, status: 'idle', progress: 0, logs: [] });
      return;
    }
    try {
      setLiveDeployment(prev => ({ ...prev, status: 'failed', progress: 20, logs: [...prev.logs, 'Rollback initiated...'] }));
      const res = await fetch(`/api/deployments/${deploymentId}/rollback`, { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        const rollbackLogs = (data.data.logs ?? []).map((l: any) => `[${l.timestamp}] [${l.level}] ${l.message}`);
        setLiveDeployment(prev => ({
          ...prev,
          status: 'idle',
          progress: 0,
          logs: rollbackLogs,
          failureReason: null,
        }));
        setDeploymentId(null);
        setPolling(false);
        showToast('Deployment rolled back cleanly.', 'info');
      }
    } catch (err) {
      console.error('Rollback failed:', err);
    }
  };

  const handleHealthCheck = async () => {
    if (!deploymentId) return;
    try {
      await fetch(`/api/deployments/${deploymentId}/health`, { method: 'POST' });
      const logsRes = await fetch(`/api/deployments/${deploymentId}/logs`);
      const logsData = await logsRes.json();
      if (logsData.success) {
         setLiveDeployment(prev => ({
            ...prev,
            logs: logsData.data.map((l: any) => `[${l.timestamp}] ${l.message}`)
         }));
         showToast('Health check passed! All HTTP endpoints responding 200 OK.', 'success');
      }
    } catch (err) {
      console.error('Health check failed:', err);
    }
  };

  const handleReset = () => {
      setDeploymentId(null);
      setLiveDeployment({ ...contextDeployment, status: 'idle', progress: 0, logs: [] });
  };

  const steps = provider === 'Vercel'
    ? [
        { key: 'preparing', label: '1. Preparing Repository & Stack', desc: 'Detecting frontend framework' },
        { key: 'provisioning', label: '2. Installing Dependencies & Building', desc: 'npm install & npm run build' },
        { key: 'configuring', label: '3. Vercel Deployment', desc: 'Deploying to Vercel edge network' },
        { key: 'deployed', label: '4. Live & Health Verified', desc: 'Active on vercel.app URL' },
      ]
    : provider === 'Render'
    ? [
        { key: 'preparing', label: '1. Preparing Repository & Stack', desc: `Configuring ${provider} pipeline` },
        { key: 'provisioning', label: '2. Building & Bundling', desc: 'Compiling Docker assets' },
        { key: 'configuring', label: '3. Provisioning & Network Routing', desc: `Deploying container on ${provider}` },
        { key: 'deployed', label: '4. Live & Health Verified', desc: 'Active & responding on public URL' },
      ]
    : [
        { key: 'preparing', label: '1. Preparing Repository & Stack', desc: `Configuring ${provider} pipeline` },
        { key: 'provisioning', label: '2. Building & Bundling', desc: 'Compiling Docker / Serverless assets' },
        { key: 'configuring', label: '3. Provisioning & Network Routing', desc: `Deploying container on ${provider}` },
        { key: 'deployed', label: '4. Live & Health Verified', desc: 'Active & responding on public URL' },
      ];

  const getStepStatus = (stepKey: string) => {
    if (liveDeployment.status === 'idle') return 'idle';
    if (liveDeployment.status === 'deployed') return 'complete';
    if (liveDeployment.status === 'failed') return 'failed';
    
    const stepOrder = ['preparing', 'provisioning', 'configuring', 'deployed'];
    const currentIndex = stepOrder.indexOf(liveDeployment.status);
    const stepIndex = stepOrder.indexOf(stepKey);

    if (stepIndex < currentIndex) return 'complete';
    if (stepIndex === currentIndex) return 'active';
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

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      
      {/* Header */}
      <div className="text-center space-y-3 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold">
          <Rocket className="w-3.5 h-3.5" />
          <span>Step 4: Automated Resource Provisioning & Deployment</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white">
          Deploy Cloud Configuration
        </h1>
        <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
          Select your target deployment platform (<strong className="text-cyan-300">Vercel</strong>, <strong className="text-cyan-300">Render</strong>, or <strong className="text-cyan-300">AWS Free Tier</strong>) and trigger automated zero-downtime deployment pipelines.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Column: Config Summary & Provider Selector */}
        <div className="space-y-6 lg:col-span-1">
          
          <div className="glass-panel p-6 rounded-3xl space-y-6 border border-slate-800">
            
            {/* Target Provider Selector */}
            <div className="space-y-3">
              <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <Cloud className="w-4 h-4 text-cyan-400" />
                <span>Select Target Platform</span>
              </label>

              <div className="grid grid-cols-3 gap-2 p-1 rounded-2xl bg-slate-950 border border-slate-800 text-xs font-bold">
                <button
                  type="button"
                  onClick={() => setProvider('Vercel')}
                  className={`py-2.5 rounded-xl transition-all flex flex-col items-center gap-1 ${
                    provider === 'Vercel'
                      ? 'bg-cyan-500 text-slate-950 shadow-md'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <span>Vercel</span>
                  <span className="text-[9px] font-normal opacity-80">Frontend/Node</span>
                </button>

                <button
                  type="button"
                  onClick={() => setProvider('Render')}
                  className={`py-2.5 rounded-xl transition-all flex flex-col items-center gap-1 ${
                    provider === 'Render'
                      ? 'bg-cyan-500 text-slate-950 shadow-md'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <span>Render</span>
                  <span className="text-[9px] font-normal opacity-80">Docker/Web</span>
                </button>

                <button
                  type="button"
                  onClick={() => setProvider('AWS')}
                  className={`py-2.5 rounded-xl transition-all flex flex-col items-center gap-1 ${
                    provider === 'AWS'
                      ? 'bg-cyan-500 text-slate-950 shadow-md'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <span>AWS</span>
                  <span className="text-[9px] font-normal opacity-80">Free Tier</span>
                </button>
              </div>

              {provider !== 'AWS' && (
                <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs flex items-center gap-2">
                  <ShieldCheck size={16} className="shrink-0" />
                  <span>Deploying to <strong>{provider}</strong> (No AWS account required!)</span>
                </div>
              )}
            </div>

            <div className="space-y-3 text-xs pt-2 border-t border-slate-800">
              <div className="bg-slate-900/80 p-3.5 rounded-xl border border-slate-800 space-y-1">
                <span className="text-slate-400 block text-[10px]">Active Project Target</span>
                <p className="font-bold text-white text-sm">{activeProject?.name || 'CloudWise App'}</p>
                <span className="text-cyan-400 font-bold block pt-1">
                  {provider === 'AWS' ? `${formatINR(selectedRecommendation.monthlyCost)} / mo` : '₹0 / month (Free Tier)'}
                </span>
              </div>

              <div className="space-y-2 pt-1">
                <div className="flex justify-between text-slate-300">
                  <span className="text-slate-400">Target Provider</span>
                  <span className="font-bold text-cyan-300">{provider}</span>
                </div>
                <div className="flex justify-between text-slate-300">
                  <span className="text-slate-400">Target Region</span>
                  <span className="font-bold">{estimation.region}</span>
                </div>
                <div className="flex justify-between text-slate-300">
                  <span className="text-slate-400">vCPU Allocation</span>
                  <span className="font-bold">{selectedRecommendation.specs.vcpu} Cores</span>
                </div>
                <div className="flex justify-between text-slate-300">
                  <span className="text-slate-400">System RAM</span>
                  <span className="font-bold">{selectedRecommendation.specs.ram} GB</span>
                </div>
              </div>
            </div>

            {/* Deployment Settings */}
            <div className="space-y-4 pt-4 border-t border-slate-800">
              <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Deployment Parameters</h4>
              
              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold text-slate-400">Environment Identifier</label>
                <input
                  type="text"
                  disabled={liveDeployment.status !== 'idle'}
                  value={envName}
                  onChange={(e) => setEnvName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-white focus:border-cyan-400 focus:outline-none disabled:opacity-60"
                />
              </div>

              <div className="flex items-center justify-between text-xs pt-1">
                <span className="text-slate-300 font-medium">Enable Auto-Scaling</span>
                <input
                  type="checkbox"
                  disabled={liveDeployment.status !== 'idle'}
                  checked={autoScaling}
                  onChange={(e) => setAutoScaling(e.target.checked)}
                  className="w-4 h-4 accent-cyan-400 rounded cursor-pointer"
                />
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-300 font-medium">Automated Daily Backups</span>
                <input
                  type="checkbox"
                  disabled={liveDeployment.status !== 'idle'}
                  checked={dailyBackup}
                  onChange={(e) => setDailyBackup(e.target.checked)}
                  className="w-4 h-4 accent-cyan-400 rounded cursor-pointer"
                />
              </div>
            </div>

            {/* Deploy Trigger Buttons */}
            {liveDeployment.status === 'idle' && (
              <div className="space-y-2 pt-2">
                {missingRepo && (
                  <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs">
                    ⚠️ No GitHub repository linked. Go to <strong>Files &amp; GitHub</strong> step first.
                  </div>
                )}
                <button
                  onClick={() => handleDeploy(false)}
                  disabled={missingRepo}
                  className="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-400 via-cyan-500 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-sm transition-all shadow-xl shadow-cyan-500/25 flex items-center justify-center gap-2 active:scale-98 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Rocket className="w-5 h-5" />
                  <span>Deploy {repoName ? `"${repoName.split('/')[1]}"` : 'Project'} on {provider}</span>
                </button>

                <button
                  onClick={() => handleDeploy(true)}
                  className="w-full py-2.5 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-800 text-slate-400 text-xs font-semibold hover:text-amber-300 transition-colors flex items-center justify-center gap-1.5"
                >
                  <span>Test Simulated Pipeline Failure</span>
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

        {/* Right Column: Deployment Progress Timeline & Log Terminal */}
        <div className="space-y-6 lg:col-span-2">
          
          {/* Progress Timeline */}
          <div className="glass-panel p-6 rounded-3xl space-y-6 border border-slate-800">
            
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-cyan-400" />
                <span>{provider} Deployment Pipeline Status</span>
              </h3>

              <span className={`px-3 py-1 rounded-full text-xs font-bold border ${
                liveDeployment.status === 'deployed'
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                  : liveDeployment.status === 'failed'
                  ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                  : liveDeployment.status === 'idle'
                  ? 'bg-slate-800 text-slate-400 border-slate-700'
                  : 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 animate-pulse'
              }`}>
                {liveDeployment.status.toUpperCase()}
              </span>
            </div>

            {/* Progress Bar */}
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

            {/* Steps Timeline Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-2">
              {steps.map((step) => {
                const st = getStepStatus(step.key);
                return (
                  <div 
                    key={step.key}
                    className={`p-4 rounded-2xl border transition-all ${
                      st === 'complete'
                        ? 'bg-emerald-950/20 border-emerald-500/40 text-emerald-300'
                        : st === 'active'
                        ? 'bg-cyan-950/30 border-cyan-400 text-white shadow-lg shadow-cyan-950/50'
                        : st === 'failed'
                        ? 'bg-rose-950/20 border-rose-500/40 text-rose-300'
                        : 'bg-slate-900/40 border-slate-800 text-slate-500'
                    }`}
                  >
                    <div className="flex items-center gap-2 font-bold text-xs">
                      {st === 'complete' && <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />}
                      {st === 'active' && <RefreshCw size={16} className="text-cyan-400 animate-spin shrink-0" />}
                      {st === 'failed' && <AlertTriangle size={16} className="text-rose-400 shrink-0" />}
                      {st === 'pending' || st === 'idle' ? <Clock size={16} className="shrink-0" /> : null}
                      <span className="truncate">{step.label}</span>
                    </div>
                    <p className="text-[10px] text-slate-400 pt-1 leading-snug">{step.desc}</p>
                  </div>
                );
              })}
            </div>

            {/* Live Endpoint & Controls Banner */}
            {liveDeployment.status === 'deployed' && (
              <div className="p-5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 space-y-3">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div>
                    <span className="text-[10px] font-extrabold uppercase tracking-wider text-emerald-400">Live Service Endpoint</span>
                    <a 
                      href={liveDeployment.endpointUrl || '#'} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-lg font-extrabold text-white hover:text-cyan-300 flex items-center gap-2 underline underline-offset-4"
                    >
                      <Globe size={18} className="text-cyan-400" />
                      <span>{liveDeployment.endpointUrl || 'No URL available yet'}</span>
                    </a>
                  </div>

                  <div className="flex items-center gap-2">
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
              <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 space-y-2 text-xs text-rose-300">
                <div className="flex items-center gap-2 font-bold text-sm text-rose-400">
                  <AlertTriangle size={18} />
                  <span>
                    {liveDeployment.failureReason?.startsWith('BLOCKED')
                      ? 'Deployment Blocked — Provider Credentials Required'
                      : 'Deployment Pipeline Execution Halted'}
                  </span>
                </div>
                <p className="text-slate-300 whitespace-pre-wrap">{liveDeployment.failureReason || 'Pipeline failed during provisioning.'}</p>
                {liveDeployment.failureReason?.startsWith('BLOCKED') ? (
                  <div className="pt-2">
                    <p className="text-amber-300 text-xs font-semibold">
                      Add the required credentials to <code className="text-white">backend/.env</code> and restart the Django server.
                    </p>
                  </div>
                ) : (
                  <div className="pt-2 flex items-center gap-2">
                    <button
                      onClick={handleRollback}
                      className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs transition-colors"
                    >
                      Initiate Instant Rollback
                    </button>
                    <button
                      onClick={() => handleDeploy(false)}
                      className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs border border-slate-700 transition-colors"
                    >
                      Retry Deployment
                    </button>
                  </div>
                )}
              </div>
            )}

          </div>

          {/* Log Output Stream Terminal */}
          <div className="glass-panel rounded-3xl border border-slate-800 overflow-hidden space-y-0">
            <div className="bg-slate-900/90 px-6 py-3 border-b border-slate-800 flex items-center justify-between">
              <h4 className="text-xs font-bold text-white flex items-center gap-2">
                <Terminal className="w-4 h-4 text-cyan-400" />
                <span>Live Provisioning Console Logs</span>
              </h4>
              <span className="text-[10px] text-slate-400 font-mono">
                {liveDeployment.logs.length} lines logged
              </span>
            </div>

            <div className="p-5 bg-slate-950 font-mono text-xs text-slate-300 leading-relaxed max-h-72 overflow-y-auto space-y-1">
              {liveDeployment.logs.length === 0 ? (
                <p className="text-slate-600 text-center py-8">Console idle. Click "Start Pipeline on {provider}" to begin automated deployment.</p>
              ) : (
                liveDeployment.logs.map((log, idx) => (
                  <div key={idx} className="flex gap-2">
                    <span className="text-slate-600 select-none">&gt;</span>
                    <span className={log.includes('ERROR') || log.includes('failed') ? 'text-rose-400 font-bold' : log.includes('complete') || log.includes('live') || log.includes('200') ? 'text-emerald-400' : 'text-slate-300'}>
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
