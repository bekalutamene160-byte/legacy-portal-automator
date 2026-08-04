Build Roadmap

This project is being built in 10 phases, each with a clear exit criterion. This document tracks progress and serves as a record of the engineering process every phase is committed separately so the git history tells the story.

Phases
 Phase 0 — Pre-flight check (verify Python, Git, Groq key, GitHub repo)
 Phase 1 — Project scaffolding (folders, git, venv, config files)
 Phase 2 — Install dependencies + pin versions
 Phase 3 — Config layer (pydantic-settings reads .env)
 Phase 4 — Pydantic models (I/O schemas with SecretStr)
 Phase 5 — Browser layer with stealth (Playwright + playwright-stealth)
 Phase 6 — Agent layer — the centerpiece (5-stage loop, Groq LLM)
 Phase 7 — Demo legacy portal (the target — self-hosted FastAPI)
 Phase 8 — FastAPI server (agent's REST API)
 Phase 9 — Demo script + end-to-end test (the "it works" moment)
 Phase 10 — Tests + Docker + README polish + demo video

Tech Stack & Why

Layer                       	Choice	             Rationale
LLM	                        Groq Llama 4 Scout	  Free tier, vision-capable, sub-second inference
Browser automation	        Playwright	          Industry standard, async, official Docker images
Agent framework	            browser-use	         LLM-driven action loop, DOM simplification, MIT licensed
API server	                 FastAPI	          Async, auto OpenAPI docs, type-safe with Pydantic
Validation	                 Pydantic v2	       Fast, JSON schema generation, SecretStr for passwords
Target portal	            Self-hosted FastAPI	   Fully reproducible — anyone can git clone and run


Cost Analysis

Component	Free Tier	                 Our Usage	                Cost

Groq API	30 req/min, 14,400 req/day	~10-30 req per agent run	$0
GitHub	    Unlimited public repos	     1 repo	                    $0
All Pythonpackages OSS (MIT/Apache)	   -                    	$0
Playwright	OSS (Apache 2.0)	           —	                    $0
browser-use	OSS (MIT)	                   —	                    $0

Total			$0


Risk Register

Risk	                                             Mitigation

Groq rate limit hit mid-demo	                 2s delay between steps; cached responses in tests
Llama 4 Scout vision API format mismatch	     Config flag to switch to text-only Llama 3.3 70B
Playwright install fails on Windows	             Run as admin; fallback to --with-deps flag
asyncio event loop crash on Windows	             Set WindowsProactorEventLoopPolicy at startup
Committing the Groq API key                    	.gitignore has .env; pre-commit pattern scan
