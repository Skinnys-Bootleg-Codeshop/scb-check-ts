export function label(n: number): string {
  return `a${n}`;
}
declare const one: string;
declare const two: string;
declare function sql(s: TemplateStringsArray, ...v: unknown[]): string;
export const q = sql`${one}`;
export const two = `${one}${two}`;
export const wide = `${JSON.stringify({
  k0: 0,
  k1: 1,
  k2: 2,
  k3: 3,
  k4: 4,
  k5: 5,
  k6: 6,
  k7: 7,
  k8: 8,
  k9: 9,
  k10: 10,
  k11: 11,
  k12: 12,
  k13: 13,
})}`;
