export const api = {
  base: "/api",
  url(path: string): string {
    return this.base + path;
  },
  fetchAll: async (path: string) => {
    const response = await fetch(api.url(path));
    if (!response.ok) {
      throw new Error("failed");
    }
    return response.json();
  },
  format: function (value: number): string {
    return value.toFixed(2);
  },
  get label() {
    return "api";
  },
  retry(times: number) {
    let attempts = 0;
    while (attempts < times) {
      attempts++;
    }
    return attempts;
  },
};

export function make() {
  const handler = function (x: number) {
    return x + 1;
  };
  return { handler, twice: (x: number) => handler(handler(x)) };
}
