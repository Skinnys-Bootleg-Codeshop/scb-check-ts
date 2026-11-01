type Dep = ReadonlyArray<unknown>;

function useMemo<T>(factory: () => T, deps: Dep): T {
  void deps;
  return factory();
}

function useCallback<A extends unknown[], R>(fn: (...a: A) => R, deps: Dep) {
  void deps;
  return fn;
}

export const useTotals = (items: number[], factor: number) => {
  const total = useMemo(() => {
    let sum = 0;
    for (const item of items) {
      if (item > 0) {
        sum += item * factor;
      }
    }
    return sum;
  }, [items, factor]);

  const scale = useCallback((value: number) => {
    if (value > 100) {
      return 100;
    }
    return value * factor;
  }, [factor]);

  const labels = useMemo(() => items.map((item) => `#${item}`), [items]);

  return { total, scale, labels };
};

export const identity = <T>(value: T): T => value;
export const double = (n: number) => n * 2;
