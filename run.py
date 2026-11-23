"""
Vigil - one command to run everything.

    python run.py

1. Loads the JSON exports from data/ into the database      (backend/insert_data.py)
2. Computes dormant / ghost / damage / risk metrics          (backend/metrics.py)
3. Builds the React dashboard when it is missing or outdated (frontend/)
4. Starts the API + dashboard and prints the link            (backend/expose_backend.py)

Options (environment variables):
    VIGIL_PORT             port to serve on (default 8001)
    VIGIL_ADMIN_USER       super admin username created on first run (default superadmin)
    VIGIL_ADMIN_PASSWORD   super admin password created on first run (demo login from the README if not set)
"""
import logging
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
DIST_INDEX = FRONTEND / "dist" / "index.html"

HOST = "127.0.0.1"
PORT = int(os.environ.get("VIGIL_PORT", "8001"))

sys.path.insert(0, str(ROOT))
logging.basicConfig(level=logging.ERROR)


def step(number, text):
    print(f"\n[{number}/4] {text}")


def check_python_packages():
    missing = []

    for package in ["fastapi", "uvicorn", "pydantic"]:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        sys.exit(f"Missing Python packages: {', '.join(missing)}\nInstall them with: pip install -r requirements.txt")


def load_data():
    from backend.insert_data import load_all

    counts = load_all()
    print(f"      {counts['identities']} identities, {counts['accounts']} accounts, "
          f"{counts['entitlements']} entitlements, {counts['new_audit_events']} new events")


def compute_metrics():
    from backend.metrics import run

    as_of, scored = run()
    print(f"      {scored} identities scored (as of {as_of})")


def frontend_is_outdated():
    if not DIST_INDEX.exists():
        return True

    built_at = DIST_INDEX.stat().st_mtime
    sources = list((FRONTEND / "src").rglob("*")) + [FRONTEND / "index.html", FRONTEND / "package.json"]

    return any(path.is_file() and path.stat().st_mtime > built_at for path in sources)


def build_frontend():
    if not frontend_is_outdated():
        print("      already up to date")
        return

    npm = shutil.which("npm")

    if npm is None:
        sys.exit("Node.js / npm is needed to build the dashboard. Install it from https://nodejs.org and run again.")

    if not (FRONTEND / "node_modules").exists():
        print("      installing frontend packages (first run only)...")
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND, check=True)

    print("      building dashboard...")
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True, stdout=subprocess.DEVNULL)


def port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((HOST, port)) != 0


def start_server():
    import uvicorn

    if not port_is_free(PORT):
        sys.exit(f"Port {PORT} is already in use. Stop the other server or run with VIGIL_PORT=<another port>.")

    url = f"http://localhost:{PORT}"

    print("\n" + "=" * 60)
    print(f"  Vigil is live at:  {url}")
    print(f"  API docs:          {url}/docs")
    print("  Press Ctrl+C to stop.")
    print("=" * 60 + "\n")

    uvicorn.run("backend.expose_backend:app", host=HOST, port=PORT, log_level="warning")


def main():
    os.chdir(ROOT)
    check_python_packages()

    step(1, "Loading data from data/ ...")
    load_data()

    step(2, "Computing risk metrics ...")
    compute_metrics()

    step(3, "Preparing the dashboard ...")
    build_frontend()

    step(4, "Starting the server ...")
    start_server()


if __name__ == "__main__":
    main()
