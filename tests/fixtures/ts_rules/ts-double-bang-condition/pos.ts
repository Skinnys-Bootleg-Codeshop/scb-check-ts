export function a(x: string | undefined, y: string): number {
  if (!!x) { // HIT
    return 1;
  }
  while (!!y) { // HIT
    return 2;
  }
  return !!x ? 3 : 4; // HIT
}
