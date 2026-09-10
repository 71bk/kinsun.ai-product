"""Start the local Agent with python-dotenv interpolation, never print secrets."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env", override=True)
os.environ["APP_ENV"] = "development"
sys.path.insert(0, str(ROOT / "services/agent-runtime/src"))

if __name__ == "__main__":
    uvicorn.run("agent_runtime.app:app", host="127.0.0.1", port=8001)
