import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Cloud, ShieldCheck, Sparkles, User, LogOut, Menu, X } from 'lucide-react';
import { useCloudWise, formatINR } from '@/context/CloudWiseContext';
import { SlideTabs, SlideTabItem } from '@/components/ui/slide-tabs';

interface HeaderProps {
  navItems: SlideTabItem[];
}

export const Header: React.FC<HeaderProps> = ({ navItems }) => {
  const location = useLocation();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
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
      case '/connect-aws':
        return { label: 'AWS Setup', step: 'Connect AWS Account' };
      case '/deployment':
        return { label: 'Step 4 of 5', step: 'Provision & Deploy' };
      case '/monitoring':
        return { label: 'Step 4b', step: 'Live Monitoring' };
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
    <header className="sticky top-0 z-40 w-full border-b border-slate-800/80 bg-slate-950/85 backdrop-blur-xl">
      <div className="relative flex h-[76px] w-full items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex shrink-0 items-center gap-2.5 group">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-indigo-600 p-0.5 shadow-lg shadow-cyan-500/20 transition-all duration-300 group-hover:shadow-cyan-500/40">
            <div className="flex h-full w-full items-center justify-center rounded-[10px] bg-slate-950">
              <Cloud className="h-5 w-5 text-cyan-400 transition-transform duration-300 group-hover:scale-110" />
            </div>
          </div>
          <div className="flex flex-col">
            <span className="text-lg font-bold tracking-tight text-white">CloudWise</span>
            <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">Resource Intelligence</span>
          </div>
        </Link>

        {/* Center navigation */}
        <div className="absolute left-1/2 top-1/2 hidden max-w-[calc(100%-25rem)] -translate-x-1/2 -translate-y-1/2 lg:block">
          <SlideTabs
            items={navItems}
            className="!static !left-auto !max-w-full !translate-x-0"
          />
        </div>

        <div className="ml-auto flex items-center gap-3">
          <button
            type="button"
            onClick={() => setIsMenuOpen((open) => !open)}
            aria-expanded={isMenuOpen}
            aria-controls="header-menu"
            aria-label={isMenuOpen ? 'Close menu' : 'Open menu'}
            className="rounded-lg border border-slate-700 bg-slate-900/80 p-2.5 text-slate-300 transition-colors hover:border-cyan-400/60 hover:text-cyan-300"
          >
            {isMenuOpen ? <X size={21} /> : <Menu size={21} />}
          </button>
        </div>


      <div className="border-t border-slate-800/70 px-2 py-2 lg:hidden">
        <SlideTabs items={navItems} className="!static !left-auto !max-w-full !translate-x-0" />
      </div>

      {isMenuOpen && (
        <>
          <button
            type="button"
            aria-label="Close menu overlay"
            onClick={() => setIsMenuOpen(false)}
            className="fixed inset-0 top-[76px] bg-slate-950/50 backdrop-blur-[2px]"
          />
          <aside
            id="header-menu"
            className="absolute right-4 top-[84px] z-50 w-[min(22rem,calc(100vw-2rem))] rounded-2xl border border-slate-700 bg-slate-950/95 p-5 shadow-2xl shadow-cyan-950/40 backdrop-blur-xl sm:right-6 lg:right-8"
          >
            <div className="mb-5 flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-400">CloudWise</p>
                <p className="mt-1 text-lg font-bold text-white">Control center</p>
              </div>
              <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase text-cyan-300">
                {badge.label}
              </span>
            </div>

            <div className="space-y-3">
              <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                <p className="text-[11px] text-slate-500">Current workflow</p>
                <p className="mt-1 font-semibold text-cyan-300">{badge.step}</p>
              </div>

              {activeProject && (
                <Link
                  to="/projects"
                  onClick={() => setIsMenuOpen(false)}
                  className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/70 p-3 transition-colors hover:border-cyan-500/50"
                >
                  <span className="text-xs text-slate-400">Project</span>
                  <span className="max-w-[150px] truncate text-sm font-bold text-white">{activeProject.name}</span>
                </Link>
              )}

              {deployment.status === 'deployed' && (
                <div className="flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-400">
                  <ShieldCheck className="h-4 w-4" />
                  Live Cluster Active
                </div>
              )}

              <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                <span className="text-xs text-slate-400">Estimated monthly cost</span>
                <span className="font-bold text-cyan-400">{formatINR(effectiveMonthlyCost)}/mo</span>
              </div>

              {user ? (
                <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                  <span className="flex items-center gap-2 text-sm font-semibold text-white">
                    <User size={15} className="text-cyan-400" />
                    <span className="max-w-[140px] truncate">{user.name}</span>
                  </span>
                  <button onClick={logoutUser} title="Sign Out" className="text-slate-400 transition-colors hover:text-rose-400">
                    <LogOut size={17} />
                  </button>
                </div>
              ) : (
                <Link
                  to="/auth"
                  onClick={() => setIsMenuOpen(false)}
                  className="flex items-center justify-center gap-2 rounded-xl bg-cyan-400 px-4 py-3 text-sm font-bold text-slate-950 transition-colors hover:bg-cyan-300"
                >
                  <User size={16} />
                  Sign In
                </Link>
              )}

              <Link
                to="/projects"
                onClick={() => setIsMenuOpen(false)}
                className="flex items-center justify-center gap-2 rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-4 py-3 text-sm font-semibold text-cyan-300 transition-colors hover:bg-cyan-500/20"
              >
                <Sparkles size={16} />
                My Projects
              </Link>
            </div>
          </aside>
        </>
      )}
      </div>
    </header>
  );
};
