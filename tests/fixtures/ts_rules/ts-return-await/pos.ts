declare function load(): Promise<number>;
export async function total(): Promise<number> {
  return await load(); // HIT
}
