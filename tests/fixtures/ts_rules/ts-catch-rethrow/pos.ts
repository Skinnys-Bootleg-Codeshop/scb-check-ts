export function run(go: () => void): void {
  try { go(); } catch (error) { throw error; } // HIT
}
