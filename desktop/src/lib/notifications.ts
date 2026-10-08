/** Returns effect cleanup so replacing a message cancels its old timer. */
export function dismissAfterDelay(enabled: boolean, dismiss: () => void) {
  if (!enabled) return;
  const timer = setTimeout(dismiss, 3000);
  return () => clearTimeout(timer);
}
