declare function load(): Promise<number>;
export async function total(): Promise<number> {
  try {
    return await load();
  } catch {
    return 0;
  }
}
