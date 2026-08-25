import React from 'react';
import { Link } from 'react-router-dom';
import { 
  Info, 
  Cloud, 
  Target, 
  TrendingUp, 
  ShieldCheck, 
  Users, 
  Cpu, 
  CheckCircle2, 
  ArrowRight,
  Sparkles,
  Layers,
  Calculator,
  Rocket,
  FileCode,
  Activity,
  Zap,
  Award,
  Globe2,
  Server
} from 'lucide-react';

export const About: React.FC = () => {
  const steps = [
    {
      num: '01',
      title: 'Resource Sizing',
      icon: Calculator,
      desc: 'Define vCPU, RAM, storage, and expected traffic requirements to calculate real-world hardware profiles.',
      route: '/estimation'
    },
    {
      num: '02',
      title: 'Multi-Cloud Matching',
      icon: Sparkles,
      desc: 'Benchmark monthly and hourly instance rates across AWS, Azure, GCP, and DigitalOcean with AI reasoning.',
      route: '/recommendation'
    },
    {
      num: '03',
      title: 'Files & GitHub Sync',
      icon: FileCode,
      desc: 'Auto-generate Dockerfiles and CI/CD pipelines, preview code, and push directly to GitHub repositories.',
      route: '/generate'
    },
    {
      num: '04',
      title: 'Automated Provisioning',
      icon: Rocket,
      desc: 'Simulate cluster creation, VPC routing, and elastic IP attachment with live logs and rollback support.',
      route: '/deployment'
    },
    {
      num: '05',
      title: 'Cost Tuning',
      icon: Zap,
      desc: 'Apply 1-click recommendations to eliminate underutilized nodes, orphan storage, and idle DBs.',
      route: '/optimization'
    }
  ];

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-16">
      
      {/* Header */}
      <div className="text-center space-y-4 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold">
          <Info className="w-3.5 h-3.5" />
          <span>About CloudWise</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white leading-tight">
          Intelligent Multi-Cloud Planning & Continuous Optimization
        </h1>
        <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
          CloudWise was engineered to solve the multi-billion dollar problem of cloud resource waste, over-provisioning, and unpredictable infrastructure bills for modern engineering teams.
        </p>
      </div>

      {/* Metric Highlights */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass-card p-6 rounded-2xl text-center space-y-1 border border-slate-800">
          <p className="text-3xl sm:text-4xl font-extrabold text-cyan-400">₹20 Cr+</p>
          <p className="text-xs text-slate-400 font-medium">Cloud Waste Eliminated</p>
        </div>
        <div className="glass-card p-6 rounded-2xl text-center space-y-1 border border-slate-800">
          <p className="text-3xl sm:text-4xl font-extrabold text-indigo-400">450+</p>
          <p className="text-xs text-slate-400 font-medium">Production Clusters Sized</p>
        </div>
        <div className="glass-card p-6 rounded-2xl text-center space-y-1 border border-slate-800">
          <p className="text-3xl sm:text-4xl font-extrabold text-teal-400">99.99%</p>
          <p className="text-xs text-slate-400 font-medium">SLA Accuracy Target</p>
        </div>
        <div className="glass-card p-6 rounded-2xl text-center space-y-1 border border-slate-800">
          <p className="text-3xl sm:text-4xl font-extrabold text-amber-400">32%</p>
          <p className="text-xs text-slate-400 font-medium">Average Bill Reduction</p>
        </div>
      </div>

      {/* Main Problem & Solution Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        
        {/* Card 1: The Problem */}
        <div className="glass-panel p-8 rounded-3xl space-y-4 border border-rose-500/20 bg-rose-950/5">
          <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center">
            <Target className="w-5 h-5 text-rose-400" />
          </div>
          <h3 className="text-2xl font-bold text-white">The Problem We Solve</h3>
          <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
            Over 30% of global cloud spend is completely wasted on over-provisioned vCPU cores, idle staging nodes, unattached storage volumes, and non-optimized instances.
          </p>
          <ul className="space-y-2.5 text-xs text-slate-400 pt-2">
            <li className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-400 shrink-0" />
              <span>Lack of upfront capacity estimation before launching instances</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-400 shrink-0" />
              <span>Opaque pricing across AWS, Azure, GCP, and DigitalOcean</span>
            </li>
            <li className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-400 shrink-0" />
              <span>Manual rightsizing requiring complex script maintenance</span>
            </li>
          </ul>
        </div>

        {/* Card 2: The CloudWise Solution */}
        <div className="glass-panel p-8 rounded-3xl space-y-4 border border-cyan-500/30 bg-cyan-950/5">
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-cyan-400" />
          </div>
          <h3 className="text-2xl font-bold text-white">The CloudWise Solution</h3>
          <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
            CloudWise unifies estimation, multi-cloud matching, automated provisioning, live performance telemetry, and right-sizing optimization into a single fluid workflow.
          </p>
          <ul className="space-y-2.5 text-xs text-slate-400 pt-2">
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
              <span>Accurate workload sizing algorithm tailored to traffic and memory</span>
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
              <span>Side-by-side multi-cloud provider comparisons with SLA transparency</span>
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
              <span>Continuous 1-click optimization applying savings plans & rightsizing</span>
            </li>
          </ul>
        </div>

      </div>

      {/* How It Works Process Section */}
      <div className="space-y-8">
        <div className="text-center space-y-2 max-w-2xl mx-auto">
          <h2 className="text-xs font-bold text-cyan-400 uppercase tracking-widest">Architectural Methodology</h2>
          <h3 className="text-3xl font-extrabold text-white">How CloudWise Operates</h3>
          <p className="text-slate-400 text-xs sm:text-sm">
            Our 5-step pipeline bridges the gap between infrastructure design and live execution.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {steps.map((step) => {
            const Icon = step.icon;
            return (
              <div key={step.num} className="glass-card p-5 rounded-2xl space-y-3 flex flex-col justify-between border border-slate-800">
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
                      <Icon className="w-4 h-4 text-cyan-400" />
                    </div>
                    <span className="text-xs font-black text-slate-600">{step.num}</span>
                  </div>
                  <h4 className="text-sm font-bold text-white">{step.title}</h4>
                  <p className="text-[11px] text-slate-400 leading-relaxed">{step.desc}</p>
                </div>
                <Link to={step.route} className="inline-flex items-center gap-1 text-[11px] font-bold text-cyan-400 hover:text-cyan-300 pt-2 border-t border-slate-800">
                  <span>Explore</span>
                  <ArrowRight size={12} />
                </Link>
              </div>
            );
          })}
        </div>
      </div>

      {/* Who It's Built For Section */}
      <div className="glass-panel p-8 sm:p-10 rounded-3xl border border-slate-800 space-y-6">
        <div className="text-center space-y-2">
          <h2 className="text-xs font-bold text-cyan-400 uppercase tracking-widest">Built For Modern Engineering</h2>
          <h3 className="text-2xl sm:text-3xl font-extrabold text-white">Who Benefits from CloudWise</h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-2">
          
          <div className="glass-card p-6 rounded-2xl space-y-3 border border-slate-800">
            <Users className="w-6 h-6 text-cyan-400" />
            <h4 className="text-base font-bold text-white">DevOps & Site Reliability Engineers</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Eliminate guesswork when launching new microservices. Model exact instance capacity before provisioning production nodes.
            </p>
          </div>

          <div className="glass-card p-6 rounded-2xl space-y-3 border border-slate-800">
            <Globe2 className="w-6 h-6 text-indigo-400" />
            <h4 className="text-base font-bold text-white">SaaS Founders & CTOs</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Gain transparent multi-cloud unit economics. Compare AWS, GCP, Azure, and DigitalOcean rates before scaling your startup.
            </p>
          </div>

          <div className="glass-card p-6 rounded-2xl space-y-3 border border-slate-800">
            <Award className="w-6 h-6 text-emerald-400" />
            <h4 className="text-base font-bold text-white">FinOps & Infrastructure Leads</h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Continuously audit idle assets, orphan disks, and non-optimized nodes to slash monthly cloud bills automatically.
            </p>
          </div>

        </div>
      </div>

      {/* Vision CTA Banner */}
      <div className="glass-panel p-8 sm:p-12 rounded-3xl text-center space-y-6 border border-cyan-500/20 max-w-4xl mx-auto">
        <h3 className="text-2xl sm:text-3xl font-extrabold text-white">
          Our Vision: Transparent, Autonomous Cloud Operations
        </h3>
        <p className="text-slate-400 text-xs sm:text-sm max-w-2xl mx-auto leading-relaxed">
          We envision a future where cloud infrastructure self-tunes in real-time, delivering maximum performance at the lowest possible financial cost.
        </p>

        <div className="pt-2 flex justify-center">
          <Link
            to="/estimation"
            className="px-8 py-4 rounded-xl bg-gradient-to-r from-cyan-400 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-sm transition-all shadow-xl shadow-cyan-500/20 flex items-center gap-2"
          >
            <span>Try the CloudWise Workflow</span>
            <ArrowRight size={18} />
          </Link>
        </div>
      </div>

    </div>
  );
};
