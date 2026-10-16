export type ModalKey = { key: string; shiftKey: boolean; ctrlKey: boolean; altKey: boolean };
export type ModalAction = { type: "close" } | { type: "release" } | { type: "focus"; index: number } | null;

/**
 * F8 alone (the menu key of TigerVNC's viewer): the only key the remote screen never receives. A lone
 * key on purpose: noVNC sends modifiers as soon as they go down and only releases them on window blur,
 * so a Ctrl/Alt/Shift shortcut would leave them stuck on the server once focus leaves its canvas.
 */
export const isReleaseKey = (e: ModalKey) => e.key === "F8" && !e.ctrlKey && !e.altKey && !e.shiftKey;

/**
 * Keyboard policy of the CAPTCHA modal. `remote`: focus is on the noVNC screen, whose keys (Escape and
 * Tab included) belong to the server's browser, except the release shortcut that hands focus back to
 * the modal. Elsewhere, Escape closes and Tab / Shift+Tab cycle through the modal's `count` focusable
 * elements (`index` = the focused one, -1 if none) so focus never reaches the page behind.
 */
export function modalKeyAction(e: ModalKey, remote: boolean, index: number, count: number): ModalAction {
  if (remote) return isReleaseKey(e) ? { type: "release" } : null;
  if (e.key === "Escape") return { type: "close" };
  if (e.key !== "Tab" || count === 0) return null;
  if (e.shiftKey) return { type: "focus", index: index <= 0 ? count - 1 : index - 1 };
  return { type: "focus", index: index < 0 || index >= count - 1 ? 0 : index + 1 };
}
