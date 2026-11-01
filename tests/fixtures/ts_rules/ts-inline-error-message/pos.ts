export function describe(e: unknown): string {
  return e instanceof Error ? e.message : String(e); // HIT
}
