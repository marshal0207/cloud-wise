import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Zap, 
  TrendingDown, 
  Check, 
  Sliders, 
  Info, 
  X, 
  Sparkles
} from 'lucide-react';
import { useCloudWise, OptimizationItem, formatINR } from '@/context/CloudWiseContext';

export const Optimization: React.FC = () => {
  const { 
    selectedRecommendation, 
    optimizations, 
    applyOptimization, 
    totalMonthlySavings, 
    effectiveMonthlyCost 
  } = useCloudWise();

  const [detailItem, setDetailItem] = useState<OptimizationItem | null>(null);

  const initialCost = selectedRecommendation.monthlyCost;
  const savingsPercent = Math.round((totalMonthlySavings / initialCost) * 100) || 0;

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      
      {/* Page Header */}
      <div className="text-center space-y-3 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-semibold">
          <Zap className="w-3.5 h-3.5" />
          <span>Step 5: Resource & Cost Optimization</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white">
          Cloud Cost Tuning & Recommendations
        </h1>
        <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
          Apply automated optimization policies to downsize underutilized nodes, clean up orphan disks, and commit to savings plans.
        </p>
      </div>

      {/* Financial Summary Cards Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* Card 1: Baseline Cost */}
        <div className="glass-card p-6 rounded-3xl space-y-2 border border-slate-800">
          <span className="text-xs font-semibold text-slate-400">Current Monthly Spend</span>
          <p className="text-3xl font-extrabold text-white">{formatINR(initialCost)} <span className="text-xs font-normal text-slate-400">/ mo</span></p>
          <p className="text-xs text-slate-400">Baseline on-demand provisioned rate</p>
        </div>

        {/* Card 2: Potential / Active Savings */}
        <div className="glass-card p-6 rounded-3xl space-y-2 border border-emerald-500/40 bg-emerald-950/10">
          <div className="flex justify-between items-center text-xs font-semibold text-emerald-400">
            <span>Monthly Savings Realized</span>
            <TrendingDown className="w-4 h-4" />
          </div>
          <p className="text-3xl font-extrabold text-emerald-400">{formatINR(totalMonthlySavings)} <span className="text-xs font-normal text-emerald-300">/ mo</span></p>
          <p className="text-xs text-emerald-300 font-medium">
            {savingsPercent > 0 ? `Reduced spend by ${savingsPercent}%!` : 'Select optimizations below to apply savings'}
          </p>
        </div>

        {/* Card 3: Optimized Cost */}
        <div className="glass-card p-6 rounded-3xl space-y-2 border border-cyan-500/40 bg-cyan-950/10">
          <div className="flex justify-between items-center text-xs font-semibold text-cyan-400">
            <span>Tuned Monthly Cost</span>
            <Sparkles className="w-4 h-4" />
          </div>
          <p className="text-3xl font-extrabold text-cyan-300">{formatINR(effectiveMonthlyCost)} <span className="text-xs font-normal text-cyan-400">/ mo</span></p>
          <p className="text-xs text-cyan-400 font-medium">Optimized multi-cloud execution</p>
        </div>

      </div>

      {/* Optimization Cards Grid */}
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Sliders className="w-5 h-5 text-cyan-400" />
            <span>Actionable Optimization Opportunities</span>
          </h2>
          <span className="text-xs text-slate-400">
            {optimizations.filter((o) => o.applied).length} of {optimizations.length} Applied
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {optimizations.map((item) => {
            return (
              <motion.div
                key={item.id}
                whileHover={{ y: -3 }}
                className={`glass-card p-6 rounded-3xl flex flex-col justify-between space-y-6 border transition-all ${
                  item.applied
                    ? 'border-emerald-500/50 bg-emerald-950/10 ring-1 ring-emerald-500/30'
                    : 'border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="space-y-4">
                  <div className="flex justify-between items-start gap-2">
                    <span className="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider bg-slate-800 text-slate-300 border border-slate-700">
                      {item.category}
                    </span>

                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      item.impact === 'High' 
                        ? 'bg-amber-500/20 text-amber-300' 
                        : 'bg-cyan-500/20 text-cyan-300'
                    }`}>
                      {item.impact} Impact
                    </span>
                  </div>

                  <div>
                    <h3 className="text-lg font-bold text-white leading-snug">
                      {item.title}
                    </h3>
                    <p className="text-xs text-slate-400 pt-1 leading-relaxed">
                      {item.description}
                    </p>
                  </div>

                  <div className="bg-slate-950/60 p-3 rounded-2xl border border-slate-800 flex items-center justify-between text-xs">
                    <span className="text-slate-400">Estimated Monthly Impact</span>
                    <span className="font-extrabold text-emerald-400 text-sm">
                      Save {formatINR(item.savings)} / month
                    </span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-3 pt-2 border-t border-slate-800/80">
                  <button
                    onClick={() => applyOptimization(item.id)}
                    className={`flex-1 py-3 rounded-xl font-bold text-xs transition-all flex items-center justify-center gap-1.5 active:scale-95 ${
                      item.applied
                        ? 'bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/20'
                        : 'bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 shadow-md shadow-cyan-500/20'
                    }`}
                  >
                    {item.applied ? <Check size={16} /> : <Zap size={16} />}
                    <span>{item.applied ? 'Recommendation Applied' : 'Apply Recommendation'}</span>
                  </button>

                  <button
                    onClick={() => setDetailItem(item)}
                    className="px-3.5 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 font-semibold text-xs transition-colors flex items-center justify-center gap-1"
                  >
                    <Info size={14} />
                    <span>Details</span>
                  </button>
                </div>

              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Details Modal */}
      <AnimatePresence>
        {detailItem && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="glass-panel max-w-lg w-full p-6 rounded-3xl space-y-6 border border-slate-700 shadow-2xl relative"
            >
              <button
                onClick={() => setDetailItem(null)}
                className="absolute top-5 right-5 text-slate-400 hover:text-white p-1 rounded-lg bg-slate-900 border border-slate-800"
              >
                <X size={18} />
              </button>

              <div className="space-y-1">
                <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">{detailItem.category} Optimization</span>
                <h3 className="text-xl font-extrabold text-white">{detailItem.title}</h3>
              </div>

              <div className="bg-slate-900/80 p-4 rounded-2xl border border-slate-800 space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-400">Original Item Spend:</span>
                  <span className="font-bold text-white">{formatINR(detailItem.currentCost)}/mo</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Net Monthly Savings:</span>
                  <span className="font-bold text-emerald-400">{formatINR(detailItem.savings)}/mo</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Tuned Cost:</span>
                  <span className="font-bold text-cyan-300">{formatINR(detailItem.currentCost - detailItem.savings)}/mo</span>
                </div>
              </div>

              <p className="text-xs text-slate-300 leading-relaxed">
                {detailItem.description}
              </p>

              <div className="pt-2 flex gap-3">
                <button
                  onClick={() => {
                    applyOptimization(detailItem.id);
                    setDetailItem(null);
                  }}
                  className="flex-1 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs transition-all shadow-md shadow-cyan-500/20"
                >
                  {detailItem.applied ? 'Revert Optimization' : 'Apply Now'}
                </button>
                <button
                  onClick={() => setDetailItem(null)}
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
