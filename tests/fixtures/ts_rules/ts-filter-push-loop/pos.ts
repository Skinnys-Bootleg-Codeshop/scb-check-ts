export function open(rows: { id: string; open: boolean }[]): string[] {
  const out: string[] = [];
  // HIT-NEXT
  for (const row of rows) {
    if (row.open) {
      out.push(row.id);
    }
  }
  return out;
}
