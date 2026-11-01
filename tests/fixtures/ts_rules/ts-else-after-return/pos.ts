export function sign(n: number): string {
  if (n < 0) {
    return "negative";
  } else { // HIT
    return "non-negative";
  }
}
