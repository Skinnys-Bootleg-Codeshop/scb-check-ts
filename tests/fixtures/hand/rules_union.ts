export function copyA(x: object): object {
  const y = JSON.parse(JSON.stringify(x));
  y.copied = true;
  return y;
}

export function copyB(q: object): object {
  const r = JSON.parse(JSON.stringify(q));
  r.copied = true;
  return r;
}

export function solo(v: object): object[] {
  const w = JSON.parse(JSON.stringify(v));
  return [w];
}
