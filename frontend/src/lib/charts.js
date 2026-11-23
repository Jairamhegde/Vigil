// Shared Recharts styling so every chart looks the same.

import { COLORS } from "./format";

export const AXIS = {
    stroke: COLORS.grid,
    tick: { fill: COLORS.text, fontSize: 12 },
    tickLine: false,
    axisLine: false,
};

export const GRID = {
    stroke: COLORS.grid,
    strokeDasharray: "3 3",
};

export const LEGEND = {
    iconType: "circle",
    iconSize: 8,
    itemSorter: () => 0,
    wrapperStyle: { fontSize: 12, color: COLORS.text, paddingTop: 8 },
};

export const CURSOR = { fill: "rgba(133, 140, 149, 0.08)" };

export const PIE_STROKE = { stroke: COLORS.surface, strokeWidth: 3 };
