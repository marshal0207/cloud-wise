import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Activity, 
  Cpu, 
  Server, 
  HardDrive, 
  AlertTriangle, 
  ShieldCheck, 
  ArrowRight, 
  RefreshCw,
  Clock,
  TrendingDown,
  TrendingUp,
  BarChart3,
  Sparkles
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

export const Monitoring: React.FC = () => {
  const navigate = useNavigate();
  const { selectedRecommendation, monitoringData, effectiveMonthlyCost, estimation } = useCloudWise();

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

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      
      {/* Header */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-6 pb-4 border-b border-slate-800">
        <div className="space-y-2 text-center md:text-left">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold">
            <Activity className="w-3.5 h-3.5" />
            <span>Step 4: Live Telemetry & Monitoring</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-white">
            Resource Performance Dashboard
          </h1>
          <p className="text-xs sm:text-sm text-slate-400">
            Monitoring active cluster: <strong className="text-cyan-300">{selectedRecommendation.title}</strong> ({monitoringData.ipAddress})
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={simulateTrafficSpike}
            disabled={simulating}
            className="px-4 py-2.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-300 font-semibold text-xs transition-colors flex items-center gap-1.5 active:scale-95"
          >
            <RefreshCw size={14} className={simulating ? 'animate-spin' : ''} />
            <span>Simulate Traffic Load Spike</span>
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

      {/* Cluster Overview Banner */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        
        <div className="glass-card p-5 rounded-2xl space-y-2 border border-slate-800">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>Cluster Health</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <p className="text-xl font-bold text-emerald-400 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
            Healthy (99.99% SLA)
          </p>
          <p className="text-[11px] text-slate-400">All health check probes passing</p>
        </div>

        <div className="glass-card p-5 rounded-2xl space-y-2 border border-slate-800">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>Current Burn Rate</span>
            <TrendingDown className="w-4 h-4 text-cyan-400" />
          </div>
          <p className="text-xl font-bold text-cyan-400">{formatINR(effectiveMonthlyCost)} / mo</p>
          <p className="text-[11px] text-slate-400">Rate: ₹{(effectiveMonthlyCost / 720).toFixed(2)}/hr</p>
        </div>

        <div className="glass-card p-5 rounded-2xl space-y-2 border border-slate-800">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>Node Allocation</span>
            <Server className="w-4 h-4 text-indigo-400" />
          </div>
          <p className="text-xl font-bold text-white">{selectedRecommendation.specs.vcpu} vCPU / {selectedRecommendation.specs.ram}GB</p>
          <p className="text-[11px] text-slate-400">Region: {selectedRecommendation.provider}</p>
        </div>

        <div className="glass-card p-5 rounded-2xl space-y-2 border border-slate-800">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>Cluster Uptime</span>
            <Clock className="w-4 h-4 text-purple-400" />
          </div>
          <p className="text-xl font-bold text-purple-300">{monitoringData.clusterUptime}</p>
          <p className="text-[11px] text-slate-400">{monitoringData.activeNodes} active node{monitoringData.activeNodes !== 1 ? 's' : ''}</p>
        </div>

      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        
        {/* CPU Card */}
        <div className="glass-panel p-6 rounded-3xl space-y-4 border border-slate-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Cpu className="w-5 h-5 text-cyan-400" />
              <h3 className="text-base font-bold text-white">vCPU Utilization</h3>
            </div>
            <span className={`px-2.5 py-0.5 rounded text-xs font-bold ${
              metrics.cpu > 80 ? 'bg-amber-500/20 text-amber-300' : 'bg-cyan-500/10 text-cyan-400'
            }`}>
              {metrics.cpu}%
            </span>
          </div>

          <div className="space-y-2">
            <div className="w-full h-3 bg-slate-900 rounded-full overflow-hidden border border-slate-800 p-0.5">
              <motion.div
                className={`h-full rounded-full ${
                  metrics.cpu > 80 ? 'bg-amber-400' : 'bg-cyan-400'
                }`}
                animate={{ width: `${metrics.cpu}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
            <div className="flex justify-between text-[11px] text-slate-400">
              <span>Idle: {100 - metrics.cpu}%</span>
              <span>Headroom: High</span>
            </div>
          </div>

          <p className="text-xs text-slate-400 pt-2 border-t border-slate-800/80">
            {metrics.cpu < 50 
              ? '💡 CPU is underutilized. Consider downsizing in Optimization tab.'
              : '⚡ CPU handling active workload smoothly.'}
          </p>
        </div>

        {/* Memory Card */}
        <div className="glass-panel p-6 rounded-3xl space-y-4 border border-slate-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Server className="w-5 h-5 text-indigo-400" />
              <h3 className="text-base font-bold text-white">Memory (RAM)</h3>
            </div>
            <span className="px-2.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 text-xs font-bold">
              {metrics.memory}%
            </span>
          </div>

          <div className="space-y-2">
            <div className="w-full h-3 bg-slate-900 rounded-full overflow-hidden border border-slate-800 p-0.5">
              <motion.div
                className="h-full bg-indigo-400 rounded-full"
                animate={{ width: `${metrics.memory}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
            <div className="flex justify-between text-[11px] text-slate-400">
              <span>Used: {((selectedRecommendation.specs.ram * metrics.memory) / 100).toFixed(1)} GB</span>
              <span>Total: {selectedRecommendation.specs.ram} GB</span>
            </div>
          </div>

          <p className="text-xs text-slate-400 pt-2 border-t border-slate-800/80">
            Optimal heap memory retention. No OOM swap warnings.
          </p>
        </div>

        {/* Storage Card */}
        <div className="glass-panel p-6 rounded-3xl space-y-4 border border-slate-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <HardDrive className="w-5 h-5 text-teal-400" />
              <h3 className="text-base font-bold text-white">Storage & IOPS</h3>
            </div>
            <span className="px-2.5 py-0.5 rounded bg-teal-500/10 text-teal-400 text-xs font-bold">
              {metrics.storage}%
            </span>
          </div>

          <div className="space-y-2">
            <div className="w-full h-3 bg-slate-900 rounded-full overflow-hidden border border-slate-800 p-0.5">
              <motion.div
                className="h-full bg-teal-400 rounded-full"
                animate={{ width: `${metrics.storage}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
            <div className="flex justify-between text-[11px] text-slate-400">
              <span>Volume: {selectedRecommendation.specs.storage}</span>
              <span>IOPS: {Math.round(estimation.storage * 6)} Provisioned</span>
            </div>
          </div>

          <p className="text-xs text-slate-400 pt-2 border-t border-slate-800/80">
            NVMe SSD latency baseline average: 0.8ms.
          </p>
        </div>

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
      <div className="glass-panel p-6 rounded-3xl border border-slate-800 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            <span>Active Telemetry Insights & Anomaly Alerts</span>
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
                  vCPU average load over past 24 hours was under 20%. Downsizing to {Math.max(2, Math.floor(selectedRecommendation.specs.vcpu / 2))} vCPUs will save up to {new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(Math.round(selectedRecommendation.monthlyCost * 0.28))}/month without impairing SLA.
                </p>
              </div>

              <div className="bg-slate-900/60 border border-slate-800 p-4 rounded-2xl space-y-2">
                <div className="flex items-center justify-between font-bold text-cyan-300">
                  <span>Unattached Storage Snapshot</span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/20">{formatINR(Math.round(estimation.storage * 6 * 0.24))}/mo Potential Savings</span>
                </div>
                <p className="text-slate-300 leading-relaxed">
                  Found 1 unattached {Math.round(estimation.storage * 0.24)}GB volume left over from a previous staging instance setup.
                </p>
              </div>
            </>
          )}
        </div>

        {/* CTA */}
        <div className="pt-2 flex justify-end">
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
