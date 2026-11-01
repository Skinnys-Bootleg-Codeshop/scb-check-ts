declare const raw: object;
export const a = raw as unknown;
export const b = raw as Record<string, string>;
export function narrow(value: object): string[] {
  return value as unknown as string[];
}
