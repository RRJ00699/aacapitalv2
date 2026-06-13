
// Safe number coercion — prevents .toFixed() crashes when Neon returns strings
export const n = (v: unknown): number => { const x = Number(v); return isNaN(x) ? 0 : x; }
