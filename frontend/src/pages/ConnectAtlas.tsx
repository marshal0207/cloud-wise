import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCloudWise } from '@/context/CloudWiseContext';
import {
  Database, CheckCircle2, AlertTriangle, Loader2, ArrowRight, Unplug, ShieldCheck, Server, KeyRound, ChevronDown, ChevronUp
} from 'lucide-react';

type ConnectionInfo = {
  connected: boolean;
  configured: boolean;
  publicKeyPresent: boolean;
  privateKeyPresent: boolean;
  projectIdPresent: boolean;
  projectId: string;
  status: string;
  connectedAt?: string | null;
};

export const ConnectAtlas: React.FC = () => {
  const { user, showToast } = useCloudWise();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [showManual, setShowManual] = useState(false);

  const [isConnected, setIsConnected] = useState(false);
  const [projectId, setProjectId] = useState('');
  const [info, setInfo] = useState<ConnectionInfo | null>(null);

  const [formClientId, setFormClientId] = useState('');
  const [formClientSecret, setFormClientSecret] = useState('');
  const [formProjectId, setFormProjectId] = useState('');

  const authHeaders = () => {
    const token = localStorage.getItem('cloudwise_token');
    return {
      'Content-Type': 'application/json',
      Authorization: token ? `Bearer ${token}` : '',
    };
  };

  const loadConnection = async () => {
    try {
      const res = await fetch('/api/atlas/connection', { headers: authHeaders() });
      const data: ConnectionInfo = await res.json();
      setInfo(data);
      setIsConnected(Boolean(data.connected));
      setProjectId(data.projectId || '');
      // Only fall back to the manual form when the server has no Atlas
      // configuration at all.
      setShowManual(!data.connected && !data.configured);
    } catch (err) {
      console.error('Failed to load Atlas connection:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!user) {
      setLoading(false);
      return;
    }
    loadConnection();
  }, [user]);

  const applyConnected = (data: any) => {
    showToast('MongoDB Atlas connected successfully', 'success');
    setIsConnected(true);
    setProjectId(data?.projectId || '');
    loadConnection();
  };

  const handleConnectServer = async () => {
    setSubmitting(true);
    try {
      // Empty body → the backend uses its own MONGODB_ATLAS_* .env config.
      const res = await fetch('/api/atlas/connect', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (data.success) {
        applyConnected(data.data);
      } else {
        showToast(data.error || 'Failed to connect Atlas', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to connect Atlas', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleConnectManual = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formClientId.trim() || !formClientSecret.trim() || !formProjectId.trim()) {
      showToast('Please fill all fields', 'error');
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch('/api/atlas/connect', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          clientId: formClientId.trim(),
          clientSecret: formClientSecret.trim(),
          projectId: formProjectId.trim(),
        }),
      });
      const data = await res.json();
      if (data.success) {
        // The secret stays on the backend — clear it from the form and
        // from component state right away.
        setFormClientId('');
        setFormClientSecret('');
        setFormProjectId('');
        applyConnected(data.data);
      } else {
        showToast(data.error || 'Failed to connect Atlas', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to connect Atlas', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDisconnect = async () => {
    setDisconnecting(true);
    try {
      const res = await fetch('/api/atlas/disconnect', {
        method: 'POST',
        headers: authHeaders()
      });
      const data = await res.json();
      if (data.success) {
        showToast('MongoDB Atlas disconnected', 'success');
        setIsConnected(false);
        setProjectId('');
        loadConnection();
      } else {
        showToast('Failed to disconnect Atlas', 'error');
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to disconnect Atlas', 'error');
    } finally {
      setDisconnecting(false);
    }
  };

  if (!user) {
    return (
      <div className="flex h-[80vh] items-center justify-center">
        <div className="text-center">
          <Database size={48} className="mx-auto mb-4 text-slate-700" />
          <h2 className="text-xl font-bold text-white">Sign in required</h2>
          <p className="mt-2 text-slate-400">Please sign in to configure MongoDB Atlas.</p>
          <button
            onClick={() => navigate('/auth')}
            className="mt-6 rounded-lg bg-emerald-500 px-6 py-2 font-semibold text-white hover:bg-emerald-600"
          >
            Sign In
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-[80vh] items-center justify-center">
        <Loader2 className="animate-spin text-emerald-500" size={32} />
      </div>
    );
  }

  const envCheck = (label: string, present?: boolean) => (
    <div key={label} className="flex items-center justify-between py-1.5">
      <span className="font-mono text-xs text-slate-400">{label}</span>
      <span className={`text-xs font-bold ${present ? 'text-emerald-400' : 'text-amber-400'}`}>
        {present ? 'detected' : 'missing'}
      </span>
    </div>
  );

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-10 text-center">
        <div className="mb-4 inline-flex items-center justify-center rounded-2xl bg-emerald-500/10 p-4 ring-1 ring-emerald-500/20">
          <Database size={40} className="text-emerald-400" />
        </div>
        <h1 className="mb-4 text-3xl font-extrabold tracking-tight text-white sm:text-5xl">
          MongoDB <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400">Atlas</span>
        </h1>
        <p className="mx-auto max-w-2xl text-lg text-slate-400">
          One-time verification so CloudWise can add each new deployment's IP to your Atlas Network Access list.
        </p>
      </div>

      <div className="mx-auto max-w-2xl">
        {isConnected ? (
          <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/50 shadow-2xl backdrop-blur-xl">
            <div className="border-b border-slate-800/50 bg-slate-900/80 p-6 sm:p-8">
              <div className="flex items-center gap-4">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-emerald-500/10 ring-1 ring-emerald-500/20">
                  <CheckCircle2 size={28} className="text-emerald-400" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-white">✓ Connected</h2>
                  <p className="mt-1 text-sm text-slate-400">CloudWise is authorized to manage IP Access Lists.</p>
                </div>
              </div>
            </div>

            <div className="p-6 sm:p-8">
              <div className="mb-8 rounded-xl border border-slate-800/50 bg-slate-950/50 p-4">
                <p className="text-sm text-slate-400">Project ID</p>
                <p className="mt-1 font-mono text-lg font-bold text-emerald-400">{projectId}</p>
              </div>

              <div className="rounded-xl border border-blue-500/20 bg-blue-500/10 p-4">
                <div className="flex items-start gap-3">
                  <ShieldCheck size={20} className="mt-0.5 text-blue-400" />
                  <div>
                    <h4 className="font-bold text-blue-200">How it works</h4>
                    <p className="mt-1 text-sm text-blue-300/80">
                      When you deploy an application that uses a MONGO_URI, CloudWise will automatically fetch the new EC2 public IP and add it to your Atlas Project's Network Access list.
                    </p>
                  </div>
                </div>
              </div>

              <div className="mt-8 flex justify-end">
                <button
                  onClick={handleDisconnect}
                  disabled={disconnecting}
                  className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-6 py-3 text-sm font-bold text-slate-300 transition-all hover:bg-slate-700 disabled:opacity-50"
                >
                  {disconnecting ? <Loader2 size={16} className="animate-spin" /> : <Unplug size={16} />}
                  Disconnect Atlas
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/50 shadow-2xl backdrop-blur-xl">
            <div className="border-b border-slate-800/50 bg-slate-900/80 p-6 sm:p-8">
              <h2 className="text-xl font-bold text-white">MongoDB Atlas Authorization Required</h2>
              <p className="mt-2 text-sm text-slate-400">
                CloudWise verifies your Atlas configuration from its own backend settings, then stores it for this account.
              </p>
            </div>

            <div className="p-6 sm:p-8">
              <div className="mb-6 rounded-xl border border-slate-800/50 bg-slate-950/50 p-4">
                <div className="mb-2 flex items-center gap-2">
                  <Server size={16} className="text-emerald-400" />
                  <h4 className="text-sm font-bold text-slate-200">Server-side configuration</h4>
                </div>
                {envCheck('MONGODB_ATLAS_PUBLIC_KEY', info?.publicKeyPresent)}
                {envCheck('MONGODB_ATLAS_PRIVATE_KEY', info?.privateKeyPresent)}
                {envCheck('MONGODB_ATLAS_PROJECT_ID', info?.projectIdPresent)}
                <p className="mt-3 text-xs text-slate-500">
                  Values stay on the CloudWise backend and are never sent to the browser.
                </p>
              </div>

              <button
                onClick={handleConnectServer}
                disabled={submitting || !info?.configured}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 py-4 font-bold text-white transition-all hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <Loader2 size={18} className="animate-spin" />
                    Verifying with Atlas...
                  </>
                ) : (
                  <>
                    Connect Atlas
                    <ArrowRight size={18} />
                  </>
                )}
              </button>

              {!info?.configured && (
                <div className="mt-4 flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4">
                  <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-500" />
                  <p className="text-xs text-amber-200/80">
                    The backend .env is missing one or more of MONGODB_ATLAS_PUBLIC_KEY,
                    MONGODB_ATLAS_PRIVATE_KEY, MONGODB_ATLAS_PROJECT_ID. Add them to
                    backend/.env and restart CloudWise, or enter an Atlas API key below.
                  </p>
                </div>
              )}

              <button
                type="button"
                onClick={() => setShowManual((v) => !v)}
                className="mt-6 flex w-full items-center justify-center gap-2 text-sm font-semibold text-slate-400 transition-colors hover:text-slate-200"
              >
                <KeyRound size={14} />
                {showManual ? 'Hide' : 'Use'} manual API key entry
                {showManual ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>

              {showManual && (
                <form onSubmit={handleConnectManual} className="mt-4 space-y-6">
                  <div>
                    <label className="mb-2 block text-sm font-bold text-slate-300">Project ID</label>
                    <input
                      type="text"
                      value={formProjectId}
                      onChange={(e) => setFormProjectId(e.target.value)}
                      placeholder="e.g. 5f3d5b7a9b1c8a001b2c3d4e"
                      className="w-full rounded-xl border border-slate-800 bg-slate-950 p-4 font-mono text-white placeholder-slate-600 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                      required
                    />
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-bold text-slate-300">Public API Key (Client ID)</label>
                    <input
                      type="text"
                      value={formClientId}
                      onChange={(e) => setFormClientId(e.target.value)}
                      placeholder="e.g. wgkjdfsa"
                      className="w-full rounded-xl border border-slate-800 bg-slate-950 p-4 font-mono text-white placeholder-slate-600 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                      required
                    />
                  </div>

                  <div>
                    <label className="mb-2 block text-sm font-bold text-slate-300">Private API Key (Client Secret)</label>
                    <input
                      type="password"
                      value={formClientSecret}
                      onChange={(e) => setFormClientSecret(e.target.value)}
                      placeholder="••••••••••••••••"
                      className="w-full rounded-xl border border-slate-800 bg-slate-950 p-4 font-mono text-white placeholder-slate-600 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                      required
                    />
                    <p className="mt-2 text-xs text-slate-500">
                      Encrypted on the backend, never displayed again and never passed to your deployed app.
                    </p>
                  </div>

                  <button
                    type="submit"
                    disabled={submitting}
                    className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 py-4 font-bold text-white transition-all hover:bg-emerald-400 disabled:opacity-50"
                  >
                    {submitting ? (
                      <>
                        <Loader2 size={18} className="animate-spin" />
                        Verifying...
                      </>
                    ) : (
                      <>
                        Connect Atlas
                        <ArrowRight size={18} />
                      </>
                    )}
                  </button>
                </form>
              )}

              <div className="mt-8 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle size={20} className="mt-0.5 text-amber-500" />
                  <div>
                    <h4 className="text-sm font-bold text-amber-500">Permissions Note</h4>
                    <p className="mt-1 text-xs text-amber-200/80">
                      The API key needs the "Project Network Access Manager" role. Connection is
                      recorded only after Atlas confirms authentication, project access and
                      Network Access management.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ConnectAtlas;
