import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Zap, LogOut, Moon, Sun, ArrowRight } from 'lucide-react';
import { useCloudWise } from '@/context/CloudWiseContext';
import {
  MobileNav,
  MobileNavHeader,
  MobileNavMenu,
  MobileNavToggle,
  NavBody,
  NavItems,
  Navbar,
} from '@/components/ui/resizable-navbar';

export const Header: React.FC = () => {
  const location = useLocation();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const { user, logoutUser, deployment } = useCloudWise();

  const links = [
    { name: 'Home', url: '/' },
    { name: 'Projects', url: '/projects' },
    { name: 'Connect AWS', url: '/connect-aws' },
    { name: 'Connect Atlas', url: '/connect-atlas' },
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
      <Navbar>
        <NavBody>
          <Link to="/" className="relative z-20 mr-4 flex shrink-0 items-center gap-2 px-2 py-1 group">
            <Zap size={18} className="text-emerald-400 transition-colors group-hover:text-emerald-300 animate-pulse" />
            <span className="text-sm font-bold tracking-widest uppercase text-white drop-shadow-[0_0_8px_rgba(16,185,129,0.5)]">
              CloudWise
            </span>
          </Link>
          <NavItems
            items={links.map(({ name, url }) => ({ name, link: url }))}
            activePath={location.pathname}
          />
          <div className="relative z-20 flex shrink-0 items-center gap-3">
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-white/5 bg-white/5 text-slate-300 transition-colors hover:bg-white/10 hover:text-white"
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <Moon size={14} /> : <Sun size={14} />}
            </button>
            {user ? (
              <div className="relative group">
                <button className="flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 py-1 pl-2 pr-3 transition-colors hover:border-emerald-500/50">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500 text-[10px] font-bold text-slate-950">
                    {getUserInitials()}
                  </span>
                  <span className="text-[11px] font-bold text-emerald-100">{user.name.split(' ')[0]}</span>
                </button>
                <div className="invisible absolute right-0 top-[calc(100%+0.5rem)] w-48 rounded-2xl border border-slate-800 bg-[#0A0E17]/95 p-2 opacity-0 backdrop-blur-xl transition-all group-hover:visible group-hover:opacity-100">
                  <div className="mb-1 border-b border-slate-800/80 px-3 py-2">
                    <p className="truncate text-xs font-bold text-white">{user.name}</p>
                    <p className="truncate text-[10px] text-slate-400">{user.email}</p>
                  </div>
                  <Link to="/projects" className="flex items-center rounded-lg px-3 py-2 text-xs font-medium text-slate-300 hover:bg-white/5 hover:text-white">My Projects</Link>
                  <button onClick={logoutUser} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-medium text-rose-400 hover:bg-rose-500/10 hover:text-rose-300">
                    <LogOut size={12} /> Sign Out
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Link to="/auth" className="px-3 py-1.5 text-xs font-bold text-slate-300 transition-colors hover:text-white">Sign In</Link>
                <Link to="/auth" className="flex items-center gap-1 rounded-full bg-emerald-500 px-4 py-1.5 text-xs font-bold text-slate-950 shadow-lg shadow-emerald-500/20 transition-colors hover:bg-emerald-400">Sign Up <ArrowRight size={12} /></Link>
              </div>
            )}
          </div>
        </NavBody>

        <MobileNav>
          <MobileNavHeader>
            <Link to="/" className="flex items-center gap-2 px-2 py-1">
              <Zap size={18} className="text-emerald-400" />
              <span className="text-sm font-bold tracking-widest uppercase text-white">CloudWise</span>
            </Link>
            <MobileNavToggle isOpen={isMenuOpen} onClick={() => setIsMenuOpen(!isMenuOpen)} />
          </MobileNavHeader>
          <MobileNavMenu isOpen={isMenuOpen} onClose={() => setIsMenuOpen(false)}>
            {links.map((link) => (
              <Link key={link.name} to={link.url} onClick={() => setIsMenuOpen(false)} className="flex w-full items-center justify-between rounded-lg px-4 py-3 text-xs font-bold uppercase tracking-wider text-slate-300 hover:bg-white/5 hover:text-white">
                {link.name}
                {getStatusDot(link.url)}
              </Link>
            ))}
            {!user && (
              <div className="mt-2 flex w-full flex-col gap-2 border-t border-white/10 pt-3">
                <Link to="/auth" onClick={() => setIsMenuOpen(false)} className="rounded-lg bg-white/5 px-4 py-3 text-center text-xs font-bold text-white">Sign In</Link>
                <Link to="/auth" onClick={() => setIsMenuOpen(false)} className="rounded-lg bg-emerald-500 px-4 py-3 text-center text-xs font-bold text-slate-950">Sign Up</Link>
              </div>
            )}
          </MobileNavMenu>
        </MobileNav>
      </Navbar>
    </header>
  );
};
