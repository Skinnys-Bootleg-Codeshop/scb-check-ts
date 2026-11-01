export interface Box<T> {
  value: T;
}

export function box<T>(value: T): Box<T> {
  return { value };
}

export function mapBox<T, U>(b: Box<T>, fn: (v: T) => U): Box<U> {
  return { value: fn(b.value) };
}

export function pick<T, K extends keyof T>(obj: T, key: K): T[K] {
  return obj[key];
}

export function firstOr<T>(items: T[], fallback: T): T {
  if (items.length === 0) {
    return fallback;
  }
  return items[0];
}

export function groupBy<T, K extends string>(
  items: T[],
  keyOf: (item: T) => K,
): Record<K, T[]> {
  const out = {} as Record<K, T[]>;
  for (const item of items) {
    const key = keyOf(item);
    if (!out[key]) {
      out[key] = [];
    }
    out[key].push(item);
  }
  return out;
}

export type Pair<A, B> = [A, B];
export const pair = <A, B>(a: A, b: B): Pair<A, B> => [a, b];
