import React, { useState } from 'react';
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
  TrendingDown
} from 'lucide-react';
import { useCloudWise, formatINR } from '@/context/CloudWiseContext';

export const Monitoring: React.FC = () => {
  const navigate = useNavigate();
  const { selectedRecommendation, monitoringData, deployment, effectiveMonthlyCost } = useCloudWise();

  const [metrics, setMetrics] = useState({
    cpu: monitoringData.cpuUsage,
    memory: monitoringData.memoryUsage,
    storage: monitoringData.storageUsage,
    netIn: monitoringData.networkInMB,
    netOut: monitoringData.networkOutMB,
  });

  const [simulating, setSimulating] = useState(false);

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
            Monitoring active cluster: <strong className="text-cyan-300">{selectedRecommendation.title}</strong> ({deployment.ipAddress || '35.120.45.19'})
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
          <p className="text-xl font-bold text-purple-300">14d 08h 32m</p>
          <p className="text-[11px] text-slate-400">Zero unhandled downtime</p>
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
              <span>IOPS: 3,000 Provisioned</span>
            </div>
          </div>

          <p className="text-xs text-slate-400 pt-2 border-t border-slate-800/80">
            NVMe SSD latency baseline average: 0.8ms.
          </p>
        </div>

      </div>

      {/* Anomaly & Cost Tuning Recommendations Panel */}
      <div className="glass-panel p-6 rounded-3xl border border-slate-800 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            <span>Active Telemetry Insights & Anomaly Alerts</span>
          </h3>
          <span className="text-xs text-slate-400">Real-time scan complete</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="bg-amber-950/20 border border-amber-500/30 p-4 rounded-2xl space-y-2">
            <div className="flex items-center justify-between font-bold text-amber-300">
              <span>Underutilized Instance Alert</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/20">High Savings Opportunity</span>
            </div>
            <p className="text-slate-300 leading-relaxed">
              vCPU average load over past 24 hours was under 20%. Downsizing to 4 vCPUs will save up to ₹3,480/month without impairing SLA.
            </p>
          </div>

          <div className="bg-slate-900/60 border border-slate-800 p-4 rounded-2xl space-y-2">
            <div className="flex items-center justify-between font-bold text-cyan-300">
              <span>Unattached Storage Snapshot</span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/20">₹1,240/mo Potential Savings</span>
            </div>
            <p className="text-slate-300 leading-relaxed">
              Found 1 unattached 120GB gp3 volume left over from a previous staging instance setup.
            </p>
          </div>
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
