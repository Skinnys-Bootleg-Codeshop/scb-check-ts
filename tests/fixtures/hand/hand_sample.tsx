import { useState } from "react";

export function First({ items, label }: { items: string[]; label?: string }) {
  const [open, setOpen] = useState(false);
  if (!items.length) {
    return null;
  }
  return (
    <ul title={label ? label : "list"}>
      {open && <li>{items[0]}</li>}
      {/* first item only */}
      <li onClick={setOpen}>more</li>
    </ul>
  );
}

export function Second({ rows, name }: { rows: string[]; name?: string }) {
  const [shut, setShut] = useState(true);
  if (!rows.length) {
    return null;
  }
  return (
    <ol lang={name ? name : "list"}>
      {shut && <li>{rows[0]}</li>}
      {/* first row only */}
      <li onClick={setShut}>less</li>
    </ol>
  );
}

export const Badge = ({ n }: { n: number }) => {
  let tone = "";
  if (n > 1) tone = "a";
  if (n > 2) tone = "b";
  if (n > 3) tone = "c";
  if (n > 4) tone = "d";
  if (n > 5) tone = "e";
  if (n > 6) tone = "f";
  if (n > 7) tone = "g";
  if (n > 8) tone = "h";
  if (n > 9) tone = "i";
  if (n > 10) tone = "j";
  return <b>{tone}</b>;
};

export function Gate(a: boolean, b: boolean, c: boolean, d: boolean) {
  if (a) {
    if (b) {
      if (c) {
        if (d) {
          return <i>one</i>;
        }
      }
    }
  }
  if (d) {
    return <i>two</i>;
  }
  return <i>three</i>;
}
