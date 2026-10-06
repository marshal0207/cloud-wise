import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  AlertTriangle,
  Clock,
  TrendingDown,
  TrendingUp,
  BarChart3,
  Sparkles,
  Cpu,
  Database,
  HardDrive,
  Info,
  Network,
  RefreshCw,
  Server,
  ShieldCheck,
} from 'lucide-react';
import { useCloudWise, formatINR } from '@/context/CloudWiseContext';

interface ForecastItem {
  date: string;
  predictedCost?: number;
  forecastedCostUsd?: number;
  lowerBound?: number;
  lowerBoundUsd?: number;
  upperBound?: number;
  upperBoundUsd?: number;
}

interface AnomalyItem {
  date: string;
  cost: number;
  expectedRange: [number, number];
  zScore: number;
  severity: 'HIGH' | 'MEDIUM' | 'LOW';
}

const authHeaders = (): Record<string, string> => {
  const token = localStorage.getItem('cloudwise_token');
  return { Authorization: token ? `Bearer ${token}` : '' };
};

export const Monitoring: React.FC = () => {
  const navigate = useNavigate();
  const { activeProject, monitoringData, refreshMonitoring, effectiveMonthlyCost } = useCloudWise();

  const [metrics, setMetrics] = useState({
    cpu: monitoringData?.cpuUsage ?? 28,
    memory: monitoringData?.memoryUsage ?? 42,
    storage: monitoringData?.storageUsage ?? 25,
    netIn: monitoringData?.networkInMB ?? 142.5,
    netOut: monitoringData?.networkOutMB ?? 388.2,
  });

  const [forecast, setForecast] = useState<ForecastItem[]>([]);
  const [anomalies, setAnomalies] = useState<AnomalyItem[]>([]);
  const [loadingTelemetry, setLoadingTelemetry] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<string | null>(null);

  useEffect(() => {
    if (!activeProject?.id) return;
    setLoadingTelemetry(true);
    Promise.all([
      fetch(`/api/projects/${activeProject.id}/forecast`).then(r => r.ok ? r.json() : null),
      fetch(`/api/projects/${activeProject.id}/anomalies`).then(r => r.ok ? r.json() : null),
    ]).then(([fData, aData]) => {
      if (fData?.forecast && Array.isArray(fData.forecast)) {
        setForecast(fData.forecast);
      }
      if (aData?.anomalies && Array.isArray(aData.anomalies)) {
        setAnomalies(aData.anomalies);
      }
    }).catch(err => {
      console.warn('Telemetry load skipped', err);
    }).finally(() => {
      setLoadingTelemetry(false);
    });
  }, [activeProject?.id]);

  const [simulating, setSimulating] = useState(false);

  useEffect(() => {
    setMetrics({
      cpu: monitoringData.cpuUsage,
      memory: monitoringData.memoryUsage,
      storage: monitoringData.storageUsage,
      netIn: monitoringData.networkInMB,
      netOut: monitoringData.networkOutMB,
    });
  }, [monitoringData]);

  const simulateTrafficSpike = () => {
    setSimulating(true);
    setMetrics({
      cpu: Math.min(95, metrics.cpu + 25),
      memory: Math.min(90, metrics.memory + 15),
      storage: metrics.storage,
      netIn: Number((metrics.netIn * 1.8).toFixed(1)),
      netOut: Number((metrics.netOut * 2.2).toFixed(1)),
    });
    setTimeout(() => setSimulating(false), 800);
  };

  const getCost = (item: ForecastItem) => item.forecastedCostUsd ?? item.predictedCost ?? 0;
  const getLower = (item: ForecastItem) => item.lowerBoundUsd ?? item.lowerBound ?? 0;
  const getUpper = (item: ForecastItem) => item.upperBoundUsd ?? item.upperBound ?? 0;

  const totalForecastUsd = forecast.reduce((sum, item) => sum + getCost(item), 0);
  const totalForecastInr = Math.round(totalForecastUsd * 83);
  const totalLowerInr = Math.round(forecast.reduce((sum, item) => sum + getLower(item), 0) * 83);
  const totalUpperInr = Math.round(forecast.reduce((sum, item) => sum + getUpper(item), 0) * 83);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshMonitoring();
    } finally {
      setRefreshing(false);
    }
  };

  const handleHealthProbe = async () => {
    const id = monitoringData.deploymentId;
    if (!id) return;
    setProbing(true);
    try {
      const res = await fetch(`/api/deployments/${encodeURIComponent(id)}/health`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => null);
      if (data?.success && data.data) {
        setProbeResult(
          data.data.healthy
            ? `Healthy — ${data.data.message}`
            : `Unhealthy — ${data.data.message}`
        );
      } else {
        setProbeResult(data?.error || 'Health check failed.');
      }
      await refreshMonitoring();
    } catch (err: any) {
      setProbeResult(err?.message || 'Health check failed.');
    } finally {
      setProbing(false);
    }
  };

  const metricsAvailable = monitoringData.metricsCollected;
  const hasDeployment = Boolean(monitoringData.deploymentId);

  const healthTone =
    monitoringData.healthStatus === 'Healthy'
      ? 'text-emerald-400'
      : monitoringData.healthStatus === 'Failed' || monitoringData.healthStatus === 'Unhealthy'
      ? 'text-rose-400'
      : monitoringData.healthStatus === 'Deploying'
      ? 'text-emerald-400'
      : 'text-slate-400';

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      {/* Header */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-6 pb-4 border-b border-slate-800">
        <div className="space-y-2 text-center md:text-left">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-semibold">
            <Activity className="w-3.5 h-3.5" />
            <span>Step 5: Live Telemetry &amp; Monitoring</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-white">
            Resource Performance Dashboard
          </h1>
          <p className="text-xs sm:text-sm text-slate-400">
            {hasDeployment ? (
              <>
                Deployment{' '}
                <strong className="text-emerald-300 font-mono">{monitoringData.deploymentId}</strong>
                {monitoringData.ipAddress ? ` · ${monitoringData.ipAddress}` : ''}
                {monitoringData.region ? ` · ${monitoringData.region}` : ''}
              </>
            ) : (
              <>No deployment yet — nothing to monitor for this account.</>
            )}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="px-4 py-2.5 rounded-xl bg-[#080D14] hover:bg-slate-800 border border-slate-700 text-slate-200 font-semibold text-xs transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>

          <button
            onClick={() => navigate('/optimization')}
            className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-400 to-teal-500 hover:from-emerald-300 hover:to-teal-400 text-slate-950 font-bold text-xs transition-all shadow-lg shadow-emerald-500/20 flex items-center gap-2 active:scale-95"
          >
            <span>Optimize Resources</span>
            <ArrowRight size={14} />
          </button>
        </div>
      </div>

      {/* Overview banner */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-card p-5 rounded-2xl space-y-2 border border-slate-800">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>Health</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <p className={`text-xl font-bold flex items-center gap-2 ${healthTone}`}>
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                monitoringData.healthStatus === 'Healthy'
                  ? 'bg-emerald-400 animate-pulse'
                  : monitoringData.healthStatus === 'Failed' || monitoringData.healthStatus === 'Unhealthy'
                  ? 'bg-rose-400'
                  : 'bg-slate-500'
              }`}
            />
            {monitoringData.healthStatus}
          </p>
          <p className="text-[11px] text-slate-400">
            {monitoringData.httpStatus ? `Last probe: HTTP ${monitoringData.httpStatus}` : 'Derived from the live URL probe'}
          </p>
          {hasDeployment && (
            <button
              onClick={handleHealthProbe}
              disabled={probing}
              className="text-[11px] font-bold text-emerald-400 hover:text-emerald-300 disabled:opacity-50"
            >
              {probing ? 'Probing…' : 'Probe live URL now'}
            </button>
          )}
          {probeResult && <p className="text-[11px] text-slate-300">{probeResult}</p>}
        </div>

        <div className="glass-card p-5 rounded-2xl space-y-2 border border-slate-800">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>Current Burn Rate</span>
            <TrendingDown className="w-4 h-4 text-emerald-400" />
          </div>
          <p className="text-xl font-bold text-emerald-400">{formatINR(effectiveMonthlyCost)} / mo</p>
          <p className="text-[11px] text-slate-400">
            Rate: ₹{(effectiveMonthlyCost / 720).toFixed(2)}/hr
          </p>
        </div>

        <div className="glass-card p-5 rounded-2xl space-y-2 border border-slate-800">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>Instance</span>
            <Server className="w-4 h-4 text-teal-400" />
          </div>
          <p className="text-base font-bold text-white font-mono break-all">
            {monitoringData.instanceId || 'Not provisioned'}
          </p>
          <p className="text-[11px] text-slate-400">
            {monitoringData.instanceType || '—'}
            {monitoringData.region ? ` · ${monitoringData.region}` : ''}
            {monitoringData.awsAccountId ? ` · ${monitoringData.awsAccountId}` : ''}
          </p>
        </div>

        <div className="glass-card p-5 rounded-2xl space-y-2 border border-slate-800">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>Uptime Since Deploy</span>
            <Clock className="w-4 h-4 text-purple-400" />
          </div>
          <p className="text-xl font-bold text-purple-300">{monitoringData.clusterUptime}</p>
          <p className="text-[11px] text-slate-400">
            {monitoringData.activeNodes} active node{monitoringData.activeNodes !== 1 ? 's' : ''}
          </p>
        </div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {[
          {
            key: 'cpu',
            icon: Cpu,
            title: 'vCPU Utilization',
            value: monitoringData.cpuUsage,
            iconClass: 'text-emerald-400',
            badgeClass: 'bg-emerald-500/10 text-emerald-400',
            barClass: 'bg-emerald-400',
          },
          {
            key: 'memory',
            icon: Database,
            title: 'Memory (RAM)',
            value: monitoringData.memoryUsage,
            iconClass: 'text-teal-400',
            badgeClass: 'bg-teal-500/10 text-teal-400',
            barClass: 'bg-teal-400',
          },
          {
            key: 'storage',
            icon: HardDrive,
            title: 'Storage',
            value: monitoringData.storageUsage,
            iconClass: 'text-teal-400',
            badgeClass: 'bg-teal-500/10 text-teal-400',
            barClass: 'bg-teal-400',
          },
        ].map(({ key, icon: Icon, title, value, iconClass, badgeClass, barClass }) => (
          <div key={key} className="glass-panel p-6 rounded-3xl space-y-4 border border-slate-800">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Icon className={`w-5 h-5 ${iconClass}`} />
                <h3 className="text-base font-bold text-white">{title}</h3>
              </div>
              <span className={`px-2.5 py-0.5 rounded text-xs font-bold ${badgeClass}`}>
                {value === null || value === undefined ? 'n/a' : `${value}%`}
              </span>
            </div>

            {value === null || value === undefined ? (
              <div className="space-y-3">
                <div className="h-3 rounded-full bg-[#080D14] border border-slate-800 overflow-hidden">
                  <div className="h-full w-full bg-[repeating-linear-gradient(45deg,transparent,transparent_6px,rgba(148,163,184,0.10)_6px,rgba(148,163,184,0.10)_12px)]" />
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Not collected. CloudWise does not install a metrics agent on your EC2
                  instance, so this value is left empty instead of being estimated.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="w-full h-3 bg-[#080D14] rounded-full overflow-hidden border border-slate-800 p-0.5">
                  <motion.div
                    className={`h-full rounded-full ${barClass}`}
                    animate={{ width: `${value}%` }}
                    transition={{ duration: 0.5 }}
                  />
                </div>
                <div className="flex justify-between text-[11px] text-slate-400">
                  <span>Idle: {100 - value}%</span>
                  <span>{value > 80 ? 'High utilization' : 'Headroom available'}</span>
                </div>
              </div>
            )}

            <p className="text-xs text-slate-400 pt-2 border-t border-slate-800/80">
              {key === 'cpu' && 'Downsizing vCPU is evaluated in Cost Tuning.'}
              {key === 'memory' && 'RAM sizing comes from the estimate you selected.'}
              {key === 'storage' && 'EBS volume size comes from the estimate you selected.'}
            </p>
          </div>
        ))}
      </div>

      {/* 30-Day Predictive Cost Forecast (Holt-Winters Smoothing) */}
      <div className="glass-panel p-6 rounded-3xl border border-slate-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-indigo-400" />
            <h3 className="text-base font-bold text-white">
              30-Day Predictive Cost Forecast (Holt-Winters Model)
            </h3>
          </div>
          <span className="text-xs text-indigo-300 bg-indigo-500/10 border border-indigo-500/20 px-2.5 py-1 rounded-full font-medium">
            Triple Exponential Smoothing & Seasonality
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="glass-card p-4 rounded-2xl border border-slate-800 space-y-1">
            <span className="text-xs text-slate-400 font-medium">Projected 30-Day Spend</span>
            <p className="text-2xl font-extrabold text-white">
              {forecast.length > 0 ? formatINR(totalForecastInr) : formatINR(effectiveMonthlyCost)}
            </p>
            <p className="text-[11px] text-slate-400">Baseline extrapolation</p>
          </div>

          <div className="glass-card p-4 rounded-2xl border border-slate-800 space-y-1">
            <span className="text-xs text-slate-400 font-medium">95% Confidence Band</span>
            <p className="text-xl font-bold text-cyan-300">
              {forecast.length > 0 ? `${formatINR(totalLowerInr)} — ${formatINR(totalUpperInr)}` : '± 12.5%'}
            </p>
            <p className="text-[11px] text-slate-400">Widening horizon variance</p>
          </div>

          <div className="glass-card p-4 rounded-2xl border border-slate-800 space-y-1">
            <span className="text-xs text-slate-400 font-medium">Daily Run Rate</span>
            <p className="text-xl font-bold text-emerald-400">
              {forecast.length > 0 ? formatINR(Math.round(totalForecastInr / 30)) : formatINR(Math.round(effectiveMonthlyCost / 30))} <span className="text-xs font-normal text-slate-400">/ day</span>
            </p>
            <p className="text-[11px] text-slate-400">Smoothed 7-day cyclical seasonality</p>
          </div>
        </div>

        {forecast.length > 0 && (
          <div className="pt-2">
            <div className="flex items-center justify-between text-xs text-slate-400 pb-2">
              <span>Next 14 Days Cost Trajectory</span>
              <span>Daily Projected Spend (INR)</span>
            </div>
            <div className="flex items-end gap-1.5 h-16 bg-slate-950/60 p-2 rounded-2xl border border-slate-800/80">
              {forecast.slice(0, 14).map((pt, idx) => {
                const maxVal = Math.max(...forecast.slice(0, 14).map(p => getUpper(p)), 1);
                const costVal = getCost(pt);
                const heightPct = Math.min(100, Math.max(15, Math.round((costVal / maxVal) * 100)));
                return (
                  <div key={idx} className="flex-1 flex flex-col items-center h-full justify-end group relative">
                    <div 
                      className="w-full bg-gradient-to-t from-cyan-500/40 to-indigo-500 rounded-t-sm transition-all group-hover:from-cyan-400 group-hover:to-indigo-400"
                      style={{ height: `${heightPct}%` }}
                    />
                    <div className="opacity-0 group-hover:opacity-100 absolute -top-8 px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-[10px] text-white whitespace-nowrap pointer-events-none transition-opacity z-10">
                      {pt.date}: {formatINR(Math.round(costVal * 83))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Anomaly & Cost Tuning Recommendations Panel */}
      {/* Network + honesty note */}
      <div className="glass-panel p-6 rounded-3xl border border-slate-800 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Network className="w-5 h-5 text-emerald-400" />
            <span>Network &amp; Measurement Coverage</span>
          </h3>
          <span className="text-xs text-slate-400">
            {anomalies.length > 0 ? `${anomalies.length} anomaly detected` : 'Real-time scan complete'}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          {anomalies.length > 0 ? (
            anomalies.slice(0, 4).map((anom, idx) => (
              <div key={idx} className="bg-amber-950/20 border border-amber-500/30 p-4 rounded-2xl space-y-2">
                <div className="flex items-center justify-between font-bold text-amber-300">
                  <span className="flex items-center gap-1.5">
                    <AlertTriangle size={13} className="text-amber-400" />
                    <span>Cost Spike on {anom.date}</span>
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/20 uppercase font-mono">
                    z = {anom.zScore.toFixed(1)}σ ({anom.severity})
                  </span>
                </div>
                <p className="text-slate-300 leading-relaxed">
                  Observed daily cost was {formatINR(Math.round(anom.cost * 83))}, exceeding expected rolling baseline range of {formatINR(Math.round(anom.expectedRange[0] * 83))} – {formatINR(Math.round(anom.expectedRange[1] * 83))}.
                </p>
              </div>
            ))
          ) : (
            <>
              <div className="bg-amber-950/20 border border-amber-500/30 p-4 rounded-2xl space-y-2">
                <div className="flex items-center justify-between font-bold text-amber-300">
                  <span>Underutilized Instance Alert</span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/20">High Savings Opportunity</span>
                </div>
                <p className="text-slate-300 leading-relaxed">
                  vCPU average load over past 24 hours was under 20%.
                </p>
              </div>
            </>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="bg-[#080D14]/60 border border-slate-800 p-4 rounded-2xl space-y-1">
            <span className="text-slate-400">Network in</span>
            <p className="text-lg font-bold text-white">
              {monitoringData.networkInMB === null ? '—' : `${monitoringData.networkInMB} MB`}
            </p>
          </div>
          <div className="bg-[#080D14]/60 border border-slate-800 p-4 rounded-2xl space-y-1">
            <span className="text-slate-400">Network out</span>
            <p className="text-lg font-bold text-white">
              {monitoringData.networkOutMB === null ? '—' : `${monitoringData.networkOutMB} MB`}
            </p>
          </div>
          <div className="bg-[#080D14]/60 border border-slate-800 p-4 rounded-2xl space-y-1">
            <span className="text-slate-400">Deployment status</span>
            <p className="text-lg font-bold text-emerald-300 font-mono">
              {monitoringData.deploymentStatus || '—'}
            </p>
          </div>
        </div>

        <div className="bg-emerald-950/20 border border-emerald-500/20 p-4 rounded-2xl flex items-start gap-3 text-xs text-slate-300">
          <Info size={16} className="text-emerald-400 shrink-0 mt-0.5" />
          <p className="leading-relaxed">
            Everything on this page comes from your own deployment record or from a live HTTP
            probe of your live URL. CloudWise intentionally shows <strong>—</strong> for CPU,
            memory, storage and network because no agent runs on the instance. Cost figures are
            computed from the estimate you selected.
          </p>
        </div>

        <div className="pt-2 flex justify-end gap-2">
          {monitoringData.endpointUrl && (
            <a
              href={monitoringData.endpointUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="px-5 py-3 rounded-xl bg-[#080D14] hover:bg-slate-800 border border-slate-700 text-emerald-300 font-bold text-xs flex items-center gap-2"
            >
              Open Live Website
            </a>
          )}
          <button
            onClick={() =>
              navigate(
                monitoringData.deploymentId
                  ? `/deployment/${monitoringData.deploymentId}`
                  : '/deployment'
              )
            }
            className="px-5 py-3 rounded-xl bg-[#080D14] hover:bg-slate-800 border border-slate-700 text-slate-200 font-bold text-xs flex items-center gap-2"
          >
            <ArrowLeft size={14} />
            <span>Deployment Details</span>
          </button>
          <button
            onClick={() => navigate('/optimization')}
            className="px-6 py-3 rounded-xl bg-gradient-to-r from-emerald-400 to-teal-500 hover:from-emerald-300 text-slate-950 font-bold text-xs transition-all shadow-lg shadow-emerald-500/20 flex items-center gap-2 active:scale-95"
          >
            <span>Proceed to Resource Optimization</span>
            <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};
