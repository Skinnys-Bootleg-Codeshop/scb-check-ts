export function flags(ready: boolean): boolean[] {
  const yes = ready ? true : false; // HIT
  const no = ready ? false : true; // HIT
  return [yes, no];
}
