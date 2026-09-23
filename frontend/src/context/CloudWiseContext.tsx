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
  providerError?: {
    provider?: string;
    deploymentId?: string;
    projectId?: string;
    status?: string;
    url?: string | null;
    errorCode?: string;
    errorMessage?: string;
    errorStep?: string;
    gitSource?: { sha?: string; ref?: string };
    projectSettings?: Record<string, any>;
    buildLogs?: string[];
  } | null;
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

export interface MonitoringData {
  cpuUsage: number;
  memoryUsage: number;
  storageUsage: number;
  networkInMB: number;
  networkOutMB: number;
  healthStatus: string;
  clusterUptime: string;
  activeNodes: number;
  ipAddress: string;
  endpointUrl: string | null;
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

// Optimizations are generated dynamically from the selected recommendation cost
export const buildOptimizations = (monthlyCost: number, vcpu: number, storage: number): OptimizationItem[] => {
  const rightsizeSavings = Math.round(monthlyCost * 0.28);
  const storageCost = Math.round(storage * 6);
  const reservationBase = Math.round(monthlyCost * 0.72);
  const reservationSavings = Math.round(reservationBase * 0.34);
  const dbCost = Math.round(monthlyCost * 0.19);
  const dbSavings = Math.round(dbCost * 0.64);
  return [
    {
      id: 'opt-1',
      title: 'Rightsize Underutilized Compute Instance',
      category: 'Compute',
      description: `Average CPU utilization over past 7 days was 14%. Downgrading from ${vcpu} vCPUs to ${Math.max(2, Math.floor(vcpu / 2))} vCPUs will maintain headroom while cutting cost.`,
      currentCost: monthlyCost,
      savings: rightsizeSavings,
      impact: 'High',
      applied: false,
    },
    {
      id: 'opt-2',
      title: 'Delete Unattached Storage Volume',
      category: 'Storage',
      description: `Found 1 unattached ${Math.round(storage * 0.24)}GB volume left over from a previous staging instance setup.`,
      currentCost: storageCost,
      savings: storageCost,
      impact: 'Medium',
      applied: false,
    },
    {
      id: 'opt-3',
      title: 'Purchase 1-Year Compute Savings Plan',
      category: 'Reservation',
      description: 'Commit to steady-state baseline usage for 12 months to receive automatic 34% discount off on-demand rates.',
      currentCost: reservationBase,
      savings: reservationSavings,
      impact: 'High',
      applied: false,
    },
    {
      id: 'opt-4',
      title: 'Automate Off-Peak Staging Database Shutdown',
      category: 'Database',
      description: 'Shut down non-production database clusters during weekend non-business hours (Friday 10 PM - Monday 6 AM).',
      currentCost: dbCost,
      savings: dbSavings,
      impact: 'Low',
      applied: false,
    },
  ];
};

export const defaultOptimizations: OptimizationItem[] = buildOptimizations(12280, 8, 500);

export const buildRecommendations = (est: EstimationData): RecommendationOption[] => {
  const vcpu = est.vcpu;
  const ram = est.ram;
  const storage = est.storage;
  const region = est.region;
  const regionMult = region.toLowerCase().includes('gujarat') ? 0.92
    : region.toLowerCase().includes('bengaluru') ? 1.05
    : region.toLowerCase().includes('kolkata') ? 0.96 : 1.0;
  const base = Math.round((vcpu * 1000 + ram * 200 + storage * 6) * regionMult);
  const awsCost  = Math.round(base * 1.00);
  const gcpCost  = Math.round(base * 1.16);
  const azureCost = Math.round(base * 1.11);
  const doCost   = Math.round(base * 0.74);
  return [
    {
      id: 'aws-rec-1',
      title: `AWS (c6i — ${vcpu}vCPU/${ram}GB)`,
      provider: 'AWS',
      badge: 'Recommended',
      specs: { vcpu, ram, storage: `${storage} GB NVMe SSD`, network: '10 Gbps' },
      monthlyCost: awsCost,
      hourlyCost: Math.round((awsCost / 720) * 100) / 100,
      reliability: '99.99% SLA',
      features: ['Auto-scaling enabled', 'AWS Shield DDoS Protection', 'Daily EBS Snapshots', 'Multi-AZ Replication'],
      reasoning: `AWS c6i provides optimal compute throughput for ${est.appType} with ${vcpu} vCPUs and ${ram}GB RAM in ${region}.`,
    },
    {
      id: 'gcp-rec-2',
      title: `GCP (n2-standard — ${vcpu}vCPU/${ram}GB)`,
      provider: 'GCP',
      badge: 'Performance Option',
      specs: { vcpu, ram, storage: `${storage} GB Hyperdisk`, network: '16 Gbps' },
      monthlyCost: gcpCost,
      hourlyCost: Math.round((gcpCost / 720) * 100) / 100,
      reliability: '99.99% SLA',
      features: ['Custom machine types', 'Google Cloud Armor', 'Live Migration', 'Sustained Use Discount'],
      reasoning: `GCP n2-standard offers 16 Gbps network bandwidth ideal for high-traffic ${est.appType} workloads.`,
    },
    {
      id: 'azure-rec-3',
      title: `Azure (Dsv5 — ${vcpu}vCPU/${ram}GB)`,
      provider: 'Azure',
      badge: 'Alternative',
      specs: { vcpu, ram, storage: `${storage} GB Premium SSD`, network: '12 Gbps' },
      monthlyCost: azureCost,
      hourlyCost: Math.round((azureCost / 720) * 100) / 100,
      reliability: '99.95% SLA',
      features: ['Azure Defender', 'Accelerated Networking', 'Hybrid Benefit', 'Zone Redundant Storage'],
      reasoning: `Azure Dsv5 suits enterprise compliance and hybrid deployments for ${est.appType} in ${region}.`,
    },
    {
      id: 'do-rec-4',
      title: `DigitalOcean (CPU-Opt — ${vcpu}vCPU/${Math.round(ram * 0.5)}GB)`,
      provider: 'DigitalOcean',
      badge: 'Budget Option',
      specs: { vcpu, ram: Math.round(ram * 0.5), storage: `${Math.round(storage * 0.8)} GB NVMe SSD`, network: '5 Gbps' },
      monthlyCost: doCost,
      hourlyCost: Math.round((doCost / 720) * 100) / 100,
      reliability: '99.99% SLA',
      features: ['Free 5TB Bandwidth', 'Simple Firewalls', '1-Click Monitoring', 'Fixed Pricing'],
      reasoning: `DigitalOcean offers maximum savings with flat pricing for budget-conscious ${est.appType} deployments.`,
    },
  ];
};

export const defaultRecommendations: RecommendationOption[] = buildRecommendations(defaultEstimation);

interface CloudWiseContextType {
  user: UserProfile | null;
  loginUser: (userData: UserProfile, token?: string) => void;
  logoutUser: () => void;

  projects: Project[];
  projectsLoading: boolean;
  projectsError: string | null;
  refetchProjects: () => Promise<void>;
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
  rollbackDeployment: () => void;
  resetDeployment: () => void;

  optimizations: OptimizationItem[];
  applyOptimization: (id: string) => void;
  totalMonthlySavings: number;
  effectiveMonthlyCost: number;

  monitoringData: MonitoringData;

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
    setProjects([]);
    setActiveProjectId(null);
    try {
      localStorage.removeItem('cloudwise_user');
      localStorage.removeItem('cloudwise_token');
      localStorage.removeItem('cloudwise_projects');
      localStorage.removeItem('cloudwise_active_project_id');
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

  const [projectsLoading, setProjectsLoading] = useState<boolean>(() => {
    return !!localStorage.getItem('cloudwise_token');
  });
  const [projectsError, setProjectsError] = useState<string | null>(null);

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

  const fetchBackendProjects = async () => {
    const token = localStorage.getItem('cloudwise_token');
    if (!token) {
      setProjects([]);
      setActiveProjectId(null);
      setProjectsLoading(false);
      return;
    }

    setProjectsLoading(true);
    setProjectsError(null);
    try {
      const res = await fetch('/api/projects', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      const data = await res.json();
      if (res.ok && data.success && Array.isArray(data.data)) {
        setProjects(data.data);
        if (data.data.length > 0) {
          setActiveProjectId((prev) => {
            if (prev && data.data.some((p: Project) => p.id === prev)) {
              return prev;
            }
            return data.data[0].id;
          });
        } else {
          setActiveProjectId(null);
        }
      } else if (res.status === 401) {
        setProjects([]);
        setActiveProjectId(null);
      } else {
        setProjectsError(data.error || 'Failed to load projects from server.');
      }
    } catch (err: any) {
      console.warn('Backend fetch error:', err);
      setProjectsError('Could not reach the server to fetch projects.');
    } finally {
      setProjectsLoading(false);
    }
  };

  useEffect(() => {
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

    const token = localStorage.getItem('cloudwise_token');
    if (!token) {
      showToast('Please sign in to create a project.', 'error');
      return null;
    }

    try {
      const res = await fetch('/api/projects', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name: data.name,
          description: data.description || 'Cloud infrastructure workload project',
          environment: data.environment || 'Production',
          role: userRole
        })
      });

      const resData = await res.json();
      if (!res.ok || !resData.success || !resData.data) {
        throw new Error(resData.error || 'Failed to create project on server.');
      }

      const createdProject: Project = {
        id: resData.data.id,
        userId: resData.data.userId || user?.id || 'default_user',
        name: resData.data.name,
        description: resData.data.description || 'Cloud infrastructure workload project',
        environment: resData.data.environment || 'Production',
        userRole: resData.data.userRole || userRole,
        currentStep: resData.data.currentStep || 'estimation',
        estimation: resData.data.estimation && Object.keys(resData.data.estimation).length > 0 ? resData.data.estimation : defaultEstimation,
        selectedRecommendation: resData.data.selectedRecommendation || defaultRecommendations[0],
        deployment: resData.data.deployment || {
          status: 'idle',
          progress: 0,
          logs: [],
          deployedAt: null,
          endpointUrl: null,
          ipAddress: null,
          environmentName: `${data.name.toLowerCase().replace(/\s+/g, '-')}-cluster`
        },
        optimizations: resData.data.optimizations || defaultOptimizations,
        createdAt: resData.data.createdAt || new Date().toISOString(),
        updatedAt: resData.data.updatedAt || new Date().toISOString()
      };

      setProjects((prev) => [createdProject, ...prev.filter(p => p.id !== createdProject.id)]);
      setActiveProjectId(createdProject.id);
      showToast(`Project "${createdProject.name}" created successfully!`, 'success');
      return createdProject;
    } catch (err: any) {
      showToast(err.message || 'Failed to create project.', 'error');
      throw err;
    }
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
      if (token) {
        await fetch(`/api/projects/${activeProject.id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify(updates)
        });
      }
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

    const token = localStorage.getItem('cloudwise_token');
    try {
      if (token) {
        const res = await fetch(`/api/projects/${id}`, {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        const resData = await res.json();
        if (!res.ok || !resData.success) {
          throw new Error(resData.error || 'Failed to delete project on server.');
        }
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to delete project on server.', 'error');
      return false;
    }

    setProjects((prev) => prev.filter((p) => p.id !== id));
    if (activeProjectId === id) {
      const remaining = projects.filter((p) => p.id !== id);
      setActiveProjectId(remaining.length > 0 ? remaining[0].id : null);
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

  const availableRecommendations = buildRecommendations(estimation);
  const selectedRecommendation = (() => {
    const saved = activeProject?.selectedRecommendation;
    if (!saved) return availableRecommendations[0];
    // Re-sync specs from current estimation so saved selection stays current
    const live = availableRecommendations.find(r => r.id === saved.id);
    return live ?? availableRecommendations[0];
  })();

  const setSelectedRecommendation = (rec: RecommendationOption) => {
    updateActiveProject({ selectedRecommendation: rec });
    showToast(`Selected ${rec.provider} plan: ${rec.title}`, 'success');
  };

  const connectGitHub = async (repoName: string): Promise<boolean> => {
    const githubRepo = {
      name: repoName,
      connectedAt: new Date().toLocaleTimeString() + ' ' + new Date().toLocaleDateString(),
      synced: true
    };

    let targetProjectId: string;

    if (activeProject) {
      // Active project exists — update it directly in state
      if (activeProject.userRole === 'viewer') {
        showToast('Access Denied (RBAC): Viewer role cannot link GitHub repository.', 'error');
        return false;
      }
      targetProjectId = activeProject.id;
      setProjects((prev) =>
        prev.map((p) =>
          p.id === targetProjectId
            ? { ...p, githubRepo, currentStep: 'generate' as const, updatedAt: new Date().toISOString() }
            : p
        )
      );
    } else {
      // No active project — create one locally (no backend wait)
      const projName = repoName.includes('/') ? repoName.split('/')[1] : repoName;
      const newProject: Project = {
        id: `proj_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
        userId: user?.id || 'default_user',
        name: projName,
        description: `Deployment project for GitHub repository ${repoName}`,
        environment: 'Production',
        userRole: user?.role || 'owner',
        currentStep: 'generate',
        estimation: defaultEstimation,
        selectedRecommendation: availableRecommendations[0],
        githubRepo,
        deployment: {
          status: 'idle',
          progress: 0,
          logs: [],
          deployedAt: null,
          endpointUrl: null,
          ipAddress: null,
          environmentName: `${projName.toLowerCase().replace(/\s+/g, '-')}-prod`
        },
        optimizations: defaultOptimizations,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
      targetProjectId = newProject.id;
      setProjects((prev) => [newProject, ...prev]);
      setActiveProjectId(newProject.id);

      // Attempt to persist to backend (fire-and-forget, don't block UI)
      const token = localStorage.getItem('cloudwise_token');
      fetch('/api/projects', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : '',
          'x-user-role': newProject.userRole,
          'x-user-id': user?.id || 'default_user'
        },
        body: JSON.stringify({ name: projName, description: newProject.description, environment: 'Production' })
      }).catch((err) => console.warn('Backend project create skipped', err));
    }

    // Sync github_repo to backend (fire-and-forget, don't block UI)
    const token = localStorage.getItem('cloudwise_token');
    fetch(`/api/projects/${targetProjectId}/github`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
      },
      body: JSON.stringify({ repoName })
    }).catch((err) => console.warn('Backend GitHub connect skipped', err));

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

  const rollbackDeployment = () => {
    updateActiveProject({
      deployment: {
        status: 'idle',
        progress: 0,
        logs: [`[${new Date().toLocaleTimeString()}] Deployment rolled back. Environment reset.`],
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

  const optimizations = (() => {
    const saved = activeProject?.optimizations;
    const rec = selectedRecommendation;
    const storageNum = parseInt(String(rec.specs.storage)) || estimation.storage;
    if (saved && saved.length > 0 && saved[0].currentCost === rec.monthlyCost) {
      return saved;
    }
    return buildOptimizations(rec.monthlyCost, rec.specs.vcpu, storageNum);
  })();

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

  const effectiveMonthlyCost = Math.max(0, selectedRecommendation.monthlyCost - totalMonthlySavings);

  // Monitoring data — fetched from backend, derived from estimation as fallback
  const [monitoringData, setMonitoringData] = useState<MonitoringData>({
    cpuUsage: 38,
    memoryUsage: 62,
    storageUsage: 41,
    networkInMB: 12.4,
    networkOutMB: 48.7,
    healthStatus: 'Healthy',
    clusterUptime: '0d 00h 00m',
    activeNodes: 1,
    ipAddress: 'Not yet deployed',
    endpointUrl: null,
  });

  useEffect(() => {
    const fetchMonitoring = async () => {
      try {
        const res = await fetch('/api/monitoring');
        const data = await res.json();
        if (res.ok && data.success) {
          setMonitoringData({
            cpuUsage: data.data.cpuUsage,
            memoryUsage: data.data.memoryUsage,
            storageUsage: data.data.storageUsage,
            networkInMB: data.data.networkInMB,
            networkOutMB: data.data.networkOutMB,
            healthStatus: data.data.healthStatus,
            clusterUptime: data.data.clusterUptime,
            activeNodes: data.data.activeNodes,
            ipAddress: data.data.ipAddress ?? 'Not yet deployed',
            endpointUrl: data.data.endpointUrl ?? null,
          });
        }
      } catch {
        // keep fallback
      }
    };
    fetchMonitoring();
  }, []);

  return (
    <CloudWiseContext.Provider
      value={{
        user,
        loginUser,
        logoutUser,
        projects,
        projectsLoading,
        projectsError,
        refetchProjects: fetchBackendProjects,
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
        rollbackDeployment,
        resetDeployment,
        optimizations,
        applyOptimization,
        totalMonthlySavings,
        effectiveMonthlyCost,
        monitoringData,
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
