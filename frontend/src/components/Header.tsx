import React, { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Zap, Menu, X, User, LogOut, Moon, Sun, ArrowRight, Github } from 'lucide-react';
import { useCloudWise, formatINR } from '@/context/CloudWiseContext';
import { motion, AnimatePresence } from 'framer-motion';

export const Header: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const { user, logoutUser, activeProject, deployment } = useCloudWise();

  const links = [
    { name: 'Home', url: '/' },
    { name: 'Projects', url: '/projects' },
    { name: 'Connect GitHub', url: '/github' },
    { name: 'Estimate', url: '/estimation' },
    { name: 'Recommendation', url: '/recommendation' },
    { name: 'Generate', url: '/generate' },
    { name: 'Deploy', url: '/deployment' },
    { name: 'Monitor', url: '/monitoring' },
    { name: 'Contact', url: '/contact' },
  ];

  const getStatusDot = (url: string) => {
    if (url === '/monitoring' && deployment.status === 'success') {
      return <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse ml-1.5 glow-emerald" />;
    }
    if (url === '/deployment' && (deployment.status === 'validating' || deployment.status === 'running')) {
      return <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse ml-1.5 glow-amber" />;
    }
    return null;
  };

  const getUserInitials = () => {
    if (!user?.name) return 'U';
    return user.name.split(' ').map((n: string) => n[0]).slice(0, 2).join('').toUpperCase();
  };

  return (
    <header className="fixed top-4 sm:top-6 left-1/2 -translate-x-1/2 z-50 w-[96%] max-w-7xl">
      <div className="flex h-[56px] w-full items-center justify-between rounded-full border border-white/10 bg-black/60 px-5 backdrop-blur-md shadow-2xl transition-all">
        
        {/* Left: Logo */}
        <Link to="/" className="flex shrink-0 items-center gap-2 group">
          <Zap size={18} className="text-emerald-400 group-hover:text-emerald-300 transition-colors animate-pulse" />
          <span className="text-sm font-bold tracking-widest uppercase text-white drop-shadow-[0_0_8px_rgba(16,185,129,0.5)]">
            CloudWise
          </span>
        </Link>

        {/* Center: Links (Desktop) */}
        <nav className="hidden xl:flex flex-1 items-center justify-center gap-1.5">
          {links.map((link) => {
            const isActive = link.url === '/' ? location.pathname === '/' : location.pathname.startsWith(link.url);
            return (
              <Link
                key={link.name}
                to={link.url}
                className={`relative flex items-center px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider transition-all rounded-full ${
                  isActive ? 'text-white bg-white/5' : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {link.name}
                {getStatusDot(link.url)}
                {isActive && (
                  <motion.div
                    layoutId="active-nav-pill"
                    className="absolute inset-0 border border-white/10 rounded-full"
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                  />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Right: Actions */}
        <div className="hidden lg:flex items-center gap-3 shrink-0">
          <button
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-white/5 text-slate-300 hover:text-white hover:bg-white/10 transition-colors border border-white/5"
          >
            {theme === 'dark' ? <Moon size={14} /> : <Sun size={14} />}
          </button>

          {user ? (
            <div className="relative group">
              <button className="flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 pl-2 pr-3 py-1 hover:border-emerald-500/50 transition-colors">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500 text-[10px] font-bold text-slate-950">
                  {getUserInitials()}
                </span>
                <span className="text-[11px] font-bold text-emerald-100">{user.name.split(' ')[0]}</span>
              </button>
              <div className="absolute right-0 top-[calc(100%+0.5rem)] w-48 rounded-2xl border border-slate-800 bg-[#0A0E17]/95 p-2 backdrop-blur-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all">
                <div className="px-3 py-2 border-b border-slate-800/80 mb-1">
                  <p className="text-xs font-bold text-white truncate">{user.name}</p>
                  <p className="text-[10px] text-slate-400 truncate">{user.email}</p>
                </div>
                <Link to="/projects" className="flex items-center px-3 py-2 text-xs font-medium text-slate-300 hover:text-white hover:bg-white/5 rounded-lg">
                  My Projects
                </Link>
                <button
                  onClick={logoutUser}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 rounded-lg text-left"
                >
                  <LogOut size={12} />
                  Sign Out
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link to="/auth" className="text-xs font-bold text-slate-300 hover:text-white px-3 py-1.5 transition-colors">
                Sign In
              </Link>
              <Link to="/auth" className="flex items-center gap-1 rounded-full bg-emerald-500 hover:bg-emerald-400 px-4 py-1.5 text-xs font-bold text-slate-950 transition-colors shadow-lg shadow-emerald-500/20">
                Sign Up <ArrowRight size={12} />
              </Link>
            </div>
          )}
        </div>

        {/* Mobile Menu Toggle */}
        <button
          onClick={() => setIsMenuOpen(!isMenuOpen)}
          className="lg:hidden flex h-8 w-8 items-center justify-center rounded-full bg-white/5 text-slate-300 border border-white/5"
        >
          {isMenuOpen ? <X size={14} /> : <Menu size={14} />}
        </button>
      </div>

      {/* Mobile Drawer */}
      <AnimatePresence>
        {isMenuOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="absolute top-[calc(100%+0.5rem)] left-0 right-0 rounded-2xl border border-white/10 bg-black/80 backdrop-blur-xl p-4 lg:hidden"
          >
            <nav className="flex flex-col gap-2">
              {links.map((link) => (
                <Link
                  key={link.name}
                  to={link.url}
                  onClick={() => setIsMenuOpen(false)}
                  className="flex items-center justify-between rounded-lg px-4 py-3 text-xs font-bold uppercase tracking-wider text-slate-300 hover:bg-white/5 hover:text-white"
                >
                  {link.name}
                  {getStatusDot(link.url)}
                </Link>
              ))}
              {!user && (
                <div className="mt-4 flex flex-col gap-2 border-t border-white/10 pt-4">
                  <Link to="/auth" className="rounded-lg bg-white/5 px-4 py-3 text-center text-xs font-bold text-white">Sign In</Link>
                  <Link to="/auth" className="rounded-lg bg-emerald-500 px-4 py-3 text-center text-xs font-bold text-slate-950">Sign Up</Link>
                </div>
              )}
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
};
