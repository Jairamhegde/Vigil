"""
Step 4 - API service.

Serves the query results to the frontend over HTTP. Only a super admin can read dashboard data.

Run:
    python -m uvicorn backend.expose_backend:app --port 8001

When the frontend/ folder exists it is served at http://localhost:8001/, otherwise run the frontend
from any static server and allow its origin with VIGIL_CORS_ORIGINS="http://localhost:5500".
"""
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import auth, queries
from backend.insert_data import load_all
from backend.metrics import run as compute_metrics
from utils.path import FRONTEND_DIR

@asynccontextmanager
async def lifespan(app):
    auth.ensure_default_admin()
    yield


app = FastAPI(title="Vigil API", version="3.0", lifespan=lifespan)

allowed_origins = [origin.strip() for origin in os.environ.get("VIGIL_CORS_ORIGINS", "").split(",") if origin.strip()]

if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

bearer = HTTPBearer(auto_error=False)
refresh_lock = threading.Lock()


# ___________________ Auth ____________________________________________________

class LoginRequest(BaseModel):
    username: str
    password: str


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")

    payload = auth.read_token(credentials.credentials)

    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid")

    return payload


def super_admin_only(user=Depends(current_user)):
    if user["role"] != "super_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a super admin can view the dashboard")

    return user


@app.post("/api/auth/login")
def login(request: LoginRequest):
    try:
        user = auth.verify_user(request.username, request.password)
    except PermissionError as error:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error))

    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")

    token, expires_at = auth.create_token(user)

    return {"token": token, "username": user["username"], "role": user["role"], "expires_at": expires_at}


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return {"username": user["sub"], "role": user["role"], "expires_at": user["exp"]}


# ___________________ Dashboard data (super admin only) _______________________

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/summary")
def summary(user=Depends(super_admin_only)):
    return queries.get_summary()


@app.get("/api/charts")
def charts(user=Depends(super_admin_only)):
    return {
        "tier_distribution": queries.get_tier_distribution(),
        "risk_distribution": queries.get_risk_distribution(),
        "department_risk": queries.get_department_risk(),
        "event_timeline": queries.get_event_timeline(),
    }


@app.get("/api/identities/risky")
def risky_identities(include_all: bool = False, user=Depends(super_admin_only)):
    return queries.get_risky_identities(only_risky=not include_all)


@app.get("/api/identities/dormant/cross-platform")
def cross_platform_dormant(user=Depends(super_admin_only)):
    return queries.get_cross_platform_dormant_identities()


@app.get("/api/identities/dormant/inactive")
def inactive_identities(days: int = Query(30, ge=1, le=365), user=Depends(super_admin_only)):
    return queries.get_inactive_identities(days)


@app.get("/api/identities/privileged")
def privileged_identities(max_tier: int = Query(1, ge=0, le=2), user=Depends(super_admin_only)):
    return queries.get_privileged_identities(max_tier)


@app.post("/api/refresh")
def refresh(user=Depends(super_admin_only)):
    """Re-read the JSON exports, reload the database and recompute the metrics."""
    if not refresh_lock.acquire(blocking=False):
        raise HTTPException(status.HTTP_409_CONFLICT, "A refresh is already running")

    try:
        started = time.time()
        counts = load_all()
        as_of, scored = compute_metrics()
    finally:
        refresh_lock.release()

    return {"loaded": counts, "metrics_as_of": as_of, "identities_scored": scored,
            "seconds": round(time.time() - started, 1)}


# ___________________ Frontend (optional) _____________________________________

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
