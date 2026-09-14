import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Sparkles, 
  Check, 
  ArrowRight, 
  ShieldCheck, 
  Cpu, 
  Server, 
  HardDrive, 
  Info, 
  X,
  Cloud
} from 'lucide-react';
import { useCloudWise, RecommendationOption, formatINR } from '@/context/CloudWiseContext';

export const Recommendation: React.FC = () => {
  const navigate = useNavigate();
  const { estimation, availableRecommendations, selectedRecommendation, setSelectedRecommendation } = useCloudWise();
  
  const [detailModalItem, setDetailModalItem] = useState<RecommendationOption | null>(null);
  const [recommendations, setRecommendations] = useState(availableRecommendations);
  const [awsPricingStatus, setAwsPricingStatus] = useState<'loading' | 'live' | 'estimate'>('loading');

  useEffect(() => {
    const loadAwsPricing = async () => {
      try {
        const response = await fetch(
          `/api/pricing/aws?instanceType=c6i.xlarge&region=${encodeURIComponent('Asia Pacific (Mumbai)')}`
        );
        const data = await response.json();
        if (!response.ok || !data.success) {
          throw new Error(data.error || 'AWS pricing unavailable');
        }

        setRecommendations((current) => current.map((recommendation) => (
          recommendation.id === 'aws-rec-1'
            ? {
                ...recommendation,
                monthlyCost: data.data.monthlyInr,
                hourlyCost: data.data.hourlyUsd,
                reasoning: `${(recommendation.reasoning || '').split(' Live AWS Pricing API rate:')[0]} Live AWS Pricing API rate: $${data.data.hourlyUsd}/hour, converted at ₹${data.data.usdToInrRate}/USD.`
              }
            : recommendation
        )));
        setAwsPricingStatus('live');
      } catch {
        setAwsPricingStatus('estimate');
      }
    };

    loadAwsPricing();
  }, []);

  const selectedDisplayRecommendation = recommendations.find(
    (recommendation) => recommendation.id === selectedRecommendation.id
  ) || selectedRecommendation;

  const handleSelectAndProceed = (rec: RecommendationOption) => {
    setSelectedRecommendation(rec);
    navigate('/generate');
  };

  const aiPick = recommendations.find((r) => r.badge === 'Recommended') || recommendations[0];

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      
      {/* Page Header */}
      <div className="text-center space-y-3 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Step 2: Multi-Cloud Comparison Engine</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white">
          Cloud Infrastructure Recommendations
        </h1>
        <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
          Based on your workload profile (<strong className="text-cyan-300">{estimation.appType}</strong> requiring ~{estimation.vcpu} vCPUs & {estimation.ram}GB RAM in {estimation.region}), we matched 4 top cloud configurations.
        </p>
        <p className="text-[11px] text-slate-500">
          AWS pricing: {awsPricingStatus === 'loading' ? 'loading live rate...' : awsPricingStatus === 'live' ? 'live AWS Pricing API' : 'estimated fallback'}; other providers are estimated.
        </p>
      </div>

      {/* AI Recommendation Reasoning Callout Banner */}
      <div className="glass-panel p-6 sm:p-8 rounded-3xl border border-cyan-500/40 bg-cyan-950/20 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-300">
              <Sparkles size={20} />
            </div>
            <div>
              <span className="text-[11px] font-extrabold text-cyan-400 uppercase tracking-widest block">AI-Suggested Top Pick</span>
              <h3 className="text-xl font-bold text-white flex items-center gap-2">
                <span>{aiPick.title}</span>
                <span className="px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 text-xs font-bold border border-cyan-500/40">
                  {aiPick.provider} • {formatINR(aiPick.monthlyCost)}/mo
                </span>
              </h3>
            </div>
          </div>
        </div>

        <div className="bg-slate-900/80 p-4 rounded-2xl border border-slate-800 space-y-2 text-xs">
          <span className="text-slate-400 font-bold uppercase tracking-wider block text-[10px]">AI Optimization Rationale & Tradeoffs</span>
          <p className="text-slate-200 leading-relaxed">
            {aiPick.reasoning || `${aiPick.title} provides the best price-to-performance ratio for ${estimation.appType} workloads with ${estimation.vcpu} vCPUs and ${estimation.ram}GB RAM, giving maximum reliability without exceeding your budget.`}
          </p>
        </div>
      </div>

      {/* Recommended Configuration Summary Banner */}
      <div className="glass-panel p-6 rounded-2xl border border-cyan-500/30 flex flex-col md:flex-row items-center justify-between gap-6">
        <div className="space-y-1 text-center md:text-left">
          <span className="text-xs font-semibold text-slate-400">Currently Selected Configuration</span>
          <p className="text-xl font-bold text-white flex items-center gap-2 justify-center md:justify-start">
            <span>{selectedDisplayRecommendation.title}</span>
            <span className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 text-xs font-semibold border border-cyan-500/40">
              {selectedDisplayRecommendation.badge}
            </span>
          </p>
          <p className="text-xs text-slate-400">
            {selectedDisplayRecommendation.specs.vcpu} vCPU • {selectedDisplayRecommendation.specs.ram}GB RAM • {selectedDisplayRecommendation.specs.storage} • {selectedDisplayRecommendation.reliability}
          </p>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right">
            <span className="text-[11px] text-slate-400 block">Est. Cost</span>
            <span className="text-2xl font-extrabold text-cyan-400">{formatINR(selectedDisplayRecommendation.monthlyCost)}/mo</span>
          </div>
          <button
            onClick={() => handleSelectAndProceed(selectedRecommendation)}
            className="px-6 py-3 rounded-xl bg-gradient-to-r from-cyan-400 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-sm transition-all shadow-lg shadow-cyan-500/20 flex items-center gap-2 active:scale-95 whitespace-nowrap"
          >
            <span>Continue to File Generation</span>
            <ArrowRight size={16} />
          </button>
        </div>
      </div>

      {/* Cards Comparison Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {recommendations.map((rec) => {
          const isSelected = selectedRecommendation.id === rec.id;

          const getBadgeColor = (badge: string) => {
            switch (badge) {
              case 'Recommended':
                return 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40';
              case 'Performance Option':
                return 'bg-purple-500/20 text-purple-300 border-purple-500/40';
              case 'Alternative':
                return 'bg-blue-500/20 text-blue-300 border-blue-500/40';
              case 'Budget Option':
                return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
              default:
                return 'bg-slate-800 text-slate-300 border-slate-700';
            }
          };

          return (
            <motion.div
              key={rec.id}
              whileHover={{ y: -4 }}
              transition={{ duration: 0.2 }}
              className={`glass-card p-6 rounded-2xl flex flex-col justify-between space-y-6 relative border transition-all ${
                isSelected 
                  ? 'border-cyan-400 ring-2 ring-cyan-500/30 bg-slate-900/90 shadow-xl shadow-cyan-950/50' 
                  : 'border-slate-800 hover:border-slate-700'
              }`}
            >
              <div className="space-y-4">
                {/* Badge & Provider */}
                <div className="flex justify-between items-start gap-2">
                  <span className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${getBadgeColor(rec.badge)}`}>
                    {rec.badge}
                  </span>
                  <span className="text-xs font-bold text-slate-400 flex items-center gap-1">
                    <Cloud className="w-3.5 h-3.5 text-cyan-400" />
                    {rec.provider}
                  </span>
                </div>

                {/* Title */}
                <div>
                  <h3 className="text-lg font-bold text-white leading-tight">
                    {rec.title}
                  </h3>
                  <span className="text-[11px] text-emerald-400 font-medium">{rec.reliability}</span>
                </div>

                {/* Pricing */}
                <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80 space-y-0.5">
                  <span className="text-[10px] text-slate-400">Monthly Estimate</span>
                  <div className="flex items-baseline gap-1">
                    <span className="text-2xl font-black text-cyan-300">{formatINR(rec.monthlyCost)}</span>
                    <span className="text-xs text-slate-400">/ mo (₹{rec.hourlyCost}/hr)</span>
                  </div>
                </div>

                {/* Specs List */}
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between items-center text-slate-300">
                    <span className="text-slate-400 flex items-center gap-1">
                      <Cpu size={14} className="text-cyan-400" /> vCPU
                    </span>
                    <span className="font-bold">{rec.specs.vcpu} Cores</span>
                  </div>

                  <div className="flex justify-between items-center text-slate-300">
                    <span className="text-slate-400 flex items-center gap-1">
                      <Server size={14} className="text-indigo-400" /> RAM
                    </span>
                    <span className="font-bold">{rec.specs.ram} GB</span>
                  </div>

                  <div className="flex justify-between items-center text-slate-300">
                    <span className="text-slate-400 flex items-center gap-1">
                      <HardDrive size={14} className="text-teal-400" /> Storage
                    </span>
                    <span className="font-bold text-[11px]">{rec.specs.storage}</span>
                  </div>
                </div>

              </div>

              {/* Action Buttons */}
              <div className="space-y-2 pt-4 border-t border-slate-800/80">
                <button
                  onClick={() => setSelectedRecommendation(rec)}
                  className={`w-full py-2.5 rounded-xl font-bold text-xs transition-all flex items-center justify-center gap-1.5 ${
                    isSelected
                      ? 'bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20'
                      : 'bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700/80'
                  }`}
                >
                  {isSelected && <Check size={14} />}
                  <span>{isSelected ? 'Selected Plan' : 'Select Configuration'}</span>
                </button>

                <button
                  onClick={() => setDetailModalItem(rec)}
                  className="w-full py-2 rounded-xl text-xs font-semibold text-slate-400 hover:text-cyan-300 hover:bg-slate-900/60 transition-colors flex items-center justify-center gap-1"
                >
                  <Info size={14} />
                  <span>View Details & Rationale</span>
                </button>
              </div>

            </motion.div>
          );
        })}
      </div>

      {/* Continue to File Generation Action Bar */}
      <div className="glass-panel p-6 rounded-3xl text-center space-y-4 max-w-xl mx-auto border border-cyan-500/20">
        <h4 className="text-base font-bold text-white">Accept {selectedDisplayRecommendation.provider} Configuration?</h4>
        <p className="text-xs text-slate-400">
          Selected <strong className="text-cyan-300">{selectedDisplayRecommendation.title}</strong> at {formatINR(selectedDisplayRecommendation.monthlyCost)}/month. Proceed to generate Dockerfile and CI/CD code.
        </p>
        <button
          onClick={() => handleSelectAndProceed(selectedRecommendation)}
          className="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-400 via-cyan-500 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-sm transition-all shadow-xl shadow-cyan-500/20 flex items-center justify-center gap-2 group active:scale-98"
        >
          <span>Continue to Dockerfile & GitHub Generation</span>
          <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
        </button>
      </div>

      {/* Details Modal */}
      <AnimatePresence>
        {detailModalItem && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="glass-panel max-w-lg w-full p-6 rounded-3xl space-y-6 border border-slate-700 shadow-2xl relative"
            >
              <button
                onClick={() => setDetailModalItem(null)}
                className="absolute top-5 right-5 text-slate-400 hover:text-white p-1 rounded-lg bg-slate-900 border border-slate-800"
              >
                <X size={18} />
              </button>

              <div className="space-y-1">
                <span className="text-xs font-bold text-cyan-400">{detailModalItem.provider} Configuration</span>
                <h3 className="text-xl font-extrabold text-white">{detailModalItem.title}</h3>
                <p className="text-xs text-slate-400">{detailModalItem.reliability}</p>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs bg-slate-900/80 p-4 rounded-2xl border border-slate-800">
                <div>
                  <span className="text-slate-400 block">vCPU Cores</span>
                  <span className="font-bold text-white">{detailModalItem.specs.vcpu} vCPUs</span>
                </div>
                <div>
                  <span className="text-slate-400 block">System RAM</span>
                  <span className="font-bold text-white">{detailModalItem.specs.ram} GB</span>
                </div>
                <div>
                  <span className="text-slate-400 block">Storage</span>
                  <span className="font-bold text-white">{detailModalItem.specs.storage}</span>
                </div>
                <div>
                  <span className="text-slate-400 block">Monthly Rate</span>
                  <span className="font-bold text-cyan-400">{formatINR(detailModalItem.monthlyCost)}/mo</span>
                </div>
              </div>

              <div className="space-y-2">
                <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Key Features & Security</h4>
                <ul className="space-y-2 text-xs">
                  {detailModalItem.features.map((feat, idx) => (
                    <li key={idx} className="flex items-center gap-2 text-slate-300">
                      <ShieldCheck size={14} className="text-cyan-400 shrink-0" />
                      <span>{feat}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="pt-2 flex gap-3">
                <button
                  onClick={() => {
                    setSelectedRecommendation(detailModalItem);
                    setDetailModalItem(null);
                  }}
                  className="flex-1 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs transition-all shadow-md shadow-cyan-500/20"
                >
                  Select This Plan
                </button>
                <button
                  onClick={() => setDetailModalItem(null)}
                  className="px-4 py-3 rounded-xl bg-slate-900 border border-slate-800 text-slate-300 font-semibold text-xs hover:bg-slate-800"
                >
                  Close
                </button>
              </div>

            </motion.div>
          </div>
        )}
      </AnimatePresence>

    </div>
  );
};
