Legacy Portal Automator
-
An AI-powered automation agent that learns to navigate legacy web portals — the kind of server-rendered, form-based intranets found in banks, hospitals, and government offices — and automatically downloads documents from them.

Built with browser-use, Groq (LLaMA 3.3 70B), FastAPI, and ReportLab. 100% free to run.

What It Does
You give the agent:

A portal URL
Login credentials
Which tab to navigate to
What files to download
The agent then:

Opens a headless browser
Navigates to the portal
Logs in using the credentials
Finds the target tab
Downloads matching files
Verifies the downloads
Returns a structured result
You can trigger runs via a REST API and generate professional PDF reports of each automation run.

Architecture
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ demo-portal │ │ portal-agent │ │ server │
│ │ │ │ │ │
│ FastAPI app │◄────│ browser-use │◄────│ FastAPI API │
│ that simulates │ │ agent powered │ │ POST /api/runs │
│ a legacy 2010 │ │ by Groq LLaMA │ │ returns JSON │
│ intranet portal│ │ 3.3 70B │ │ │
└─────────────────┘ └─────────────────┘ └────────┬────────┘
│
▼
┌─────────────────┐
│ reports │
│ │
│ ReportLab PDF │
│ generator │
└─────────────────┘

**Four independent packages:**

| Package | Purpose | Tests |
|---------|---------|-------|
| `demo-portal/` | The target website (FastAPI + Jinja2) | 29 |
| `portal-agent/` | The automation agent (browser-use + Groq) | 120 |
| `server/` | HTTP API layer (FastAPI) | 48 |
| `reports/` | PDF report generator (ReportLab) | 26 |
| `e2e/` | End-to-end integration tests | 10+ |

**Total: 230+ tests, all passing.**

---

## Tech Stack

- **Python 3.11**
- **browser-use 0.13.7** — LLM-driven browser automation
- **Groq API** — free LLM inference (LLaMA 3.3 70B Versatile)
- **FastAPI 0.141** — HTTP API framework
- **Pydantic v2** — settings + domain models with validation
- **ReportLab 4.4** — PDF report generation
- **Playwright** — headless Chromium (via browser-use)
- **pytest + pytest-asyncio** — async test suite

---

## Project Structure
legacy-portal-automator/
├── demo-portal/ # The target website
│ ├── app.py # FastAPI app (login, tabs, downloads)
│ ├── seed_pdfs.py # Generates placeholder PDFs
│ ├── templates/ # Jinja2 HTML templates
│ │ ├── base.html
│ │ ├── login.html
│ │ ├── dashboard.html
│ │ └── tab.html
│ ├── static/ # CSS
│ └── pdfs/ # Generated PDFs (auto-created)
│
├── portal-agent/ # The automation agent
│ ├── src/
│ │ ├── config.py # Pydantic Settings (env vars)
│ │ ├── models.py # Domain models (4 Pydantic models)
│ │ ├── browser.py # BrowserProfile + stealth config
│ │ └── agent.py # 5-stage agent loop (Plan→Execute→Verify→Recover→Report)
│ ├── tests/ # 120 tests
│ ├── requirements.txt
│ └── pytest.ini
│
├── server/ # HTTP API layer
│ ├── main.py # FastAPI app + routes
│ ├── schemas.py # HTTP request/response models
│ ├── runner.py # HTTP request → PortalAgent → result
│ ├── tests/ # 48 tests
│ └── pytest.ini
│
├── reports/ # PDF report generator
│ ├── generator.py # ReportLab PDF generation
│ ├── tests/ # 26 tests
│ ├── make_sample.py # Generate a sample PDF
│ └── pytest.ini
│
├── e2e/ # End-to-end integration tests
│ ├── test_full_pipeline.py # Portal → Server → Report
│ └── pytest.ini
│
├── pyrightconfig.json # Pylance config (cross-folder imports)
├── requirements.txt # Root dependencies
└── README.md # This file

---

## Setup

### Prerequisites

- Python 3.11+
- A Groq API key (free — get one at https://console.groq.com)
- Windows / macOS / Linux

### Installation

```bash
git clone https://github.com/bekalutamene160-byte/legacy-portal-automator.git
cd legacy-portal-automator

python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate    # macOS/Linux

pip install -r portal-agent/requirements.txt
pip install -r demo-portal/requirements.txt
pip install -r server/requirements.txt
pip install -r reports/requirements.txt
pip install pypdf==5.8.0

playwright install chromium
Environment Variables
Create portal-agent/.env:
GROQ_API_KEY=gsk_your_real_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
PORTAL_URL=http://localhost:8001
HEADLESS=true
Running the Components
1. Start the Demo Portal (Terminal 1)
cd demo-portal
uvicorn app:app --port 8001
Open http://localhost:8001 — log in with admin / portal123.

2. Start the API Server (Terminal 2)
cd server
uvicorn main:app --port 8000
Open http://localhost:8000/docs for interactive API docs.

3. Submit an Automation Run
curl -X POST http://localhost:8000/api/runs `
  -H "Content-Type: application/json" `
  -d '{"portal_url":"http://localhost:8001","username":"admin","password":"portal123","target_tab":"Invoices","file_pattern":"*.pdf","max_downloads":5}'

  4. Generate a PDF Report
cd reports
python make_sample.py
Open reports/sample_report.pdf.

Running the Tests
Each package has its own test suite. Run them individually:
# Demo portal tests (29 tests)
cd portal-agent
python -m pytest tests/test_portal.py -v

# Agent tests (120 tests)
cd portal-agent
python -m pytest tests/ -v

# Server tests (48 tests)
cd server
python -m pytest tests/ -v

# Report generator tests (26 tests)
cd reports
python -m pytest tests/ -v

# End-to-end integration tests
cd e2e
python -m pytest tests/ -v

API Reference
GET /health
Returns server health status.

Response:{"status": "ok", "service": "legacy-portal-automator-api"}

GET /api/info
Returns server configuration.

Response:{
  "name": "Legacy Portal Automator API",
  "version": "0.1.0",
  "configured_model": "llama-3.3-70b-versatile",
  "headless_mode": true,
  "max_steps": 50
}

POST /api/runs
Submit a portal automation task.

Request:{
  "portal_url": "http://localhost:8001",
  "username": "admin",
  "password": "portal123",
  "target_tab": "Invoices",
  "file_pattern": "*.pdf",
  "max_downloads": 5,
  "download_subdir": ""
}


Response:
{
  "success": true,
  "files_downloaded": [
    {
      "filename": "invoice_001.pdf",
      "size_bytes": 1936,
      "downloaded_at": "2024-06-15T10:30:00Z",
      "local_path": "/tmp/downloads/invoice_001.pdf"
    }
  ],
  "total_steps": 12,
  "total_tokens": 4500,
  "error": null,
  "agent_trace": ["start", "login", "navigate", "download", "done"],
  "started_at": "2024-06-15T10:29:50Z",
  "completed_at": "2024-06-15T10:30:42Z",
  "duration_seconds": 52.3
}

The 5-Stage Agent Pattern
The PortalAgent implements a robust 5-stage loop:

Plan — Build a detailed prompt with portal URL, credentials, target tab, and step-by-step instructions
Execute — Launch the browser-use Agent with a timeout
Verify — Scan the download folder for matching files
Recover — If verification fails, retry with an augmented prompt (up to 2 retries)
Report — Return a structured PortalRunResult (never raises)
This pattern ensures the agent is resilient — transient failures are retried, and the caller always gets a result object back.

Portfolio Highlights

This project demonstrates:

LLM-driven automation — using browser-use + Groq to automate real web interactions
Production-grade architecture — four independent packages with clear separation of concerns
Comprehensive testing — 230+ tests covering unit, integration, and end-to-end scenarios
Type safety — Pydantic v2 models with validation throughout
Security awareness — filename sanitization, path traversal prevention, SecretStr for passwords
Stealth browsing — custom User-Agent, disabled automation flags, proxy support
Professional reporting — ReportLab PDFs with executive summaries, tables, and traces
Clean documentation — structured README, inline docstrings, API reference


License
MIT — Built for the AI Automation portfolio project.

---

## Step 7 — Run the e2e tests

```powershell
cd C:\Users\Muler\Documents\legacy-portal-automator\e2e
python -m pytest tests/ -v
You should see 10+ tests pass, 0 failures.

