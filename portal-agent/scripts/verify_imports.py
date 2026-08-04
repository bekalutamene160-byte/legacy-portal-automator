"""
Phase 2 - Verify all critical imports work.
Run: python scripts/verify_imports.py
"""

print("Verifying all imports...")

from browser_use import Agent, BrowserProfile, BrowserSession
print("  [OK] browser_use (Agent, BrowserProfile, BrowserSession)")

from browser_use.llm import ChatGroq
print("  [OK] browser_use.llm.ChatGroq")

from playwright.async_api import async_playwright, Browser, BrowserContext
print("  [OK] playwright.async_api")

from playwright_stealth import Stealth
print("  [OK] playwright_stealth.Stealth")

from pydantic import BaseModel, Field, SecretStr
print("  [OK] pydantic")

from pydantic_settings import BaseSettings, SettingsConfigDict
print("  [OK] pydantic_settings")

from fastapi import FastAPI
print("  [OK] fastapi")

import uvicorn
print("  [OK] uvicorn")

import httpx
print("  [OK] httpx")

import pytest
print("  [OK] pytest")

import jinja2
print("  [OK] jinja2")

import itsdangerous
print("  [OK] itsdangerous")

import reportlab
print("  [OK] reportlab")

print()
print("=" * 50)
print("ALL 13 IMPORTS OK - ready for Groq connection test")
print("=" * 50)