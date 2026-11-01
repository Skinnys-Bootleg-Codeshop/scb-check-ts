export function pick(name: string | undefined, fallback: string): string {
  return name ? name.trim() : fallback;
}
export function next(queue: number[]): number {
  return queue.shift() ? queue.shift() ?? 0 : 0;
}
