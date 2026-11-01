export function names(rows: { name: string }[], send: (r: { name: string }) => void): void {
  rows.forEach(send);
}
