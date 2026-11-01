export function flags(ready: boolean): number[] {
  const yes = ready ? 1 : 0;
  return [yes];
}
