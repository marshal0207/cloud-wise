import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';

import { CloudWiseProvider } from '@/context/CloudWiseContext';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';

import { Home } from '@/pages/Home';
import { Projects } from '@/pages/Projects';
import { Estimation } from '@/pages/Estimation';
import { Recommendation } from '@/pages/Recommendation';
import { GenerateFiles } from '@/pages/GenerateFiles';
import { ConnectAws } from '@/pages/ConnectAws';
import { ConnectAtlas } from '@/pages/ConnectAtlas';
import { Deployment } from '@/pages/Deployment';
import { DeploymentDetails } from '@/pages/DeploymentDetails';
import { Optimization } from '@/pages/Optimization';
import { Monitoring } from '@/pages/Monitoring';
import { About } from '@/pages/About';
import { Contact } from '@/pages/Contact';
import { Auth } from '@/pages/Auth';

const AnimatedRoutes: React.FC = () => {
  const location = useLocation();
  const isAuth = location.pathname === '/auth';

  return (
    <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 15, filter: 'blur(6px)', scale: 0.98 }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)', scale: 1 }}
          exit={{ opacity: 0, y: -15, filter: 'blur(6px)', scale: 0.98 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="min-h-full"
        >
        <Routes location={location}>
          <Route path="/" element={<Home />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/estimation" element={<Estimation />} />
          <Route path="/recommendation" element={<Recommendation />} />
          <Route path="/generate" element={<GenerateFiles />} />
          <Route path="/connect-aws" element={<ConnectAws />} />
          <Route path="/connect-atlas" element={<ConnectAtlas />} />
          <Route path="/deployment" element={<Deployment />} />
          <Route path="/deployment/:id" element={<DeploymentDetails />} />
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

// Layout wrapper that skips container/footer for auth page
const AppLayout: React.FC = () => {
  const location = useLocation();
  const isAuth = location.pathname === '/auth';

  if (isAuth) {
    return (
      <div className="relative bg-[#07090E] text-slate-100 min-h-screen">
        <Header />
        <Auth />
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen relative bg-[#07090E] text-slate-100">
      <Header />
      <main className="flex-1 pt-28 pb-12 flex flex-col items-center">
        <div className="w-full max-w-7xl px-4 sm:px-6 lg:px-8">
          <AnimatedRoutes />
        </div>
      </main>
      <Footer />
    </div>
  );
};


export const App: React.FC = () => {
  return (
    <CloudWiseProvider>
      <BrowserRouter>
        <AppLayout />
      </BrowserRouter>
    </CloudWiseProvider>
  );
};

export default App;
