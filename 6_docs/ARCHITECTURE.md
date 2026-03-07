# ReconMind — Updated Architecture

## Complete System Flow

```
User opens Landing Page
        ↓
Clicks "Start Scanning"
        ↓
Login Modal appears
        ↓
User clicks "Continue with Google"
        ↓
Google OAuth authenticates
        ↓
Backend creates/updates user record
Backend generates JWT token
        ↓
Frontend receives token (httpOnly cookie)
        ↓
Dashboard unlocks
        ↓
User configures target + dork categories
        ↓
Scan starts → Backend API receives task
        ↓
Scanner Engine executes dorks
        ↓
Results stored in PostgreSQL
        ↓
AI Model analyzes results (after training)
        ↓
Report generated
        ↓
User downloads report
```

## Updated Project Structure

```
reconmind/
│
├── frontend/
│   ├── app/              → Next.js app pages
│   │   ├── page.tsx      → Landing page (public)
│   │   ├── dashboard/    → Main dashboard (protected)
│   │   ├── scan/         → New scan page (protected)
│   │   ├── results/      → Results viewer (protected)
│   │   └── reports/      → Reports page (protected)
│   │
│   ├── components/       → Reusable UI components
│   │   ├── Card.tsx
│   │   ├── Badge.tsx
│   │   ├── Button.tsx
│   │   ├── ScanProgress.tsx
│   │   └── ResultsTable.tsx
│   │
│   ├── auth/             → Auth system
│   │   ├── AuthContext.tsx
│   │   ├── useAuth.ts
│   │   ├── GoogleLoginButton.tsx
│   │   ├── ProtectedRoute.tsx
│   │   └── authService.ts
│   │
│   └── dashboard/        → Dashboard-specific components
│       ├── Sidebar.tsx
│       ├── Topbar.tsx
│       ├── StatCards.tsx
│       └── ScanHistory.tsx
│
├── backend/
│   ├── api/              → Route handlers
│   │   ├── scans.py
│   │   ├── targets.py
│   │   ├── results.py
│   │   └── reports.py
│   │
│   ├── auth/             → Auth system
│   │   ├── google_oauth.py
│   │   ├── jwt_handler.py
│   │   ├── middleware.py
│   │   └── schemas.py
│   │
│   ├── scanner/          → Scanner task manager
│   │   ├── task_manager.py
│   │   └── result_processor.py
│   │
│   ├── models/           → Database models
│   └── utils/            → Helpers
│
├── scanner/              → Independent scanner engine
│   ├── dork_engine/
│   ├── discovery/
│   ├── validator/
│   └── evidence/
│
├── ai-model/             → Local AI model
├── training/             → Training pipeline
├── database/             → PostgreSQL schemas
└── reports/              → Report templates
```

## Development Phases

| Phase | What            | Status         |
|-------|-----------------|----------------|
| 1     | Project Structure | ✅ Complete   |
| 2     | Frontend + Landing + Auth UI | ✅ Complete |
| 3     | Backend API + Google OAuth + JWT | ⏳ Next |
| 4     | Scanner Engine  | ⏳ Pending     |
| 5     | AI Training     | ⏳ Pending     |
| 6     | AI Integration  | ⏳ Pending     |
