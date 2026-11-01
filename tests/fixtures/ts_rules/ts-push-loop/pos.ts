export function ids(rows: { id: string }[]): string[] {
  const out: string[] = [];
  // HIT-NEXT
  for (const row of rows) {
    out.push(row.id);
  }
  return out;
}
