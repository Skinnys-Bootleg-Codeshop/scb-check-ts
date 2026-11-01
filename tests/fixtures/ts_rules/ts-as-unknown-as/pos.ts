declare const raw: object;
export const a = raw as unknown as string[]; // HIT
export const c = (raw as unknown) as string[]; // HIT
