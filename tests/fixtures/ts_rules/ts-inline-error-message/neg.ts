declare function errorMessage(e: unknown): string;
export function describe(e: unknown): string {
  return errorMessage(e);
}
