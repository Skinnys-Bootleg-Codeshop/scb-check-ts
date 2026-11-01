export function isAdult(age: number, log: (n: number) => void): boolean {
  if (age >= 18) return true;
  log(age);
  return false;
}
export function always(age: number): boolean {
  if (age >= 18) return true;
  return true;
}
export function allowed(a: boolean, b: boolean, c: boolean): boolean {
  if (a) return false;
  if (b) return false;
  if (c) return false;
  return true;
}
