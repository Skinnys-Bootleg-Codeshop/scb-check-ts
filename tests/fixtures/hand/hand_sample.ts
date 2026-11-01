// Grades a pair of scores.
export function grade(a: number, b: number): string {
  let out = "";
  if (a > 1) out += "a";
  if (a > 2) out += "b";
  if (a > 3) out += "c";
  if (a > 4) out += "d";
  if (a > 5) out += "e";
  if (b > 1) out += "f";
  if (b > 2) out += "g";
  if (b > 3) out += "h";
  if (b > 4) out += "i";
  if (b > 5) out += "j";
  return out;
}

export function sumA(xs: number[]): number {
  let total = 0;
  for (const x of xs) {
    total += x;
  }
  return total;
}

export function sumB(ys: number[]): number {
  let sum = 0;
  for (const y of ys) {
    sum += y;
  }
  return sum;
}

export function deep(a: boolean, b: boolean, c: boolean, d: boolean): number {
  if (a) {
    if (b) {
      if (c) {
        if (d) {
          return 1;
        }
      }
    }
  }
  if (d) {
    return 2;
  }
  return 3;
}
