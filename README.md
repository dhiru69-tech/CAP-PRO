
# ReconMind — AI-Powered Reconnaissance Platform

Complete project source code across all 6 phases + full deployment setup.

## Folder Structure

```
ReconMind_Complete/
│
├── 1_frontend/          ← HTML/CSS/JS UI (landing + dashboard)
│   ├── landing_page.html
│   └── dashboard.html
│
├── 2_backend/           ← FastAPI backend (Python)
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── auth/            ← Google OAuth + JWT
│   ├── database/        ← SQLAlchemy models + SQL migration
│   ├── scans/           ← Scan CRUD API
│   ├── ai/              ← AI analysis service + routes + worker
│   ├── reports/         ← HTML/JSON report generator
│   ├── middleware/
│   ├── dorks/
│   └── utils/
│
├── 3_scanner/           ← Standalone scan engine (Python)
│   ├── engine/          ← ScanRunner + DB worker
│   ├── dork_engine/     ← Depth-aware dork generation
│   ├── discovery/       ← SerpAPI + DuckDuckGo
│   ├── validator/       ← HTTP alive check + risk heuristics
│   ├── evidence/        ← Write results to PostgreSQL
│   └── utils/
│
├── 4_ai_model/          ← Local AI inference engine
│   └── inference/
│       └── inference_engine.py
│
├── 5_training/          ← AI model training pipeline
│   ├── pipeline/
│   │   ├── 01_collect.py
│   │   ├── 02_clean.py
│   │   ├── 03_build_dataset.py
│   │   ├── 04_finetune.py      ← QLoRA (needs GPU)
│   │   ├── 05_evaluate.py
│   │   └── run_pipeline.py
│   └── data/
│       ├── raw/
│       ├── cleaned/
│       └── datasets/           ← Ready train/val/test JSONL
│
├── 6_docs/              ← Architecture docs
│   └── ARCHITECTURE.md
│
└── 7_deployment/        ← Full production deployment
    ├── docker-compose.yml         ← All 5 services
    ├── docker-compose.dev.yml     ← Dev hot-reload
    ├── .env.example               ← Environment template
    ├── docker/
    │   ├── Dockerfile.backend     ← Backend + AI worker
    │   └── Dockerfile.scanner     ← Scanner worker
    ├── nginx/
    │   └── nginx.conf             ← Reverse proxy + SSL
    ├── scripts/
    │   ├── deploy.sh              ← One-click deploy
    │   ├── setup_ssl.sh           ← Let's Encrypt SSL
    │   └── backup_db.sh           ← DB backup
    └── github-actions/
        └── deploy.yml             ← CI/CD pipeline
```

## Quick Start (Local Dev)

```bash
cd 2_backend
pip install -r requirements.txt
cp .env.example .env   # fill in credentials
uvicorn main:app --reload --port 8000
```

## Quick Deploy (Production)

```bash
cp 7_deployment/.env.example .env   # fill in ALL values
chmod +x 7_deployment/scripts/deploy.sh
./7_deployment/scripts/deploy.sh
```

See `7_deployment/README.md` for full deployment guide.

## Phase Summary

| Phase | Folder | What was built |
|-------|--------|---------------|
| 1 — Frontend   | 1_frontend/   | Landing page + full dashboard UI |
| 2 — Auth       | 2_backend/auth/ | Google OAuth + JWT authentication |
| 3 — Backend    | 2_backend/    | FastAPI REST API + PostgreSQL |
| 4 — Scanner    | 3_scanner/    | Dork engine + discovery + validator |
| 5 — Training   | 5_training/   | QLoRA fine-tuning pipeline + dataset |
| 6 — AI         | 2_backend/ai/ | Risk classification + reports + worker |
| 7 — Deployment | 7_deployment/ | Docker + Nginx + CI/CD + SSL scripts |
