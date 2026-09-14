import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  Mail, 
  Send, 
  CheckCircle2, 
  MessageSquare, 
  Phone, 
  MapPin, 
  HelpCircle, 
  RefreshCw,
  AlertCircle
} from 'lucide-react';

export const Contact: React.FC = () => {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    subject: 'Cloud Resource Consultation',
    message: '',
  });

  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const [responseId, setResponseId] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.email || !formData.message) return;

    setLoading(true);
    setError('');

    try {
      const res = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to send message.');
      }

      setSubmitted(true);
      if (data.data?.id) {
        setResponseId(data.data.id);
      }
    } catch (err: any) {
      setError(err.message || 'Error submitting message. Please check backend connection.');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setFormData({
      name: '',
      email: '',
      subject: 'Cloud Resource Consultation',
      message: '',
    });
    setSubmitted(false);
    setError('');
    setResponseId(null);
  };

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-12">
      
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, x: -24 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.45, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
        className="text-center space-y-3 max-w-3xl mx-auto"
      >
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-semibold">
          <Mail className="w-3.5 h-3.5" />
          <span>Contact CloudWise</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white">
          Get in Touch with Our Cloud Engineers
        </h1>
        <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
          Have questions about multi-cloud estimation, custom enterprise SLA matching, or cost optimization strategies? Send us a message below.
        </p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Contact Information & Support Cards */}
        <motion.div
          initial={{ opacity: 0, x: -32 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, delay: 0.16, ease: [0.22, 1, 0.36, 1] }}
          className="space-y-6 lg:col-span-1"
        >
          
          <div className="glass-panel p-6 rounded-3xl space-y-6 border border-slate-800">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-cyan-400" />
              <span>Direct Channels</span>
            </h3>

            <div className="space-y-4 text-xs">
              
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center shrink-0">
                  <Mail className="w-4 h-4 text-cyan-400" />
                </div>
                <div>
                  <span className="text-slate-400 block">Email Support</span>
                  <span className="font-bold text-white">support@cloudwise.app</span>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center shrink-0">
                  <Phone className="w-4 h-4 text-indigo-400" />
                </div>
                <div>
                  <span className="text-slate-400 block">Enterprise Sales</span>
                  <span className="font-bold text-white">+91 79 5550 WISE</span>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-lg bg-teal-500/10 border border-teal-500/30 flex items-center justify-center shrink-0">
                  <MapPin className="w-4 h-4 text-teal-400" />
                </div>
                <div>
                  <span className="text-slate-400 block">Headquarters</span>
                  <span className="font-bold text-white">GIFT City, Gandhinagar • Gujarat, India</span>
                </div>
              </div>

            </div>
          </div>

          <div className="glass-card p-6 rounded-3xl space-y-3 border border-slate-800">
            <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <HelpCircle size={16} className="text-cyan-400" />
              <span>Response Time</span>
            </h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Our cloud architects typically respond to technical inquiries within 2 business hours.
            </p>
          </div>

        </motion.div>

        {/* Contact Form Column */}
        <motion.div
          initial={{ opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.55, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          className="lg:col-span-2 glass-panel p-6 sm:p-8 rounded-3xl border border-slate-800 space-y-6"
        >
          
          {submitted ? (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="py-12 text-center space-y-6"
            >
              <div className="w-16 h-16 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center mx-auto text-emerald-400">
                <CheckCircle2 size={36} />
              </div>

              <div className="space-y-2 max-w-md mx-auto">
                <h3 className="text-2xl font-bold text-white">Message Transmitted!</h3>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Thank you, <strong className="text-cyan-300">{formData.name}</strong>. Your inquiry regarding <strong className="text-white">"{formData.subject}"</strong> has been successfully received by our backend storage.
                </p>
                {responseId && (
                  <p className="text-[11px] text-slate-400 font-mono pt-1">
                    Ticket Reference ID: <span className="text-cyan-400">{responseId}</span>
                  </p>
                )}
              </div>

              <div className="pt-4">
                <button
                  onClick={handleReset}
                  className="px-6 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 font-semibold text-xs transition-colors inline-flex items-center gap-2"
                >
                  <RefreshCw size={14} />
                  <span>Send Another Message</span>
                </button>
              </div>
            </motion.div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-6">
              
              {error && (
                <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
                  <AlertCircle size={16} className="shrink-0 text-rose-400" />
                  <span>{error}</span>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-300">Your Full Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Rohan Mehta"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-400"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-slate-300">Email Address</label>
                  <input
                    type="email"
                    required
                    placeholder="rohan.mehta@company.in"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-400"
                  />
                </div>

              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-300">Topic / Inquiry Category</label>
                <select
                  value={formData.subject}
                  onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-400"
                >
                  <option value="Cloud Resource Consultation">Cloud Resource Consultation</option>
                  <option value="Multi-Cloud Pricing Benchmark">Multi-Cloud Pricing Benchmark</option>
                  <option value="Enterprise SLA & Dedicated Support">Enterprise SLA & Dedicated Support</option>
                  <option value="Feature Request / Feedback">Feature Request / Feedback</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-300">Message Content</label>
                <textarea
                  rows={5}
                  required
                  placeholder="Describe your cloud architecture requirements or questions..."
                  value={formData.message}
                  onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-cyan-400"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-400 to-blue-600 hover:from-cyan-300 hover:to-blue-500 text-slate-950 font-bold text-sm transition-all shadow-xl shadow-cyan-500/20 flex items-center justify-center gap-2 active:scale-98 disabled:opacity-50"
              >
                {loading ? <RefreshCw size={18} className="animate-spin" /> : <Send size={18} />}
                <span>{loading ? 'Transmitting to Server...' : 'Submit Message'}</span>
              </button>

            </form>
          )}

        </motion.div>

      </div>

    </div>
  );
};
