export function totalPrices(items: { price: number }[]): number {
  let total = 0;
  for (const item of items) {
    total += item.price;
  }
  return total;
}

export function describeUser(user: { name: string; age: number }): string {
  const label = user.name.trim();
  const years = user.age;
  return `${label} (${years})`;
}

export const ids = (rows: { id: string }[]) => rows.map((x) => x.id);

export function noop(): void {
  return;
}

export function lastOf<T>(xs: T[]): T | undefined {
  return xs[xs.length - 1];
}
