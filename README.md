Legacy Portal Automator

Autonomous browser agent that logs into a legacy-style web portal, navigates to the notices section, and downloads announcement PDFs — built with Groq (free LLM API), browser-use, Playwright, and FastAPI.

What This Project Demonstrates
This is a portfolio piece for an AI automation engineer role. It shows you can:

Build a production-grade browser agent with stealth, self-healing, and cost tracking
Integrate a free LLM API (Groq) instead of paid OpenAI
Ship a FastAPI service with typed I/O and OpenAPI docs
Write clean, tested, Dockerized Python code
Think in 5-stage agent loops: Plan → Execute → Verify → Recover → Report
[![Status](https://img.shields.io/badge/status-phase_6_agent-green)]()
[![Tests](https://img.shields.io/badge/tests-120_passing-brightgreen)]()


Tech Stack

Layer	                      Technology	                                                  Cost
LLM	                        Groq (Llama 4 Scout)	                                                     Free
Browser automation	       Playwright + browser-use	                                                   Free (OSS)
Stealth	                   playwright-stealth                                             Free (OSS)
API server	               FastAPI + Uvicorn	                                                    Free (OSS)
Validation	               Pydantic v2	                                                           Free (OSS)
Target portal	           Self-hosted FastAPI demo	                                                          Free


Total cost to build, demo, and deploy: $0

Project Structure

legacy-portal-automator/
├── portal-agent/ # The automator (main portfolio piece)
│ ├── src/
│ │ ├── config.py # Settings via pydantic-settings
│ │ ├── models.py # Pydantic I/O schemas
│ │ ├── browser.py # Playwright + stealth factory
│ │ ├── agent.py # The 5-stage agent loop
│ │ └── main.py # FastAPI server
│ ├── tests/
│ └── examples/
│ └── demo_run.py # Standalone demo script
│
└── legacy-portal/ # The target (self-hosted demo portal)
├── app.py # FastAPI app (login, notices, downloads)
└── templates/


## Build Progress

See [`ROADMAP.md`](./ROADMAP.md) for the full 10-phase build plan and current status.

## License

MIT