export function a(x: boolean, y: number, z: number): boolean[] {
  return [
    Boolean(!x), // HIT
    Boolean(y === z), // HIT
    Boolean(y !== z), // HIT
  ];
}
