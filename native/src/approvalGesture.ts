// A release must finish a deliberate, single-finger horizontal drag.
export function completesApprovalDrag(width: number, dx: number, dy: number, touches: number, duration: number) {
  return width > 100 && dx >= (width - 60) * 0.94 && Math.abs(dy) <= 28 && touches === 1 && duration >= 300;
}
