"""
Step 4 - API service.

Serves the query results to the frontend over HTTP. Only a super admin can read dashboard data.

Run:
    python -m uvicorn backend.expose_backend:app --port 8001

When the frontend/ folder exists it is served at http://localhost:8001/, otherwise run the frontend
from any static server and allow its origin with VIGIL_CORS_ORIGINS="http://localhost:5500".
On Azure the dashboard is on Azure Static Web Apps, so its URL is in VIGIL_CORS_ORIGINS.
"""
import os
import threading
import time
from contextlib import asynccontextmanager
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import auth, queries, raw_data, revocation
from backend.bootstrap import ensure_data_loaded
from backend.db_connection import close_pool
from backend.insert_data import load_all
from backend.metrics import run as compute_metrics
from utils.path import FRONTEND_DIR


@asynccontextmanager
async def lifespan(app):
    # Azure Database for PostgreSQL starts empty: the first API start loads data/ (no-op on SQLite)
    ensure_data_loaded()
    auth.ensure_default_admin()

    # SQLite with VIGIL_STATE_DIR: bring back revocations saved outside the container
    if revocation.restore_state():
        compute_metrics()

    yield

    close_pool()   # return pooled PostgreSQL connections on shutdown (no-op on SQLite)


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
def inactive_identities(days: int = Query(30, ge=0, le=365), user=Depends(super_admin_only)):
    return queries.get_inactive_identities(days)


@app.get("/api/identities/privileged")
def privileged_identities(max_tier: int = Query(1, ge=0, le=2), user=Depends(super_admin_only)):
    return queries.get_privileged_identities(max_tier)


# ___________________ Revoking access (two-step verification) _________________

class RevokeRequest(BaseModel):
    employee_id: str
    account_ids: List[int] = Field(min_length=1, max_length=50)
    reason: str = Field(max_length=500)


class RevokeConfirm(BaseModel):
    challenge_id: str
    password: str
    confirm_text: str


@app.get("/api/identities/{employee_id}/access")
def identity_access(employee_id: str, user=Depends(super_admin_only)):
    person = revocation.get_identity_access(employee_id)

    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown employee {employee_id}")

    return person


@app.post("/api/revocations/prepare")
def prepare_revocation(request: RevokeRequest, user=Depends(super_admin_only)):
    """Step 1: check the selection and issue a short-lived confirmation challenge."""
    try:
        return revocation.prepare_revocation(user["sub"], request.employee_id, request.account_ids, request.reason)
    except revocation.RevocationError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error))


@app.post("/api/revocations/confirm")
def confirm_revocation(request: RevokeConfirm, user=Depends(super_admin_only)):
    """Step 2: re-enter the password and type the employee ID. Then the access is revoked."""
    try:
        revocation.check_challenge(user["sub"], request.challenge_id, request.confirm_text)

        try:
            verified = auth.verify_user(user["sub"], request.password)
        except PermissionError as error:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error))

        if verified is None:
            # 400, not 401: a wrong password here must not sign the admin out
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Wrong password. Nothing was revoked.")

        challenge = revocation.check_challenge(user["sub"], request.challenge_id, request.confirm_text, consume=True)
    except revocation.RevocationError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error))

    with refresh_lock:
        revoked = revocation.revoke(challenge)
        saved = revocation.save_state()
        compute_metrics()

    after = revocation.get_identity_access(challenge["employee_id"])

    return {"employee_id": challenge["employee_id"], "full_name": challenge["full_name"],
            "revoked_accounts": revoked, "risk_score": after["risk_score"] if after else None,
            "saved": saved}


@app.get("/api/revocations")
def revocations(user=Depends(super_admin_only)):
    return revocation.list_revocations()


# ___________________ Raw data browser ________________________________________

@app.get("/api/raw")
def raw_datasets(user=Depends(super_admin_only)):
    return raw_data.list_datasets()


@app.get("/api/raw/{dataset}")
def raw_dataset(dataset: str, search: str = Query("", max_length=200), offset: int = Query(0, ge=0),
                limit: int = Query(50, ge=1, le=200), user=Depends(super_admin_only)):
    page = raw_data.get_dataset_page(dataset, search, offset, limit)

    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown dataset {dataset}")

    return page


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
