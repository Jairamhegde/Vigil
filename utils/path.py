from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ___________________ Databases and frontend ___________________________________
GUARD_DB = BASE_DIR / "backend" / "database.db"     # identities, accounts, entitlements, events, metrics
AUTH_DB = BASE_DIR / "backend" / "auth.db"          # dashboard users (kept separate from identity data)
FRONTEND_DIR = BASE_DIR / "frontend" / "dist"       # built React app (cd frontend && npm run build)

# ___________________ Dataset Paths ____________________________________________
DATASETS_DIR = BASE_DIR / "data"

HR_IDENTITIES_JSON = DATASETS_DIR / "identities (2).json"
AD_JSON = DATASETS_DIR / "ad_directory.json"
OKTA_IDENTITIES_JSON = DATASETS_DIR / "okta_identities.json"
AWS_CLOUDTRAIL_JSON = DATASETS_DIR / "aws_cloudtrail_logs.json"

# Optional event logs. Not in the current dataset, picked up automatically when added.
OKTA_SYSTEM_LOG_JSON = DATASETS_DIR / "okta_system_log.json"
AZURE_ACTIVITY_LOG_JSON = DATASETS_DIR / "azure_activity_logs.json"
