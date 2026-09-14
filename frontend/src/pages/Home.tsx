import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Calculator, 
  Sparkles, 
  FileCode,
  Rocket, 
  Zap, 
  ArrowRight, 
  CheckCircle2, 
  ShieldCheck, 
  Mail,
  Send,
  RefreshCw,
  Star,
  Quote,
  Check,
  FolderPlus,
  UserPlus
} from 'lucide-react';
import { useCloudWise } from '@/context/CloudWiseContext';

export const Home: React.FC = () => {
  const { user } = useCloudWise();
  const [waitlistEmail, setWaitlistEmail] = useState('');
  const [waitlistLoading, setWaitlistLoading] = useState(false);
  const [waitlistSuccess, setWaitlistSuccess] = useState(false);
  const [waitlistError, setWaitlistError] = useState('');

  const handleWaitlistSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!waitlistEmail) return;

    setWaitlistLoading(true);
    setWaitlistError('');

    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: waitlistEmail, source: 'home_page_cta' })
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to subscribe to waitlist.');
      }

      setWaitlistSuccess(true);
      setWaitlistEmail('');
    } catch (err: any) {
      setWaitlistError(err.message || 'Something went wrong. Please try again.');
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
      description: 'Benchmark multi-cloud configurations across AWS, Azure, GCP, and DigitalOcean with AI recommendation reasoning.',
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

  return (
    <div className="min-h-screen space-y-24 pb-20">
      
      {/* Hero Section */}
      <section className="relative mx-auto max-w-7xl px-4 pb-8 pt-14 sm:px-6 lg:px-8 lg:pb-12 lg:pt-20">
        <div className="pointer-events-none absolute left-1/4 top-1/3 -z-10 h-72 w-72 rounded-full bg-cyan-500/10 blur-[120px]" />
        <div className="grid items-center gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
          <motion.div
            initial={{ opacity: 0, x: -24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.55 }}
            className="space-y-7"
          >
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-cyan-300">
              <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
              <span>Cloud resource intelligence</span>
            </div>

            <div className="space-y-1">
              <p className="text-4xl font-extrabold tracking-tight text-white sm:text-6xl">COST</p>
              <p className="text-5xl font-black tracking-tight text-gradient sm:text-7xl">OPTIMIZATION</p>
              <p className="text-4xl font-extrabold tracking-tight text-white sm:text-6xl">&amp; AUTO DEPLOY.</p>
            </div>

            <p className="max-w-xl text-base leading-relaxed text-slate-400 sm:text-lg">
              Size workloads accurately, remove cloud waste, and move from a recommendation to a production-ready deployment in one guided workflow.
            </p>

            <div className="flex flex-col gap-3 sm:flex-row">
              {user ? (
                <Link to="/projects" className="flex items-center justify-center gap-2 rounded-lg bg-cyan-400 px-6 py-3.5 text-sm font-bold text-slate-950 shadow-lg shadow-cyan-500/20 transition-all hover:bg-cyan-300 active:scale-95">
                  <FolderPlus className="h-4 w-4" />
                  Go to My Projects
                  <ArrowRight className="h-4 w-4" />
                </Link>
              ) : (
                <Link to="/auth" className="flex items-center justify-center gap-2 rounded-lg bg-cyan-400 px-6 py-3.5 text-sm font-bold text-slate-950 shadow-lg shadow-cyan-500/20 transition-all hover:bg-cyan-300 active:scale-95">
                  <UserPlus className="h-4 w-4" />
                  Start Planning
                  <ArrowRight className="h-4 w-4" />
                </Link>
              )}
              <Link to="/recommendation" className="flex items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-900/80 px-6 py-3.5 text-sm font-semibold text-white transition-colors hover:border-cyan-500/50 hover:bg-slate-800">
                Compare Providers
              </Link>
            </div>

            <div className="grid max-w-lg grid-cols-3 gap-3 border-t border-slate-800/80 pt-5">
              <div><p className="text-xl font-bold text-cyan-400">32%</p><p className="text-[11px] text-slate-500">Avg. savings</p></div>
              <div><p className="text-xl font-bold text-cyan-400">4</p><p className="text-[11px] text-slate-500">Cloud providers</p></div>
              <div><p className="text-xl font-bold text-cyan-400">&lt;2 min</p><p className="text-[11px] text-slate-500">To deploy</p></div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.55, delay: 0.1 }}
            className="relative"
          >
            <div className="absolute -right-2 top-6 h-full w-1 rounded-full bg-cyan-400 shadow-[0_0_18px_rgba(34,211,238,0.7)]" />
            <div className="overflow-hidden rounded-xl border border-slate-700 bg-slate-950/95 shadow-2xl shadow-cyan-950/30">
              <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
                <div className="flex items-center gap-2 text-sm font-bold text-white">
                  <Rocket className="h-4 w-4 text-cyan-400" />
                  AUTO DEPLOY WORKFLOW
                </div>
                <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-1 font-mono text-[10px] text-cyan-300">RUN 04 / 05</span>
              </div>
              <div className="space-y-5 p-5 sm:p-7">
                <div className="flex items-center justify-between rounded-lg border border-cyan-500/30 bg-slate-900/80 p-4">
                  <div>
                    <div className="flex items-center gap-2 text-sm font-bold text-white"><span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />Provisioning live</div>
                    <p className="mt-1 text-xs text-slate-500">Production cluster · Mumbai region</p>
                  </div>
                  <span className="text-xs font-bold text-emerald-400">ACTIVE</span>
                </div>

                <div className="space-y-3">
                  {['Validating workload profile', 'Selecting lowest-cost instance', 'Generating deployment files', 'Provisioning cloud resources'].map((step, index) => (
                    <div key={step} className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-3">
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
                      <span className="flex-1 text-xs font-semibold text-slate-200">{step}</span>
                      <span className="font-mono text-[10px] text-slate-500">0{index + 1}</span>
                    </div>
                  ))}
                </div>

                <div className="rounded-lg border border-slate-800 bg-black/30 p-4 font-mono text-[11px] leading-6 text-slate-400">
                  <p><span className="text-cyan-400">&gt;</span> cloudwise plan --optimize</p>
                  <p><span className="text-emerald-400">✓</span> Estimated monthly cost: <span className="text-white">₹14,280</span></p>
                  <p><span className="text-emerald-400">✓</span> Deployment target ready</p>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Interactive CloudWise Workflow Section */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
        <div className="text-center space-y-4 max-w-3xl mx-auto">
          <h2 className="text-xs font-bold text-cyan-400 uppercase tracking-widest">End-To-End Architecture</h2>
          <h3 className="text-3xl sm:text-4xl font-bold text-white">The CloudWise Optimization Engine</h3>
          <p className="text-slate-400 text-sm sm:text-base">
            From initial resource sizing to automated GitHub file sync, provisioning, and cost tuning, our unified 5-step workflow ensures your infrastructure is right-sized.
          </p>
        </div>

        {/* Workflow Chain Visual Bar */}
        <div className="flex items-center justify-center gap-2 overflow-x-auto pb-2 text-xs font-semibold text-slate-300">
          <span className="px-3 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 whitespace-nowrap">1. Sizing</span>
          <span className="text-slate-600">→</span>
          <span className="px-3 py-1.5 rounded-lg bg-teal-500/10 border border-teal-500/30 text-teal-300 whitespace-nowrap">2. Compare & Recommend</span>
          <span className="text-slate-600">→</span>
          <span className="px-3 py-1.5 rounded-lg bg-violet-500/10 border border-violet-500/30 text-violet-300 whitespace-nowrap">3. Files & GitHub</span>
          <span className="text-slate-600">→</span>
          <span className="px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 whitespace-nowrap">4. Deploy</span>
          <span className="text-slate-600">→</span>
          <span className="px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 whitespace-nowrap">5. Cost Tuning</span>
        </div>

        {/* Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {workflowSteps.map((item, idx) => {
            const Icon = item.icon;
            return (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: idx * 0.1 }}
                className="glass-card p-6 rounded-2xl flex flex-col justify-between space-y-6 group"
              >
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className={`w-12 h-12 rounded-xl bg-gradient-to-tr ${item.color} p-0.5 shadow-md`}>
                      <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
                        <Icon className="w-6 h-6 text-white group-hover:scale-110 transition-transform" />
                      </div>
                    </div>
                    <span className="text-2xl font-black text-slate-700 group-hover:text-cyan-400 transition-colors">
                      {item.step}
                    </span>
                  </div>

                  <h4 className="text-xl font-bold text-white group-hover:text-cyan-300 transition-colors">
                    {item.title}
                  </h4>
                  <p className="text-slate-400 text-xs leading-relaxed">
                    {item.description}
                  </p>
                </div>

                <Link
                  to={item.route}
                  className="inline-flex items-center gap-2 text-xs font-bold text-cyan-400 hover:text-cyan-300 transition-colors pt-2 border-t border-slate-800/80"
                >
                  <span>Explore Module</span>
                  <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
                </Link>
              </motion.div>
            );
          })}
        </div>
      </section>

      {/* Feature Highlights */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="glass-panel p-8 sm:p-12 rounded-3xl space-y-8 border border-slate-800">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center">
            
            <div className="space-y-6">
              <span className="px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-semibold border border-emerald-500/30">
                Why CloudWise?
              </span>
              <h3 className="text-3xl font-extrabold text-white leading-tight">
                Eliminate Invisible Cloud Overspending
              </h3>
              <p className="text-slate-400 text-sm leading-relaxed">
                Engineering teams often over-specify vCPU and RAM when launching new services. CloudWise calculates precise workload specifications and continually optimizes active deployments.
              </p>

              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
                  <p className="text-xs text-slate-300"><strong className="text-white">Multi-Cloud Parity:</strong> Compare AWS, Azure, GCP, and DigitalOcean side-by-side with transparent monthly pricing.</p>
                </div>
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
                  <p className="text-xs text-slate-300"><strong className="text-white">Simulated Deployment Pipeline:</strong> Test cluster creation flow before committing live cloud spend.</p>
                </div>
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
                  <p className="text-xs text-slate-300"><strong className="text-white">Actionable Cost Tuning:</strong> Apply right-sizing, snapshot cleanup, and savings plans in one click.</p>
                </div>
              </div>

              <div className="pt-2">
                <Link
                  to="/estimation"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-sm transition-all shadow-lg shadow-cyan-500/20"
                >
                  <span>Start Free Estimate</span>
                  <ArrowRight size={16} />
                </Link>
              </div>
            </div>

            {/* Mock Dashboard Preview */}
            <div className="glass-card p-6 rounded-2xl border border-slate-700/60 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                  <span className="text-xs font-bold text-white">Live Cluster Summary</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 text-[10px] font-semibold border border-emerald-500/30">
                  Optimal State
                </span>
              </div>

              <div className="space-y-3 text-xs">
                <div className="flex justify-between items-center bg-slate-900/80 p-3 rounded-lg">
                  <span className="text-slate-400">Selected Provider</span>
                  <span className="text-cyan-300 font-bold">AWS (c6i.xlarge)</span>
                </div>
                <div className="flex justify-between items-center bg-slate-900/80 p-3 rounded-lg">
                  <span className="text-slate-400">Provisioned Nodes</span>
                  <span className="text-white font-bold">8 vCPU / 32 GB RAM</span>
                </div>
                <div className="flex justify-between items-center bg-slate-900/80 p-3 rounded-lg">
                  <span className="text-slate-400">Current Cost vs Savings</span>
                  <span className="text-emerald-400 font-bold">₹12,280/mo (-₹3,480/mo saved)</span>
                </div>
              </div>
            </div>

          </div>
        </div>
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
      </section>

      {/* Waitlist / Early Access Section */}
      <section className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="glass-panel p-8 sm:p-12 rounded-3xl text-center space-y-6 border border-cyan-500/30 bg-gradient-to-b from-slate-950 to-slate-900">
          <div className="w-12 h-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center mx-auto text-cyan-400">
            <Mail size={24} />
          </div>

          <div className="space-y-2 max-w-xl mx-auto">
            <h3 className="text-2xl sm:text-3xl font-extrabold text-white">
              Stay Ahead of Cloud Optimization
            </h3>
            <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
              Subscribe to receive weekly multi-cloud pricing benchmarks, FinOps right-sizing tips, and early access to our AI workload auto-scaler.
            </p>
          </div>

          {waitlistSuccess ? (
            <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-semibold flex items-center justify-center gap-2 max-w-md mx-auto">
              <Check size={16} />
              <span>You're on the list! Check your inbox soon for updates.</span>
            </div>
          ) : (
            <form onSubmit={handleWaitlistSubmit} className="flex flex-col sm:flex-row items-center gap-3 max-w-md mx-auto">
              <input
                type="email"
                required
                placeholder="rohan.mehta@company.in"
                value={waitlistEmail}
                onChange={(e) => setWaitlistEmail(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-3 text-xs text-white focus:outline-none focus:border-cyan-400"
              />
              <button
                type="submit"
                disabled={waitlistLoading}
                className="w-full sm:w-auto px-6 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs transition-all shadow-lg shadow-cyan-500/20 whitespace-nowrap flex items-center justify-center gap-1.5 active:scale-95 disabled:opacity-50"
              >
                {waitlistLoading ? <RefreshCw size={14} className="animate-spin" /> : <Send size={14} />}
                <span>Subscribe</span>
              </button>
            </form>
          )}

          {waitlistError && (
            <p className="text-xs text-rose-400">{waitlistError}</p>
          )}
        </div>
      </section>

    </div>
  );
};
