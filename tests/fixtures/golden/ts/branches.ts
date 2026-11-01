export function ladder(n: number): string {
  if (n === 1) {
    return "one";
  } else if (n === 2) {
    return "two";
  } else if (n === 3) {
    return "three";
  } else if (n === 4) {
    return "four";
  } else if (n === 5) {
    return "five";
  } else if (n === 6) {
    return "six";
  } else if (n === 7) {
    return "seven";
  } else if (n === 8) {
    return "eight";
  }
  return "many";
}

export function pick(kind: string, flag: boolean): number {
  switch (kind) {
    case "a":
      return 1;
    case "b":
      return 2;
    default:
      break;
  }
  const level = flag ? (kind === "x" ? 1 : kind === "y" ? 2 : 3) : 0;
  return level;
}

export function guarded(input: string): number {
  let result = 0;
  try {
    result = parseInt(input, 10);
    if (Number.isNaN(result) || result < 0) {
      throw new Error("bad");
    }
  } catch (error) {
    result = -1;
  } finally {
    result += 1;
  }
  let i = 0;
  do {
    i++;
  } while (i < 3 && result > 0);
  return result + i;
}
