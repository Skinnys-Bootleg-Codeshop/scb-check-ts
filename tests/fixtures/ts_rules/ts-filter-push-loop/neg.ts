export function open(rows: { id: string; open: boolean }[]): string[] {
  const out: string[] = [];
  for (const row of rows) {
    if (row.open) {
      out.push(row.id);
    } else {
      out.push("closed");
    }
  }
  return out;
}
export function pick(rows: { open: boolean; closed: boolean; id: string; name: string }[]): string[] {
  const out: string[] = [];
  for (const row of rows) {
    if (row.open) out.push(row.id);
    else if (row.closed) out.push(row.name);
  }
  return out;
}
