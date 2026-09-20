import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Calculator, 
  Cpu, 
  HardDrive, 
  Globe, 
  Sliders, 
  ArrowRight, 
  Sparkles, 
  CheckCircle,
  Layers,
  Server,
  DollarSign,
  AlertTriangle,
  CheckCircle2,
  Zap
} from 'lucide-react';
import { useCloudWise, formatINR } from '@/context/CloudWiseContext';

export const Estimation: React.FC = () => {
  const navigate = useNavigate();
  const { estimation, calculateEstimation, updateActiveProject, activeProject, showToast } = useCloudWise();

  const [formData, setFormData] = useState({
    appType: activeProject?.estimation?.appType || estimation.appType,
    vcpu: activeProject?.estimation?.vcpu || estimation.vcpu,
    ram: activeProject?.estimation?.ram || estimation.ram,
    storage: activeProject?.estimation?.storage || estimation.storage,
    traffic: activeProject?.estimation?.traffic || estimation.traffic,
    region: activeProject?.estimation?.region || estimation.region,
    performanceTier: activeProject?.estimation?.performanceTier || estimation.performanceTier,
    budgetTier: activeProject?.estimation?.budgetTier || estimation.budgetTier,
  });

  const [calculated, setCalculated] = useState(false);
  const [freeTierStatus, setFreeTierStatus] = useState<any>(null);

  // Evaluate free tier when formData changes
  useEffect(() => {
    const isFree = formData.vcpu <= 2 && formData.ram <= 2 && formData.storage <= 30;
    const violations: string[] = [];
    if (formData.vcpu > 2) violations.push(`${formData.vcpu} vCPUs requested (Free Tier covers up to 1-2 vCPU t3.micro)`);
    if (formData.ram > 2) violations.push(`${formData.ram} GB RAM requested (Free Tier covers up to 1-2 GB RAM)`);
    if (formData.storage > 30) violations.push(`${formData.storage} GB storage requested (Free Tier covers up to 30 GB EBS)`);

    setFreeTierStatus({
      isFreeTier: isFree,
      violations,
      recommendationNeeded: !isFree,
    });
  }, [formData]);

  const handleInputChange = (field: string, value: any) => {
    const updated = { ...formData, [field]: value };
    setFormData(updated);
    calculateEstimation(updated);
  };

  const applyFreeTierRecommendation = () => {
    const updated = {
      ...formData,
      vcpu: 2,
      ram: 2,
      storage: 30,
      budgetTier: 'Economy',
    };
    setFormData(updated);
    calculateEstimation(updated);
    showToast('Applied AWS Free Tier recommendation (t3.micro - $0/mo)', 'success');
  };

  const applyLowCostRecommendation = () => {
    const updated = {
      ...formData,
      vcpu: 2,
      ram: 4,
      storage: 50,
      budgetTier: 'Economy',
    };
    setFormData(updated);
    calculateEstimation(updated);
    showToast('Applied Low-Cost recommendation (t3.small - ~$15/mo)', 'success');
  };

  const handleEstimate = async (e: React.FormEvent) => {
    e.preventDefault();
    calculateEstimation(formData);
    setCalculated(true);

    try {
      const res = await fetch('/api/estimate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
      const data = await res.json();
      if (data.success && data.freeTierStatus) {
        setFreeTierStatus(data.freeTierStatus);
      }
    } catch (err) {
      console.warn('Backend server notification skipped:', err);
    }

    if (activeProject) {
      updateActiveProject({
        estimation: {
          ...estimation,
          ...formData,
        }
      });
    }
  };

  const handleProceedToRecommendation = () => {
    calculateEstimation(formData);
    if (activeProject) {
      updateActiveProject({
        currentStep: 'recommendation',
        estimation: {
          ...estimation,
          ...formData,
        }
      });
    }
    navigate('/recommendation');
  };

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      
      {/* Header */}
      <div className="text-center space-y-3 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold">
          <Calculator className="w-3.5 h-3.5" />
          <span>Step 1: Resource Estimator & Free Tier Validator</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white">
          Estimate Workload & Free Tier Validation
        </h1>
        <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
          Input your project application specifications. CloudWise automatically verifies AWS Free Tier compliance and suggests cost-optimised instance configurations.
        </p>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Form Column (2 Cols on LG) */}
        <div className="lg:col-span-2 glass-panel p-6 sm:p-8 rounded-3xl space-y-6 border border-slate-800">
          <form onSubmit={handleEstimate} className="space-y-6">
            
            {/* Application Type */}
            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                <Layers className="w-4 h-4 text-cyan-400" />
                <span>Application Workload Type</span>
              </label>
              <select
                value={formData.appType}
                onChange={(e) => handleInputChange('appType', e.target.value)}
                className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400"
              >
                <option value="Microservices & Web APIs">Microservices & Web APIs</option>
                <option value="E-Commerce & High Traffic Portal">E-Commerce & High Traffic Portal</option>
                <option value="AI / ML Model Inference & Training">AI / ML Model Inference & Training</option>
                <option value="Data Analytics & ETL Pipeline">Data Analytics & ETL Pipeline</option>
                <option value="Relational / NoSQL Database Node">Relational / NoSQL Database Node</option>
              </select>
            </div>

            {/* vCPU & RAM sliders */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              
              {/* vCPU */}
              <div className="space-y-2 bg-slate-900/60 p-4 rounded-2xl border border-slate-800">
                <div className="flex justify-between items-center text-xs font-bold">
                  <span className="text-slate-300 flex items-center gap-1.5">
                    <Cpu className="w-4 h-4 text-cyan-400" />
                    vCPU Cores
                  </span>
                  <span className="text-cyan-400 font-extrabold text-sm">{formData.vcpu} vCPUs</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={64}
                  step={1}
                  value={formData.vcpu}
                  onChange={(e) => handleInputChange('vcpu', Number(e.target.value))}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span>1 Core (Free Tier)</span>
                  <span>16 Cores</span>
                  <span>64 Cores</span>
                </div>
              </div>

              {/* RAM */}
              <div className="space-y-2 bg-slate-900/60 p-4 rounded-2xl border border-slate-800">
                <div className="flex justify-between items-center text-xs font-bold">
                  <span className="text-slate-300 flex items-center gap-1.5">
                    <Server className="w-4 h-4 text-indigo-400" />
                    System RAM
                  </span>
                  <span className="text-indigo-400 font-extrabold text-sm">{formData.ram} GB</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={256}
                  step={1}
                  value={formData.ram}
                  onChange={(e) => handleInputChange('ram', Number(e.target.value))}
                  className="w-full accent-indigo-400 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span>1 GB (Free Tier)</span>
                  <span>64 GB</span>
                  <span>256 GB</span>
                </div>
              </div>

            </div>

            {/* Storage & Expected Traffic */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              
              {/* Storage */}
              <div className="space-y-2 bg-slate-900/60 p-4 rounded-2xl border border-slate-800">
                <div className="flex justify-between items-center text-xs font-bold">
                  <span className="text-slate-300 flex items-center gap-1.5">
                    <HardDrive className="w-4 h-4 text-teal-400" />
                    Storage Capacity
                  </span>
                  <span className="text-teal-400 font-extrabold text-sm">{formData.storage} GB</span>
                </div>
                <input
                  type="range"
                  min={10}
                  max={2000}
                  step={10}
                  value={formData.storage}
                  onChange={(e) => handleInputChange('storage', Number(e.target.value))}
                  className="w-full accent-teal-400 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span>30 GB (Free Tier)</span>
                  <span>500 GB</span>
                  <span>2000 GB</span>
                </div>
              </div>

              {/* Traffic */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                  <Globe className="w-4 h-4 text-cyan-400" />
                  <span>Expected Traffic / Requests</span>
                </label>
                <select
                  value={formData.traffic}
                  onChange={(e) => handleInputChange('traffic', e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-400"
                >
                  <option value="100,000 req/day">100,000 requests/day (Low)</option>
                  <option value="1,000,000 req/day">1,000,000 requests/day (Medium)</option>
                  <option value="5,000,000 req/day">5,000,000 requests/day (High)</option>
                  <option value="20,000,000 req/day">20,000,000+ requests/day (Enterprise)</option>
                </select>
              </div>

            </div>

            {/* Region & Performance / Budget Tiers */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              
              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-400">Deployment Region</label>
                <select
                  value={formData.region}
                  onChange={(e) => handleInputChange('region', e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2.5 text-xs text-white focus:border-cyan-400"
                >
                  <option value="Gujarat (GIFT City / Gandhinagar)">Gujarat (GIFT City / Gandhinagar)</option>
                  <option value="Mumbai (ap-south-1)">Mumbai (ap-south-1)</option>
                  <option value="Bengaluru (ap-south-2)">Bengaluru (ap-south-2)</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-400">Performance Requirement</label>
                <select
                  value={formData.performanceTier}
                  onChange={(e) => handleInputChange('performanceTier', e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2.5 text-xs text-white focus:border-cyan-400"
                >
                  <option value="Standard">Standard Tier</option>
                  <option value="High Performance">High Performance (Low Latency)</option>
                  <option value="Compute Optimized">Compute Optimized</option>
                  <option value="Memory Optimized">Memory Optimized</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-400">Budget Preference</label>
                <select
                  value={formData.budgetTier}
                  onChange={(e) => handleInputChange('budgetTier', e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2.5 text-xs text-white focus:border-cyan-400"
                >
                  <option value="Economy">Economy (Cost Efficient)</option>
                  <option value="Balanced">Balanced (Cost & SLA)</option>
                  <option value="High Availability">High Availability Enterprise</option>
                </select>
              </div>

            </div>

            {/* Free Tier Recommendation Banner */}
            {freeTierStatus?.recommendationNeeded && (
              <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs space-y-3">
                <div className="flex items-start gap-2.5">
                  <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-extrabold text-amber-300 text-sm">Notice: Selected Configuration Exceeds AWS Free Tier</h4>
                    <p className="text-amber-200/90 text-xs pt-1 leading-relaxed">
                      You selected {formData.vcpu} vCPUs, {formData.ram}GB RAM, and {formData.storage}GB storage. If your project is in development, staging, or has moderate traffic, switching to Free Tier or Low Cost can save up to 100% of your cloud bill.
                    </p>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 pt-1">
                  <button
                    type="button"
                    onClick={applyFreeTierRecommendation}
                    className="px-3.5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs transition-all flex items-center justify-center gap-1.5 shadow"
                  >
                    <Zap size={14} />
                    <span>Apply AWS Free Tier (t3.micro - $0/mo)</span>
                  </button>

                  <button
                    type="button"
                    onClick={applyLowCostRecommendation}
                    className="px-3.5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold text-xs transition-all flex items-center justify-center gap-1.5"
                  >
                    <span>Apply Low Cost (t3.small - ~$15/mo)</span>
                  </button>
                </div>
              </div>
            )}

            {!freeTierStatus?.recommendationNeeded && (
              <div className="p-3.5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2.5 font-semibold">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>🟢 Workload is 100% AWS Free Tier Eligible (t3.micro, 1-2 vCPU, 30GB EBS - $0/mo)</span>
              </div>
            )}

            {/* Calculate CTA */}
            <div className="pt-2">
              <button
                type="submit"
                className="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-bold text-sm transition-all shadow-lg shadow-cyan-500/20 active:scale-98 flex items-center justify-center gap-2"
              >
                <Calculator className="w-5 h-5" />
                <span>Calculate & Check Free Tier Compliance</span>
              </button>
            </div>

          </form>
        </div>

        {/* Results Card (1 Col) */}
        <div className="space-y-6">
          <div className="glass-panel p-6 sm:p-8 rounded-3xl space-y-6 border border-cyan-500/20">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-cyan-400" />
                <span>Suggested Profile</span>
              </h3>
              <span className={`px-2.5 py-1 rounded text-xs font-bold border ${freeTierStatus?.isFreeTier ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40' : 'bg-amber-500/20 text-amber-300 border-amber-500/40'}`}>
                {freeTierStatus?.isFreeTier ? 'Free Tier' : 'Standard Billing'}
              </span>
            </div>

            {/* Calculated specs summary */}
            <div className="space-y-4 text-xs">
              
              <div className="bg-slate-900/80 p-4 rounded-2xl border border-slate-800 space-y-1">
                <span className="text-slate-400 text-[11px]">Estimated Monthly Spend Range</span>
                <p className="text-2xl sm:text-3xl font-extrabold text-cyan-400 flex items-center gap-1">
                  {freeTierStatus?.isFreeTier ? '₹0' : `${formatINR(estimation.calculatedResult.minCost)} - ${formatINR(estimation.calculatedResult.maxCost)}`}
                  <span className="text-xs font-medium text-slate-400">/ mo</span>
                </p>
                {freeTierStatus?.isFreeTier && (
                  <p className="text-[10px] text-emerald-400 font-bold pt-1">
                    🎉 100% Free under AWS 12-Month Free Tier Trial
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-center bg-slate-900/40 p-3 rounded-xl">
                  <span className="text-slate-400">Target vCPU Cores</span>
                  <span className="text-white font-bold">{formData.vcpu} Cores</span>
                </div>

                <div className="flex justify-between items-center bg-slate-900/40 p-3 rounded-xl">
                  <span className="text-slate-400">Allocated RAM</span>
                  <span className="text-white font-bold">{formData.ram} GB</span>
                </div>

                <div className="flex justify-between items-center bg-slate-900/40 p-3 rounded-xl">
                  <span className="text-slate-400">Suggested Node Count</span>
                  <span className="text-indigo-400 font-bold">{freeTierStatus?.isFreeTier ? 1 : estimation.calculatedResult.suggestedInstances} Nodes</span>
                </div>

                <div className="flex justify-between items-center bg-slate-900/40 p-3 rounded-xl">
                  <span className="text-slate-400">Estimated Bandwidth</span>
                  <span className="text-teal-400 font-bold">{estimation.calculatedResult.bandwidthGB} GB / mo</span>
                </div>
              </div>

            </div>

            {/* Next Step CTA */}
            <div className="pt-2 space-y-3">
              <button
                onClick={handleProceedToRecommendation}
                className="w-full py-4 rounded-xl bg-gradient-to-r from-emerald-400 to-teal-500 hover:from-emerald-300 hover:to-teal-400 text-slate-950 font-bold text-sm transition-all shadow-lg shadow-emerald-500/20 active:scale-95 flex items-center justify-center gap-2 group"
              >
                <span>Save & Get Cloud Recommendation</span>
                <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </button>
              <p className="text-[11px] text-slate-400 text-center">
                Passes estimated requirements directly to multi-cloud provider matching engine.
              </p>
            </div>

          </div>
        </div>

      </div>

    </div>
  );
};
