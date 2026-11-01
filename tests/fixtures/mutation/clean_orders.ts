type Order = { id: string; total: number; open: boolean };

function isOpen(order: Order): boolean {
  return order.open;
}

function toId(order: Order): string {
  return order.id;
}

export function openIds(orders: Order[]): string[] {
  return orders.filter(isOpen).map(toId);
}

export function grandTotal(orders: Order[]): number {
  return orders.reduce((sum, order) => sum + order.total, 0);
}

export function parseOrder(raw: string): Order | null {
  try {
    return JSON.parse(raw) as Order;
  } catch (error) {
    reportError(error);
    return null;
  }
}
