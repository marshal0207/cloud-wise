import React from 'react';
import { Link } from 'react-router-dom';
import { Cloud, Github, Twitter, Linkedin, ArrowUpRight } from 'lucide-react';

export const Footer: React.FC = () => {
  return (
    <footer className="border-t border-slate-800/80 bg-slate-950/80 pt-12 pb-16 text-slate-400 text-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-10">
          
          {/* Brand Col */}
          <div className="space-y-4 md:col-span-1">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
                <Cloud className="w-4 h-4 text-cyan-400" />
              </div>
              <span className="text-lg font-bold text-white tracking-tight">CloudWise</span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              CloudWise empowers teams to estimate, compare, deploy, monitor, and optimize multi-cloud infrastructure with total cost transparency and automated recommendations.
            </p>
            <div className="flex items-center gap-3 text-slate-400 pt-1">
              <Link to="/about" className="hover:text-cyan-400 transition-colors" title="Twitter"><Twitter size={18} /></Link>
              <Link to="/about" className="hover:text-cyan-400 transition-colors" title="LinkedIn"><Linkedin size={18} /></Link>
              <Link to="/about" className="hover:text-cyan-400 transition-colors" title="GitHub"><Github size={18} /></Link>
            </div>
          </div>

          {/* Workflow Links */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-white uppercase tracking-wider">Cloud Workflow</h4>
            <ul className="space-y-2 text-xs">
              <li><Link to="/estimation" className="hover:text-cyan-400 transition-colors flex items-center gap-1">1. Workload Sizing <ArrowUpRight size={12} /></Link></li>
              <li><Link to="/recommendation" className="hover:text-cyan-400 transition-colors flex items-center gap-1">2. Cloud Recommendation <ArrowUpRight size={12} /></Link></li>
              <li><Link to="/generate" className="hover:text-cyan-400 transition-colors flex items-center gap-1">3. Files & GitHub Sync <ArrowUpRight size={12} /></Link></li>
              <li><Link to="/deployment" className="hover:text-cyan-400 transition-colors flex items-center gap-1">4. Cloud Provisioning <ArrowUpRight size={12} /></Link></li>
              <li><Link to="/monitoring" className="hover:text-cyan-400 transition-colors flex items-center gap-1">4b. Live Monitoring <ArrowUpRight size={12} /></Link></li>
              <li><Link to="/optimization" className="hover:text-cyan-400 transition-colors flex items-center gap-1">5. Cost Tuning <ArrowUpRight size={12} /></Link></li>
            </ul>
          </div>

          {/* Company Links */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-white uppercase tracking-wider">Company & Info</h4>
            <ul className="space-y-2 text-xs">
              <li><Link to="/about" className="hover:text-cyan-400 transition-colors">About Us</Link></li>
              <li><Link to="/contact" className="hover:text-cyan-400 transition-colors">Contact & Support</Link></li>
              <li><Link to="/about" className="hover:text-cyan-400 transition-colors">Documentation</Link></li>
              <li><Link to="/about" className="hover:text-cyan-400 transition-colors">Privacy Policy</Link></li>
              <li><Link to="/about" className="hover:text-cyan-400 transition-colors">Terms of Service</Link></li>
            </ul>
          </div>

          {/* Cloud Providers supported */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-white uppercase tracking-wider">Supported Clouds</h4>
            <p className="text-xs text-slate-400">
              Integrates with major cloud infrastructure providers:
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <span className="px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-[11px] text-slate-300 font-medium">Amazon Web Services</span>
              <span className="px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-[11px] text-slate-300 font-medium">Microsoft Azure</span>
              <span className="px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-[11px] text-slate-300 font-medium">Google Cloud</span>
              <span className="px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-[11px] text-slate-300 font-medium">DigitalOcean</span>
            </div>
          </div>

        </div>

        <div className="border-t border-slate-800/60 pt-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
          <p>© {new Date().getFullYear()} CloudWise Inc. All rights reserved.</p>
          <p className="flex items-center gap-2">
            <span>Built with precision for cloud resource planning</span>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span className="text-emerald-400">Systems Operational</span>
          </p>
        </div>
      </div>
    </footer>
  );
};
