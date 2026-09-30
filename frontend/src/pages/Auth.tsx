import React, { useState, ChangeEvent, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Cloud, Server, Github, Database, ShieldCheck, Zap, Activity,
  Container, GitBranch, Cpu, DollarSign, Globe, BarChart3,
  Lock, Mail, Building2, User, Eye, EyeOff, KeyRound,
  ArrowRight, RefreshCw, CheckCircle2, AlertCircle, Sparkles
} from 'lucide-react';
import { useCloudWise } from '@/context/CloudWiseContext';

// ─── Left panel ──────────────────────────────────────────────────────────────
const LeftPanel: React.FC = () => {
  const stats = [
    { value: '9+', label: 'Cloud Regions' },
    { value: '4x', label: 'Cost Reduction' },
    { value: '<30s', label: 'Deploy Time' },
  ];

  const features = [
    { icon: <Github size={14} className="text-white" />, text: 'GitHub OAuth — 1-click repo connect' },
    { icon: <BarChart3 size={14} className="text-emerald-400" />, text: 'AI-driven cost estimation engine' },
    { icon: <Zap size={14} className="text-amber-400" />, text: 'Automated EC2 provisioning & deploy' },
    { icon: <Activity size={14} className="text-cyan-400" />, text: 'Real-time monitoring & live logs' },
    { icon: <DollarSign size={14} className="text-emerald-400" />, text: 'Multi-cloud cost comparison (AWS/GCP/Azure)' },
    { icon: <ShieldCheck size={14} className="text-teal-400" />, text: 'IAM-secured deployment pipeline' },
  ];

  const cloudBadges = [
    { name: 'AWS', color: 'text-amber-400 border-amber-500/30 bg-amber-500/10' },
    { name: 'GCP', color: 'text-blue-400 border-blue-500/30 bg-blue-500/10' },
    { name: 'Azure', color: 'text-sky-400 border-sky-500/30 bg-sky-500/10' },
    { name: 'DigitalOcean', color: 'text-indigo-400 border-indigo-500/30 bg-indigo-500/10' },
  ];

  return (
    <div className="hidden lg:flex flex-col justify-center w-[45%] h-full relative overflow-hidden bg-[#05080D] p-6 xl:p-8 gap-6">
      {/* Background texture */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 left-0 w-full h-full bg-[radial-gradient(ellipse_80%_50%_at_20%_-10%,rgba(16,185,129,0.08),transparent)]" />
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-emerald-500/5 rounded-full blur-3xl" />
        <svg className="absolute inset-0 w-full h-full opacity-[0.03]" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="white" strokeWidth="0.5"/>
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
      </div>

      {/* All content — single centered block */}
      <div className="relative z-10 flex flex-col gap-5">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 w-fit">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[11px] font-semibold uppercase tracking-widest text-emerald-300">Cloud Deployment Engine</span>
        </div>

        {/* Heading */}
        <div>
          <h2 className="text-4xl xl:text-5xl font-black text-white leading-[1.1] tracking-tight">
            Deploy Smarter.<br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-teal-300">
              Cut Cloud Costs.
            </span>
          </h2>
          <p className="text-sm text-slate-400 leading-relaxed max-w-sm mt-3">
            CloudWise analyzes your repository, estimates infrastructure costs across AWS, GCP, and Azure, then
            deploys your full stack automatically — in one workflow.
          </p>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-3">
          {stats.map((s) => (
            <div key={s.label} className="rounded-xl border border-slate-800 bg-[#0D121F]/80 px-4 py-3">
              <p className="text-xl font-black text-emerald-400 tabular-nums">{s.value}</p>
              <p className="text-[11px] text-slate-500 font-medium mt-0.5 uppercase tracking-wide">{s.label}</p>
            </div>
          ))}
        </div>

        {/* Feature list */}
        <div className="space-y-2">
          {features.map((f, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.1 + i * 0.07 }}
              className="flex items-center gap-3"
            >
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-slate-800 bg-[#0D121F]">
                {f.icon}
              </div>
              <span className="text-xs text-slate-400">{f.text}</span>
            </motion.div>
          ))}
        </div>

        {/* Cloud badges */}
        <div>
          <p className="text-[11px] uppercase tracking-widest text-slate-600 mb-2 font-semibold">Supported Clouds</p>
          <div className="flex flex-wrap gap-2">
            {cloudBadges.map((b) => (
              <span key={b.name} className={`rounded-full border px-3 py-1 text-[11px] font-semibold ${b.color}`}>
                {b.name}
              </span>
            ))}
          </div>
        </div>

        {/* Trust line */}
        <div className="pt-3 border-t border-slate-800/80 flex items-center gap-2">
          <ShieldCheck size={13} className="text-emerald-400" />
          <p className="text-[11px] text-slate-500">IAM-secured · End-to-end encrypted · Zero credential storage</p>
        </div>
      </div>
    </div>
  );
};

// ─── Form input ───────────────────────────────────────────────────────────────
interface FieldProps {
  label: string;
  icon: React.ReactNode;
  type: string;
  placeholder: string;
  value: string;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
  right?: React.ReactNode;
  autoComplete?: string;
}

const Field: React.FC<FieldProps> = ({ label, icon, type, placeholder, value, onChange, right, autoComplete }) => (
  <div>
    <label className="block text-[11px] font-semibold uppercase tracking-widest text-slate-500 mb-1.5">
      <span className="inline-flex items-center gap-1.5">
        <span className="text-emerald-500/80">{icon}</span>
        {label}
      </span>
    </label>
    <div className="relative">
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        autoComplete={autoComplete}
        className="w-full rounded-lg border border-slate-800 bg-[#080C14] px-4 py-2.5 text-sm text-white placeholder:text-slate-700 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/20 transition-all"
      />
      {right && (
        <div className="absolute inset-y-0 right-0 flex items-center pr-3">{right}</div>
      )}
    </div>
  </div>
);

// ─── Auth page ────────────────────────────────────────────────────────────────
export const Auth: React.FC = () => {
  const navigate = useNavigate();
  const { loginUser } = useCloudWise();

  const [tab, setTab] = useState<'login' | 'signup'>('login');
  const [showPass, setShowPass] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const [form, setForm] = useState({
    name: '', company: '', email: '', password: '', confirmPassword: '',
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const set = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value }));

  const reset = () => {
    setForm({ name: '', company: '', email: '', password: '', confirmPassword: '' });
    setError(''); setSuccess('');
  };

  const switchTab = (t: 'login' | 'signup') => { setTab(t); reset(); };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(''); setSuccess('');

    const { name, company, email, password, confirmPassword } = form;

    if (tab === 'signup') {
      if (!name || !company || !email || !password || !confirmPassword) { setError('Please complete all fields.'); return; }
      if (password !== confirmPassword) { setError('Passwords do not match.'); return; }
    } else {
      if (!email || !password) { setError('Enter your email and password.'); return; }
    }

    setLoading(true);
    try {
      const endpoint = tab === 'login' ? '/api/auth/login' : '/api/auth/signup';
      const body = tab === 'login' ? { email, password } : { name, company, email, password };
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || 'Authentication failed.');
      loginUser(data.user, data.token);
      setSuccess('Authenticated! Redirecting…');
      setTimeout(() => navigate('/projects'), 600);
    } catch (err: any) {
      setError(err.message || 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed top-[88px] inset-x-0 bottom-0 bg-[#07090E] flex z-10">

      {/* ── Left panel ── */}
      <LeftPanel />

      {/* ── Divider ── */}
      <div className="hidden lg:block w-px bg-gradient-to-b from-transparent via-slate-800 to-transparent shrink-0" />

      {/* ── Right: form ── */}
      <div className="flex-1 overflow-y-auto h-full">
        <div className="flex flex-col justify-center min-h-full px-6 xl:px-8 py-8 items-start">
          <div className="w-full max-w-md">

            {/* Mobile logo */}
            <div className="lg:hidden flex items-center gap-2 mb-8">
              <div className="h-8 w-8 rounded-lg bg-gradient-to-tr from-emerald-500 to-teal-500 flex items-center justify-center">
                <Cloud size={16} className="text-white" />
              </div>
              <span className="font-bold text-white">CloudWise</span>
            </div>

            {/* Heading */}
            <div className="mb-6">
              <p className="text-[11px] font-semibold uppercase tracking-widest text-emerald-400 mb-1">
                {'//'} {tab === 'login' ? 'Secure Authentication' : 'Create Your Account'}
              </p>
              <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
                {tab === 'login' ? 'Sign In to CloudWise' : 'Start Deploying Free'}
              </h1>
              <p className="mt-1.5 text-sm text-slate-500">
                {tab === 'login'
                  ? 'Access your cloud cost optimization and deployment dashboard.'
                  : 'Analyze repositories, compare cloud costs, and deploy in minutes.'}
              </p>
            </div>

            {/* Tab switcher */}
            <div className="flex mb-6 rounded-lg border border-slate-800 bg-[#080C14] p-1">
              {(['login', 'signup'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => switchTab(t)}
                  className={`flex-1 py-2.5 text-xs font-bold uppercase tracking-widest rounded-md transition-all ${
                    tab === t
                      ? 'bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/30'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {t === 'login' ? 'Sign In' : 'Create Account'}
                </button>
              ))}
            </div>

            {/* Alerts */}
            <AnimatePresence>
              {error && (
                <motion.div key="err"
                  initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                  className="flex items-start gap-2.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-xs text-rose-300 mb-5"
                >
                  <AlertCircle size={14} className="shrink-0 mt-0.5 text-rose-400" />
                  {error}
                </motion.div>
              )}
              {success && (
                <motion.div key="ok"
                  initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                  className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-xs text-emerald-300 mb-5"
                >
                  <CheckCircle2 size={14} className="shrink-0 text-emerald-400" />
                  {success}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              <AnimatePresence mode="wait">
                {tab === 'signup' && (
                  <motion.div key="signup-fields"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="space-y-4 overflow-hidden"
                  >
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Full Name" icon={<User size={11} />} type="text"
                        placeholder="e.g. Rohan Mehta" value={form.name} onChange={set('name')} autoComplete="name" />
                      <Field label="Organization" icon={<Building2 size={11} />} type="text"
                        placeholder="e.g. TechMatrix" value={form.company} onChange={set('company')} autoComplete="organization" />
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <Field label="Work Email" icon={<Mail size={11} />} type="email"
                placeholder="you@company.com" value={form.email} onChange={set('email')} autoComplete="email" />

              <Field label={`Password${tab === 'signup' ? ' (min. 6 chars)' : ''}`}
                icon={<Lock size={11} />}
                type={showPass ? 'text' : 'password'}
                placeholder="••••••••••••"
                value={form.password} onChange={set('password')} autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
                right={
                  <button type="button" onClick={() => setShowPass((p) => !p)}
                    className="text-slate-600 hover:text-slate-300 transition-colors">
                    {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                }
              />

              {tab === 'signup' && (
                <Field label="Confirm Password" icon={<KeyRound size={11} />}
                  type={showConfirm ? 'text' : 'password'}
                  placeholder="••••••••••••"
                  value={form.confirmPassword} onChange={set('confirmPassword')} autoComplete="new-password"
                  right={
                    <button type="button" onClick={() => setShowConfirm((p) => !p)}
                      className="text-slate-600 hover:text-slate-300 transition-colors">
                      {showConfirm ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  }
                />
              )}

              {/* Submit */}
              <button
                type="submit"
                disabled={loading}
                className="group relative w-full mt-2 flex items-center justify-center gap-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 disabled:opacity-60 py-3 text-sm font-bold text-slate-950 transition-all shadow-lg shadow-emerald-500/20"
              >
                {loading
                  ? <><RefreshCw size={15} className="animate-spin" /> Processing…</>
                  : tab === 'login'
                    ? <><ArrowRight size={15} /> Sign In to CloudWise</>
                    : <><Sparkles size={15} /> Create Account & Start Free →</>
                }
              </button>
            </form>

            {/* Switch link */}
            <p className="text-center text-xs text-slate-600 mt-5">
              {tab === 'login' ? (
                <>Don't have an account?{' '}
                  <button onClick={() => switchTab('signup')}
                    className="font-semibold text-emerald-400 hover:text-emerald-300 transition-colors">
                    Create one free
                  </button>
                </>
              ) : (
                <>Already have an account?{' '}
                  <button onClick={() => switchTab('login')}
                    className="font-semibold text-emerald-400 hover:text-emerald-300 transition-colors">
                    Sign In
                  </button>
                </>
              )}
            </p>

            {/* Trust badges */}
            <div className="mt-8 pt-6 border-t border-slate-800/80 grid grid-cols-2 gap-2">
              {[
                { icon: <ShieldCheck size={12} className="text-emerald-400" />, text: 'Supabase JWT Encrypted' },
                { icon: <Zap size={12} className="text-amber-400" />, text: 'Zero Credential Storage' },
                { icon: <Globe size={12} className="text-blue-400" />, text: 'Multi-Region Deploy' },
                { icon: <Activity size={12} className="text-teal-400" />, text: 'Real-time Monitoring' },
              ].map((b, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px] text-slate-600">
                  {b.icon}
                  {b.text}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
