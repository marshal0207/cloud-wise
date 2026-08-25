import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  FolderPlus, 
  Folder, 
  Play, 
  Trash2, 
  Plus, 
  ArrowRight, 
  Shield, 
  Clock, 
  CheckCircle2, 
  Cpu, 
  Cloud, 
  X, 
  AlertCircle,
  Building2,
  Sparkles,
  Zap,
  Sliders,
  FileCode,
  Rocket
} from 'lucide-react';
import { useCloudWise, formatINR, Project } from '@/context/CloudWiseContext';

export const Projects: React.FC = () => {
  const navigate = useNavigate();
  const { 
    projects, 
    activeProject, 
    setActiveProjectById, 
    createProject, 
    deleteProject, 
    user,
    showToast
  } = useCloudWise();

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [environment, setEnvironment] = useState('Production');
  const [role, setRole] = useState<'owner' | 'editor' | 'viewer' | 'admin'>('owner');
  const [loading, setLoading] = useState(false);

  // First-time user auto route to Create Project modal
  useEffect(() => {
    if (projects.length === 0) {
      setShowCreateModal(true);
    }
  }, [projects.length]);

  const handleCloseModal = (e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    setShowCreateModal(false);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setLoading(true);
    try {
      const created = await createProject({
        name: name.trim(),
        description: description.trim(),
        environment,
        role
      });

      if (created) {
        setShowCreateModal(false);
        setName('');
        setDescription('');
        navigate('/estimation');
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to create project.', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleResumeWorkflow = (proj: Project) => {
    setActiveProjectById(proj.id);
    const routeMap: Record<string, string> = {
      estimation: '/estimation',
      recommendation: '/recommendation',
      generate: '/generate',
      deployment: '/deployment',
      optimization: '/optimization'
    };
    const targetRoute = routeMap[proj.currentStep] || '/estimation';
    navigate(targetRoute);
  };

  const handleDelete = async (e: React.MouseEvent, proj: Project) => {
    e.stopPropagation();
    if (confirm(`Are you sure you want to delete project "${proj.name}"?`)) {
      await deleteProject(proj.id);
    }
  };

  const getStepLabel = (step: string) => {
    switch (step) {
      case 'estimation':
        return { label: 'Step 1: Workload Sizing', icon: Cpu, color: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30' };
      case 'recommendation':
        return { label: 'Step 2: Cloud Matched', icon: Sparkles, color: 'text-blue-400 bg-blue-500/10 border-blue-500/30' };
      case 'generate':
        return { label: 'Step 3: Files Generated', icon: FileCode, color: 'text-violet-400 bg-violet-500/10 border-violet-500/30' };
      case 'deployment':
        return { label: 'Step 4: Provision & Deploy', icon: Rocket, color: 'text-amber-400 bg-amber-500/10 border-amber-500/30' };
      case 'optimization':
        return { label: 'Step 5: Cost Tuning', icon: Zap, color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' };
      default:
        return { label: 'Step 1: Workload Sizing', icon: Cpu, color: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30' };
    }
  };

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-6 border-b border-slate-800">
        <div className="space-y-1">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold">
            <Folder className="w-3.5 h-3.5" />
            <span>Module 2: Project Management</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-white">
            My Cloud Projects
          </h1>
          <p className="text-xs sm:text-sm text-slate-400">
            Select an existing workflow instance to resume progress or launch a new cloud advisory project.
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          className="px-5 py-3 rounded-xl bg-gradient-to-r from-cyan-400 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-xs transition-all shadow-lg shadow-cyan-500/20 flex items-center gap-2 active:scale-95 whitespace-nowrap"
        >
          <Plus size={16} />
          <span>Create New Project</span>
        </button>
      </div>

      {/* Projects List Grid */}
      {projects.length === 0 ? (
        <div className="glass-panel p-12 rounded-3xl text-center space-y-4 max-w-lg mx-auto border border-slate-800">
          <div className="w-16 h-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center mx-auto text-cyan-400">
            <FolderPlus size={32} />
          </div>
          <h3 className="text-xl font-extrabold text-white">No Active Projects Found</h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            Create your first cloud infrastructure project to start workload sizing, multi-cloud comparison, Dockerfile generation, and cost tuning.
          </p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-6 py-3.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs transition-all shadow-lg shadow-cyan-500/20 inline-flex items-center gap-2"
          >
            <Plus size={16} />
            <span>Create First Project</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((proj) => {
            const isCurrentActive = activeProject?.id === proj.id;
            const stepInfo = getStepLabel(proj.currentStep);
            const StepIcon = stepInfo.icon;
            const roleColor = proj.userRole === 'viewer' ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' : 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40';

            return (
              <motion.div
                key={proj.id}
                whileHover={{ y: -4 }}
                onClick={() => setActiveProjectById(proj.id)}
                className={`glass-card p-6 rounded-3xl flex flex-col justify-between space-y-6 cursor-pointer border transition-all ${
                  isCurrentActive
                    ? 'border-cyan-400 ring-2 ring-cyan-500/30 bg-slate-900/90 shadow-xl shadow-cyan-950/50'
                    : 'border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="space-y-4">
                  {/* Top Bar: Role & Environment */}
                  <div className="flex justify-between items-start gap-2">
                    <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${roleColor}`}>
                      Role: {proj.userRole}
                    </span>

                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] font-semibold border border-slate-700">
                      {proj.environment}
                    </span>
                  </div>

                  {/* Project Name & Description */}
                  <div>
                    <h3 className="text-lg font-bold text-white leading-snug flex items-center justify-between">
                      <span className="truncate">{proj.name}</span>
                      {isCurrentActive && (
                        <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse shrink-0 ml-2" title="Active Project" />
                      )}
                    </h3>
                    <p className="text-xs text-slate-400 pt-1 line-clamp-2 leading-relaxed">
                      {proj.description || 'No description provided'}
                    </p>
                  </div>

                  {/* Current Step Badge */}
                  <div className={`p-3 rounded-2xl border flex items-center justify-between text-xs ${stepInfo.color}`}>
                    <div className="flex items-center gap-2 font-bold">
                      <StepIcon size={16} />
                      <span>{stepInfo.label}</span>
                    </div>
                  </div>

                  {/* Pricing & Provider Summary */}
                  <div className="bg-slate-950/60 p-3.5 rounded-2xl border border-slate-800/80 space-y-1 text-xs">
                    <div className="flex justify-between text-slate-400">
                      <span>Matched Provider</span>
                      <span className="font-bold text-cyan-300">{proj.selectedRecommendation?.provider || 'AWS'}</span>
                    </div>
                    <div className="flex justify-between text-slate-400 pt-0.5">
                      <span>Monthly Spend</span>
                      <span className="font-extrabold text-white">{formatINR(proj.selectedRecommendation?.monthlyCost || 12280)}/mo</span>
                    </div>
                  </div>
                </div>

                {/* Actions Bar */}
                <div className="flex items-center gap-3 pt-4 border-t border-slate-800/80">
                  <button
                    onClick={() => handleResumeWorkflow(proj)}
                    className="flex-1 py-3 rounded-xl bg-gradient-to-r from-cyan-400 via-cyan-500 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-xs transition-all shadow-md shadow-cyan-500/20 flex items-center justify-center gap-1.5 active:scale-95"
                  >
                    <Play size={14} fill="currentColor" />
                    <span>Resume Workflow</span>
                  </button>

                  <button
                    onClick={(e) => handleDelete(e, proj)}
                    title="Delete Project"
                    className="p-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-rose-400 transition-colors"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>

              </motion.div>
            );
          })}
        </div>
      )}

      {/* Create Project Modal */}
      <AnimatePresence>
        {showCreateModal && (
          <div 
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md"
            onClick={handleCloseModal}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              onClick={(e) => e.stopPropagation()}
              className="glass-panel max-w-lg w-full p-6 sm:p-8 rounded-3xl space-y-6 border border-slate-700 shadow-2xl relative"
            >
              <button
                type="button"
                onClick={handleCloseModal}
                aria-label="Close modal"
                className="absolute top-5 right-5 text-slate-400 hover:text-white p-1.5 rounded-lg bg-slate-900 border border-slate-800 cursor-pointer z-10"
              >
                <X size={18} />
              </button>

              <div className="space-y-1">
                <div className="inline-flex items-center gap-1.5 text-xs font-bold text-cyan-400 uppercase tracking-wider">
                  <FolderPlus size={14} />
                  <span>Module 2: Project Setup</span>
                </div>
                <h3 className="text-2xl font-extrabold text-white">Create New Cloud Project</h3>
                <p className="text-xs text-slate-400">
                  Initialize a new workload instance to model specs, compare multi-cloud costs, generate deployment code, and tune spend.
                </p>
              </div>

              <form onSubmit={handleCreateSubmit} className="space-y-4">
                
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-300">Project Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Payment Gateway Microservice"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-3 text-xs text-white focus:outline-none focus:border-cyan-400"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-300">Project Description</label>
                  <textarea
                    rows={3}
                    placeholder="e.g. Production cluster workload for real-time payment transaction processing..."
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-2.5 text-xs text-white focus:outline-none focus:border-cyan-400"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-slate-300">Environment</label>
                    <select
                      value={environment}
                      onChange={(e) => setEnvironment(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-cyan-400"
                    >
                      <option value="Production">Production</option>
                      <option value="Staging">Staging</option>
                      <option value="QA / Dev">QA / Dev</option>
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-slate-300">Your Access Role (RBAC)</label>
                    <select
                      value={role}
                      onChange={(e) => setRole(e.target.value as any)}
                      className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-cyan-400"
                    >
                      <option value="owner">Owner (Full Read/Write/Delete)</option>
                      <option value="editor">Editor (Can edit/deploy)</option>
                      <option value="viewer">Viewer (Read-only Gated)</option>
                      <option value="admin">Admin (Full Control)</option>
                    </select>
                  </div>
                </div>

                <div className="pt-2 flex gap-3">
                  <button
                    type="submit"
                    disabled={loading}
                    className="flex-1 py-3.5 rounded-xl bg-gradient-to-r from-cyan-400 via-cyan-500 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-xs transition-all shadow-lg shadow-cyan-500/20 flex items-center justify-center gap-2 active:scale-98 disabled:opacity-50"
                  >
                    <Sparkles size={16} />
                    <span>{loading ? 'Initializing Project...' : 'Initialize Project Workflow'}</span>
                  </button>

                  <button
                    type="button"
                    onClick={handleCloseModal}
                    className="px-4 py-3.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-300 font-semibold text-xs hover:bg-slate-800 cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>

              </form>

            </motion.div>
          </div>
        )}
      </AnimatePresence>

    </div>
  );
};
