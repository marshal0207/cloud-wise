import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info';
}

interface ToastProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export const Toast: React.FC<ToastProps> = ({ toasts, onDismiss }) => {
  return (
    <div className="fixed top-20 right-4 z-50 flex flex-col gap-2 max-w-md w-full pointer-events-none px-4 sm:px-0">
      <AnimatePresence>
        {toasts.map((toast) => {
          const isSuccess = toast.type === 'success';
          const isError = toast.type === 'error';

          return (
            <motion.div
              key={toast.id}
              initial={{ opacity: 0, y: -20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              className={`pointer-events-auto p-4 rounded-2xl border backdrop-blur-xl shadow-2xl flex items-start gap-3 justify-between ${
                isSuccess
                  ? 'bg-slate-950/90 border-emerald-500/40 text-emerald-300 ring-1 ring-emerald-500/20'
                  : isError
                  ? 'bg-slate-950/90 border-rose-500/40 text-rose-300 ring-1 ring-rose-500/20'
                  : 'bg-slate-950/90 border-cyan-500/40 text-cyan-300 ring-1 ring-cyan-500/20'
              }`}
            >
              <div className="flex items-start gap-2.5">
                {isSuccess && <CheckCircle2 size={18} className="text-emerald-400 shrink-0 mt-0.5" />}
                {isError && <AlertCircle size={18} className="text-rose-400 shrink-0 mt-0.5" />}
                {!isSuccess && !isError && <Info size={18} className="text-cyan-400 shrink-0 mt-0.5" />}
                <p className="text-xs font-semibold leading-relaxed text-white">
                  {toast.message}
                </p>
              </div>

              <button
                onClick={() => onDismiss(toast.id)}
                className="text-slate-400 hover:text-white p-1 rounded-lg bg-slate-900 border border-slate-800 shrink-0 transition-colors"
              >
                <X size={14} />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
};
