// Formatting helpers and shared colors.

// Mirrors the CSS variables in styles.css
export const COLORS = {
    critical: "#e07b83",
    high: "#e3a16f",
    medium: "#d8c47e",
    low: "#8bc4a4",
    accent: "#a3a7f6",        // Wondrous Wisteria
    accentDeep: "#6e73d9",    // darker wisteria, for a fourth series
    light: "#dcd9db",         // Salt n Pepa
    grey: "#858c95",          // Common Feldspar
    slate: "#5f6067",         // Windsor Grey
    surface: "#2e2f35",
    grid: "rgba(133, 140, 149, 0.16)",
    text: "#858c95",
};

export const TIER_COLORS = [COLORS.critical, COLORS.high, COLORS.slate];

// Neutral series colours for platforms (not severity)
export const PLATFORM_COLORS = [COLORS.accent, COLORS.light, COLORS.grey, COLORS.accentDeep];

export const TIER_LABELS = ["Tier 0 · Admin", "Tier 1 · Elevated", "Tier 2 · Standard"];

export const PLATFORM_NAMES = { ad: "Active Directory", okta: "Okta", aws: "AWS", azure: "Azure" };

export const BANDS = [
    { name: "Critical", min: 70, css: "critical", color: COLORS.critical },
    { name: "High", min: 40, css: "high", color: COLORS.high },
    { name: "Medium", min: 20, css: "medium", color: COLORS.medium },
    { name: "Low", min: 0, css: "low", color: COLORS.low },
];

export function riskBand(score) {
    return BANDS.find((band) => score >= band.min);
}

export function platformName(platform) {
    return PLATFORM_NAMES[platform] || platform;
}

export function formatNumber(value) {
    return Number(value || 0).toLocaleString();
}

export function formatDate(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value.length === 10 ? value + "T00:00:00Z" : value);

    return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function initials(name) {
    return String(name || "?")
        .split(/[\s._-]+/)
        .filter(Boolean)
        .map((part) => part[0])
        .slice(0, 2)
        .join("")
        .toUpperCase();
}

export function prettySignal(signal) {
    const text = String(signal).replaceAll("_", " ");
    return text.charAt(0).toUpperCase() + text.slice(1);
}

// "2026-08-25T08:14:27Z" -> "Aug 25, 2026"
export function readableDates(text) {
    return String(text).replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z/g, (stamp) => formatDate(stamp));
}

export function splitReason(reason) {
    const split = reason.indexOf(":");

    if (split < 0) {
        return { signal: reason, detail: "" };
    }

    return { signal: reason.slice(0, split), detail: readableDates(reason.slice(split + 1).trim()) };
}

export function matchesSearch(row, text) {
    if (!text) {
        return true;
    }

    const haystack = [row.full_name, row.employee_id, row.department, row.role_title].join(" ").toLowerCase();
    return haystack.includes(text.toLowerCase());
}

export function countBy(items, getKey) {
    const counts = {};

    items.forEach((item) => {
        const key = getKey(item);
        counts[key] = (counts[key] || 0) + 1;
    });

    return counts;
}
