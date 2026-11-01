declare const raw: unknown;
export const a = raw as any; // HIT
export const b = (raw as any).items; // HIT
