// Actions that change data (revoking access) need the raw request, a toast and a data reload.
// The Dashboard provides them once, so any page can offer a Revoke button.

import { createContext, useContext } from "react";

const ActionsContext = createContext(null);

export function ActionsProvider({ request, notify, dataChanged, children }) {
    return <ActionsContext.Provider value={{ request, notify, dataChanged }}>{children}</ActionsContext.Provider>;
}

export function useActions() {
    return useContext(ActionsContext);
}
