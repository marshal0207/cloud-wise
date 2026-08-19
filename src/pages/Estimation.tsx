import React, { useState } from 'react';
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
  DollarSign
} from 'lucide-react';
import { useCloudWise, formatINR } from '@/context/CloudWiseContext';

export const Estimation: React.FC = () => {
  const navigate = useNavigate();
  const { estimation, calculateEstimation } = useCloudWise();

  const [formData, setFormData] = useState({
    appType: estimation.appType,
    vcpu: estimation.vcpu,
    ram: estimation.ram,
    storage: estimation.storage,
    traffic: estimation.traffic,
    region: estimation.region,
    performanceTier: estimation.performanceTier,
    budgetTier: estimation.budgetTier,
  });

  const [calculated, setCalculated] = useState(false);

  const handleInputChange = (field: string, value: any) => {
    const updated = { ...formData, [field]: value };
    setFormData(updated);
    calculateEstimation(updated);
  };

  const handleEstimate = async (e: React.FormEvent) => {
    e.preventDefault();
    calculateEstimation(formData);
    setCalculated(true);

    try {
      await fetch('/api/estimate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
    } catch (err) {
      console.warn('Backend server notification skipped:', err);
    }
  };

  const handleProceedToRecommendation = () => {
    calculateEstimation(formData);
    navigate('/recommendation');
  };

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      
      {/* Header */}
      <div className="text-center space-y-3 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold">
          <Calculator className="w-3.5 h-3.5" />
          <span>Step 1: Resource Estimator</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white">
          Estimate Workload Requirements
        </h1>
        <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
          Input your application specifications, expected traffic volume, and performance criteria to calculate optimal vCPU, RAM, storage, and cost parameters.
        </p>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Form Column (2 Cols on LG) */}
        <div className="lg:col-span-2 glass-panel p-6 sm:p-8 rounded-3xl space-y-6">
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
                  min={2}
                  max={64}
                  step={2}
                  value={formData.vcpu}
                  onChange={(e) => handleInputChange('vcpu', Number(e.target.value))}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span>2 Cores</span>
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
                  min={4}
                  max={256}
                  step={4}
                  value={formData.ram}
                  onChange={(e) => handleInputChange('ram', Number(e.target.value))}
                  className="w-full accent-indigo-400 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span>4 GB</span>
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
                  min={50}
                  max={2000}
                  step={50}
                  value={formData.storage}
                  onChange={(e) => handleInputChange('storage', Number(e.target.value))}
                  className="w-full accent-teal-400 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span>50 GB</span>
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
                  <option value="Kolkata (ap-east-2)">Kolkata (ap-east-2)</option>
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

            {/* Calculate CTA */}
            <div className="pt-2">
              <button
                type="submit"
                className="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-bold text-sm transition-all shadow-lg shadow-cyan-500/20 active:scale-98 flex items-center justify-center gap-2"
              >
                <Calculator className="w-5 h-5" />
                <span>Calculate Resource Requirements</span>
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
              <span className="px-2.5 py-1 rounded bg-cyan-500/10 text-cyan-300 text-xs font-bold border border-cyan-500/30">
                Calculated
              </span>
            </div>

            {/* Calculated specs summary */}
            <div className="space-y-4 text-xs">
              
              <div className="bg-slate-900/80 p-4 rounded-2xl border border-slate-800 space-y-1">
                <span className="text-slate-400 text-[11px]">Estimated Monthly Spend Range</span>
                <p className="text-2xl sm:text-3xl font-extrabold text-cyan-400 flex items-center gap-1">
                  {formatINR(estimation.calculatedResult.minCost)} - {formatINR(estimation.calculatedResult.maxCost)}
                  <span className="text-xs font-medium text-slate-400">/ mo</span>
                </p>
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
                  <span className="text-indigo-400 font-bold">{estimation.calculatedResult.suggestedInstances} Nodes (Load-Balanced)</span>
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
                <span>Get Cloud Recommendation</span>
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
