import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  FileCode, 
  Github, 
  Download, 
  Copy, 
  Check, 
  ArrowRight, 
  Sparkles, 
  Terminal, 
  ShieldCheck, 
  X, 
  RefreshCw,
  GitBranch,
  Layers,
  Code,
  Folder,
  FileText,
  AlertCircle,
  CheckCircle2,
  ExternalLink
} from 'lucide-react';
import { useCloudWise, formatINR } from '@/context/CloudWiseContext';

export const GenerateFiles: React.FC = () => {
  const navigate = useNavigate();
  const { 
    estimation, 
    selectedRecommendation, 
    githubRepo, 
    connectGitHub, 
    updateActiveProject,
    showToast,
    activeProject
  } = useCloudWise();

  const [activeTab, setActiveTab] = useState<'dockerfile' | 'cicd' | 'compose' | 'vercel' | 'render'>('dockerfile');
  const [copied, setCopied] = useState(false);
  const [showGithubModal, setShowGithubModal] = useState(false);
  const [repoInput, setRepoInput] = useState(githubRepo?.name || activeProject?.githubRepo?.name || '');
  const [connecting, setConnecting] = useState(false);
  const [syncedStatus, setSyncedStatus] = useState(githubRepo?.synced || activeProject?.githubRepo?.synced || false);
  const [oauthStarting, setOauthStarting] = useState(false);
  const [loadingRepositories, setLoadingRepositories] = useState(false);
  const [pushingFiles, setPushingFiles] = useState(false);
  const [inspectionLoading, setInspectionLoading] = useState(false);
  const [githubError, setGithubError] = useState('');
  
  const [repoTree, setRepoTree] = useState<Array<{ path: string; type: string; size?: number }>>([]);
  const [detectedInfo, setDetectedInfo] = useState<{
    technology?: string;
    dockerfilePreserved?: boolean;
    composePreserved?: boolean;
    cicdPreserved?: boolean;
    port?: number;
  }>({});

  const [generatedFiles, setGeneratedFiles] = useState<Record<string, string> | null>(null);
  const [repositories, setRepositories] = useState<Array<{
    id: number;
    name: string;
    full_name: string;
    private: boolean;
    default_branch: string;
  }>>([]);
  const [searchParams, setSearchParams] = useSearchParams();

  const providerName = selectedRecommendation.provider;

  const loadRepositories = async () => {
    setLoadingRepositories(true);
    setGithubError('');
    try {
      const token = localStorage.getItem('cloudwise_token');
      const response = await fetch('/api/github/repos', {
        headers: {
          Authorization: token ? `Bearer ${token}` : '',
        },
        credentials: 'include',
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || 'Unable to retrieve GitHub repositories.');
      }
      setRepositories(data.data || []);
      if (data.data && data.data.length > 0 && !repoInput) {
        setRepoInput(data.data[0].full_name);
      }
    } catch (error: any) {
      setGithubError(error.message || 'Unable to retrieve GitHub repositories.');
    } finally {
      setLoadingRepositories(false);
    }
  };

  useEffect(() => {
    if (searchParams.get('github') === 'connected') {
      setShowGithubModal(true);
      setSyncedStatus(false);
      loadRepositories();
      searchParams.delete('github');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // Keep synced status up-to-date when activeProject changes
  useEffect(() => {
    if (activeProject?.githubRepo?.name) {
      setSyncedStatus(true);
      setRepoInput((prev) => prev || activeProject.githubRepo!.name);
    }
  }, [activeProject?.githubRepo?.name]);

  const handleStartGithubOAuth = async () => {
    setOauthStarting(true);
    setGithubError('');
    try {
      const token = localStorage.getItem('cloudwise_token');
      const response = await fetch('/api/github/oauth/start', {
        headers: {
          Authorization: token ? `Bearer ${token}` : '',
        },
        credentials: 'include',
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || 'Unable to start GitHub authorization.');
      }
      window.location.assign(data.authorizationUrl);
    } catch (error: any) {
      setGithubError(error.message || 'Unable to start GitHub authorization.');
      setOauthStarting(false);
    }
  };

  const getActiveCode = () => {
    if (generatedFiles) {
      switch (activeTab) {
        case 'dockerfile':
          return generatedFiles['Dockerfile'] || '# Dockerfile not generated';
        case 'compose':
          return generatedFiles['docker-compose.yml'] || '# docker-compose.yml not generated';
        case 'cicd':
          return generatedFiles['.github/workflows/aws-deploy.yml'] || generatedFiles['.github/workflows/deploy.yml'] || '# CI/CD pipeline not generated';
        case 'vercel':
          return generatedFiles['vercel.json'] || '# vercel.json configuration';
        case 'render':
          return generatedFiles['render.yaml'] || '# render.yaml configuration';
      }
    }

    if (activeTab === 'dockerfile') {
      return `# Auto-generated Dockerfile by CloudWise
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
EXPOSE 3000
CMD ["npm", "start"]`;
    }
    if (activeTab === 'compose') {
      return `version: '3.8'
services:
  app:
    build: .
    ports:
      - "3000:3000"
    restart: unless-stopped`;
    }
    if (activeTab === 'cicd') {
      return `name: AWS EC2 / ECS CloudWise Auto-Deployment
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t cloudwise-app .`;
    }
    if (activeTab === 'vercel') {
      return `{\n  "version": 2,\n  "builds": [{ "src": "package.json", "use": "@vercel/node" }]\n}`;
    }
    return `services:\n  - type: web\n    name: cloudwise-app\n    env: docker\n    dockerfilePath: ./Dockerfile`;
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(getActiveCode());
    setCopied(true);
    showToast('Snippet copied to clipboard!', 'success');
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const filenames: Record<string, string> = {
      dockerfile: 'Dockerfile',
      cicd: 'aws-deploy.yml',
      compose: 'docker-compose.yml',
      vercel: 'vercel.json',
      render: 'render.yaml'
    };
    const content = getActiveCode();
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filenames[activeTab];
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    showToast(`Downloaded ${filenames[activeTab]}`, 'success');
  };

  const handleConnectSubmit = async (e?: React.FormEvent, repoToSelect?: string) => {
    if (e) e.preventDefault();
    const repoName = (repoToSelect || repoInput).trim();
    if (!repoName) return;

    setConnecting(true);
    setGithubError('');
    try {
      const success = await connectGitHub(repoName);
      if (success) {
        setRepoInput(repoName);
        setShowGithubModal(false);
        setSyncedStatus(true);
        // Small delay to allow backend DB write to complete before inspect
        await new Promise((r) => setTimeout(r, 500));
        void handleInspectRepository(repoName);
      } else {
        setGithubError('Failed to link repository. Please try again.');
      }
    } catch (err: any) {
      setGithubError(err?.message || 'Failed to link repository. Please try again.');
    } finally {
      setConnecting(false);
    }
  };

  const handleInspectRepository = async (overrideRepoName?: string) => {
    const targetRepo = overrideRepoName || repoInput || activeProject?.githubRepo?.name;
    if (!targetRepo) {
      setGithubError('Connect and select a GitHub repository before inspecting it.');
      setShowGithubModal(true);
      return;
    }

    setInspectionLoading(true);
    setGithubError('');
    try {
      const token = localStorage.getItem('cloudwise_token');
      const inspectUrl = activeProject?.id 
        ? `/api/projects/${activeProject.id}/github/inspect`
        : `/api/projects/default/github/inspect`;

      const inspectResponse = await fetch(inspectUrl, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '' 
        },
        // Pass repo name as fallback in case the DB hasn't been updated yet
        body: JSON.stringify({ repoName: targetRepo }),
      });
      const inspectData = await inspectResponse.json();
      if (!inspectResponse.ok || !inspectData.success) {
        throw new Error(inspectData.error || 'Unable to inspect the selected repository.');
      }

      setRepoTree(inspectData.data.tree || []);

      const generateResponse = await fetch('/api/deployment/generate-files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: providerName, files: inspectData.data.files }),
      });
      const generateData = await generateResponse.json();
      if (!generateResponse.ok || !generateData.success) {
        throw new Error(generateData.error || 'Unable to generate deployment files.');
      }

      setDetectedInfo({
        technology: generateData.data.technology?.technology || inspectData.data.technology?.technology,
        dockerfilePreserved: generateData.data.dockerfile_preserved,
        composePreserved: generateData.data.compose_preserved,
        cicdPreserved: generateData.data.cicd_preserved,
        port: generateData.data.port,
      });

      setGeneratedFiles(generateData.data.files);
      showToast(`Scanned ${inspectData.data.tree?.length || 0} repository files from ${targetRepo}.`, 'success');
    } catch (error: any) {
      setGithubError(error.message || 'Repository inspection failed.');
      showToast(error.message || 'Repository inspection failed.', 'error');
    } finally {
      setInspectionLoading(false);
    }
  };

  const handleProceedToDeployment = () => {
    updateActiveProject({ currentStep: 'deployment' });
    navigate('/deployment');
  };

  const handlePushGeneratedFiles = async () => {
    if (!activeProject || !syncedStatus) {
      setGithubError('Connect and select a GitHub repository before pushing files.');
      setShowGithubModal(true);
      return;
    }

    setPushingFiles(true);
    setGithubError('');
    try {
      const token = localStorage.getItem('cloudwise_token');
      const response = await fetch(`/api/projects/${activeProject.id}/github/push`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          files: generatedFiles || {
            Dockerfile: getActiveCode(),
            'docker-compose.yml': getActiveCode(),
            '.github/workflows/aws-deploy.yml': getActiveCode(),
          },
          commit_message: 'Add CloudWise deployment configuration',
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || 'Unable to push generated files.');
      }
      showToast(`Files committed to ${data.data.repository}.`, 'success');
    } catch (error: any) {
      setGithubError(error.message || 'Unable to push generated files.');
      showToast(error.message || 'Unable to push generated files.', 'error');
    } finally {
      setPushingFiles(false);
    }
  };

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      
      {/* Header */}
      <div className="text-center space-y-3 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-violet-500/10 border border-violet-500/30 text-violet-300 text-xs font-semibold">
          <FileCode className="w-3.5 h-3.5" />
          <span>Step 3: GitHub Repo Analyzer & Smart File Generator</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white">
          Repository File Inspection & Infrastructure Code
        </h1>
        <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
          CloudWise inspects every file in your GitHub repository. If a Dockerfile exists, CloudWise preserves it and generates matching docker-compose & AWS/Vercel/Render pipeline files.
        </p>
      </div>

      {/* GitHub Integration Banner */}
      <div className="glass-panel p-6 rounded-3xl border border-violet-500/30 bg-violet-950/10 flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-slate-900 border border-slate-700 flex items-center justify-center text-white shrink-0">
            <Github size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-white">GitHub Repository Sync</h3>
              {syncedStatus || activeProject?.githubRepo?.name ? (
                <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 text-xs font-bold border border-emerald-500/40 flex items-center gap-1">
                  <ShieldCheck size={12} /> Connected
                </span>
              ) : (
                <span className="px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 text-xs font-bold border border-amber-500/40">
                  Not Linked
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 pt-0.5">
              {activeProject?.githubRepo?.name || repoInput 
                ? `Linked repository: ${activeProject?.githubRepo?.name || repoInput}`
                : 'Link your GitHub repository to scan files and generate deployment artifacts.'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setShowGithubModal(true);
              loadRepositories();
            }}
            className="px-6 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-white font-bold text-xs transition-colors flex items-center gap-2"
          >
            <Github size={16} />
            <span>{syncedStatus || activeProject?.githubRepo ? 'Change GitHub Repo' : 'Connect GitHub Repo'}</span>
          </button>
          
          <button
            onClick={() => handleInspectRepository()}
            disabled={inspectionLoading}
            className="px-5 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {inspectionLoading ? <RefreshCw size={16} className="animate-spin" /> : <GitBranch size={16} />}
            <span>{inspectionLoading ? 'Scanning Tree...' : 'Scan Repo Tree'}</span>
          </button>
        </div>
      </div>

      {/* Detection Banner */}
      {detectedInfo.dockerfilePreserved && (
        <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-3 font-semibold">
          <CheckCircle2 size={20} className="text-emerald-400 shrink-0" />
          <div>
            <span className="font-extrabold text-sm block text-emerald-300">Existing Dockerfile Preserved!</span>
            <span className="text-emerald-200/90 text-xs">
              CloudWise detected your existing Dockerfile (Port {detectedInfo.port || 3000}). Preserved original Dockerfile instructions and generated matching <code className="text-white">docker-compose.yml</code> and AWS/Vercel/Render CI/CD files.
            </span>
          </div>
        </div>
      )}

      {/* Grid: Repo File Tree + Code Viewer */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Repo File Tree (1 Col) */}
        <div className="glass-panel p-5 rounded-3xl border border-slate-800 space-y-4 max-h-[550px] overflow-y-auto">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Folder className="w-4 h-4 text-cyan-400" />
              <span>Full Repository File Tree</span>
            </h3>
            <span className="text-[10px] text-slate-400 font-mono">
              {repoTree.length > 0 ? `${repoTree.length} items` : 'No repo loaded'}
            </span>
          </div>

          {repoTree.length === 0 ? (
            <div className="text-center py-10 text-slate-500 text-xs space-y-2">
              <GitBranch size={28} className="mx-auto text-slate-600" />
              <p>Click "Connect GitHub Repo" & "Scan Repo Tree" to view all repository files.</p>
            </div>
          ) : (
            <div className="space-y-1 font-mono text-xs">
              {repoTree.map((item, idx) => (
                <div 
                  key={idx} 
                  className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-slate-900 transition-colors ${
                    item.path.toLowerCase().includes('dockerfile') ? 'text-cyan-300 font-bold bg-cyan-950/30' : 'text-slate-300'
                  }`}
                >
                  {item.type === 'folder' ? (
                    <Folder size={14} className="text-amber-400 shrink-0" />
                  ) : (
                    <FileText size={14} className="text-slate-400 shrink-0" />
                  )}
                  <span className="truncate">{item.path}</span>
                  {item.path.toLowerCase().includes('dockerfile') && (
                    <span className="ml-auto text-[9px] px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                      Dockerfile
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Tabbed Code Viewer (2 Cols) */}
        <div className="lg:col-span-2 glass-panel rounded-3xl border border-slate-800 overflow-hidden flex flex-col">
          
          {/* Header & Tabs */}
          <div className="bg-slate-900/90 px-6 py-4 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
            <div className="flex bg-slate-950 p-1 rounded-2xl border border-slate-800 text-xs font-semibold overflow-x-auto">
              <button
                onClick={() => setActiveTab('dockerfile')}
                className={`px-3.5 py-2 rounded-xl transition-all flex items-center gap-1.5 ${
                  activeTab === 'dockerfile' ? 'bg-cyan-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'
                }`}
              >
                <Code size={14} />
                <span>Dockerfile</span>
              </button>

              <button
                onClick={() => setActiveTab('compose')}
                className={`px-3.5 py-2 rounded-xl transition-all flex items-center gap-1.5 ${
                  activeTab === 'compose' ? 'bg-cyan-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'
                }`}
              >
                <Layers size={14} />
                <span>docker-compose.yml</span>
              </button>

              <button
                onClick={() => setActiveTab('cicd')}
                className={`px-3.5 py-2 rounded-xl transition-all flex items-center gap-1.5 ${
                  activeTab === 'cicd' ? 'bg-cyan-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'
                }`}
              >
                <GitBranch size={14} />
                <span>AWS CI/CD</span>
              </button>

              <button
                onClick={() => setActiveTab('vercel')}
                className={`px-3.5 py-2 rounded-xl transition-all flex items-center gap-1.5 ${
                  activeTab === 'vercel' ? 'bg-cyan-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'
                }`}
              >
                <span>vercel.json</span>
              </button>

              <button
                onClick={() => setActiveTab('render')}
                className={`px-3.5 py-2 rounded-xl transition-all flex items-center gap-1.5 ${
                  activeTab === 'render' ? 'bg-cyan-500 text-slate-950 font-bold shadow' : 'text-slate-400 hover:text-white'
                }`}
              >
                <span>render.yaml</span>
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleCopy}
                className="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 font-semibold text-xs flex items-center gap-1.5"
              >
                {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                <span>{copied ? 'Copied!' : 'Copy'}</span>
              </button>

              <button
                onClick={handleDownload}
                className="px-3 py-1.5 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 font-semibold text-xs flex items-center gap-1.5"
              >
                <Download size={14} />
                <span>Download</span>
              </button>
            </div>
          </div>

          {/* Code Body */}
          <div className="p-6 bg-slate-950 font-mono text-xs text-slate-300 leading-relaxed overflow-x-auto min-h-[380px] max-h-[500px]">
            <pre className="text-slate-200">
              <code>{getActiveCode()}</code>
            </pre>
          </div>
        </div>

      </div>

      {/* Action Bar */}
      <div className="glass-panel p-6 rounded-3xl text-center space-y-4 max-w-xl mx-auto border border-cyan-500/20">
        <h4 className="text-base font-bold text-white">Ready for Multi-Cloud Deployment?</h4>
        <p className="text-xs text-slate-400">
          Generated artifacts ready. Proceed to launch live deployment pipeline targeting <strong className="text-cyan-300">Vercel</strong>, <strong className="text-cyan-300">Render</strong>, or <strong className="text-cyan-300">AWS Free Tier</strong>.
        </p>
        <div className="flex flex-col sm:flex-row items-center gap-3">
          <button
            onClick={handleProceedToDeployment}
            className="flex-1 py-4 rounded-xl bg-gradient-to-r from-cyan-400 via-cyan-500 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-sm transition-all shadow-xl shadow-cyan-500/20 flex items-center justify-center gap-2 group"
          >
            <span>Proceed to Deployment Page</span>
            <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
          </button>
          
          <button
            onClick={handlePushGeneratedFiles}
            disabled={pushingFiles}
            className="px-6 py-4 rounded-xl bg-violet-500/15 hover:bg-violet-500/25 border border-violet-500/40 text-violet-200 font-bold text-xs transition-all flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {pushingFiles ? <RefreshCw size={16} className="animate-spin" /> : <Github size={16} />}
            <span>Push to GitHub</span>
          </button>
        </div>
      </div>

      {/* GitHub OAuth Modal */}
      <AnimatePresence>
        {showGithubModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="glass-panel max-w-lg w-full p-6 sm:p-8 rounded-3xl space-y-6 border border-slate-700 shadow-2xl relative"
            >
              <button
                onClick={() => setShowGithubModal(false)}
                className="absolute top-5 right-5 text-slate-400 hover:text-white p-1 rounded-lg bg-slate-900 border border-slate-800"
              >
                <X size={18} />
              </button>

              <div className="space-y-1">
                <div className="w-10 h-10 rounded-xl bg-slate-900 border border-slate-700 flex items-center justify-center text-white mb-2">
                  <Github size={20} />
                </div>
                <h3 className="text-xl font-extrabold text-white">Connect GitHub Repository</h3>
                <p className="text-xs text-slate-400">
                  Select your repository to inspect all files and commit Dockerfile and CI/CD files.
                </p>
              </div>

              {githubError && (
                <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
                  {githubError}
                </div>
              )}

              <button
                type="button"
                onClick={handleStartGithubOAuth}
                disabled={oauthStarting}
                className="w-full py-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-white font-bold text-xs transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {oauthStarting ? <RefreshCw size={16} className="animate-spin" /> : <Github size={16} />}
                <span>{oauthStarting ? 'Opening GitHub OAuth...' : 'Authorize GitHub Account'}</span>
              </button>

              {loadingRepositories && (
                <p className="text-xs text-cyan-300 flex items-center gap-2">
                  <RefreshCw size={14} className="animate-spin" /> Loading repositories...
                </p>
              )}

              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-300">Repository Name (owner/repo)</label>
                  <input
                    type="text"
                    value={repoInput}
                    onChange={(e) => setRepoInput(e.target.value)}
                    placeholder="e.g. Tirth-22/doctor-appointment-management-system"
                    className="w-full bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-xs text-white focus:border-cyan-400"
                  />
                </div>

                {repositories.length > 0 && (
                  <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                    <label className="text-[11px] font-bold text-slate-400">
                      Click any repository to select &amp; link it:
                    </label>
                    <div className="space-y-1.5">
                      {repositories.map((repo) => {
                        const isSelected = repoInput === repo.full_name;
                        const isLinking = connecting && repoInput === repo.full_name;
                        return (
                          <button
                            key={repo.id}
                            type="button"
                            disabled={connecting}
                            onClick={() => {
                              setRepoInput(repo.full_name);
                              void handleConnectSubmit(undefined, repo.full_name);
                            }}
                            className={`w-full p-3 rounded-xl text-xs flex items-center justify-between border cursor-pointer transition-all text-left disabled:cursor-wait ${
                              isSelected
                                ? 'bg-cyan-500/20 border-cyan-400 text-white font-bold ring-1 ring-cyan-500/50 shadow-md'
                                : 'bg-slate-900/80 border-slate-800 text-slate-300 hover:border-cyan-500/50 hover:bg-slate-800/80'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0 pr-2">
                              {isLinking ? (
                                <RefreshCw size={15} className="text-cyan-400 shrink-0 animate-spin" />
                              ) : isSelected ? (
                                <CheckCircle2 size={15} className="text-cyan-400 shrink-0" />
                              ) : (
                                <Github size={15} className="text-slate-500 shrink-0" />
                              )}
                              <span className="truncate">{repo.full_name}</span>
                              {repo.private && (
                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 shrink-0">
                                  Private
                                </span>
                              )}
                            </div>

                            <span className={`ml-2 px-2.5 py-1 rounded-lg font-bold text-[10px] shrink-0 whitespace-nowrap ${
                              isLinking
                                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                                : isSelected
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : 'bg-cyan-500/15 text-cyan-400 border border-cyan-500/30'
                            }`}>
                              {isLinking ? 'Linking...' : isSelected ? '✓ Linked' : 'Select & Link'}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                <button
                  type="button"
                  onClick={(e) => handleConnectSubmit(e)}
                  disabled={connecting}
                  className="w-full py-3.5 rounded-xl bg-gradient-to-r from-cyan-400 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-xs transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {connecting ? <RefreshCw size={16} className="animate-spin" /> : <Check size={16} />}
                  <span>{connecting ? 'Linking Repository...' : 'Confirm Repository Selection'}</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

    </div>
  );
};
