export function names(rows: { name: string }[]): string[] {
  const out: string[] = [];
  rows.forEach((row) => { out.push(row.name); }); // HIT
  return out;
}
