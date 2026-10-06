import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion, useScroll, useTransform, AnimatePresence } from 'framer-motion';
import {
  ArrowRight, Github, Zap, Cloud, Server, Database, ShieldCheck,
  BarChart3, Activity, Rocket, CheckCircle2, RefreshCw,
  Send, ChevronRight, Terminal, Cpu, DollarSign, Globe,
  GitBranch, Container, Workflow, Star, TrendingUp, Play,
  Calculator, Sparkles, FileCode, Quote, Check, FolderPlus, UserPlus
} from 'lucide-react';
import { useCloudWise } from '@/context/CloudWiseContext';

// ── Animated ticker ──────────────────────────────────────────────────────────
const tags = [
  'Intelligent repository analysis',
  'Multi-cloud cost optimization',
  'Automated AWS EC2 deployments',
  'Real-time monitoring & alerts',
  'Zero-config Docker generation',
];

const Ticker: React.FC = () => {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((p) => (p + 1) % tags.length), 3000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-slate-500">
      <span className="h-1 w-6 bg-emerald-500/50 rounded-full" />
      <AnimatePresence mode="wait">
        <motion.span
          key={idx}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.3 }}
          className="text-emerald-400/80"
        >
          {tags[idx]}
        </motion.span>
      </AnimatePresence>
      <span className="h-1 w-6 bg-emerald-500/50 rounded-full" />
    </div>
  );
};

// ── Floating status badge ─────────────────────────────────────────────────────
const StatusBadge: React.FC = () => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ delay: 1.2, duration: 0.6 }}
    className="fixed bottom-6 right-6 z-20 flex items-center gap-2.5 rounded-full border border-emerald-500/30 bg-[#0B1220]/90 backdrop-blur-md px-4 py-2 shadow-lg shadow-emerald-500/10"
  >
    <span className="relative flex h-2 w-2">
      <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
      <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
    </span>
    <span className="text-[11px] font-bold uppercase tracking-widest text-emerald-300">⚡ CloudWise AI | COPILOT</span>
  </motion.div>
);

// ── Pipeline step card ─────────────────────────────────────────────────────────
interface StepProps {
  num: string;
  title: string;
  desc: string;
  icon: React.ReactNode;
  accent: string;
  delay: number;
}
const PipelineStep: React.FC<StepProps> = ({ num, title, desc, icon, accent, delay }) => (
  <motion.div
    initial={{ opacity: 0, y: 30 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true }}
    transition={{ delay, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    className="group relative flex flex-col gap-4 rounded-2xl border border-slate-800 bg-[#0D121F]/60 p-6 hover:border-emerald-500/30 transition-all duration-300 hover:shadow-lg hover:shadow-emerald-500/5"
  >
    <div className="flex items-start justify-between">
      <div className={`flex h-10 w-10 items-center justify-center rounded-xl border border-slate-700 bg-[#080C14] text-lg ${accent}`}>
        {icon}
      </div>
      <span className="font-mono text-[11px] text-slate-700 font-bold">{num}</span>
    </div>
    <div>
      <h3 className="font-bold text-white text-base mb-1">{title}</h3>
      <p className="text-xs text-slate-500 leading-relaxed">{desc}</p>
    </div>
    <div className="absolute inset-x-0 bottom-0 h-px rounded-full bg-gradient-to-r from-transparent via-emerald-500/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
  </motion.div>
);

// ── Cloud comparison mini-card ────────────────────────────────────────────────
interface CloudCardProps {
  name: string;
  instance: string;
  monthly: string;
  score: number;
  recommended?: boolean;
}
const CloudCard: React.FC<CloudCardProps> = ({ name, instance, monthly, score, recommended }) => (
  <div className={`flex flex-col gap-2 rounded-xl border p-4 transition-all ${
    recommended
      ? 'border-emerald-500/40 bg-emerald-500/5 shadow-md shadow-emerald-500/10'
      : 'border-slate-800 bg-[#0D121F]/50'
  }`}>
    <div className="flex items-center justify-between">
      <span className="text-xs font-bold text-white">{name}</span>
      {recommended && (
        <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-400 border border-emerald-500/30">
          RECOMMENDED
        </span>
      )}
    </div>
    <p className="text-[11px] font-mono text-slate-500">{instance}</p>
    <p className="text-xl font-black text-white">{monthly}<span className="text-xs font-normal text-slate-500">/mo</span></p>
    <div className="h-1.5 w-full rounded-full bg-slate-800">
      <div
        className={`h-full rounded-full ${recommended ? 'bg-emerald-500' : 'bg-slate-600'}`}
        style={{ width: `${score}%` }}
      />
    </div>
    <p className="text-[10px] text-slate-600">Cost efficiency: {score}%</p>
  </div>
);

// ── Main Home component ───────────────────────────────────────────────────────
export const Home: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useCloudWise();
  const [waitlistEmail, setWaitlistEmail] = useState('');
  const [waitlistLoading, setWaitlistLoading] = useState(false);
  const [waitlistSuccess, setWaitlistSuccess] = useState(false);
  const [waitlistError, setWaitlistError] = useState('');
  const heroRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: heroRef });
  const heroOpacity = useTransform(scrollYProgress, [0, 0.5], [1, 0]);
  const heroY = useTransform(scrollYProgress, [0, 0.5], [0, -60]);

  const handleWaitlistSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!waitlistEmail) return;
    setWaitlistLoading(true);
    setWaitlistError('');
    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: waitlistEmail, source: 'home_page_cta' }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || 'Failed to subscribe.');
      setWaitlistSuccess(true);
      setWaitlistEmail('');
    } catch (err: any) {
      setWaitlistError(err.message || 'Something went wrong.');
    } finally {
      setWaitlistLoading(false);
    }
  };

  const workflowSteps = [
    {
      step: '01',
      title: 'Workload Sizing',
      route: '/estimation',
      icon: Calculator,
      color: 'from-blue-500 to-cyan-400',
      description: 'Define your workload requirements (vCPU, RAM, storage, expected traffic & budget) with real-time profile calculation.',
    },
    {
      step: '02',
      title: 'Compare & Recommend',
      route: '/recommendation',
      icon: Sparkles,
      color: 'from-cyan-400 to-teal-400',
      description: 'Benchmark multi-cloud configurations across AWS, Azure, and GCP with AI recommendation reasoning.',
    },
    {
      step: '03',
      title: 'Generate Files & GitHub Sync',
      route: '/generate',
      icon: FileCode,
      color: 'from-violet-500 to-indigo-400',
      description: 'Auto-generate production Dockerfile and CI/CD YAML, preview/download code, and sync to GitHub repository.',
    },
    {
      step: '04',
      title: 'Deploy Cloud Config',
      route: '/deployment',
      icon: Rocket,
      color: 'from-amber-400 to-orange-500',
      description: 'Provision your chosen cloud environment with live streaming logs, health verification, and rollback protection.',
    },
    {
      step: '05',
      title: 'Cost Tuning',
      route: '/optimization',
      icon: Zap,
      color: 'from-emerald-400 to-teal-500',
      description: 'Apply 1-click recommendations to rightsize instances, eliminate orphan disks, and update monthly costs in real-time.',
    },
  ];

  const testimonials = [
    {
      quote: "CloudWise eliminated over ₹11.5 Lakhs in annual AWS waste within our first 30 days. The side-by-side multi-cloud pricing comparison is indispensable.",
      author: "Rohan Mehta",
      title: "VP of Engineering",
      company: "TechMatrix India",
      metrics: "34% Cost Savings"
    },
    {
      quote: "Being able to test our provisioning pipeline before committing cloud spend gave our SRE team total confidence. Highly recommended!",
      author: "Priya Sharma",
      title: "Lead Cloud Architect",
      company: "Kavya Tech Solutions",
      metrics: "Zero Downtime Deployments"
    },
    {
      quote: "The 1-click optimization recommendations cut down our unattached EBS disk clutter instantly. Simple, beautiful, and hyper-effective.",
      author: "Aravind Kumar",
      title: "Head of Infrastructure",
      company: "ZettaCloud Systems",
      metrics: "₹99,600/mo Saved"
    }
  ];

  const pipelineSteps = [
    { num: '01', title: 'Connect Repository', desc: 'OAuth GitHub connect. Select your repo and branch in seconds.', icon: <Github size={18} />, accent: 'text-white', delay: 0.1 },
    { num: '02', title: 'Workload Estimation', desc: 'AI-driven analysis of CPU, RAM, and storage requirements from your code.', icon: <BarChart3 size={18} />, accent: 'text-emerald-400', delay: 0.15 },
    { num: '03', title: 'Cloud Recommendation', desc: 'Side-by-side pricing comparison across AWS, GCP, Azure, and DigitalOcean.', icon: <DollarSign size={18} />, accent: 'text-amber-400', delay: 0.2 },
    { num: '04', title: 'Generate Artifacts', desc: 'Auto-generate Dockerfile, docker-compose.yml, nginx.conf, and .env template.', icon: <Terminal size={18} />, accent: 'text-cyan-400', delay: 0.25 },
    { num: '05', title: 'Provision & Deploy', desc: 'Automated EC2 provisioning, security group configuration, and container launch.', icon: <Rocket size={18} />, accent: 'text-purple-400', delay: 0.3 },
    { num: '06', title: 'Monitor & Optimize', desc: 'Live CPU, RAM, and network telemetry with cost optimization recommendations.', icon: <Activity size={18} />, accent: 'text-teal-400', delay: 0.35 },
  ];

  return (
    <div className="relative -mt-0">
      <StatusBadge />

      {/* ── HERO ────────────────────────────────────────────────────────── */}
      <section ref={heroRef} className="relative min-h-[88vh] flex flex-col items-center justify-center overflow-hidden pt-8 pb-20">
        {/* Ambient glows */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-emerald-500/6 rounded-full blur-[120px]" />
          <div className="absolute top-1/3 left-1/4 w-64 h-64 bg-cyan-500/5 rounded-full blur-3xl" />
          <div className="absolute top-1/3 right-1/4 w-64 h-64 bg-teal-500/5 rounded-full blur-3xl" />
        </div>

        {/* Background giant text */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none select-none overflow-hidden">
          <motion.p
            style={{ opacity: heroOpacity, y: heroY }}
            className="text-[clamp(3rem,12vw,10rem)] font-black uppercase tracking-[0.3em] text-white/[0.025] whitespace-nowrap"
          >
            C L O U D W I S E
          </motion.p>
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8 }}
          className="relative z-10 flex flex-col items-center text-center px-4 gap-6"
        >
          {/* Ticker */}
          <Ticker />

          {/* Headline */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          >
            <h1 className="text-5xl sm:text-6xl lg:text-7xl font-black text-white leading-[1.05] tracking-tight max-w-4xl">
              Deploy any stack to{' '}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400">
                AWS
              </span>{' '}
              in one workflow.
            </h1>
          </motion.div>

          {/* Subheading */}
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35, duration: 0.6 }}
            className="text-base sm:text-lg text-slate-400 max-w-xl leading-relaxed"
          >
            CloudWise analyzes your GitHub repository, estimates cloud costs across providers, generates production-ready Docker configs, and deploys to AWS EC2 — automatically.
          </motion.p>

          {/* CTA Buttons */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5, duration: 0.5 }}
            className="flex flex-wrap items-center gap-3 justify-center"
          >
            <button
              onClick={() => navigate(user ? '/projects' : '/auth')}
              className="group flex items-center gap-2 rounded-full bg-emerald-500 hover:bg-emerald-400 px-6 py-3 text-sm font-bold text-slate-950 transition-all shadow-lg shadow-emerald-500/25 hover:shadow-emerald-500/40 hover:scale-[1.02]"
            >
              <Rocket size={15} />
              Start Deploying
              <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
            </button>
            <Link
              to="/projects"
              className="group flex items-center gap-2 rounded-full border border-slate-700 hover:border-emerald-500/50 bg-slate-900/60 hover:bg-emerald-500/5 px-6 py-3 text-sm font-bold text-slate-300 hover:text-white transition-all backdrop-blur-sm"
            >
              <Github size={15} />
              Connect GitHub
            </Link>
          </motion.div>

          {/* Social proof micro-row */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.7 }}
            className="flex flex-wrap items-center gap-4 text-xs text-slate-600"
          >
            {['AWS EC2 Provisioning', 'Multi-cloud Pricing', 'Real-time Monitoring', 'Auto Docker Build'].map((t) => (
              <span key={t} className="flex items-center gap-1.5">
                <CheckCircle2 size={11} className="text-emerald-500/70" />
                {t}
              </span>
            ))}
          </motion.div>
        </motion.div>

      </section>

      {/* Customer Testimonials Section */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <div className="text-center space-y-3 max-w-2xl mx-auto">
          <span className="px-3 py-1 rounded-full bg-cyan-500/10 text-cyan-300 text-xs font-semibold border border-cyan-500/30">
            Trusted By Engineers
          </span>
          <h3 className="text-3xl font-extrabold text-white">What Cloud Architects Say</h3>
          <p className="text-slate-400 text-xs sm:text-sm">
            Read how engineering leaders optimize multi-cloud infrastructure with CloudWise.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {testimonials.map((t, i) => (
            <div key={i} className="glass-card p-6 rounded-2xl space-y-4 flex flex-col justify-between border border-slate-800 relative">
              <Quote className="w-8 h-8 text-cyan-500/20 absolute top-4 right-4" />
              
              <div className="space-y-3">
                <div className="flex items-center gap-1 text-amber-400">
                  {[...Array(5)].map((_, idx) => (
                    <Star key={idx} size={14} fill="currentColor" />
                  ))}
                </div>
                <p className="text-xs text-slate-300 leading-relaxed italic">
                  "{t.quote}"
                </p>
              </div>
              <div className="pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs">
                <div>
                  <h5 className="font-bold text-white">{t.author}</h5>
                  <p className="text-[11px] text-slate-400">{t.title} • {t.company}</p>
                </div>
                <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 text-[10px] font-bold border border-emerald-500/30">
                  {t.metrics}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Tech stack orbit row */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.9, duration: 0.6 }}
          className="absolute bottom-8 left-1/2 -translate-x-1/2 flex items-center gap-3"
        >
          {[
            { icon: <Github size={14} />, label: 'GitHub' },
            { icon: <Container size={14} />, label: 'Docker' },
            { icon: <Server size={14} />, label: 'EC2' },
            { icon: <Database size={14} />, label: 'MongoDB' },
            { icon: <Globe size={14} />, label: 'Nginx' },
          ].map((t) => (
            <div key={t.label} className="flex items-center gap-1.5 rounded-full border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-[11px] text-slate-500 backdrop-blur-sm">
              {t.icon}
              {t.label}
            </div>
          ))}
        </motion.div>
      </section>

      {/* ── CLOUD COST PREVIEW ──────────────────────────────────────────── */}
      <section className="py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="flex flex-col items-center text-center gap-3 mb-12"
          >
            <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-[11px] font-bold uppercase tracking-widest text-cyan-400">
              Multi-Cloud Pricing Intelligence
            </span>
            <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
              See exactly what you'll pay — before you deploy.
            </h2>
            <p className="text-sm text-slate-500 max-w-lg">
              Estimated for a React + Node.js + MongoDB stack. 2 vCPU · 4 GB RAM · 30 GB SSD.
            </p>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: 0 }}>
              <CloudCard name="Amazon AWS" instance="t3.medium · us-east-1" monthly="$34.80" score={95} recommended />
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: 0.1 }}>
              <CloudCard name="Google Cloud" instance="e2-medium · us-central1" monthly="$38.20" score={72} />
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: 0.2 }}>
              <CloudCard name="Microsoft Azure" instance="Standard_B2s · East US" monthly="$36.50" score={78} />
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="mt-6 text-center"
          >
            <Link
              to="/estimation"
              className="inline-flex items-center gap-2 text-sm text-emerald-400 hover:text-emerald-300 font-semibold transition-colors"
            >
              Calculate your exact costs <ChevronRight size={14} />
            </Link>
          </motion.div>
        </div>
      </section>

      {/* ── PIPELINE ────────────────────────────────────────────────────── */}
      <section className="py-20 px-4 border-t border-slate-900">
        <div className="max-w-5xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="flex flex-col items-center text-center gap-3 mb-12"
          >
            <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-[11px] font-bold uppercase tracking-widest text-emerald-400">
              6-Step Automated Pipeline
            </span>
            <h2 className="text-3xl sm:text-4xl font-black text-white tracking-tight">
              From GitHub repo to live URL.
            </h2>
            <p className="text-sm text-slate-500 max-w-md">
              One continuous workflow. Zero DevOps experience required.
            </p>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {pipelineSteps.map((s) => (
              <PipelineStep key={s.num} {...s} />
            ))}
          </div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mt-10 text-center"
          >
            <button
              onClick={() => navigate(user ? '/projects' : '/auth')}
              className="group inline-flex items-center gap-2 rounded-full bg-emerald-500 hover:bg-emerald-400 px-8 py-3.5 text-sm font-bold text-slate-950 transition-all shadow-lg shadow-emerald-500/20"
            >
              <Play size={14} fill="currentColor" />
              Start Your First Deployment
              <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
            </button>
          </motion.div>
        </div>
      </section>

      {/* ── TECH STACK ──────────────────────────────────────────────────── */}
      <section className="py-20 px-4 border-t border-slate-900">
        <div className="max-w-5xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="flex flex-col items-center text-center gap-3 mb-12"
          >
            <h2 className="text-2xl sm:text-3xl font-black text-white tracking-tight">
              Built for full-stack teams.
            </h2>
            <p className="text-sm text-slate-500">Auto-detected stack support. More coming soon.</p>
          </motion.div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { name: 'React', sub: 'Frontend', color: 'text-cyan-400', bg: 'bg-cyan-500/5 border-cyan-500/20', icon: <Globe size={20} /> },
              { name: 'Node.js / Express', sub: 'Backend API', color: 'text-emerald-400', bg: 'bg-emerald-500/5 border-emerald-500/20', icon: <Server size={20} /> },
              { name: 'MongoDB', sub: 'Database', color: 'text-green-400', bg: 'bg-green-500/5 border-green-500/20', icon: <Database size={20} /> },
              { name: 'Docker + Nginx', sub: 'Orchestration', color: 'text-blue-400', bg: 'bg-blue-500/5 border-blue-500/20', icon: <Container size={20} /> },
            ].map((t, i) => (
              <motion.div
                key={t.name}
                initial={{ opacity: 0, scale: 0.95 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.08 }}
                className={`flex flex-col items-center gap-2 rounded-2xl border p-5 text-center ${t.bg}`}
              >
                <div className={t.color}>{t.icon}</div>
                <p className="text-sm font-bold text-white">{t.name}</p>
                <p className="text-[11px] text-slate-600">{t.sub}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── WAITLIST CTA ─────────────────────────────────────────────────── */}
      <section className="py-20 px-4 border-t border-slate-900">
        <div className="max-w-xl mx-auto flex flex-col items-center gap-6 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <p className="text-[11px] font-bold uppercase tracking-widest text-emerald-400 mb-2">Early Access</p>
            <h2 className="text-3xl font-black text-white mb-3">Get notified when new cloud providers launch.</h2>
            <p className="text-sm text-slate-500">Join the waitlist. We'll notify you when Azure and GCP auto-deploy go live.</p>
          </motion.div>

          <motion.form
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            onSubmit={handleWaitlistSubmit}
            className="flex w-full gap-2"
          >
            {!waitlistSuccess ? (
              <>
                <input
                  type="email"
                  placeholder="you@company.com"
                  value={waitlistEmail}
                  onChange={(e) => setWaitlistEmail(e.target.value)}
                  className="flex-1 rounded-lg border border-slate-800 bg-[#080C14] px-4 py-2.5 text-sm text-white placeholder:text-slate-700 focus:outline-none focus:border-emerald-500/60 transition-all"
                />
                <button
                  type="submit"
                  disabled={waitlistLoading}
                  className="flex items-center gap-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 px-5 py-2.5 text-sm font-bold text-slate-950 transition-all disabled:opacity-60"
                >
                  {waitlistLoading ? <RefreshCw size={14} className="animate-spin" /> : <Send size={14} />}
                  {waitlistLoading ? '' : 'Join'}
                </button>
              </>
            ) : (
              <div className="flex w-full items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
                <CheckCircle2 size={15} className="text-emerald-400" />
                You're on the list! We'll be in touch.
              </div>
            )}
          </motion.form>
          {waitlistError && <p className="text-xs text-rose-400">{waitlistError}</p>}
        </div>
      </section>
    </div>
  );
};
