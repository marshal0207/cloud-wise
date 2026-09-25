# CloudWise - Multi-Cloud Resource Intelligence & Cost Sizing Platform

CloudWise is a cloud infrastructure resource intelligence, estimation, deployment advisory, and cost tuning platform built with **React (TypeScript + Vite)** on the frontend and **Django + Django REST Framework** on the backend.

---

## 📁 Repository Structure

```
Cloudwise-try/
├── frontend/               # React + TypeScript + Vite + Tailwind CSS Frontend
│   ├── src/                # Pages, Components, Context, and Styles
│   ├── package.json
│   ├── vite.config.ts      # Configured with proxy to http://127.0.0.1:8000
│   └── README.md
├── backend/                # Django + Django REST Framework Backend
│   ├── backend/            # Django Settings, URLs, WSGI, ASGI
│   ├── api/                # Models, Serializers, Views, Permissions, Admin
│   ├── manage.py
│   ├── requirements.txt
│   └── .env.example
└── README.md
```

---

## 🚀 Quick Start Guide

### 1. Start Django Backend

```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Run database migrations
python manage.py migrate

# Start Django development server (runs on http://127.0.0.1:8000)
python manage.py runserver 127.0.0.1:8000
```

- **API Base URL**: `http://127.0.0.1:8000/api/`
- **Django Admin Panel**: `http://127.0.0.1:8000/admin/`

---

### 2. Start React Frontend

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start Vite development server (runs on http://localhost:5173)
npm run dev
```

The frontend will start at `http://localhost:5173` and automatically proxy `/api/*` requests to the Django backend on port `8000`.

---

## 🛠️ Tech Stack

### Frontend
- **Framework**: React 18 + TypeScript + Vite
- **Styling**: Tailwind CSS + Framer Motion
- **Icons**: Lucide React
- **Routing**: React Router v6

### Backend
- **Framework**: Python 3 + Django 5 + Django REST Framework
- **Authentication**: SimpleJWT (JWT Authentication)
- **Database**: Django ORM + SQLite (Local Dev) / PostgreSQL (Production)
- **CORS**: `django-cors-headers`

---

## 🔐 Features Implemented
- User Registration & Sign In (JWT Authentication)
- Role-Based Access Control (RBAC: Owner, Editor, Viewer, Admin)
- INR ₹ Resource Cost Sizing Engine
- Multi-Cloud Comparison (AWS, GCP, Azure, DigitalOcean)
- GitHub Repository Integration & Manifest Generation
- Infrastructure Deployment Simulator & Logging
- Dynamic Cost Optimization Tuning
- Django Admin Control Panel for Data Management

# Django setup
```
    .\.venv\Scripts\Activate.ps1 
    python manage.py runserver
```
- cd backend
- python -m venv .venv
- .\.venv\Scripts\Activate.ps1
- pip install -r requirements.txt
- cp .env.example .env
#### Edit the .env file with your credentials if necessary
- python manage.py migrate
- python manage.py runserver

```bash
    .\.venv\Scripts\Activate.ps1
    .\.venv\Scripts\pip.exe install -r requirements.txt
    .\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

