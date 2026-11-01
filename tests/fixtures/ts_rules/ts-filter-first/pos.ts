export function first(xs: number[]): number | undefined {
  return xs.filter((x) => x > 1)[0]; // HIT
}
