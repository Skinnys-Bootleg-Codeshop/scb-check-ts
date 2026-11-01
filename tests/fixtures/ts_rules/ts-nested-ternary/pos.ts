export function label(a: boolean, b: boolean): string {
  const one = a ? (b ? "ab" : "a") : "none"; // HIT
  const two = a ? "a" : b ? "b" : "none"; // HIT
  return one + two;
}
