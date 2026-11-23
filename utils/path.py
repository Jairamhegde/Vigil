import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ___________________ Databases and frontend ___________________________________
# VIGIL_DB_PATH / VIGIL_AUTH_DB_PATH move the databases, e.g. onto a mounted volume or a test copy.
GUARD_DB = Path(os.environ.get("VIGIL_DB_PATH") or BASE_DIR / "backend" / "database.db")    # identities, accounts, metrics, revocations
AUTH_DB = Path(os.environ.get("VIGIL_AUTH_DB_PATH") or BASE_DIR / "backend" / "auth.db")    # dashboard users (kept separate from identity data)
FRONTEND_DIR = BASE_DIR / "frontend" / "dist"       # built React app (cd frontend && npm run build)

# Persistent folder that outlives the container (Azure Files on Azure). Unset locally: the database file persists.
STATE_DIR = Path(os.environ["VIGIL_STATE_DIR"]) if os.environ.get("VIGIL_STATE_DIR") else None
REVOCATIONS_STATE_FILE = STATE_DIR / "revocations.json" if STATE_DIR else None

# ___________________ Dataset Paths ____________________________________________
DATASETS_DIR = BASE_DIR / "data"

HR_IDENTITIES_JSON = DATASETS_DIR / "identities (2).json"
AD_JSON = DATASETS_DIR / "ad_directory.json"
OKTA_IDENTITIES_JSON = DATASETS_DIR / "okta_identities.json"
AWS_CLOUDTRAIL_JSON = DATASETS_DIR / "aws_cloudtrail_logs.json"

# Optional event logs. Not in the current dataset, picked up automatically when added.
OKTA_SYSTEM_LOG_JSON = DATASETS_DIR / "okta_system_log.json"
AZURE_ACTIVITY_LOG_JSON = DATASETS_DIR / "azure_activity_logs.json"
