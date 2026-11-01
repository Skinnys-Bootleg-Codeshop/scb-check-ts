export function pick(name: string | undefined, fallback: string): string {
  return name ? name : fallback; // HIT
}
