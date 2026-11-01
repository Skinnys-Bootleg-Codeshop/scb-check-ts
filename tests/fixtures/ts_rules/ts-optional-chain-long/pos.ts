type Deep = { a?: { b?: { c?: { d: number } } } };
export function read(x: Deep): number | undefined {
  return x.a?.b?.c?.d; // HIT
}
