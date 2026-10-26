// Shared data layer: one request per API path, cached until the user presses Refresh.

import { createContext, useContext, useEffect, useMemo, useState } from "react";

const DataContext = createContext(null);

export function DataProvider({ request, version, children }) {
    // A new cache for every data version, so Refresh re-fetches everything
    const cache = useMemo(() => new Map(), [version]);

    const get = (path) => {
        if (!cache.has(path)) {
            const promise = request(path).catch((error) => {
                cache.delete(path);
                throw error;
            });

            cache.set(path, promise);
        }

        return cache.get(path);
    };

    return <DataContext.Provider value={{ get, version }}>{children}</DataContext.Provider>;
}

export function useApi(path) {
    const { get, version } = useContext(DataContext);
    const [result, setResult] = useState({ data: null, error: null, loading: true });

    useEffect(() => {
        let active = true;

        setResult((previous) => ({ ...previous, loading: true }));

        get(path)
            .then((data) => active && setResult({ data, error: null, loading: false }))
            .catch((error) => active && setResult({ data: null, error, loading: false }));

        return () => {
            active = false;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [path, version]);

    return result;
}
