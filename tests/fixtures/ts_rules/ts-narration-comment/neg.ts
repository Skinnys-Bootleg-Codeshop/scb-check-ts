declare function load(): number;
export function run(): number {
  // The legacy API returns -1 for missing; callers expect 0
  const value = Math.max(load(), 0);
  return value;
}
