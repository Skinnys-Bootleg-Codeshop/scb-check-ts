export function sum(xs: number[]): number {
  let total = 0;
  // HIT-NEXT
  for (const x of xs) {
    total += x;
  }
  return total;
}
