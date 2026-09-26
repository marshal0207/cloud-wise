import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  ExternalLink,
  Globe,
  GitCommitHorizontal,
  ListChecks,
  Monitor,
  RefreshCw,
  Server,
  ShieldCheck,
  Terminal,
} from 'lucide-react';
import { useCloudWise } from '@/context/CloudWiseContext';

const authHeaders = (): Record<string, string> => {
  const token = localStorage.getItem('cloudwise_token');
  return { Authorization: token ? `Bearer ${token}` : '' };
};

interface LogEntry {
  timestamp?: string;
  level?: string;
  stage?: string;
  message?: string;
}

interface DeploymentRecord {
  id: string;
  environmentName: string;
  repository: string;
  commitSha: string;
  projectType: string;
  projectId: string | null;
  provider: string;
  awsAccountId: string;
  region: string;
  instanceId: string;
  instanceType: string;
  deploymentStatus: string;
  ipAddress: string | null;
  liveUrl: string | null;
  failureStage: string;
  createdAt: string;
  updatedAt: string;
  logs: LogEntry[];
  progress?: number;
  openUrl?: string;
  logCount?: number;
}

const IN_FLIGHT = new Set(['QUEUED', 'PREPARING', 'BUILDING', 'DEPLOYING', 'HEALTH_CHECK', 'ROLLING_BACK']);

const STATUS_TONE: Record<string, string> = {
  RUNNING: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  FAILED: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  TERMINATED: 'bg-slate-800 text-slate-300 border-slate-700',
  ROLLED_BACK: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  ROLLING_BACK: 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse',
};

const Field: React.FC<{ label: string; value: React.ReactNode; mono?: boolean }> = ({
  label,
  value,
  mono,
}) => (
  <div className="flex items-start justify-between gap-3 py-2 border-b border-slate-800 last:border-0">
    <span className="text-slate-400 text-xs shrink-0">{label}</span>
    <span
      className={`text-white text-xs font-semibold text-right break-all ${
        mono ? 'font-mono' : ''
      }`}
    >
      {value === null || value === undefined || value === '' ? '—' : value}
    </span>
  </div>
);

export const DeploymentDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useCloudWise();

  const [record, setRecord] = useState<DeploymentRecord | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [liveUrl, setLiveUrl] = useState<string | null>(null);
  const [instanceState, setInstanceState] = useState<string | null>(null);
  const [showLogs, setShowLogs] = useState(true);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [detailRes, statusRes] = await Promise.all([
        fetch(`/api/deployments/${encodeURIComponent(id)}`, { headers: authHeaders() }),
        fetch(`/api/deployments/${encodeURIComponent(id)}/status`, { headers: authHeaders() }),
      ]);
      const detail = await detailRes.json().catch(() => null);
      const live = await statusRes.json().catch(() => null);

      if (!detailRes.ok || !detail?.success) {
        setNotFound(true);
        setRecord(null);
        return;
      }

      const merged: DeploymentRecord = detail.data;
      if (live?.success && live.data) {
        merged.progress = live.data.progress ?? merged.progress;
        merged.liveUrl = live.data.liveUrl || merged.liveUrl;
        merged.ipAddress = live.data.ipAddress || merged.ipAddress;
        merged.deploymentStatus = live.data.deploymentStatus || merged.deploymentStatus;
        setLiveUrl(live.data.liveUrl || null);
        setInstanceState(live.data.instanceState ?? null);
      } else {
        setLiveUrl(merged.liveUrl || null);
      }
      setRecord(merged);
      setNotFound(false);
    } catch {
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  // Poll only while the pipeline is actually running.
  useEffect(() => {
    if (!id || !record || !IN_FLIGHT.has(record.deploymentStatus)) return;
    const timer = window.setInterval(() => void load(), 2500);
    return () => window.clearInterval(timer);
  }, [id, record?.deploymentStatus, load]);

  const act = async (name: string, path: string, successMessage: string) => {
    if (!id) return;
    try {
      setBusy(name);
      const res = await fetch(`/api/deployments/${encodeURIComponent(id)}/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.success) {
        showToast(data.error || `${name} failed.`, 'error');
      } else {
        showToast(successMessage, 'success');
      }
      await load();
    } catch (err: any) {
      showToast(err?.message || `${name} failed.`, 'error');
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-[50vh] flex items-center justify-center gap-3 text-slate-400 text-sm">
        <RefreshCw size={16} className="animate-spin" />
        <span>Loading deployment…</span>
      </div>
    );
  }

  if (notFound || !record) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center space-y-4">
        <AlertTriangle size={32} className="mx-auto text-rose-400" />
        <h1 className="text-2xl font-extrabold text-white">Deployment not found</h1>
        <p className="text-slate-400 text-sm">
          This deployment does not exist, or it belongs to another account.
        </p>
        <button
          onClick={() => navigate('/deployment')}
          className="px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs"
        >
          Back to Deploy
        </button>
      </div>
    );
  }

  const status = record.deploymentStatus;
  const tone =
    STATUS_TONE[status] ||
    (IN_FLIGHT.has(status)
      ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 animate-pulse'
      : 'bg-slate-800 text-slate-300 border-slate-700');

  const canRetry = status === 'FAILED' || status === 'ROLLED_BACK';
  const openableUrl = liveUrl || record.liveUrl || '';

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-6">
      <button
        onClick={() => navigate('/deployment')}
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-400 hover:text-white transition-colors"
      >
        <ArrowLeft size={14} />
        <span>Back to deploy pipeline</span>
      </button>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold">
            <Server className="w-3.5 h-3.5" />
            <span>Deployment {record.id}</span>
          </div>
          <h1 className="text-2xl sm:text-4xl font-extrabold text-white break-all">
            {record.repository || 'Repository'}
          </h1>
          <p className="text-slate-400 text-sm">
            {record.projectType || 'Project'} · {record.environmentName}
          </p>
        </div>
        <span className={`self-start sm:self-center px-3 py-1.5 rounded-full text-xs font-extrabold border ${tone}`}>
          {status}
        </span>
      </div>

      {openableUrl && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
        >
          <div className="min-w-0">
            <span className="text-[10px] font-extrabold uppercase tracking-wider text-emerald-400">
              Live Application
            </span>
            <a
              href={openableUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-lg font-extrabold text-white hover:text-cyan-300 flex items-center gap-2 underline underline-offset-4 break-all"
            >
              <Globe size={18} className="text-cyan-400 shrink-0" />
              <span>{openableUrl}</span>
            </a>
          </div>
          <a
            href={openableUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs transition-all shadow flex items-center gap-1.5 shrink-0"
          >
            <ExternalLink size={14} />
            <span>Open Live Website</span>
          </a>
        </motion.div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => void act('health', 'health', 'Health check completed.')}
          disabled={!!busy}
          className="px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-emerald-400 font-bold text-xs flex items-center gap-1.5 disabled:opacity-50"
        >
          <Activity size={14} />
          <span>Run Health Check</span>
        </button>
        <button
          onClick={() => void load()}
          disabled={!!busy}
          className="px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 font-bold text-xs flex items-center gap-1.5 disabled:opacity-50"
        >
          <RefreshCw size={14} className={busy === 'refresh' ? 'animate-spin' : ''} />
          <span>Refresh</span>
        </button>
        {canRetry && (
          <button
            onClick={() => void act('retry', 'retry', 'Retry queued.')}
            disabled={!!busy}
            className="px-3.5 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs flex items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw size={14} />
            <span>Retry</span>
          </button>
        )}
        <button
          onClick={() => void act('rollback', 'rollback', 'Rollback recorded. EC2 instance retained.')}
          disabled={!!busy || status === 'TERMINATED'}
          className="px-3.5 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-bold text-xs flex items-center gap-1.5 disabled:opacity-50"
        >
          <ShieldCheck size={14} />
          <span>Rollback</span>
        </button>
        <button
          onClick={() => void act('terminate', 'terminate', 'EC2 instance terminated.')}
          disabled={!!busy || status === 'TERMINATED'}
          className="px-3.5 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs flex items-center gap-1.5 disabled:opacity-50"
        >
          <AlertTriangle size={14} />
          <span>Terminate Instance</span>
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Facts */}
        <div className="glass-panel p-6 rounded-3xl border border-slate-800 space-y-4">
          <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
            <ListChecks className="w-4 h-4 text-cyan-400" />
            Deployment Facts
          </h3>
          <div>
            <Field label="Repository" value={record.repository} mono />
            <Field
              label="Commit"
              value={record.commitSha ? record.commitSha.slice(0, 12) : ''}
              mono
            />
            <Field label="Project type" value={record.projectType} />
            <Field label="AWS account" value={record.awsAccountId} mono />
            <Field label="AWS region" value={record.region} />
            <Field label="Instance ID" value={record.instanceId} mono />
            <Field label="Instance type" value={record.instanceType} mono />
            <Field label="Instance state" value={instanceState} mono />
            <Field label="Public IP" value={record.ipAddress} mono />
            <Field
              label="Deployment status"
              value={<span className="font-mono font-extrabold">{status}</span>}
            />
            <Field label="Failure stage" value={record.failureStage} />
            <Field label="Environment" value={record.environmentName} />
            <Field label="Created time" value={new Date(record.createdAt).toLocaleString()} />
            <Field label="Updated time" value={new Date(record.updatedAt).toLocaleString()} />
          </div>

          <div className="pt-2 border-t border-slate-800 space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="text-slate-400">Progress</span>
              <span className="text-cyan-400 font-bold">{record.progress ?? 0}%</span>
            </div>
            <div className="w-full h-2.5 rounded-full bg-slate-900 overflow-hidden border border-slate-800">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  status === 'FAILED'
                    ? 'bg-rose-500'
                    : status === 'RUNNING'
                    ? 'bg-emerald-400'
                    : 'bg-gradient-to-r from-cyan-500 to-blue-500'
                }`}
                style={{ width: `${record.progress ?? 0}%` }}
              />
            </div>
          </div>

          <div className="pt-2 border-t border-slate-800 space-y-1 text-[11px] text-slate-400">
            <p className="flex items-center gap-1.5">
              <GitCommitHorizontal size={13} className="text-cyan-400" />
              {record.commitSha ? `Resolved from commit ${record.commitSha.slice(0, 7)}` : 'Commit not recorded'}
            </p>
            <p className="flex items-center gap-1.5">
              <Monitor size={13} className="text-cyan-400" />
              {record.provider} provider · user-assumed IAM role
            </p>
          </div>
        </div>

        {/* Logs */}
        <div className="lg:col-span-2 glass-panel rounded-3xl border border-slate-800 overflow-hidden">
          <div className="bg-slate-900/90 px-6 py-3 border-b border-slate-800 flex items-center justify-between gap-3">
            <h3 className="text-xs font-bold text-white flex items-center gap-2">
              <Terminal className="w-4 h-4 text-cyan-400" />
              <span>Deployment Logs</span>
            </h3>
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-slate-400 font-mono">
                {(record.logs || []).length} entries
              </span>
              <button
                onClick={() => setShowLogs(v => !v)}
                className="text-[11px] font-semibold text-cyan-400 hover:text-cyan-300"
              >
                {showLogs ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          {showLogs && (
            <div className="p-5 bg-slate-950 font-mono text-[11px] leading-relaxed max-h-[32rem] overflow-y-auto space-y-1">
              {(record.logs || []).length === 0 ? (
                <p className="text-slate-600 text-center py-8">
                  No log entries recorded yet.
                </p>
              ) : (
                (record.logs || []).map((entry, idx) => (
                  <div key={idx} className="flex gap-2 items-start">
                    <span className="text-slate-600 select-none shrink-0">
                      {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '—'}
                    </span>
                    <span
                      className={
                        entry.level === 'ERROR'
                          ? 'text-rose-400 font-bold'
                          : entry.level === 'WARN'
                          ? 'text-amber-400'
                          : 'text-slate-300'
                      }
                    >
                      [{entry.stage || 'INFO'}] {entry.message}
                    </span>
                  </div>
                ))
              )}
            </div>
          )}

          <div className="px-6 py-3 border-t border-slate-800 bg-slate-900/60 flex items-center gap-4 text-[11px] text-slate-400">
            <span className="flex items-center gap-1.5">
              {IN_FLIGHT.has(status) ? (
                <RefreshCw size={12} className="animate-spin text-cyan-400" />
              ) : status === 'RUNNING' ? (
                <CheckCircle2 size={12} className="text-emerald-400" />
              ) : (
                <Clock size={12} />
              )}
              {IN_FLIGHT.has(status)
                ? 'Polling the live pipeline every 2.5s'
                : status === 'RUNNING'
                ? 'Deployment is live'
                : 'Pipeline finished — not polling'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DeploymentDetails;
