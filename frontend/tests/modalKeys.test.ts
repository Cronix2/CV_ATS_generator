import assert from "node:assert/strict";
import { test } from "node:test";

import { modalKeyAction, type ModalKey } from "../lib/modalKeys.ts";

const key = (k: string, mods: Partial<ModalKey> = {}): ModalKey => ({ key: k, shiftKey: false, ctrlKey: false, altKey: false, ...mods });

test("on the remote screen, Escape, Tab, Shift+Tab and typing go to the server's browser", () => {
  for (const e of [key("Escape"), key("Tab"), key("Tab", { shiftKey: true }), key("a"), key("Enter"), key("v", { ctrlKey: true })]) {
    assert.equal(modalKeyAction(e, true, -1, 3), null, e.key);
  }
});

test("F8 alone hands the keyboard back from the remote screen to the modal", () => {
  assert.deepEqual(modalKeyAction(key("F8"), true, -1, 3), { type: "release" });
  assert.equal(modalKeyAction(key("F8", { ctrlKey: true }), true, -1, 3), null);
  assert.equal(modalKeyAction(key("F8", { shiftKey: true }), true, -1, 3), null);
});

test("Escape on the modal's own controls closes it", () => {
  assert.deepEqual(modalKeyAction(key("Escape"), false, 0, 3), { type: "close" });
});

test("Tab and Shift+Tab wrap around inside the modal", () => {
  assert.deepEqual(modalKeyAction(key("Tab"), false, 0, 3), { type: "focus", index: 1 });
  assert.deepEqual(modalKeyAction(key("Tab"), false, 2, 3), { type: "focus", index: 0 });
  assert.deepEqual(modalKeyAction(key("Tab", { shiftKey: true }), false, 1, 3), { type: "focus", index: 0 });
  assert.deepEqual(modalKeyAction(key("Tab", { shiftKey: true }), false, 0, 3), { type: "focus", index: 2 });
  assert.deepEqual(modalKeyAction(key("Tab"), false, 0, 1), { type: "focus", index: 0 });
});

test("Tab from outside the focusable list comes back into the modal", () => {
  assert.deepEqual(modalKeyAction(key("Tab"), false, -1, 3), { type: "focus", index: 0 });
  assert.deepEqual(modalKeyAction(key("Tab", { shiftKey: true }), false, -1, 3), { type: "focus", index: 2 });
});

test("other keys on the modal's controls are left to the browser", () => {
  assert.equal(modalKeyAction(key("Enter"), false, 0, 3), null);
  assert.equal(modalKeyAction(key(" "), false, 0, 3), null);
  assert.equal(modalKeyAction(key("F8"), false, 0, 3), null);
});
