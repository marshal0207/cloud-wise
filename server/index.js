import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import crypto from 'crypto';
import { 
  addContact, 
  addEstimation, 
  addWaitlist, 
  recordDeployment, 
  findUserByEmail, 
  addUser,
  addProject,
  getProjectsByUser,
  getProjectById,
  updateProject,
  deleteProject
} from './storage.js';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

// Auth & RBAC Middleware
function authenticateUser(req, res, next) {
  const authHeader = req.headers.authorization || '';
  const userRoleHeader = req.headers['x-user-role'] || 'owner'; // fallback for dev
  const userIdHeader = req.headers['x-user-id'] || 'default_user';

  if (authHeader.startsWith('Bearer cw_token_') || authHeader.startsWith('cw_token_')) {
    const tokenParts = authHeader.replace('Bearer ', '').split('_');
    req.user = {
      id: tokenParts[2] || userIdHeader,
      role: userRoleHeader
    };
  } else {
    req.user = {
      id: userIdHeader,
      role: userRoleHeader
    };
  }
  next();
}

app.use(authenticateUser);

// Password Hashing Helper
function hashPassword(password, salt) {
  const generatedSalt = salt || crypto.randomBytes(16).toString('hex');
  const hash = crypto.pbkdf2Sync(password, generatedSalt, 1000, 64, 'sha512').toString('hex');
  return { salt: generatedSalt, hash };
}

// Request logging middleware
app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
  next();
});

// Health check endpoint
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'CloudWise API Backend',
    version: '1.2.0',
    timestamp: new Date().toISOString()
  });
});

// -------------------------------------------------------------
// Authentication Endpoints
// -------------------------------------------------------------

// Sign Up
app.post('/api/auth/signup', (req, res) => {
  const { name, company, email, password } = req.body || {};

  if (!name || !email || !password) {
    return res.status(400).json({
      success: false,
      error: 'Full Name, Email Address, and Password are required.'
    });
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return res.status(400).json({
      success: false,
      error: 'Please enter a valid email address.'
    });
  }

  const isStrictPassword = password && password.length === 8 && /[A-Z]/.test(password) && /[a-z]/.test(password) && /[0-9]/.test(password);
  if (!isStrictPassword) {
    return res.status(400).json({
      success: false,
      error: 'Password must be exactly 8 characters and include an uppercase letter, a lowercase letter, and a number.'
    });
  }

  const existing = findUserByEmail(email);
  if (existing) {
    return res.status(400).json({
      success: false,
      error: 'An account with this email address already exists. Please sign in.'
    });
  }

  const { salt, hash } = hashPassword(password);
  const user = addUser({
    name: name.trim(),
    company: (company || 'CloudWise Enterprise').trim(),
    email: email.trim().toLowerCase(),
    passwordHash: hash,
    salt
  });

  const token = `cw_token_${user.id}_${Date.now()}`;

  return res.status(201).json({
    success: true,
    message: 'Account created successfully!',
    token,
    user: {
      id: user.id,
      name: user.name,
      company: user.company,
      email: user.email,
      role: 'owner'
    }
  });
});

// Sign In / Login
app.post('/api/auth/login', (req, res) => {
  const { email, password } = req.body || {};

  if (!email || !password) {
    return res.status(400).json({
      success: false,
      error: 'Email address and password are required.'
    });
  }

  const user = findUserByEmail(email);
  if (!user) {
    return res.status(401).json({
      success: false,
      error: 'Invalid email or password.'
    });
  }

  const { hash } = hashPassword(password, user.salt);
  if (hash !== user.passwordHash) {
    return res.status(401).json({
      success: false,
      error: 'Invalid email or password.'
    });
  }

  const token = `cw_token_${user.id}_${Date.now()}`;

  return res.json({
    success: true,
    message: 'Signed in successfully.',
    token,
    user: {
      id: user.id,
      name: user.name,
      company: user.company,
      email: user.email,
      role: 'owner'
    }
  });
});

// -------------------------------------------------------------
// Projects API Endpoints (Module 2 & RBAC Module 10)
// -------------------------------------------------------------

// Get All Projects for Current User
app.get('/api/projects', (req, res) => {
  const userId = req.user?.id || 'default_user';
  const projects = getProjectsByUser(userId);
  return res.json({
    success: true,
    data: projects
  });
});

// Create New Project
app.post('/api/projects', (req, res) => {
  const role = req.body.role || req.user?.role || 'owner';
  if (role === 'viewer') {
    return res.status(403).json({
      success: false,
      error: 'Access Denied (RBAC): Users with "Viewer" role cannot create new projects.'
    });
  }

  const { name, description, environment } = req.body || {};
  if (!name) {
    return res.status(400).json({
      success: false,
      error: 'Project name is required.'
    });
  }

  const project = addProject({
    userId: req.user?.id || 'default_user',
    name: name.trim(),
    description: description ? description.trim() : 'Cloud deployment advisory project',
    environment: environment || 'Production',
    userRole: role,
    currentStep: 'estimation',
    estimation: {
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
        bandwidthGB: 450
      }
    },
    selectedRecommendation: {
      id: 'aws-rec-1',
      title: 'AWS Production Cluster (c6i.xlarge)',
      provider: 'AWS',
      badge: 'Recommended',
      specs: { vcpu: 8, ram: 32, storage: '500 GB NVMe SSD', network: '10 Gbps' },
      monthlyCost: 12280,
      hourlyCost: 17.00,
      reliability: '99.99% SLA',
      features: ['Auto-scaling enabled', 'AWS Shield Standard DDoS Protection', 'Automated Daily EBS Snapshots', 'Multi-AZ Replication']
    },
    deployment: {
      status: 'idle',
      progress: 0,
      logs: [],
      deployedAt: null,
      endpointUrl: null,
      ipAddress: null,
      environmentName: `${name.toLowerCase().replace(/\s+/g, '-')}-prod`
    },
    optimizations: [
      {
        id: 'opt-1',
        title: 'Rightsize Underutilized Compute Instance',
        category: 'Compute',
        description: 'Average CPU utilization over past 7 days was 14%. Downgrading from 8 vCPUs to 4 vCPUs will maintain headroom while cutting cost.',
        currentCost: 12280,
        savings: 3480,
        impact: 'High',
        applied: false
      },
      {
        id: 'opt-2',
        title: 'Delete Unattached EBS Storage Volume',
        category: 'Storage',
        description: 'Found 1 unattached 120GB gp3 volume left over from a previous staging instance setup.',
        currentCost: 1240,
        savings: 1240,
        impact: 'Medium',
        applied: false
      },
      {
        id: 'opt-3',
        title: 'Purchase 1-Year Compute Savings Plan',
        category: 'Reservation',
        description: 'Commit to steady-state baseline usage for 12 months to receive automatic 34% discount off on-demand rates.',
        currentCost: 8800,
        savings: 2980,
        impact: 'High',
        applied: false
      },
      {
        id: 'opt-4',
        title: 'Automate Off-Peak Staging Database Shutdown',
        category: 'Database',
        description: 'Shut down non-production database clusters during weekend non-business hours (Friday 10 PM - Monday 6 AM).',
        currentCost: 2320,
        savings: 1490,
        impact: 'Low',
        applied: false
      }
    ]
  });

  return res.status(201).json({
    success: true,
    message: 'Project created successfully',
    data: project
  });
});

// Get Project By ID
app.get('/api/projects/:id', (req, res) => {
  const project = getProjectById(req.params.id);
  if (!project) {
    return res.status(404).json({ success: false, error: 'Project not found.' });
  }
  return res.json({ success: true, data: project });
});

// Update Project (Gated by RBAC)
app.put('/api/projects/:id', (req, res) => {
  const project = getProjectById(req.params.id);
  if (!project) {
    return res.status(404).json({ success: false, error: 'Project not found.' });
  }

  const role = req.headers['x-user-role'] || req.body.role || project.userRole || 'owner';
  if (role === 'viewer') {
    return res.status(403).json({
      success: false,
      error: 'Access Denied (RBAC): Read-only "Viewer" role cannot modify project settings.'
    });
  }

  const updated = updateProject(req.params.id, req.body);
  return res.json({
    success: true,
    message: 'Project updated successfully',
    data: updated
  });
});

// Delete Project (Gated by RBAC - Owner / Admin only)
app.delete('/api/projects/:id', (req, res) => {
  const project = getProjectById(req.params.id);
  if (!project) {
    return res.status(404).json({ success: false, error: 'Project not found.' });
  }

  const role = req.headers['x-user-role'] || req.user?.role || project.userRole || 'owner';
  if (role !== 'owner' && role !== 'admin') {
    return res.status(403).json({
      success: false,
      error: 'Access Denied (RBAC): Only project Owner or Admin can delete a project.'
    });
  }

  deleteProject(req.params.id);
  return res.json({
    success: true,
    message: 'Project deleted successfully'
  });
});

// GitHub Integration Endpoint (Module 6)
app.post('/api/projects/:id/github', (req, res) => {
  const { repoName } = req.body || {};
  const project = getProjectById(req.params.id);

  if (!project) {
    return res.status(404).json({ success: false, error: 'Project not found.' });
  }

  const role = req.headers['x-user-role'] || req.user?.role || project.userRole || 'owner';
  if (role === 'viewer') {
    return res.status(403).json({
      success: false,
      error: 'Access Denied (RBAC): Viewer role cannot link GitHub repository.'
    });
  }

  const githubRepo = {
    name: repoName || 'org/app-cloudwise',
    connectedAt: new Date().toISOString(),
    synced: true,
    files: ['Dockerfile', '.github/workflows/deploy.yml', 'docker-compose.yml']
  };

  const updated = updateProject(req.params.id, {
    githubRepo,
    currentStep: 'generate'
  });

  return res.json({
    success: true,
    message: `Successfully connected GitHub repository ${githubRepo.name} and synced generated deployment artifacts!`,
    data: updated
  });
});


// -------------------------------------------------------------
// Core Application Endpoints
// -------------------------------------------------------------

// Contact Form Endpoint
app.post('/api/contact', (req, res) => {
  const { name, email, subject, message } = req.body || {};

  if (!name || !email || !message) {
    return res.status(400).json({
      success: false,
      error: 'Missing required fields: name, email, and message are required.'
    });
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return res.status(400).json({
      success: false,
      error: 'Invalid email address provided.'
    });
  }

  const savedRecord = addContact({
    name: name.trim(),
    email: email.trim().toLowerCase(),
    subject: subject || 'General Inquiry',
    message: message.trim()
  });

  return res.status(201).json({
    success: true,
    message: 'Your inquiry has been successfully transmitted to our cloud engineering team.',
    data: savedRecord
  });
});

// Estimation Endpoint (INR ₹ Pricing Engine)
app.post('/api/estimate', (req, res) => {
  const { appType, vcpu, ram, storage, traffic, region, performanceTier, budgetTier } = req.body || {};

  const vcpuNum = Number(vcpu) || 8;
  const ramNum = Number(ram) || 32;
  const storageNum = Number(storage) || 500;

  const targetRegion = (region || 'Gujarat (GIFT City / Gandhinagar)').toLowerCase();
  let regionMultiplier = 1.0;
  if (targetRegion.includes('gujarat')) regionMultiplier = 0.92;
  else if (targetRegion.includes('bengaluru')) regionMultiplier = 1.05;
  else if (targetRegion.includes('kolkata')) regionMultiplier = 0.96;

  // Cost calculation in INR (₹) with regional multiplier
  const baseCost = Math.round((vcpuNum * 1000 + ramNum * 200 + storageNum * 6) * regionMultiplier);
  const minCost = Math.round(baseCost * 0.85);
  const maxCost = Math.round(baseCost * 1.25);
  const suggestedInstances = Math.max(1, Math.ceil(vcpuNum / 4));
  const bandwidthGB = Math.round(ramNum * 15 + vcpuNum * 30);

  const calculatedResult = {
    minCost,
    maxCost,
    suggestedInstances,
    bandwidthGB
  };

  const record = addEstimation({
    appType: appType || 'Microservices & Web APIs',
    vcpu: vcpuNum,
    ram: ramNum,
    storage: storageNum,
    traffic: traffic || '1,000,000 req/day',
    region: region || 'Gujarat (GIFT City / Gandhinagar)',
    performanceTier: performanceTier || 'High Performance',
    budgetTier: budgetTier || 'Balanced',
    calculatedResult
  });

  return res.json({
    success: true,
    data: record
  });
});

// Deployment Trigger Endpoint
app.post('/api/deploy', (req, res) => {
  const { environmentName, provider, monthlyCost, specs, region } = req.body || {};

  const envName = environmentName || 'cloudwise-prod-cluster';
  const randomIP = `35.${Math.floor(Math.random() * 200 + 10)}.${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}`;
  const endpoint = `https://${envName.toLowerCase().replace(/\s+/g, '-')}.cloudwise.app`;

  const record = recordDeployment({
    environmentName: envName,
    provider: provider || 'AWS',
    monthlyCost: monthlyCost || 12280,
    specs: specs || { vcpu: 8, ram: 32, storage: '500 GB NVMe' },
    region: region || 'Asia Pacific (Mumbai)',
    status: 'deployed',
    ipAddress: randomIP,
    endpointUrl: endpoint,
    logs: [
      `[${new Date().toLocaleTimeString()}] Provisioning initiated for ${envName}...`,
      `[${new Date().toLocaleTimeString()}] Allocating elastic IP ${randomIP}...`,
      `[${new Date().toLocaleTimeString()}] Mounting storage and establishing VPC routes...`,
      `[${new Date().toLocaleTimeString()}] Health probes passed. Deployment live at ${endpoint}`
    ]
  });

  return res.json({
    success: true,
    message: 'Deployment recorded successfully',
    data: record
  });
});

// Waitlist Newsletter Endpoint
app.post('/api/waitlist', (req, res) => {
  const { email, source } = req.body || {};

  if (!email) {
    return res.status(400).json({
      success: false,
      error: 'Email address is required.'
    });
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return res.status(400).json({
      success: false,
      error: 'Please enter a valid email address.'
    });
  }

  const record = addWaitlist(email.trim().toLowerCase(), { source: source || 'home_page' });

  return res.status(201).json({
    success: true,
    message: 'Successfully subscribed to CloudWise updates and early access releases!',
    data: record
  });
});

// Monitoring Endpoint
app.get('/api/monitoring', (req, res) => {
  res.json({
    success: true,
    data: {
      cpuUsage: 38,
      memoryUsage: 62,
      storageUsage: 41,
      networkInMB: 12.4,
      networkOutMB: 48.7,
      healthStatus: 'Healthy',
      clusterUptime: '14d 08h 32m',
      activeNodes: 3
    }
  });
});

// -------------------------------------------------------------
// Pending Feature Stubs
// -------------------------------------------------------------

app.post('/api/ai/recommend-workload', (req, res) => {
  res.json({
    success: true,
    status: 'stub_pending_ml_model',
    message: 'CloudWise ML inference stub called.',
    aiRecommendations: {
      suggestedVcpu: 6,
      suggestedRam: 24,
      confidenceScore: 0.94,
      predictedCostSavingsPercent: 28.5
    }
  });
});

app.post('/api/cloud/terraform-export', (req, res) => {
  const { provider = 'aws', environmentName = 'cloudwise-prod' } = req.body || {};
  res.json({
    success: true,
    status: 'stub_ready',
    provider,
    filename: `main_${provider}.tf`,
    hclSnippet: `provider "${provider.toLowerCase()}" { region = "ap-south-1" }`
  });
});

// Restart daemon listener
app.listen(PORT, () => {
  console.log(`🚀 CloudWise Backend API Server running on http://localhost:${PORT}`);
});
