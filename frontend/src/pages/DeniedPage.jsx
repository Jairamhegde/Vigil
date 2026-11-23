import { Lock } from "lucide-react";
import { BrandMark } from "../components/ui";

export default function DeniedPage({ username, onLogout }) {
    return (
        <section className="denied">
            <div>
                <BrandMark danger icon={Lock} />
                <h1>Access restricted</h1>
                <p>
                    Only super admins can view the Vigil dashboard.
                    <br />
                    You are signed in as <b>{username}</b>.
                </p>
                <button className="btn" onClick={onLogout}>Sign out</button>
            </div>
        </section>
    );
}
