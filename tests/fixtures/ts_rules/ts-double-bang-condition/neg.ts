export function a(x: string | undefined): boolean {
  const b = !!x;
  if (x) {
    return b;
  }
  return !!x;
}
export function r(x: string | undefined): boolean {
  if (x) {
    return !!x;
  }
  return false;
}
