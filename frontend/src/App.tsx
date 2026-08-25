import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { 
  Home as HomeIcon, 
  Folder,
  Calculator, 
  Sparkles, 
  FileCode,
  Rocket, 
  Zap, 
  Info, 
  Mail,
  User
} from 'lucide-react';

import { CloudWiseProvider } from '@/context/CloudWiseContext';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import { NavBar, NavItem } from '@/components/ui/tubelight-navbar';

import { Home } from '@/pages/Home';
import { Projects } from '@/pages/Projects';
import { Estimation } from '@/pages/Estimation';
import { Recommendation } from '@/pages/Recommendation';
import { GenerateFiles } from '@/pages/GenerateFiles';
import { Deployment } from '@/pages/Deployment';
import { Optimization } from '@/pages/Optimization';
import { About } from '@/pages/About';
import { Contact } from '@/pages/Contact';
import { Auth } from '@/pages/Auth';

const navItems: NavItem[] = [
  { name: 'Home', url: '/', icon: HomeIcon },
  { name: 'Projects', url: '/projects', icon: Folder },
  { name: 'Estimation', url: '/estimation', icon: Calculator },
  { name: 'Recommend', url: '/recommendation', icon: Sparkles },
  { name: 'Files & GitHub', url: '/generate', icon: FileCode },
  { name: 'Deploy', url: '/deployment', icon: Rocket },
  { name: 'Cost Tuning', url: '/optimization', icon: Zap },
  { name: 'About', url: '/about', icon: Info },
  { name: 'Contact', url: '/contact', icon: Mail },
];

export const App: React.FC = () => {
  return (
    <CloudWiseProvider>
      <BrowserRouter>
        <div className="flex flex-col min-h-screen relative bg-slate-950 text-slate-100">
          
          {/* Main Top Header */}
          <Header />

          {/* Tubelight Floating Navbar */}
          <NavBar items={navItems} />

          {/* Main Viewport Content Container */}
          <main className="flex-1 pt-6 pb-28 sm:pb-28">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/projects" element={<Projects />} />
              <Route path="/estimation" element={<Estimation />} />
              <Route path="/recommendation" element={<Recommendation />} />
              <Route path="/generate" element={<GenerateFiles />} />
              <Route path="/deployment" element={<Deployment />} />
              <Route path="/optimization" element={<Optimization />} />
              <Route path="/about" element={<About />} />
              <Route path="/contact" element={<Contact />} />
              <Route path="/auth" element={<Auth />} />
              {/* Module 8 is intentionally excluded. Redirect any old /monitoring links to /projects */}
              <Route path="/monitoring" element={<Navigate to="/projects" replace />} />
              {/* Fallback route back to Home */}
              <Route path="*" element={<Home />} />
            </Routes>
          </main>

          {/* Footer */}
          <Footer />

        </div>
      </BrowserRouter>
    </CloudWiseProvider>
  );
};

export default App;
