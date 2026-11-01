export function sign(n: number, go: () => void, stop: () => void): void {
  if (n < 0) {
    go();
  } else {
    stop();
  }
}
