/** Unsaved changes on the form page on screen. A page that registers a save action (ui/helpers.onSave) is watched:
 *  typing in one of its fields marks it dirty; any successful write to the server (core/api) marks it clean again. */
let root: HTMLElement | null = null;
let dirty = false;

export function watchDirty(r: HTMLElement): void {
  root = r; dirty = false;
  const mark = (e: Event) => { if (r === root && (e.target as Element | null)?.closest?.(".field")) dirty = true; };
  r.addEventListener("input", mark);
  r.addEventListener("change", mark);
}
export const isDirty = (): boolean => dirty && !!root?.isConnected;
export const markClean = (): void => { dirty = false; };
