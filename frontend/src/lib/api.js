// HTTP client for backend/expose_backend.py and the cached login session.

const SESSION_KEY = "vigil.session";

export class ApiError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
    }
}

export async function apiRequest(path, { method = "GET", body, token } = {}) {
    const headers = { "Content-Type": "application/json" };

    if (token) {
        headers.Authorization = "Bearer " + token;
    }

    const response = await fetch(path, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new ApiError(response.status, data.detail || `Request failed (${response.status})`);
    }

    return data;
}

export function loadSession() {
    try {
        const saved = JSON.parse(localStorage.getItem(SESSION_KEY));

        if (saved && saved.expires_at * 1000 > Date.now()) {
            return saved;
        }
    } catch {
        // Storage blocked or corrupted: treat as signed out
    }

    return null;
}

export function saveSession(session) {
    try {
        localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch {
        // Storage blocked (private mode): the session lasts until the tab closes
    }
}

export function clearSession() {
    try {
        localStorage.removeItem(SESSION_KEY);
    } catch {
        // nothing to clear
    }
}
