import React, { createContext, useContext, useState, useEffect } from 'react';
import { Toast, ToastMessage } from '@/components/Toast';

export const formatINR = (val: number) => {
  if (isNaN(val)) return '₹0';
  return '₹' + Math.round(val).toLocaleString('en-IN');
};

export interface UserProfile {
  id?: string;
  name: string;
  email: string;
  company: string;
  role?: 'owner' | 'editor' | 'viewer' | 'admin';
}

export interface EstimationData {
  appType: string;
  vcpu: number;
  ram: number; // GB
  storage: number; // GB
  traffic: string;
  region: string;
  performanceTier: string;
  budgetTier: string;
  calculatedResult: {
    minCost: number;
    maxCost: number;
    suggestedInstances: number;
    bandwidthGB: number;
  };
}

export interface RecommendationOption {
  id: string;
  title: string;
  provider: 'AWS' | 'Azure' | 'GCP' | 'DigitalOcean';
  badge: 'Recommended' | 'Alternative' | 'Budget Option' | 'Performance Option';
  specs: {
    vcpu: number;
    ram: number;
    storage: string;
    network: string;
  };
  monthlyCost: number;
  hourlyCost: number;
  reliability: string;
  features: string[];
  reasoning?: string;
}

export interface DeploymentDetails {
  status: 'idle' | 'preparing' | 'provisioning' | 'configuring' | 'deployed' | 'failed';
  progress: number;
  logs: string[];
  deployedAt: string | null;
  endpointUrl: string | null;
  ipAddress: string | null;
  environmentName: string;
  failureReason?: string | null;
}

export interface OptimizationItem {
  id: string;
  title: string;
  category: 'Compute' | 'Storage' | 'Database' | 'Reservation';
  description: string;
  currentCost: number;
  savings: number;
  impact: 'High' | 'Medium' | 'Low';
  applied: boolean;
}

export interface Project {
  id: string;
  userId: string;
  name: string;
  description: string;
  environment: string;
  userRole: 'owner' | 'editor' | 'viewer' | 'admin';
  currentStep: 'estimation' | 'recommendation' | 'generate' | 'deployment' | 'optimization';
  estimation: EstimationData;
  selectedRecommendation: RecommendationOption;
  githubRepo?: {
    name: string;
    connectedAt: string;
    synced: boolean;
  };
  deployment: DeploymentDetails;
  optimizations: OptimizationItem[];
  createdAt: string;
  updatedAt: string;
}

export const defaultEstimation: EstimationData = {
  appType: 'Microservices & Web APIs',
  vcpu: 8,
  ram: 32,
  storage: 500,
  traffic: '1,000,000 req/day',
  region: 'Gujarat (GIFT City / Gandhinagar)',
  performanceTier: 'High Performance',
  budgetTier: 'Balanced',
  calculatedResult: {
    minCost: 14800,
    maxCost: 21700,
    suggestedInstances: 3,
    bandwidthGB: 450,
  },
};

export const defaultRecommendations: RecommendationOption[] = [
  {
    id: 'aws-free-tier-demo',
    title: 'AWS Free Tier Demo (t3.micro)',
    provider: 'AWS',
    badge: 'Budget Option',
    specs: { vcpu: 2, ram: 1, storage: '20 GB EBS', network: 'Up to 5 Gbps' },
    monthlyCost: 0,
    hourlyCost: 0,
    reliability: 'Free Tier eligible (account dependent)',
    features: ['Single-instance deployment', '20 GB EBS storage', 'Basic Docker workload', 'Free Tier usage limits enforced'],
    reasoning: 'A small single-instance profile for CloudWise demo deployments. AWS Free Tier eligibility depends on the account and remaining usage allowance.'
  },
  {
    id: 'aws-rec-1',
    title: 'AWS Production Cluster (c6i.xlarge)',
    provider: 'AWS',
    badge: 'Recommended',
    specs: { vcpu: 8, ram: 32, storage: '500 GB NVMe SSD', network: '10 Gbps' },
    monthlyCost: 12280,
    hourlyCost: 17.00,
    reliability: '99.99% SLA',
    features: ['Auto-scaling enabled', 'AWS Shield Standard DDoS Protection', 'Automated Daily EBS Snapshots', 'Multi-AZ Replication'],
    reasoning: 'AWS c6i.xlarge provides the optimal balance of compute throughput and low-latency IOPS for Microservices workloads in GIFT City / Asia regions while remaining well within your target budget tier.'
  },
  {
    id: 'gcp-rec-2',
    title: 'GCP Compute Engine (n2-standard-8)',
    provider: 'GCP',
    badge: 'Performance Option',
    specs: { vcpu: 8, ram: 32, storage: '500 GB Hyperdisk', network: '16 Gbps' },
    monthlyCost: 14280,
    hourlyCost: 19.80,
    reliability: '99.99% SLA',
    features: ['Custom machine types', 'Google Cloud Armor Integrated', 'Live Migration Support', 'Sustained Use Discount'],
    reasoning: 'Google Cloud Engine n2-standard offers higher network bandwidth (16 Gbps) and sustained use discounts, ideal if your API experiences sustained high peak traffic.'
  },
  {
    id: 'azure-rec-3',
    title: 'Azure Compute (D8s v5)',
    provider: 'Azure',
    badge: 'Alternative',
    specs: { vcpu: 8, ram: 32, storage: '500 GB Premium SSD', network: '12 Gbps' },
    monthlyCost: 13600,
    hourlyCost: 18.80,
    reliability: '99.95% SLA',
    features: ['Azure Defender Integration', 'Accelerated Networking', 'Azure Hybrid Benefit', 'Zone Redundant Storage'],
    reasoning: 'Azure D8s v5 provides seamless Active Directory and enterprise compliance integration, suitable for hybrid enterprise cloud deployments.'
  },
  {
    id: 'do-rec-4',
    title: 'DigitalOcean CPU-Optimized Droplet',
    provider: 'DigitalOcean',
    badge: 'Budget Option',
    specs: { vcpu: 8, ram: 16, storage: '400 GB NVMe SSD', network: '5 Gbps' },
    monthlyCost: 9130,
    hourlyCost: 12.60,
    reliability: '99.99% SLA',
    features: ['Free 5TB Bandwidth Transfer', 'Simple Cloud Firewalls', '1-Click Monitoring Alerts', 'Fixed Transparent Pricing'],
    reasoning: 'DigitalOcean offers maximum financial savings with flat pricing and generous bundled bandwidth transfers, perfect for startup budget optimization.'
  },
];

export const defaultOptimizations: OptimizationItem[] = [
  {
    id: 'opt-1',
    title: 'Rightsize Underutilized Compute Instance',
    category: 'Compute',
    description: 'Average CPU utilization over past 7 days was 14%. Downgrading from 8 vCPUs to 4 vCPUs will maintain headroom while cutting cost.',
    currentCost: 12280,
    savings: 3480,
    impact: 'High',
    applied: false,
  },
  {
    id: 'opt-2',
    title: 'Delete Unattached EBS Storage Volume',
    category: 'Storage',
    description: 'Found 1 unattached 120GB gp3 volume left over from a previous staging instance setup.',
    currentCost: 1240,
    savings: 1240,
    impact: 'Medium',
    applied: false,
  },
  {
    id: 'opt-3',
    title: 'Purchase 1-Year Compute Savings Plan',
    category: 'Reservation',
    description: 'Commit to steady-state baseline usage for 12 months to receive automatic 34% discount off on-demand rates.',
    currentCost: 8800,
    savings: 2980,
    impact: 'High',
    applied: false,
  },
  {
    id: 'opt-4',
    title: 'Automate Off-Peak Staging Database Shutdown',
    category: 'Database',
    description: 'Shut down non-production database clusters during weekend non-business hours (Friday 10 PM - Monday 6 AM).',
    currentCost: 2320,
    savings: 1490,
    impact: 'Low',
    applied: false,
  },
];

interface CloudWiseContextType {
  user: UserProfile | null;
  loginUser: (userData: UserProfile, token?: string) => void;
  logoutUser: () => void;

  projects: Project[];
  activeProject: Project | null;
  setActiveProjectById: (id: string) => void;
  createProject: (data: { name: string; description: string; environment?: string; role?: 'owner' | 'editor' | 'viewer' | 'admin' }) => Promise<Project | null>;
  updateActiveProject: (updates: Partial<Project>) => void;
  deleteProject: (id: string) => Promise<boolean>;

  estimation: EstimationData;
  setEstimation: React.Dispatch<React.SetStateAction<EstimationData>>;
  calculateEstimation: (data: Partial<EstimationData>) => void;
  
  selectedRecommendation: RecommendationOption;
  setSelectedRecommendation: (rec: RecommendationOption) => void;
  availableRecommendations: RecommendationOption[];
  
  githubRepo?: { name: string; connectedAt: string; synced: boolean };
  connectGitHub: (repoName: string) => Promise<boolean>;

  deployment: DeploymentDetails;
  startSimulatedDeployment: (envName?: string, simulateError?: boolean) => Promise<void>;
  rollbackDeployment: () => void;
  resetDeployment: () => void;

  optimizations: OptimizationItem[];
  applyOptimization: (id: string) => void;
  totalMonthlySavings: number;
  effectiveMonthlyCost: number;

  toasts: ToastMessage[];
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
  dismissToast: (id: string) => void;
}

const CloudWiseContext = createContext<CloudWiseContextType | undefined>(undefined);

export const CloudWiseProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(() => {
    try {
      const saved = localStorage.getItem('cloudwise_user');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    const id = `toast_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      dismissToast(id);
    }, 4500);
  };

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const loginUser = (userData: UserProfile, token?: string) => {
    const enrichedUser = { ...userData, role: userData.role || 'owner' };
    setUser(enrichedUser);
    try {
      localStorage.setItem('cloudwise_user', JSON.stringify(enrichedUser));
      if (token) localStorage.setItem('cloudwise_token', token);
    } catch (err) {
      console.warn('Failed to write user to localStorage', err);
    }
    showToast(`Welcome back, ${userData.name}!`, 'success');
  };

  const logoutUser = () => {
    setUser(null);
    try {
      localStorage.removeItem('cloudwise_user');
      localStorage.removeItem('cloudwise_token');
    } catch (err) {
      console.warn('Failed to clear user from localStorage', err);
    }
    showToast('Signed out successfully.', 'info');
  };

  // Projects Management
  const [projects, setProjects] = useState<Project[]>(() => {
    try {
      const saved = localStorage.getItem('cloudwise_projects');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  const [activeProjectId, setActiveProjectId] = useState<string | null>(() => {
    try {
      return localStorage.getItem('cloudwise_active_project_id');
    } catch {
      return null;
    }
  });

  // Sync projects with localStorage
  useEffect(() => {
    try {
      localStorage.setItem('cloudwise_projects', JSON.stringify(projects));
    } catch (err) {
      console.warn('Error saving projects to localStorage', err);
    }
  }, [projects]);

  useEffect(() => {
    if (activeProjectId) {
      localStorage.setItem('cloudwise_active_project_id', activeProjectId);
    } else {
      localStorage.removeItem('cloudwise_active_project_id');
    }
  }, [activeProjectId]);

  // Load backend projects on startup
  useEffect(() => {
    const fetchBackendProjects = async () => {
      try {
        const token = localStorage.getItem('cloudwise_token');
        const res = await fetch('/api/projects', {
          headers: {
            'Authorization': token ? `Bearer ${token}` : '',
            'x-user-role': user?.role || 'owner',
            'x-user-id': user?.id || 'default_user'
          }
        });
        const data = await res.json();
        if (res.ok && data.success && Array.isArray(data.data)) {
          setProjects(data.data);
          if (data.data.length > 0 && !activeProjectId) {
            setActiveProjectId(data.data[0].id);
          }
        }
      } catch (err) {
        console.warn('Offline mode: using local project state.', err);
      }
    };

    fetchBackendProjects();
  }, [user]);

  const activeProject = projects.find((p) => p.id === activeProjectId) || projects[0] || null;

  const setActiveProjectById = (id: string) => {
    const proj = projects.find((p) => p.id === id);
    if (proj) {
      setActiveProjectId(id);
      showToast(`Switched active project to "${proj.name}"`, 'info');
    }
  };

  const createProject = async (data: { name: string; description: string; environment?: string; role?: 'owner' | 'editor' | 'viewer' | 'admin' }): Promise<Project | null> => {
    const userRole = data.role || user?.role || 'owner';

    if (userRole === 'viewer') {
      showToast('Access Denied (RBAC): Viewer role cannot create projects.', 'error');
      return null;
    }

    const newProject: Project = {
      id: `proj_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
      userId: user?.id || 'default_user',
      name: data.name,
      description: data.description || 'Cloud infrastructure workload project',
      environment: data.environment || 'Production',
      userRole,
      currentStep: 'estimation',
      estimation: defaultEstimation,
      selectedRecommendation: defaultRecommendations[0],
      deployment: {
        status: 'idle',
        progress: 0,
        logs: [],
        deployedAt: null,
        endpointUrl: null,
        ipAddress: null,
        environmentName: `${data.name.toLowerCase().replace(/\s+/g, '-')}-cluster`
      },
      optimizations: defaultOptimizations,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };

    try {
      const token = localStorage.getItem('cloudwise_token');
      const res = await fetch('/api/projects', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : '',
          'x-user-role': userRole,
          'x-user-id': user?.id || 'default_user'
        },
        body: JSON.stringify(data)
      });
      const resData = await res.json();
      if (res.ok && resData.success && resData.data) {
        newProject.id = resData.data.id;
      }
    } catch (err) {
      console.warn('Backend create project skipped, using local creation', err);
    }

    setProjects((prev) => [newProject, ...prev]);
    setActiveProjectId(newProject.id);
    showToast(`Project "${newProject.name}" created successfully!`, 'success');
    return newProject;
  };

  const updateActiveProject = async (updates: Partial<Project>) => {
    if (!activeProject) return;

    if (activeProject.userRole === 'viewer') {
      showToast('Access Denied (RBAC): Read-only Viewer role cannot modify project settings.', 'error');
      return;
    }

    const updatedProjects = projects.map((p) => {
      if (p.id === activeProject.id) {
        return {
          ...p,
          ...updates,
          updatedAt: new Date().toISOString()
        };
      }
      return p;
    });

    setProjects(updatedProjects);

    try {
      const token = localStorage.getItem('cloudwise_token');
      await fetch(`/api/projects/${activeProject.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : '',
          'x-user-role': activeProject.userRole,
          'x-user-id': user?.id || 'default_user'
        },
        body: JSON.stringify(updates)
      });
    } catch (err) {
      console.warn('Backend update project skipped', err);
    }
  };

  const deleteProject = async (id: string): Promise<boolean> => {
    const proj = projects.find((p) => p.id === id);
    if (!proj) return false;

    const role = proj.userRole || user?.role || 'owner';
    if (role !== 'owner' && role !== 'admin') {
      showToast('Access Denied (RBAC): Only project Owner or Admin can delete projects.', 'error');
      return false;
    }

    setProjects((prev) => prev.filter((p) => p.id !== id));
    if (activeProjectId === id) {
      const remaining = projects.filter((p) => p.id !== id);
      setActiveProjectId(remaining.length > 0 ? remaining[0].id : null);
    }

    try {
      const token = localStorage.getItem('cloudwise_token');
      await fetch(`/api/projects/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': token ? `Bearer ${token}` : '',
          'x-user-role': role,
          'x-user-id': user?.id || 'default_user'
        }
      });
    } catch (err) {
      console.warn('Backend delete project skipped', err);
    }

    showToast(`Project "${proj.name}" deleted.`, 'info');
    return true;
  };

  // Helper bindings to Active Project
  const estimation = activeProject?.estimation || defaultEstimation;
  const setEstimation: React.Dispatch<React.SetStateAction<EstimationData>> = (action) => {
    const newEst = typeof action === 'function' ? action(estimation) : action;
    updateActiveProject({ estimation: newEst });
  };

  const calculateEstimation = (data: Partial<EstimationData>) => {
    const vcpu = data.vcpu ?? estimation.vcpu;
    const ram = data.ram ?? estimation.ram;
    const storage = data.storage ?? estimation.storage;
    const selectedRegion = (data.region ?? estimation.region).toLowerCase();
    
    let regionMultiplier = 1.0;
    if (selectedRegion.includes('gujarat')) regionMultiplier = 0.92;
    else if (selectedRegion.includes('bengaluru')) regionMultiplier = 1.05;
    else if (selectedRegion.includes('kolkata')) regionMultiplier = 0.96;

    const baseCost = Math.round((vcpu * 1000 + ram * 200 + storage * 6) * regionMultiplier);
    const minCost = Math.round(baseCost * 0.85);
    const maxCost = Math.round(baseCost * 1.25);
    const suggestedInstances = Math.max(1, Math.ceil(vcpu / 4));
    const bandwidthGB = Math.round(ram * 15 + vcpu * 30);

    const updatedEst: EstimationData = {
      ...estimation,
      ...data,
      calculatedResult: {
        minCost,
        maxCost,
        suggestedInstances,
        bandwidthGB,
      },
    };

    updateActiveProject({ estimation: updatedEst, currentStep: 'estimation' });
  };

  const availableRecommendations = defaultRecommendations;
  const selectedRecommendation = activeProject?.selectedRecommendation || defaultRecommendations[0];

  const setSelectedRecommendation = (rec: RecommendationOption) => {
    updateActiveProject({ selectedRecommendation: rec });
    showToast(`Selected ${rec.provider} plan: ${rec.title}`, 'success');
  };

  const connectGitHub = async (repoName: string): Promise<boolean> => {
    if (!activeProject) return false;
    if (activeProject.userRole === 'viewer') {
      showToast('Access Denied (RBAC): Viewer role cannot link GitHub repository.', 'error');
      return false;
    }

    const githubRepo = {
      name: repoName,
      connectedAt: new Date().toLocaleTimeString() + ' ' + new Date().toLocaleDateString(),
      synced: true
    };

    updateActiveProject({
      githubRepo,
      currentStep: 'generate'
    });

    try {
      const token = localStorage.getItem('cloudwise_token');
      await fetch(`/api/projects/${activeProject.id}/github`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : '',
          'x-user-role': activeProject.userRole
        },
        body: JSON.stringify({ repoName })
      });
    } catch (err) {
      console.warn('Backend GitHub connect skipped', err);
    }

    showToast(`GitHub repository "${repoName}" connected & synced!`, 'success');
    return true;
  };

  const deployment = activeProject?.deployment || {
    status: 'idle',
    progress: 0,
    logs: [],
    deployedAt: null,
    endpointUrl: null,
    ipAddress: null,
    environmentName: 'cloudwise-prod-app',
  };

  const startSimulatedDeployment = async (envName?: string, simulateError = false) => {
    if (!activeProject) return;
    const environmentName = envName || deployment.environmentName || `${activeProject.name.toLowerCase().replace(/\s+/g, '-')}-prod`;
    
    updateActiveProject({
      deployment: {
        status: 'preparing',
        progress: 15,
        logs: [`[${new Date().toLocaleTimeString()}] Initializing automated deployment pipeline for ${environmentName}...`],
        deployedAt: null,
        endpointUrl: null,
        ipAddress: null,
        environmentName,
      },
      currentStep: 'deployment'
    });

    await new Promise((resolve) => setTimeout(resolve, 800));

    if (simulateError) {
      updateActiveProject({
        deployment: {
          status: 'failed',
          progress: 45,
          logs: [
            ...deployment.logs,
            `[${new Date().toLocaleTimeString()}] Validating ${selectedRecommendation.provider} API credentials...`,
            `[${new Date().toLocaleTimeString()}] ERROR: Quota Limit Exceeded in target region (${estimation.region}). Cannot allocate ${selectedRecommendation.specs.vcpu} vCPUs.`,
            `[${new Date().toLocaleTimeString()}] Deployment halted. Rollback option available.`
          ],
          deployedAt: null,
          endpointUrl: null,
          ipAddress: null,
          environmentName,
          failureReason: `Resource Quota Exceeded in ${estimation.region}. Please select a different region or downsize vCPU allocation.`
        }
      });
      showToast('Deployment failed due to simulated cloud quota limit.', 'error');
      return;
    }

    updateActiveProject({
      deployment: {
        status: 'provisioning',
        progress: 50,
        logs: [
          ...deployment.logs,
          `[${new Date().toLocaleTimeString()}] Validating ${selectedRecommendation.provider} API credentials & region quotas...`,
          `[${new Date().toLocaleTimeString()}] Provisioning ${selectedRecommendation.specs.vcpu} vCPU / ${selectedRecommendation.specs.ram}GB RAM node cluster in ${estimation.region}...`,
        ],
        deployedAt: null,
        endpointUrl: null,
        ipAddress: null,
        environmentName,
      }
    });

    await new Promise((resolve) => setTimeout(resolve, 1000));
    updateActiveProject({
      deployment: {
        status: 'configuring',
        progress: 80,
        logs: [
          ...deployment.logs,
          `[${new Date().toLocaleTimeString()}] Allocating elastic IP address and configuring VPC subnet routes...`,
          `[${new Date().toLocaleTimeString()}] Mounting ${selectedRecommendation.specs.storage} storage volumes...`,
          `[${new Date().toLocaleTimeString()}] Injecting Docker container & CI/CD probe configurations...`,
        ],
        deployedAt: null,
        endpointUrl: null,
        ipAddress: null,
        environmentName,
      }
    });

    await new Promise((resolve) => setTimeout(resolve, 1000));
    const randomIP = `35.${Math.floor(Math.random() * 200 + 10)}.${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}`;
    const endpoint = `https://${environmentName.toLowerCase().replace(/\s+/g, '-')}.cloudwise.app`;

    updateActiveProject({
      deployment: {
        status: 'deployed',
        progress: 100,
        logs: [
          ...deployment.logs,
          `[${new Date().toLocaleTimeString()}] Health check probes passed (3/3 nodes reporting OK).`,
          `[${new Date().toLocaleTimeString()}] Deployment live at ${endpoint}`,
        ],
        deployedAt: new Date().toLocaleTimeString() + ' ' + new Date().toLocaleDateString(),
        endpointUrl: endpoint,
        ipAddress: randomIP,
        environmentName,
      },
      currentStep: 'deployment'
    });
    showToast('Infrastructure deployment live & healthy!', 'success');
  };

  const rollbackDeployment = () => {
    updateActiveProject({
      deployment: {
        status: 'idle',
        progress: 0,
        logs: [`[${new Date().toLocaleTimeString()}] Deployment rolled back successfully. Environment reset to clean state.`],
        deployedAt: null,
        endpointUrl: null,
        ipAddress: null,
        environmentName: deployment.environmentName || 'cloudwise-prod-app',
        failureReason: null
      }
    });
    showToast('Rollback completed. Deployment reset to clean state.', 'info');
  };

  const resetDeployment = () => {
    rollbackDeployment();
  };

  const optimizations = activeProject?.optimizations || defaultOptimizations;

  const applyOptimization = (id: string) => {
    if (!activeProject) return;

    if (activeProject.userRole === 'viewer') {
      showToast('Access Denied (RBAC): Viewer role cannot apply cost optimizations.', 'error');
      return;
    }

    const updatedOpts = optimizations.map((item) => (item.id === id ? { ...item, applied: !item.applied } : item));
    updateActiveProject({ optimizations: updatedOpts, currentStep: 'optimization' });
    const targetItem = optimizations.find(o => o.id === id);
    if (targetItem) {
      if (!targetItem.applied) {
        showToast(`Applied "${targetItem.title}" — saved ${formatINR(targetItem.savings)}/mo!`, 'success');
      } else {
        showToast(`Reverted "${targetItem.title}".`, 'info');
      }
    }
  };

  const totalMonthlySavings = optimizations
    .filter((o) => o.applied)
    .reduce((sum, o) => sum + o.savings, 0);

  const effectiveMonthlyCost = Math.max(
    0,
    selectedRecommendation.monthlyCost - totalMonthlySavings
  );

  return (
    <CloudWiseContext.Provider
      value={{
        user,
        loginUser,
        logoutUser,
        projects,
        activeProject,
        setActiveProjectById,
        createProject,
        updateActiveProject,
        deleteProject,
        estimation,
        setEstimation,
        calculateEstimation,
        selectedRecommendation,
        setSelectedRecommendation,
        availableRecommendations,
        githubRepo: activeProject?.githubRepo,
        connectGitHub,
        deployment,
        startSimulatedDeployment,
        rollbackDeployment,
        resetDeployment,
        optimizations,
        applyOptimization,
        totalMonthlySavings,
        effectiveMonthlyCost,
        toasts,
        showToast,
        dismissToast
      }}
    >
      {children}
      <Toast toasts={toasts} onDismiss={dismissToast} />
    </CloudWiseContext.Provider>
  );
};

export const useCloudWise = () => {
  const context = useContext(CloudWiseContext);
  if (!context) {
    throw new Error('useCloudWise must be used within a CloudWiseProvider');
  }
  return context;
};
