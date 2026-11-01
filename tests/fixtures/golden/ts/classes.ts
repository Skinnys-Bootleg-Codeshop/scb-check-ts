export abstract class Shape {
  protected name: string;

  constructor(name: string) {
    this.name = name;
  }

  abstract area(): number;

  describe(): string {
    return `${this.name}: ${this.area()}`;
  }
}

export class Rect extends Shape {
  private w: number;
  private h: number;

  constructor(w: number, h: number) {
    super("rect");
    this.w = w;
    this.h = h;
  }

  get width(): number {
    return this.w;
  }

  set width(value: number) {
    if (value < 0) {
      throw new Error("negative");
    }
    this.w = value;
  }

  area(): number {
    return this.w * this.h;
  }

  static square(side: number): Rect {
    return new Rect(side, side);
  }
}

export class Counter {
  count = 0;
  increment = () => {
    this.count += 1;
  };
}
