import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import ErrorBoundary from "./components/ErrorBoundary";
import Sidebar from "./components/Sidebar";
import Toast from "./components/Toast";
import Topbar from "./components/Topbar";
import { PageSkeleton } from "./components/ui";
import { apiRequest, clearSession, loadSession, saveSession } from "./lib/api";
import { DataProvider, useApi } from "./lib/data";
import { formatDate } from "./lib/format";
import DeniedPage from "./pages/DeniedPage";
import LoginPage from "./pages/LoginPage";

// Dashboard pages load on demand, so the login screen does not wait for the chart library
const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const RiskyPage = lazy(() => import("./pages/RiskyPage"));
const DormantPage = lazy(() => import("./pages/DormantPage"));
const PrivilegedPage = lazy(() => import("./pages/PrivilegedPage"));

const PAGES = {
    overview: {
        title: "Overview",
        subtitle: "Identity risk across HR, Active Directory, Okta, AWS and Azure",
        component: OverviewPage,
    },
    risky: {
        title: "Risky identities",
        subtitle: "Who is most likely to be misused, and how much damage they could do",
        component: RiskyPage,
    },
    dormant: {
        title: "Dormant identities",
        subtitle: "Leavers still active in the cloud, and access nobody is using",
        component: DormantPage,
    },
    privileged: {
        title: "Privileged access",
        subtitle: "Who holds admin and elevated rights, including inherited ones",
        component: PrivilegedPage,
    },
};

function pageFromHash() {
    const name = window.location.hash.replace("#/", "");
    return PAGES[name] ? name : "overview";
}

function useHashPage() {
    const [page, setPage] = useState(pageFromHash);

    useEffect(() => {
        const onChange = () => setPage(pageFromHash());

        window.addEventListener("hashchange", onChange);
        return () => window.removeEventListener("hashchange", onChange);
    }, []);

    return page;
}

export default function App() {
    const [session, setSession] = useState(loadSession);
    const [verified, setVerified] = useState(false);
    const [denied, setDenied] = useState(false);
    const [message, setMessage] = useState("");
    const [dataVersion, setDataVersion] = useState(0);

    const logout = useCallback((reason = "") => {
        clearSession();
        setSession(null);
        setVerified(false);
        setDenied(false);
        setMessage(reason);
    }, []);

    // Every dashboard request carries the token. 401 = session gone, 403 = not a super admin.
    const request = useCallback(async (path, options = {}) => {
        try {
            return await apiRequest(path, { ...options, token: session && session.token });
        } catch (error) {
            if (error.status === 401) {
                logout("Your session has expired. Please sign in again.");
            }

            if (error.status === 403) {
                setDenied(true);
            }

            throw error;
        }
    }, [session, logout]);

    // A cached session is confirmed with the server before any data is shown
    useEffect(() => {
        if (!session || verified) {
            return;
        }

        request("/api/auth/me")
            .then((me) => {
                setDenied(me.role !== "super_admin");
                setVerified(true);
            })
            .catch(() => logout());
    }, [session, verified, request, logout]);

    const login = async (username, password) => {
        const newSession = await apiRequest("/api/auth/login", { method: "POST", body: { username, password } });

        saveSession(newSession);
        setMessage("");
        setSession(newSession);
        setDenied(newSession.role !== "super_admin");
        setVerified(true);
    };

    if (!session) {
        return <LoginPage onLogin={login} message={message} />;
    }

    if (!verified) {
        return <div className="denied"><div className="muted">Checking your session…</div></div>;
    }

    if (denied) {
        return <DeniedPage username={session.username} onLogout={() => logout()} />;
    }

    return (
        <DataProvider request={request} version={dataVersion}>
            <Dashboard
                username={session.username}
                request={request}
                onLogout={() => logout()}
                onDataChanged={() => setDataVersion((version) => version + 1)}
            />
        </DataProvider>
    );
}

function Dashboard({ username, request, onLogout, onDataChanged }) {
    const page = useHashPage();
    const summary = useApi("/api/summary");
    const [refreshing, setRefreshing] = useState(false);
    const [toast, setToast] = useState(null);
    const closeToast = useCallback(() => setToast(null), []);

    const current = PAGES[page];
    const PageComponent = current.component;

    useEffect(() => {
        document.title = `${current.title} · Vigil`;
    }, [current]);

    const refresh = async () => {
        setRefreshing(true);

        try {
            const result = await request("/api/refresh", { method: "POST" });

            onDataChanged();
            setToast({
                kind: "success",
                title: "Data refreshed",
                body: `${result.loaded.identities} identities, ${result.loaded.accounts} accounts, `
                    + `${result.loaded.new_audit_events} new events · ${result.seconds}s`,
            });
        } catch (error) {
            setToast({ kind: "error", title: "Refresh failed", body: error.message });
        } finally {
            setRefreshing(false);
        }
    };

    const stamp = summary.data ? "Data as of " + formatDate(summary.data.reference_time) : "Loading data…";

    return (
        <div className="app">
            <Sidebar page={page} username={username} onLogout={onLogout}
                     riskyCount={summary.data ? summary.data.risky_identities : 0} />

            <main className="main">
                <Topbar title={current.title} subtitle={current.subtitle} stamp={stamp}
                        refreshing={refreshing} onRefresh={refresh} />
                <ErrorBoundary key={page}>
                    <Suspense fallback={<PageSkeleton />}>
                        <PageComponent />
                    </Suspense>
                </ErrorBoundary>
            </main>

            <Toast toast={toast} onClose={closeToast} />
        </div>
    );
}
