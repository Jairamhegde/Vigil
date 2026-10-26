import { useState } from "react";
import { Brand } from "../components/ui";

export default function LoginPage({ onLogin, message }) {
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);

    const submit = async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");

        try {
            await onLogin(username.trim(), password);
        } catch (failure) {
            setError(failure.message);
            setPassword("");
        } finally {
            setBusy(false);
        }
    };

    return (
        <section className="login-screen">
            <form className="login-card" onSubmit={submit}>
                <Brand />

                <h1>Welcome back</h1>
                <p>Sign in with a super admin account to open the dashboard.</p>

                <label className="field">
                    <span>Username</span>
                    <input value={username} onChange={(event) => setUsername(event.target.value)}
                           autoComplete="username" autoFocus required />
                </label>

                <label className="field">
                    <span>Password</span>
                    <input type="password" value={password} onChange={(event) => setPassword(event.target.value)}
                           autoComplete="current-password" required />
                </label>

                <button className="btn btn-primary btn-block" type="submit" disabled={busy}>
                    {busy ? "Signing in…" : "Sign in"}
                </button>

                <div className="form-error" role="alert">{error || message}</div>
                <div className="login-foot">Sessions stay signed in on this device for 8 hours.</div>
            </form>
        </section>
    );
}
