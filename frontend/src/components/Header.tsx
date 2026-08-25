import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Cloud, ShieldCheck, Sparkles, User, LogOut } from 'lucide-react';
import { useCloudWise, formatINR } from '@/context/CloudWiseContext';

export const Header: React.FC = () => {
  const location = useLocation();
  const { deployment, effectiveMonthlyCost, user, logoutUser, activeProject } = useCloudWise();

  const getWorkflowBadge = () => {
    switch (location.pathname) {
      case '/':
        return { label: 'Platform Overview', step: 'Start Workflow' };
      case '/projects':
        return { label: 'Module 2', step: 'My Projects' };
      case '/estimation':
        return { label: 'Step 1 of 5', step: 'Resource Sizing' };
      case '/recommendation':
        return { label: 'Step 2 of 5', step: 'Cloud Comparison' };
      case '/generate':
        return { label: 'Step 3 of 5', step: 'Files & GitHub Sync' };
      case '/deployment':
        return { label: 'Step 4 of 5', step: 'Provision & Deploy' };
      case '/optimization':
        return { label: 'Step 5 of 5', step: 'Cost Tuning' };
      case '/auth':
        return { label: 'Account Portal', step: 'Sign In / Register' };
      default:
        return { label: 'CloudWise', step: 'Resource Intelligence' };
    }
  };

  const badge = getWorkflowBadge();

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-800/80 bg-slate-950/70 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        
        {/* Brand Logo */}
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-indigo-600 p-0.5 shadow-lg shadow-cyan-500/20 group-hover:shadow-cyan-500/40 transition-all duration-300">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <Cloud className="w-5 h-5 text-cyan-400 group-hover:scale-110 transition-transform duration-300" />
            </div>
          </div>
          <div className="flex flex-col">
            <span className="text-lg font-bold tracking-tight text-white flex items-center gap-1.5">
              CloudWise
            </span>
            <span className="text-[10px] text-slate-400 tracking-wider uppercase font-medium">Resource Intelligence</span>
          </div>
        </Link>

        {/* Dynamic Workflow Indicator */}
        <div className="hidden sm:flex items-center gap-3">
          <div className="px-3 py-1 rounded-full bg-slate-900/90 border border-slate-800 flex items-center gap-2 text-xs">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
            <span className="text-slate-400 font-medium">{badge.label}:</span>
            <span className="text-cyan-300 font-semibold">{badge.step}</span>
          </div>

          {activeProject && (
            <Link to="/projects" className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs">
              <span className="text-slate-400 text-[10px]">Project:</span>
              <span className="text-white font-bold max-w-[120px] truncate">{activeProject.name}</span>
              <span className="px-1.5 py-0.2 rounded bg-cyan-500/20 text-cyan-300 text-[10px] font-bold uppercase">
                {activeProject.userRole}
              </span>
            </Link>
          )}

          {deployment.status === 'deployed' && (
            <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Live Cluster Active</span>
            </div>
          )}
        </div>

        {/* Actions / Live Cost & User Account */}
        <div className="flex items-center gap-3">
          
          <div className="hidden md:flex flex-col items-end text-xs">
            <span className="text-slate-400 text-[11px]">Est. Monthly Cost</span>
            <span className="font-bold text-cyan-400 flex items-center gap-1 text-sm">
              {formatINR(effectiveMonthlyCost)}/mo
            </span>
          </div>

          {/* User Auth Portal Entry */}
          {user ? (
            <div className="flex items-center gap-2">
              <div className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 flex items-center gap-2 text-xs">
                <User size={14} className="text-cyan-400" />
                <span className="font-bold text-white max-w-[100px] truncate">{user.name}</span>
              </div>
              <button
                onClick={logoutUser}
                title="Sign Out"
                className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-rose-400 transition-colors"
              >
                <LogOut size={16} />
              </button>
            </div>
          ) : (
            <Link
              to="/auth"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold transition-colors"
            >
              <User size={14} className="text-cyan-400" />
              <span>Sign In</span>
            </Link>
          )}

          <Link
            to="/projects"
            className="hidden sm:flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-semibold text-xs transition-all shadow-md shadow-cyan-500/20 active:scale-95"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>My Projects</span>
          </Link>

        </div>

      </div>
    </header>
  );
};
