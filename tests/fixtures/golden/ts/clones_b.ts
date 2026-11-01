export function totalWeights(items: { weight: number }[]): number {
  let total = 0;
  for (const item of items) {
    total += item.weight;
  }
  return total;
}

export function describeAccount(user: { name: string; age: number }): string {
  const label = user.name.trim();
  const years = user.age;
  return `${label} (${years})`;
}

export const keys = (rows: { key: string }[]) => rows.map((y) => y.key);

export function other(a: number, b: number): number {
  if (a > b) {
    return a - b;
  }
  return b - a;
}
