"""Environment settings, loaded from .env at the repo root. Import this before reading os.environ.

The shell wins over .env, so `GLADIUS_WORKSPACE=~/notes ./run.sh` overrides it for one run.
.env is not committed; copy .env.example to start one.
"""

from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
