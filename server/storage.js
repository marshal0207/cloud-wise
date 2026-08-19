import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DATA_DIR = path.resolve(__dirname, '../data');
const DB_FILE = path.join(DATA_DIR, 'cloudwise-db.json');

// Initial default database template
const defaultDb = {
  users: [],
  contacts: [],
  estimations: [],
  deployments: [],
  waitlist: [],
  optimizations: [],
  projects: []
};

// Ensure directory and JSON file exist
function initDb() {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }

  if (!fs.existsSync(DB_FILE)) {
    fs.writeFileSync(DB_FILE, JSON.stringify(defaultDb, null, 2), 'utf-8');
  }
}

// Read database
export function readDb() {
  try {
    initDb();
    const raw = fs.readFileSync(DB_FILE, 'utf-8');
    const parsed = JSON.parse(raw);
    if (!parsed.users) parsed.users = [];
    if (!parsed.projects) parsed.projects = [];
    return parsed;
  } catch (err) {
    console.error('Error reading cloudwise-db.json:', err);
    return defaultDb;
  }
}

// Write database
export function writeDb(data) {
  try {
    initDb();
    fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2), 'utf-8');
    return true;
  } catch (err) {
    console.error('Error writing cloudwise-db.json:', err);
    return false;
  }
}

// User methods
export function findUserByEmail(email) {
  const db = readDb();
  if (!email) return null;
  const target = email.trim().toLowerCase();
  return db.users.find((u) => u.email.toLowerCase() === target) || null;
}

export function addUser(userData) {
  const db = readDb();
  const record = {
    id: `user_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
    ...userData,
    createdAt: new Date().toISOString()
  };
  db.users.push(record);
  writeDb(db);
  return record;
}

// Helper methods
export function addContact(contact) {
  const db = readDb();
  const record = {
    id: `contact_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
    ...contact,
    createdAt: new Date().toISOString()
  };
  db.contacts.push(record);
  writeDb(db);
  return record;
}

export function addEstimation(estimation) {
  const db = readDb();
  const record = {
    id: `est_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
    ...estimation,
    createdAt: new Date().toISOString()
  };
  db.estimations.push(record);
  writeDb(db);
  return record;
}

export function addWaitlist(email, metadata = {}) {
  const db = readDb();
  const record = {
    id: `wait_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
    email,
    ...metadata,
    createdAt: new Date().toISOString()
  };
  db.waitlist.push(record);
  writeDb(db);
  return record;
}

export function recordDeployment(deploymentData) {
  const db = readDb();
  const record = {
    id: `dep_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
    ...deploymentData,
    createdAt: new Date().toISOString()
  };
  db.deployments.push(record);
  writeDb(db);
  return record;
}

// Project methods
export function addProject(projectData) {
  const db = readDb();
  const record = {
    id: `proj_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ...projectData
  };
  db.projects.push(record);
  writeDb(db);
  return record;
}

export function getProjectsByUser(userId) {
  const db = readDb();
  if (!userId) return db.projects;
  return db.projects.filter(p => p.userId === userId || p.ownerId === userId);
}

export function getProjectById(projectId) {
  const db = readDb();
  return db.projects.find(p => p.id === projectId) || null;
}

export function updateProject(projectId, updates) {
  const db = readDb();
  const index = db.projects.findIndex(p => p.id === projectId);
  if (index === -1) return null;
  db.projects[index] = {
    ...db.projects[index],
    ...updates,
    updatedAt: new Date().toISOString()
  };
  writeDb(db);
  return db.projects[index];
}

export function deleteProject(projectId) {
  const db = readDb();
  const initialLength = db.projects.length;
  db.projects = db.projects.filter(p => p.id !== projectId);
  writeDb(db);
  return db.projects.length < initialLength;
}

