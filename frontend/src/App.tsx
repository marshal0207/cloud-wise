import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { 
  Home as HomeIcon, 
  Folder,
  Calculator, 
  Sparkles, 
  FileCode,
  Rocket, 
  Zap, 
  Activity,
  Info, 
  Mail,
  User
} from 'lucide-react';

import { CloudWiseProvider } from '@/context/CloudWiseContext';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import { SlideTabItem } from '@/components/ui/slide-tabs';

import { Home } from '@/pages/Home';
import { Projects } from '@/pages/Projects';
import { Estimation } from '@/pages/Estimation';
import { Recommendation } from '@/pages/Recommendation';
import { GenerateFiles } from '@/pages/GenerateFiles';
import { Deployment } from '@/pages/Deployment';
import { Optimization } from '@/pages/Optimization';
import { Monitoring } from '@/pages/Monitoring';
import { About } from '@/pages/About';
import { Contact } from '@/pages/Contact';
import { Auth } from '@/pages/Auth';

const navItems: SlideTabItem[] = [
  { name: 'Home', url: '/', icon: HomeIcon },
  { name: 'Projects', url: '/projects', icon: Folder },
  { name: 'Estimation', url: '/estimation', icon: Calculator },
  { name: 'Recommend', url: '/recommendation', icon: Sparkles },
  { name: 'Files & GitHub', url: '/generate', icon: FileCode },
  { name: 'Deploy', url: '/deployment', icon: Rocket },
  { name: 'Monitoring', url: '/monitoring', icon: Activity },
  { name: 'Cost Tuning', url: '/optimization', icon: Zap },
  { name: 'About', url: '/about', icon: Info },
  { name: 'Contact', url: '/contact', icon: Mail },
];

const AnimatedRoutes: React.FC = () => {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={location.pathname}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, x: 0, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
        className="min-h-full"
      >
        <Routes location={location}>
          <Route path="/" element={<Home />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/estimation" element={<Estimation />} />
          <Route path="/recommendation" element={<Recommendation />} />
          <Route path="/generate" element={<GenerateFiles />} />
          <Route path="/deployment" element={<Deployment />} />
          <Route path="/optimization" element={<Optimization />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/about" element={<About />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/auth" element={<Auth />} />

          <Route path="*" element={<Home />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  );
};

export const App: React.FC = () => {
  return (
    <CloudWiseProvider>
      <BrowserRouter>
        <div className="flex flex-col min-h-screen relative bg-slate-950 text-slate-100">
          
          {/* Main Top Header */}
          <Header navItems={navItems} />

          {/* Main Viewport Content Container */}
          <main className="flex-1 pt-6 pb-12">
            <AnimatedRoutes />
          </main>

          {/* Footer */}
          <Footer />

        </div>
      </BrowserRouter>
    </CloudWiseProvider>
  );
};

export default App;
