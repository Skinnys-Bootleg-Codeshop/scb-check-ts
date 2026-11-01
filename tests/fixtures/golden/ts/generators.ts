export function* range(start: number, end: number): Generator<number> {
  for (let i = start; i < end; i++) {
    yield i;
  }
}

export function* take<T>(source: Iterable<T>, n: number): Generator<T> {
  let count = 0;
  for (const item of source) {
    if (count >= n) {
      return;
    }
    yield item;
    count++;
  }
}

export function* zip<A, B>(a: A[], b: B[]): Generator<[A, B]> {
  const length = Math.min(a.length, b.length);
  for (let i = 0; i < length; i++) {
    yield [a[i], b[i]];
  }
}

export async function* ticks(limit: number): AsyncGenerator<number> {
  let n = 0;
  while (n < limit) {
    yield n;
    n += 1;
  }
}

export function collect<T>(source: Iterable<T>): T[] {
  const out: T[] = [];
  for (const item of source) {
    out.push(item);
  }
  return out;
}
