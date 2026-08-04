"""
Phase 2 - Groq Connection Test
==============================

Verifies:
1. Your Groq API key works
2. The Llama 4 Scout model responds
3. The browser_use ChatGroq integration is correctly wired

Run AFTER installing all dependencies and creating your .env file.

Usage (PowerShell, with venv active, from portal-agent/ folder):
    python scripts/groq_hello_world.py

Expected output:
    [OK] Groq client initialized
    [OK] Sending test message to Llama 4 Scout...
    [OK] Response received in 0.83s
    [OK] Model reply: GROQ_CONNECTION_OK

If you see AuthenticationError, your GROQ_API_KEY is wrong or expired.
If you see RateLimitError, you hit the free tier limit - wait 60 seconds and retry.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Load .env file
from dotenv import load_dotenv

# Look for .env in the project root (two levels up from scripts/)
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)

# Verify the API key is present
api_key = os.getenv("GROQ_API_KEY", "")
if not api_key or api_key == "gsk_your_key_here":
    print("[FAIL] GROQ_API_KEY is not set.")
    print(f"       Looked in: {env_path}")
    print("       Create .env from .env.example and paste your real Groq key.")
    sys.exit(1)

print(f"[OK] Loaded .env from: {env_path}")
print(f"[OK] API key found: gsk_...{api_key[-4:]}  (last 4 chars only, for safety)")

# Now try to import browser_use's ChatGroq
# Now try to import browser_use's ChatGroq (bundled with browser-use, no langchain needed)
try:
    from browser_use.llm import ChatGroq
    print("[OK] browser_use.llm.ChatGroq imported successfully")
except ImportError as e:
    print(f"[FAIL] Could not import ChatGroq: {e}")
    print("       Run: pip install browser-use")
    sys.exit(1)


async def test_groq_connection():
    """Send a tiny message to Groq and verify we get a response."""
    model_name = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    print(f"[OK] Using model: {model_name}")

    # Initialize the chat model
    llm = ChatGroq(model=model_name, api_key=api_key, temperature=0)
    print("[OK] Groq LLM client initialized")

    # Send a test message
    print("[OK] Sending test message: 'Reply with exactly: GROQ_CONNECTION_OK'")
    start_time = time.time()

    try:
        # browser_use ChatGroq is async - use ainvoke
        messages = [{"role": "user", "content": "Reply with exactly: GROQ_CONNECTION_OK"}]
        response = await llm.ainvoke(messages)
        elapsed = time.time() - start_time

        print(f"[OK] Response received in {elapsed:.2f}s")

        # Extract the text content from the response
        if hasattr(response, "content"):
            content = response.content
        elif isinstance(response, str):
            content = response
        else:
            content = str(response)

        print(f"[OK] Model reply: {content}")

        if "GROQ_CONNECTION_OK" in str(content).upper():
            print()
            print("=" * 50)
            print("SUCCESS! Groq connection is working.")
            print("You are ready for Phase 3.")
            print("=" * 50)
            return True
        else:
            print()
            print("[WARN] Model replied, but not with the expected text.")
            print("       This is usually fine - LLMs are non-deterministic.")
            print("       Connection is working; proceeding to Phase 3.")
            return True

    except Exception as e:
        print(f"[FAIL] Error calling Groq: {type(e).__name__}: {e}")
        print()
        if "authentication" in str(e).lower() or "401" in str(e):
            print("       Your API key is invalid. Get a new one at:")
            print("       https://console.groq.com/keys")
        elif "rate" in str(e).lower() or "429" in str(e):
            print("       You hit the free tier rate limit.")
            print("       Wait 60 seconds and run this script again.")
        elif "model" in str(e).lower() and "not" in str(e).lower():
            print("       The model name is wrong. Check GROQ_MODEL in your .env")
        return False


if __name__ == "__main__":
    asyncio.run(test_groq_connection())