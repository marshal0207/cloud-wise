import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Github, Search, ShieldCheck, ArrowRight, CheckCircle2, 
  AlertCircle, LogOut, RefreshCw, Zap
} from 'lucide-react';
import { useCloudWise } from '@/context/CloudWiseContext';

export const Projects: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, connectGitHub, showToast } = useCloudWise();

  const [isConnected, setIsConnected] = useState(false);
  const [loadingRepos, setLoadingRepos] = useState(true);
  const [repositories, setRepositories] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState('');
  const [oauthStarting, setOauthStarting] = useState(false);

  useEffect(() => {
    const oauthResult = searchParams.get('github');
    if (oauthResult === 'connected') {
      showToast('GitHub account connected successfully!', 'success');
      searchParams.delete('github');
      setSearchParams(searchParams, { replace: true });
    } else if (oauthResult === 'error') {
      setError('GitHub authorization failed. Please try again.');
      searchParams.delete('github');
      searchParams.delete('github_detail');
      setSearchParams(searchParams, { replace: true });
    }
    loadRepositories();
  }, [searchParams, setSearchParams]);

  const loadRepositories = async () => {
    setLoadingRepos(true);
    setError('');
    try {
      const token = localStorage.getItem('cloudwise_token');
      const response = await fetch('/api/github/repos', {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
        credentials: 'include',
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.success) {
        setIsConnected(false);
        setRepositories([]);
      } else {
        setIsConnected(true);
        setRepositories(data.data || []);
      }
    } catch (err: any) {
      setIsConnected(false);
      setRepositories([]);
    } finally {
      setLoadingRepos(false);
    }
  };

  const handleStartGithubOAuth = async () => {
    setOauthStarting(true);
    setError('');
    try {
      const token = localStorage.getItem('cloudwise_token');
      if (!token) throw new Error('Please sign in to CloudWise before connecting your GitHub account.');
      const response = await fetch('/api/github/oauth/start', {
        headers: { Authorization: `Bearer ${token}` },
        credentials: 'include',
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.success || !data?.authorizationUrl) {
        throw new Error('Unable to start GitHub authorization.');
      }
      window.location.assign(data.authorizationUrl);
    } catch (err: any) {
      setError(err.message || 'Unable to start GitHub authorization.');
      setOauthStarting(false);
    }
  };

  const handleContinue = async () => {
    if (!selectedRepo) return;
    setConnecting(true);
    setError('');
    try {
      const { projectId, error: connectErr } = await connectGitHub(selectedRepo);
      if (projectId) {
        navigate('/estimation');
      } else {
        setError(connectErr || 'Failed to link repository.');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to link repository.');
    } finally {
      setConnecting(false);
    }
  };

  const filteredRepos = repositories.filter(r => 
    r.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
    r.full_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="w-full space-y-8 animate-in fade-in duration-500 max-w-5xl mx-auto px-4 sm:px-6">
      
      {/* ── HEADER ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-white/5 pb-6">
        <div>
          <h1 className="text-3xl font-black text-white tracking-tight">Projects & GitHub</h1>
          <p className="text-sm text-slate-400 mt-1 max-w-xl">
            Select a repository to begin the deployment analysis and cost optimization workflow.
          </p>
        </div>
        <div>
          {isConnected ? (
            <div className="status-healthy px-3 py-1.5 text-xs font-bold rounded-full flex items-center gap-1.5 border">
              <ShieldCheck size={14} /> GitHub Connected
            </div>
          ) : (
            <div className="status-idle px-3 py-1.5 text-xs font-bold rounded-full flex items-center gap-1.5 border">
              GitHub Disconnected
            </div>
          )}
        </div>
      </div>

      {error && (
        <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="p-4 rounded-xl status-failed border text-sm flex items-center gap-3">
          <AlertCircle size={16} className="shrink-0" />
          <span className="font-medium">{error}</span>
        </motion.div>
      )}

      {/* ── MAIN CONTENT ────────────────────────────────────────────────── */}
      {!isConnected && !loadingRepos ? (
        <motion.div 
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          className="glass-card rounded-[2rem] p-12 sm:p-16 flex flex-col items-center justify-center text-center space-y-6 relative overflow-hidden group mt-10"
        >
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(16,185,129,0.1),transparent_50%)] pointer-events-none" />
          
          <div className="w-20 h-20 rounded-full bg-[#05080D] border border-white/10 flex items-center justify-center text-white shadow-xl shadow-emerald-500/10 relative">
            <div className="absolute inset-0 rounded-full border border-emerald-500/30 animate-[spin_4s_linear_infinite]" />
            <Github size={32} />
          </div>

          <div className="space-y-2 max-w-sm">
            <h2 className="text-2xl font-bold text-white">Connect GitHub</h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              CloudWise needs access to your repositories to analyze your stack and generate Docker configuration files.
            </p>
          </div>

          <button
            onClick={handleStartGithubOAuth}
            disabled={oauthStarting}
            className="btn-primary mt-4"
          >
            {oauthStarting ? <RefreshCw size={16} className="animate-spin" /> : <Github size={16} />}
            <span>{oauthStarting ? 'Connecting...' : 'Authorize GitHub'}</span>
          </button>
        </motion.div>

      ) : loadingRepos ? (
        <div className="py-24 flex flex-col items-center justify-center space-y-4">
          <RefreshCw size={24} className="animate-spin text-emerald-400" />
          <p className="text-sm text-slate-400 font-medium">Syncing GitHub repositories...</p>
        </div>
      ) : (
        <div className="space-y-8">
          
          {/* Account Card */}
          <motion.div 
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            className="cw-card p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
          >
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center text-slate-300">
                <Github size={20} />
              </div>
              <div>
                <h3 className="text-white font-bold text-base">{user?.name || 'GitHub User'}</h3>
                <p className="text-slate-400 text-[11px] font-medium flex items-center gap-1.5 uppercase tracking-wider mt-0.5">
                  <span className="pulse-dot"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /></span>
                  Connected via OAuth
                </p>
              </div>
            </div>
            <button 
              onClick={() => { setIsConnected(false); setRepositories([]); }}
              className="btn-ghost"
            >
              <LogOut size={14} /> Disconnect
            </button>
          </motion.div>

          {/* Repositories Grid */}
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <FolderPlus size={18} className="text-emerald-400" /> Repository Catalog
              </h2>
              <div className="relative w-full sm:w-72">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input 
                  type="text"
                  placeholder="Search repositories..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="cw-input pl-10"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredRepos.length > 0 ? (
                filteredRepos.map((repo) => {
                  const isSelected = selectedRepo === repo.full_name;
                  return (
                    <motion.div
                      key={repo.id}
                      whileHover={{ y: -2 }}
                      onClick={() => setSelectedRepo(repo.full_name)}
                      className={`relative p-5 cursor-pointer transition-all duration-300 flex flex-col justify-between min-h-[140px] overflow-hidden ${
                        isSelected 
                          ? 'cw-card border-emerald-500/50 shadow-lg shadow-emerald-500/10 bg-emerald-950/10 glow-emerald' 
                          : 'cw-card-hover'
                      }`}
                    >
                      {isSelected && (
                        <div className="absolute top-0 right-0 p-3">
                          <CheckCircle2 size={16} className="text-emerald-400" />
                        </div>
                      )}
                      
                      <div>
                        <div className="flex items-center gap-2 text-slate-400 mb-2">
                          <Github size={14} />
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800/50">
                            {repo.default_branch || 'main'}
                          </span>
                        </div>
                        <h3 className={`font-bold text-[15px] truncate pr-6 ${isSelected ? 'text-emerald-300' : 'text-white'}`}>
                          {repo.name}
                        </h3>
                        <p className="text-[11px] text-slate-500 mt-1 truncate">
                          {repo.full_name}
                        </p>
                      </div>

                      <div className="mt-4 pt-4 border-t border-slate-800/60 flex items-center justify-between">
                        <span className="text-[10px] text-emerald-400/80 flex items-center gap-1 font-semibold uppercase tracking-wider">
                          <Zap size={10} /> Compatible
                        </span>
                        {isSelected ? (
                          <span className="text-[11px] font-bold text-emerald-400">SELECTED</span>
                        ) : (
                          <span className="text-[11px] font-bold text-slate-500 hover:text-white transition-colors">
                            SELECT →
                          </span>
                        )}
                      </div>
                    </motion.div>
                  );
                })
              ) : (
                <div className="col-span-full py-16 text-center border border-dashed border-white/10 rounded-2xl bg-white/[0.02]">
                  <p className="text-slate-500 text-sm">No repositories found matching "{searchQuery}"</p>
                </div>
              )}
            </div>
          </div>
          
          {/* Action Bar */}
          <AnimatePresence>
            {selectedRepo && (
              <motion.div
                initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }}
                className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 w-[96%] max-w-3xl"
              >
                <div className="glass-panel border-emerald-500/30 p-3 rounded-2xl shadow-2xl flex items-center justify-between gap-4">
                  <div className="px-3 min-w-0">
                    <p className="text-[10px] text-emerald-400 font-bold uppercase tracking-widest">Active Selection</p>
                    <p className="text-sm text-white font-bold truncate">{selectedRepo}</p>
                  </div>
                  <button
                    onClick={handleContinue}
                    disabled={connecting}
                    className="btn-primary shrink-0"
                  >
                    {connecting ? <RefreshCw size={16} className="animate-spin" /> : <ArrowRight size={16} />}
                    <span>{connecting ? 'Processing...' : 'Run Estimation'}</span>
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

        </div>
      )}
    </div>
  );
};
