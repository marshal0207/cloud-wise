import React, { useState } from 'react';
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
  Cloud
} from 'lucide-react';
import { useCloudWise, formatINR } from '@/context/CloudWiseContext';

export const Deployment: React.FC = () => {
  const navigate = useNavigate();
  const { 
    selectedRecommendation, 
    estimation, 
    deployment, 
    startSimulatedDeployment, 
    rollbackDeployment,
    resetDeployment,
    updateActiveProject
  } = useCloudWise();

  const [envName, setEnvName] = useState(deployment.environmentName || 'cloudwise-prod-cluster');
  const [autoScaling, setAutoScaling] = useState(true);
  const [dailyBackup, setDailyBackup] = useState(true);
  const [showDeployConfirmation, setShowDeployConfirmation] = useState(false);
  const storageGb = Number(selectedRecommendation.specs.storage.match(/\d+/)?.[0] || 0);
  const deploymentEligible = selectedRecommendation.specs.vcpu <= 2
    && selectedRecommendation.specs.ram <= 2
    && storageGb <= 30;

  const handleDeploy = async (simulateError = false) => {
    if (!deploymentEligible) {
      return;
    }
    startSimulatedDeployment(envName, simulateError);
    try {
      await fetch('/api/deploy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          environmentName: envName,
          provider: selectedRecommendation.provider,
          monthlyCost: selectedRecommendation.monthlyCost,
          specs: selectedRecommendation.specs,
          region: estimation.region,
          autoScaling,
          dailyBackup
        }),
      });
    } catch (err) {
      console.warn('Backend deployment tracking skipped:', err);
    }
  };

  const handleConfirmDeployment = () => {
    setShowDeployConfirmation(false);
    void handleDeploy(false);
  };

  const steps = [
    { key: 'preparing', label: '1. Preparing Environment', desc: 'Validating API keys & quotas' },
    { key: 'provisioning', label: '2. Provisioning Nodes', desc: 'Spinning up virtual instances' },
    { key: 'configuring', label: '3. Configuring Network', desc: 'Attaching storage & endpoints' },
    { key: 'deployed', label: '4. Deployment Complete', desc: 'Cluster active & operational' },
  ];

  const getStepStatus = (stepKey: string) => {
    if (deployment.status === 'idle') return 'idle';
    if (deployment.status === 'deployed') return 'complete';
    if (deployment.status === 'failed') return 'failed';
    
    const stepOrder = ['preparing', 'provisioning', 'configuring', 'deployed'];
    const currentIndex = stepOrder.indexOf(deployment.status);
    const stepIndex = stepOrder.indexOf(stepKey);

    if (stepIndex < currentIndex) return 'complete';
    if (stepIndex === currentIndex) return 'active';
    return 'pending';
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
          <span>Step 4: Automated Resource Provisioning</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white">
          Deploy Cloud Configuration
        </h1>
        <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
          Review cluster parameters and trigger automated provisioning. Watch live logs as your infrastructure comes online.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Column: Config Summary & Form */}
        <div className="space-y-6 lg:col-span-1">
          
          <div className="glass-panel p-6 rounded-3xl space-y-6 border border-slate-800">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Cloud className="w-4 h-4 text-cyan-400" />
                <span>Target Architecture</span>
              </h3>
              <span className="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 text-[10px] font-bold border border-cyan-500/30">
                {selectedRecommendation.provider}
              </span>
            </div>

            <div className="space-y-3 text-xs">
              <div className="bg-slate-900/80 p-3.5 rounded-xl border border-slate-800 space-y-1">
                <span className="text-slate-400 block text-[10px]">Chosen Package</span>
                <p className="font-bold text-white text-sm">{selectedRecommendation.title}</p>
                <span className="text-cyan-400 font-bold block pt-1">{formatINR(selectedRecommendation.monthlyCost)} / month</span>
              </div>

              <div className="space-y-2 pt-1">
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
                <div className="flex justify-between text-slate-300">
                  <span className="text-slate-400">Storage Type</span>
                  <span className="font-bold">{selectedRecommendation.specs.storage}</span>
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
                  disabled={deployment.status !== 'idle'}
                  value={envName}
                  onChange={(e) => setEnvName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-white focus:border-cyan-400 focus:outline-none disabled:opacity-60"
                />
              </div>

              <div className="flex items-center justify-between text-xs pt-1">
                <span className="text-slate-300 font-medium">Enable Auto-Scaling</span>
                <input
                  type="checkbox"
                  disabled={deployment.status !== 'idle'}
                  checked={autoScaling}
                  onChange={(e) => setAutoScaling(e.target.checked)}
                  className="w-4 h-4 accent-cyan-400 rounded cursor-pointer"
                />
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-300 font-medium">Automated Daily Backups</span>
                <input
                  type="checkbox"
                  disabled={deployment.status !== 'idle'}
                  checked={dailyBackup}
                  onChange={(e) => setDailyBackup(e.target.checked)}
                  className="w-4 h-4 accent-cyan-400 rounded cursor-pointer"
                />
              </div>
            </div>

            {/* Deploy Trigger Buttons */}
            {deployment.status === 'idle' && (
              <div className="space-y-2 pt-2">
                <button
                  onClick={() => setShowDeployConfirmation(true)}
                  className="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-400 via-cyan-500 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-sm transition-all shadow-xl shadow-cyan-500/25 flex items-center justify-center gap-2 active:scale-98"
                >
                  <Rocket className="w-5 h-5" />
                  <span>Trigger Provisioning Pipeline</span>
                </button>

                <button
                  onClick={() => handleDeploy(true)}
                  className="w-full py-2.5 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-800 text-slate-400 text-xs font-semibold hover:text-amber-300 transition-colors flex items-center justify-center gap-1.5"
                >
                  <span>Test Simulated Quota Failure</span>
                </button>
              </div>
            )}

            {deployment.status !== 'idle' && (
              <button
                onClick={resetDeployment}
                className="w-full py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 font-semibold text-xs transition-colors flex items-center justify-center gap-1.5"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Reset Pipeline State</span>
              </button>
            )}

          </div>

        </div>

        {/* Right Column: Simulated Deployment Progress Timeline & Log Terminal */}
        <div className="space-y-6 lg:col-span-2">
          
          {/* Progress Timeline */}
          <div className="glass-panel p-6 rounded-3xl space-y-6 border border-slate-800">
            
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-cyan-400" />
                <span>Provisioning Pipeline Status</span>
              </h3>

              <span className={`px-3 py-1 rounded-full text-xs font-bold border ${
                deployment.status === 'deployed' 
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : deployment.status === 'failed'
                  ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                  : deployment.status === 'idle'
                  ? 'bg-slate-800 text-slate-400 border-slate-700'
                  : 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30 animate-pulse'
              }`}>
                {deployment.status === 'deployed' 
                  ? '✓ Deployed Live' 
                  : deployment.status === 'failed'
                  ? '✖ Provisioning Failed'
                  : deployment.status === 'idle' 
                  ? 'Ready to Deploy' 
                  : 'Provisioning...'}
              </span>
            </div>

            {/* Progress Bar */}
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-slate-400">Completion</span>
                <span className="text-cyan-400">{deployment.progress}%</span>
              </div>
              <div className="w-full h-3 bg-slate-900 rounded-full overflow-hidden border border-slate-800 p-0.5">
                <motion.div
                  className={`h-full rounded-full ${
                    deployment.status === 'failed'
                      ? 'bg-rose-500'
                      : 'bg-gradient-to-r from-cyan-500 to-blue-500'
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${deployment.progress}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
            </div>

            {/* Step Indicators */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {steps.map((step) => {
                const status = getStepStatus(step.key);
                return (
                  <div
                    key={step.key}
                    className={`p-3 rounded-xl border text-xs space-y-1 transition-all ${
                      status === 'complete'
                        ? 'bg-emerald-950/20 border-emerald-500/40 text-emerald-300'
                        : status === 'active'
                        ? 'bg-cyan-950/40 border-cyan-400 text-cyan-200 ring-1 ring-cyan-400/40'
                        : status === 'failed'
                        ? 'bg-rose-950/20 border-rose-500/40 text-rose-300'
                        : 'bg-slate-900/40 border-slate-800 text-slate-400'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 font-bold">
                      {status === 'complete' && <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />}
                      {status === 'active' && <RefreshCw size={14} className="text-cyan-400 animate-spin shrink-0" />}
                      {status === 'pending' && <Clock size={14} className="text-slate-400 shrink-0" />}
                      {status === 'idle' && <Clock size={14} className="text-slate-400 shrink-0" />}
                      <span className="truncate">{step.label}</span>
                    </div>
                    <p className="text-[10px] text-slate-400 leading-tight">{step.desc}</p>
                  </div>
                );
              })}
            </div>

          </div>

          {/* Log Console */}
          <div className="glass-panel rounded-3xl border border-slate-800 overflow-hidden">
            <div className="bg-slate-900/90 px-6 py-3 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-300">
                <Terminal size={16} className="text-cyan-400" />
                <span>Live Deployment Logs</span>
              </div>
              <span className="text-[10px] text-slate-400 font-mono">cloudwise-cli v2.4</span>
            </div>

            <div className="p-6 bg-slate-950/90 font-mono text-xs text-slate-300 space-y-2 min-h-[180px] max-h-[260px] overflow-y-auto">
              {deployment.logs.length === 0 ? (
                <p className="text-slate-400 italic">Click "Trigger Provisioning Pipeline" above to begin deployment...</p>
              ) : (
                deployment.logs.map((log, i) => (
                  <div key={i} className="flex items-start gap-2 leading-relaxed">
                    <span className={log.includes('ERROR') ? 'text-rose-400 font-bold' : 'text-cyan-400 font-bold'}>›</span>
                    <span className={log.includes('ERROR') ? 'text-rose-300' : 'text-slate-200'}>{log}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Failure State & Rollback Option */}
          {deployment.status === 'failed' && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-panel p-6 rounded-3xl border border-rose-500/40 bg-rose-950/20 space-y-4 text-center"
            >
              <div className="space-y-1">
                <h4 className="text-lg font-bold text-rose-400 flex items-center justify-center gap-2">
                  <Clock size={20} />
                  <span>Deployment Failed</span>
                </h4>
                <p className="text-xs text-slate-300">
                  {deployment.failureReason || 'An error occurred during resource allocation in target cloud region.'}
                </p>
              </div>

              <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
                <button
                  onClick={rollbackDeployment}
                  className="w-full sm:flex-1 py-3.5 rounded-xl bg-rose-500 hover:bg-rose-400 text-slate-950 font-bold text-xs transition-all shadow-lg shadow-rose-500/20 flex items-center justify-center gap-2 active:scale-98"
                >
                  <RefreshCw size={16} />
                  <span>Rollback Infrastructure & Reset</span>
                </button>

                <button
                  onClick={() => navigate('/recommendation')}
                  className="w-full sm:w-auto px-6 py-3.5 rounded-xl bg-slate-900 border border-slate-700 text-white font-semibold text-xs hover:bg-slate-800"
                >
                  <span>Change Provider / Region</span>
                </button>
              </div>
            </motion.div>
          )}

          {/* Post-Deployment Next Step CTA */}
          {deployment.status === 'deployed' && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-panel p-6 rounded-3xl border border-emerald-500/40 bg-emerald-950/10 space-y-4 text-center"
            >
              <div className="space-y-1">
                <h4 className="text-lg font-bold text-emerald-400 flex items-center justify-center gap-2">
                  <ShieldCheck size={20} />
                  <span>Deployment Successful!</span>
                </h4>
                <p className="text-xs text-slate-300">
                  Target cluster is online at IP <strong className="text-cyan-300">{deployment.ipAddress}</strong> ({deployment.endpointUrl}).
                </p>
              </div>

              <button
                onClick={handleProceedToOptimization}
                className="w-full py-4 rounded-xl bg-gradient-to-r from-emerald-400 to-teal-500 hover:from-emerald-300 hover:to-teal-400 text-slate-950 font-bold text-sm transition-all shadow-xl shadow-emerald-500/20 flex items-center justify-center gap-2 active:scale-98"
              >
                <span>Proceed to Cloud Cost Tuning & Optimization</span>
                <ArrowRight size={18} />
              </button>
            </motion.div>
          )}

        </div>

      </div>

      {showDeployConfirmation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
          <div className="glass-panel max-w-lg w-full p-6 sm:p-8 rounded-3xl space-y-6 border border-cyan-500/40 shadow-2xl">
            <div className="space-y-2">
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">Deployment Confirmation</span>
              <h3 className="text-2xl font-extrabold text-white">Use this configuration?</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Review the selected plan before starting the provisioning pipeline. Cancel to return without deploying.
              </p>
            </div>

            <div className="bg-slate-900/80 p-4 rounded-2xl border border-slate-800 space-y-3 text-xs">
              <div className="flex items-center justify-between gap-4">
                <span className="text-slate-400">Provider and plan</span>
                <span className="font-bold text-white text-right">{selectedRecommendation.provider} · {selectedRecommendation.title}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-slate-400">Region</span>
                <span className="font-bold text-white text-right">{estimation.region}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-slate-400">Resources</span>
                <span className="font-bold text-white text-right">{selectedRecommendation.specs.vcpu} vCPU · {selectedRecommendation.specs.ram} GB RAM</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-slate-400">Storage</span>
                <span className="font-bold text-white text-right">{selectedRecommendation.specs.storage}</span>
              </div>
              <div className="flex items-center justify-between gap-4 border-t border-slate-800 pt-3">
                <span className="text-slate-400">Estimated monthly cost</span>
                <span className="font-extrabold text-cyan-300 text-base">{formatINR(selectedRecommendation.monthlyCost)}/mo</span>
              </div>
            </div>

            {!deploymentEligible && (
              <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/40 text-amber-200 text-xs leading-relaxed">
                This selected plan exceeds the AWS Free Tier demo limit. Choose a plan with up to 2 vCPU, 2 GB RAM, and 30 GB storage before deploying.
              </div>
            )}

            <div className="flex flex-col-reverse sm:flex-row gap-3">
              <button
                onClick={() => setShowDeployConfirmation(false)}
                className="flex-1 py-3.5 rounded-xl bg-slate-900 border border-slate-700 text-slate-200 font-semibold text-xs hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDeployment}
                disabled={!deploymentEligible}
                className="flex-1 py-3.5 rounded-xl bg-gradient-to-r from-cyan-400 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-xs transition-all shadow-lg shadow-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {deploymentEligible ? 'Confirm & Start Deployment' : 'Plan Exceeds Free Tier'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
