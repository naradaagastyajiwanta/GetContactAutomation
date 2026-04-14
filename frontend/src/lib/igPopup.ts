/**
 * Lightweight pub-sub store for IG status popups.
 * Module-level so it can be called from hooks and non-React code.
 */

export type IGPopupAccount = {
  username: string;
  status:
    | "banned"
    | "disconnected"
    | "auth_limited"
    | "rate_limited"
    | "connected"
    | "error";
};

export type IGPopupConfig = {
  id: string;
  type: "success" | "warning" | "error";
  title: string;
  message: string;
  accounts?: IGPopupAccount[];
  /** Label for the CTA button */
  ctaLabel?: string;
  /** href the CTA button navigates to */
  ctaHref?: string;
  /** ms until auto-dismiss. 0 = sticky until user closes. Default 12 000 */
  duration?: number;
};

type Listener = (list: IGPopupConfig[]) => void;

const _listeners = new Set<Listener>();
const _queue = new Map<
  string,
  { config: IGPopupConfig; timer?: ReturnType<typeof setTimeout> }
>();
let _counter = 0;

function _notify() {
  const list = Array.from(_queue.values()).map((e) => e.config);
  _listeners.forEach((fn) => fn(list));
}

export function showIGPopup(
  config: Omit<IGPopupConfig, "id"> & { id?: string },
) {
  const id = config.id ?? `igp-${++_counter}`;

  // Cancel existing timer if same id is re-fired
  const existing = _queue.get(id);
  if (existing?.timer) clearTimeout(existing.timer);

  const dur = config.duration ?? 12_000;
  let timer: ReturnType<typeof setTimeout> | undefined;

  if (dur > 0) {
    timer = setTimeout(() => dismissIGPopup(id), dur);
  }

  _queue.set(id, { config: { ...config, id }, timer });
  _notify();
}

export function dismissIGPopup(id: string) {
  const entry = _queue.get(id);
  if (entry?.timer) clearTimeout(entry.timer);
  _queue.delete(id);
  _notify();
}

export function subscribeIGPopup(fn: Listener) {
  _listeners.add(fn);
  // Immediately emit current state so the subscriber can hydrate
  fn(Array.from(_queue.values()).map((e) => e.config));
  return () => {
    _listeners.delete(fn);
  };
}
