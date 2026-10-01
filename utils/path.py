from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

HYBRIDDB = BASE_DIR / "hybridguard.db"

# ___________________ Dataset Paths ____________________________________________
DATASETS_DIR = BASE_DIR / "csvs"

IDENTITIES_JSON = DATASETS_DIR / "identities_messy.json"
OKTA_JSON = DATASETS_DIR / "okta_messy.json"
AWS_JSON = DATASETS_DIR / "aws_messy.json"
AZURE_JSON = DATASETS_DIR / "azure_messy.json"

# Clean fallbacks if messy files are absent
if not IDENTITIES_JSON.exists():
    IDENTITIES_JSON = DATASETS_DIR / "identities.json"
if not OKTA_JSON.exists():
    OKTA_JSON = DATASETS_DIR / "okta.json"
if not AWS_JSON.exists():
    AWS_JSON = DATASETS_DIR / "aws.json"
if not AZURE_JSON.exists():
    AZURE_JSON = DATASETS_DIR / "azure.json"