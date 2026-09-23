import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Cloud,
  ShieldCheck,
  KeyRound,
  Copy,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Unplug,
  FileJson,
  Terminal,
} from 'lucide-react';
import { useCloudWise } from '@/context/CloudWiseContext';

interface AwsConnectionInfo {
  connected: boolean;
  status?: string;
  accountId?: string;
  roleArn?: string;
  externalId?: string;
  region?: string;
  connectedAt?: string | null;
}

interface ConnectInfo {
  externalId: string;
  trustedAccountId: string;
  trustPolicy: string;
  permissionsPolicy: string;
  instructions: string[];
  defaultRegion: string;
  platformCredentialsConfigured: boolean;
  connection: AwsConnectionInfo;
}

const authHeaders = () => {
  const token = localStorage.getItem('cloudwise_token');
  return {
    'Content-Type': 'application/json',
    Authorization: token ? `Bearer ${token}` : '',
  };
};

export const ConnectAws: React.FC = () => {
  const navigate = useNavigate();
  const { user, showToast } = useCloudWise();

  const [connection, setConnection] = useState<AwsConnectionInfo | null>(null);
  const [info, setInfo] = useState<ConnectInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [roleArn, setRoleArn] = useState('');
  const [region, setRegion] = useState('');
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const loadConnection = async () => {
    try {
      const res = await fetch('/api/aws/connection', { headers: authHeaders() });
      const data = await res.json();
      if (data.success) {
        setConnection(data.data);
        if (data.data.connected && data.data.roleArn && !roleArn) {
          setRoleArn(data.data.roleArn);
        }
        if (data.data.region && !region) {
          setRegion(data.data.region);
        }
      }
    } catch (err) {
      console.error('Failed to load AWS connection:', err);
    }
  };

  const loadInfo = async () => {
    try {
      const res = await fetch('/api/aws/connect-info', { headers: authHeaders() });
      const data = await res.json();
      if (data.success) {
        setInfo(data.data);
        if (!region) setRegion(data.data.defaultRegion || 'ap-south-1');
      }
    } catch (err) {
      console.error('Failed to load AWS connect info:', err);
    }
  };

  useEffect(() => {
    if (!user) {
      setLoading(false);
      return;
    }
    (async () => {
      await Promise.all([loadConnection(), loadInfo()]);
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const copyText = async (text: string, field: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedField(field);
      showToast('Copied to clipboard', 'success');
      setTimeout(() => setCopiedField(null), 2000);
    } catch {
      showToast('Copy failed — select the text manually', 'error');
    }
  };

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!roleArn.trim()) {
      setError('Enter the IAM role ARN you created in your AWS account.');
      return;
    }
    setConnecting(true);
    setError(null);
    try {
      const res = await fetch('/api/aws/connect', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ roleArn: roleArn.trim(), region: region.trim() }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        setError(data.error || 'Failed to connect AWS account.');
        return;
      }
      showToast(data.message || 'AWS account connected.', 'success');
      await loadConnection();
    } catch (err) {
      setError(`Failed to connect: ${err instanceof Error ? err.message : err}`);
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      const res = await fetch('/api/aws/disconnect', {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = await res.json();
      if (data.success) {
        showToast('AWS account disconnected.', 'info');
        setConnection({ connected: false });
      }
    } catch (err) {
      showToast(`Disconnect failed: ${err}`, 'error');
    } finally {
      setDisconnecting(false);
    }
  };

  const isConnected = !!connection?.connected;

  if (!user) {
    return (
      <div className="min-h-screen max-w-3xl mx-auto px-4 py-16 text-center space-y-6">
        <div className="glass-panel p-10 rounded-3xl border border-slate-800 space-y-4">
          <Cloud className="w-10 h-10 text-cyan-400 mx-auto" />
          <h1 className="text-2xl font-extrabold text-white">Connect AWS</h1>
          <p className="text-sm text-slate-400">
            Sign in to authorize CloudWise to deploy into your AWS account via an IAM role.
          </p>
          <button
            onClick={() => navigate('/auth')}
            className="px-6 py-3 rounded-xl bg-gradient-to-r from-cyan-400 to-blue-600 text-slate-950 font-bold text-sm"
          >
            Sign In / Register
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen max-w-5xl mx-auto px-4 sm:px-6 py-10 space-y-8">
      {/* Header */}
      <div className="text-center space-y-3 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold">
          <KeyRound className="w-3.5 h-3.5" />
          <span>AWS Account Connection</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white">Connect AWS</h1>
        <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
          Authorize CloudWise to provision EC2 in <strong className="text-cyan-300">your</strong> AWS
          account using an IAM role with <strong className="text-cyan-300">temporary STS credentials</strong>.
          CloudWise never asks for or stores your AWS access keys.
        </p>
      </div>

      {/* Security model banner */}
      <div className="p-4 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 text-xs text-cyan-200 flex items-start gap-3">
        <ShieldCheck size={18} className="shrink-0 mt-0.5 text-cyan-300" />
        <div className="space-y-1">
          <p className="font-bold text-cyan-300">How authorization works</p>
          <p>
            You create a <strong>least-privilege IAM role</strong> in your own AWS account (no
            AdministratorAccess). CloudWise assumes it via <code className="text-white">sts:AssumeRole</code>{' '}
            with a unique External ID and receives <strong>short-lived temporary credentials</strong> only for
            the duration of each operation. Stored connection info: role ARN + external ID + account ID.
          </p>
        </div>
      </div>

      {loading && (
        <div className="glass-panel p-8 rounded-3xl border border-slate-800 flex items-center justify-center gap-3 text-slate-400 text-sm">
          <RefreshCw className="w-4 h-4 animate-spin" />
          <span>Loading AWS connection status…</span>
        </div>
      )}

      {!loading && (
        <>
          {/* Connection status */}
          <div className="glass-panel p-6 rounded-3xl border border-slate-800 space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <h2 className="text-sm font-bold text-white flex items-center gap-2">
                <Cloud className="w-4 h-4 text-cyan-400" />
                <span>Connection Status</span>
              </h2>
              <span
                className={`px-3 py-1 rounded-full text-xs font-bold border ${
                  isConnected
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                }`}
              >
                {isConnected ? 'Connected' : connection?.status === 'pending' ? 'Pending — create role & connect' : 'Not Connected'}
              </span>
            </div>

            {isConnected ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="bg-slate-900/70 p-3.5 rounded-xl border border-slate-800 space-y-1">
                  <span className="text-slate-500 block text-[10px] uppercase tracking-wider">AWS Account</span>
                  <p className="font-bold text-white font-mono">{connection?.accountId || '—'}</p>
                </div>
                <div className="bg-slate-900/70 p-3.5 rounded-xl border border-slate-800 space-y-1">
                  <span className="text-slate-500 block text-[10px] uppercase tracking-wider">Region</span>
                  <p className="font-bold text-white font-mono">{connection?.region || '—'}</p>
                </div>
                <div className="bg-slate-900/70 p-3.5 rounded-xl border border-slate-800 space-y-1 sm:col-span-2">
                  <span className="text-slate-500 block text-[10px] uppercase tracking-wider">IAM Role ARN</span>
                  <p className="font-bold text-cyan-300 font-mono break-all">{connection?.roleArn}</p>
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400">
                Not connected yet. Follow the 3 steps below to create your IAM role, then paste its ARN.
              </p>
            )}

            {isConnected && (
              <button
                onClick={handleDisconnect}
                disabled={disconnecting}
                className="px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-rose-500/40 text-rose-300 font-semibold text-xs transition-colors flex items-center gap-2 disabled:opacity-50"
              >
                <Unplug size={14} />
                <span>{disconnecting ? 'Disconnecting…' : 'Disconnect AWS Account'}</span>
              </button>
            )}
          </div>

          {!isConnected && info && (
            <>
              {/* Steps + policies */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Instructions */}
                <div className="glass-panel p-6 rounded-3xl border border-slate-800 space-y-4">
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <Terminal className="w-4 h-4 text-cyan-400" />
                    <span>Create the IAM role (3 steps)</span>
                  </h3>
                  <ol className="space-y-2.5 text-xs text-slate-300 list-decimal list-inside">
                    {info.instructions.map((step, idx) => (
                      <li key={idx} className="leading-relaxed">
                        {idx === 2 ? (
                          <>
                            Account ID:{' '}
                            <code className="text-cyan-300 font-bold">{info.trustedAccountId}</code>
                          </>
                        ) : idx === 4 ? (
                          <>
                            Attach the{' '}
                            <strong className="text-emerald-300">least-privilege</strong> policy below
                            (EC2 deploy permissions — <span className="text-rose-300">never</span>{' '}
                            AdministratorAccess).
                          </>
                        ) : (
                          step
                        )}
                      </li>
                    ))}
                  </ol>

                  <div className="bg-slate-900/70 p-3.5 rounded-xl border border-slate-800 space-y-1">
                    <span className="text-slate-500 block text-[10px] uppercase tracking-wider">
                      Your unique External ID (embedded in the trust policy)
                    </span>
                    <div className="flex items-center gap-2">
                      <code className="text-cyan-300 font-mono text-xs break-all flex-1">{info.externalId}</code>
                      <button
                        onClick={() => copyText(info.externalId, 'external')}
                        className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
                        title="Copy External ID"
                      >
                        {copiedField === 'external' ? (
                          <CheckCircle2 size={14} className="text-emerald-400" />
                        ) : (
                          <Copy size={14} />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Policies */}
                <div className="glass-panel p-6 rounded-3xl border border-slate-800 space-y-4">
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <FileJson className="w-4 h-4 text-emerald-400" />
                    <span>Paste these policies in IAM</span>
                  </h3>

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-slate-400">
                        1. Trust policy (who can assume)
                      </span>
                      <button
                        onClick={() => copyText(info.trustPolicy, 'trust')}
                        className="flex items-center gap-1 text-[11px] text-cyan-300 hover:text-cyan-200 font-semibold"
                      >
                        {copiedField === 'trust' ? <CheckCircle2 size={12} /> : <Copy size={12} />}
                        <span>{copiedField === 'trust' ? 'Copied' : 'Copy'}</span>
                      </button>
                    </div>
                    <pre className="bg-slate-950 border border-slate-800 rounded-xl p-3 text-[10px] leading-relaxed text-emerald-200 font-mono overflow-x-auto max-h-44 whitespace-pre-wrap break-all">
                      {info.trustPolicy}
                    </pre>
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-slate-400">
                        2. Permissions policy (least privilege — EC2 only)
                      </span>
                      <button
                        onClick={() => copyText(info.permissionsPolicy, 'perms')}
                        className="flex items-center gap-1 text-[11px] text-cyan-300 hover:text-cyan-200 font-semibold"
                      >
                        {copiedField === 'perms' ? <CheckCircle2 size={12} /> : <Copy size={12} />}
                        <span>{copiedField === 'perms' ? 'Copied' : 'Copy'}</span>
                      </button>
                    </div>
                    <pre className="bg-slate-950 border border-slate-800 rounded-xl p-3 text-[10px] leading-relaxed text-cyan-100 font-mono overflow-x-auto max-h-52 whitespace-pre-wrap break-all">
                      {info.permissionsPolicy}
                    </pre>
                  </div>

                  <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-[11px] text-emerald-300 flex items-start gap-2">
                    <ShieldCheck size={14} className="shrink-0 mt-0.5" />
                    <span>
                      Scope: EC2 describe/create/reuse, security groups (80/443/22), instance metadata,
                      tagging + PassRole for the instance profile. No admin, no billing, no other services.
                    </span>
                  </div>
                </div>
              </div>

              {/* Connect form */}
              <div className="glass-panel p-6 rounded-3xl border border-cyan-500/20 space-y-4 max-w-2xl mx-auto">
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <KeyRound className="w-4 h-4 text-cyan-400" />
                  <span>Connect your role</span>
                </h3>

                {error && (
                  <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
                    <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                    <span>{error}</span>
                  </div>
                )}

                <form onSubmit={handleConnect} className="space-y-4">
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-semibold text-slate-400">
                      IAM Role ARN <span className="text-rose-400">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={roleArn}
                      onChange={(e) => setRoleArn(e.target.value)}
                      placeholder="arn:aws:iam::123456789012:role/CloudWiseDeployRole"
                      className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-3 text-xs text-white font-mono focus:border-cyan-400 focus:outline-none"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-semibold text-slate-400">Deployment region</label>
                    <input
                      type="text"
                      value={region}
                      onChange={(e) => setRegion(e.target.value)}
                      placeholder="ap-south-1"
                      className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-3 text-xs text-white font-mono focus:border-cyan-400 focus:outline-none"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={connecting}
                    className="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-400 via-cyan-500 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-sm transition-all shadow-xl shadow-cyan-500/25 flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {connecting ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        <span>Validating role via STS…</span>
                      </>
                    ) : (
                      <>
                        <Cloud className="w-4 h-4" />
                        <span>Connect AWS</span>
                      </>
                    )}
                  </button>
                </form>

                {!info.platformCredentialsConfigured && (
                  <p className="text-[11px] text-amber-300/90 leading-relaxed">
                    Note: the CloudWise server needs its own deployer credentials
                    (<code className="text-white">AWS_DEPLOYER_ACCESS_KEY_ID</code> /{' '}
                    <code className="text-white">AWS_DEPLOYER_SECRET_ACCESS_KEY</code>) or an instance
                    role in <code className="text-white">backend/.env</code> to call sts:AssumeRole — these
                    are platform credentials, never yours.
                  </p>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
};

export default ConnectAws;
