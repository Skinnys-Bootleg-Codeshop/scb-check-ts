export function run(go: () => void): void {
  try {
    go();
  } catch (error) {
    throw new Error("run failed", { cause: error });
  }
}
