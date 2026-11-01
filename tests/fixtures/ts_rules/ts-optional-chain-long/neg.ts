type Deep = { a?: { b?: { c: number } } };
export function read(x: Deep): number | undefined {
  return x.a?.b?.c;
}
declare const api: { get(...a: unknown[]): { status: number } };
export function call(user?: { id: string }, org?: { id: string }, role?: { id: string }): number {
  return api.get(user?.id, org?.id, role?.id).status;
}
