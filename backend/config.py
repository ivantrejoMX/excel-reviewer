import os
import tempfile
from pathlib import Path
from dotenv import load_dotenv

# Search for .env starting from this file's directory, then up to the project root
_here = Path(__file__).parent
load_dotenv(_here / ".env", override=True)            # backend/.env
load_dotenv(_here.parent / ".env", override=True)     # excel-reviewer/.env  ← primary location

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
MODEL: str = "claude-sonnet-4-6"
MAX_AGENT_ITERATIONS: int = 50

TEMP_DIR: Path = Path(tempfile.gettempdir()) / "excel_reviewer_jobs"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS: set[str] = {".xlsx", ".xlsm"}
JOB_TTL_SECONDS: int = 2 * 60 * 60  # 2 hours
