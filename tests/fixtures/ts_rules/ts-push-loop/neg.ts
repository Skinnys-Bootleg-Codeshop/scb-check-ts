export function ids(rows: { id: string }[]): string[] {
  const out: string[] = [];
  for (const row of rows) {
    out.push(row.id);
    out.push(row.id.toUpperCase());
  }
  return out;
}
