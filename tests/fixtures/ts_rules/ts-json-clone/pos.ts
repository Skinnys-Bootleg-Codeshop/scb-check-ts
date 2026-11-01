export function copy(x: object): object {
  return JSON.parse(JSON.stringify(x)); // HIT
}
