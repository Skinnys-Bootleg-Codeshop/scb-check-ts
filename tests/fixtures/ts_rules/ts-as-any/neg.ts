declare const raw: unknown;
interface Foo { items: string[] }
export const a = raw as Foo;
export const b = (raw as Foo).items;
export const big = {
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
} as any;
