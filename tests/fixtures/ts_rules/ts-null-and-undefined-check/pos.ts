export function present(x: string | null | undefined): boolean {
  const a = x !== null && x !== undefined; // HIT
  const b = x === null || x === undefined; // HIT
  return a && !b;
}
