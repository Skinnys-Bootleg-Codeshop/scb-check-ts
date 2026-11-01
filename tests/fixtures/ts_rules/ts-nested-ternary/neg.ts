export function label(a: boolean, b: boolean): string {
  const first = a ? "a" : "none";
  const second = b ? "b" : "none";
  return first + second;
}
export function compare(a: number, b: number): number {
  return a < b ? -1 : a > b ? 1 : 0;
}
