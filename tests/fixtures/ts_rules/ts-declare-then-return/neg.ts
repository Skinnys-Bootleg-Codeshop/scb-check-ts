export function twice(n: number, log: (n: number) => void): number {
  const result = n * 2;
  log(result);
  return result;
}
