import { useEffect } from "react";

export default function Toast({ toast, onClose }) {
    useEffect(() => {
        if (!toast) {
            return undefined;
        }

        const timer = setTimeout(onClose, 4500);
        return () => clearTimeout(timer);
    }, [toast, onClose]);

    return (
        <div className={`toast ${toast ? "show" : ""} ${toast ? toast.kind : ""}`} role="status" aria-live="polite">
            {toast && (
                <div>
                    <div className="toast-title">{toast.title}</div>
                    <div className="toast-body">{toast.body}</div>
                </div>
            )}
        </div>
    );
}
