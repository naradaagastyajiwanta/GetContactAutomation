/**
 * Helpers for "return to originally requested page after login".
 *
 * There are two sources of a return path, evaluated in this priority:
 *
 *  1. React Router `location.state.from` — set by ProtectedRoute when an
 *     anonymous user is intercepted trying to reach a protected route.
 *     This is the primary path and covers both deep-link visits and
 *     session-expiry mid-page.
 *
 *  2. sessionStorage `auth_last_path_v1` — set by TopBar right before
 *     logout, so that a user who clicks logout and then logs back in on
 *     the same tab lands on the same page they were looking at.
 *     Cleared on successful login and when the tab closes.
 *
 * Every return path is funneled through {@link sanitizeReturnTo} which
 * rejects anything that could cause an open-redirect (protocol-relative
 * URLs, absolute URLs, non-root paths) and anything that would loop back
 * to `/login`. Destination must be a single-origin absolute path.
 */

export const LAST_PATH_KEY = "auth_last_path_v1";

export interface ReturnLocation {
  pathname: string;
  search?: string;
  hash?: string;
}

/** Combine pathname + search + hash into a single URL string. */
export function toPathString(loc: ReturnLocation): string {
  return `${loc.pathname}${loc.search ?? ""}${loc.hash ?? ""}`;
}

/**
 * Return `raw` if it is a safe same-origin path, otherwise `null`.
 *
 * Rules:
 *  - Must be a non-empty string
 *  - Must start with `/`
 *  - Must NOT start with `//` (protocol-relative URL, e.g. `//evil.com`)
 *  - Must NOT contain `://` (absolute URL with scheme)
 *  - Must NOT resolve to `/login` (would cause a post-login redirect loop)
 */
export function sanitizeReturnTo(
  raw: string | null | undefined,
): string | null {
  if (!raw || typeof raw !== "string") return null;
  if (!raw.startsWith("/")) return null;
  if (raw.startsWith("//")) return null;
  if (raw.includes("://")) return null;
  const pathOnly = raw.split("?")[0].split("#")[0];
  if (pathOnly === "/login") return null;
  return raw;
}

/**
 * Persist the current window URL as "last path before logout" so the
 * next successful login in the same tab session can return the user
 * there. Called from TopBar's logout mutation `onMutate` hook.
 *
 * Silently no-ops on sessionStorage access errors (private-mode Safari
 * or disabled storage) — this is a best-effort convenience, never
 * a correctness requirement.
 */
export function saveLastPathBeforeLogout(): void {
  try {
    const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    const safe = sanitizeReturnTo(current);
    if (safe) {
      sessionStorage.setItem(LAST_PATH_KEY, safe);
    }
  } catch {
    // ignore
  }
}

/**
 * Read the stored last-path *without* clearing it. Used by LoginPage's
 * initial render to compute where to redirect. We do NOT clear here
 * because the login page may re-render multiple times (bootstrap fetch,
 * form state changes) and we want the target to be stable.
 */
export function peekLastPath(): string | null {
  try {
    return sanitizeReturnTo(sessionStorage.getItem(LAST_PATH_KEY));
  } catch {
    return null;
  }
}

/**
 * Explicitly remove the stored last-path. Called from LoginPage on
 * successful login so that the value cannot leak into a later login
 * attempt by a different user in the same tab.
 */
export function clearLastPath(): void {
  try {
    sessionStorage.removeItem(LAST_PATH_KEY);
  } catch {
    // ignore
  }
}

/**
 * Pick the best post-login destination given an optional React Router
 * `location.state.from`. Returns a sanitized, same-origin absolute path.
 *
 * Priority:
 *  1. `fromState` if present and safe (deep link or session-expiry case)
 *  2. sessionStorage last-path if present and safe (post-logout case)
 *  3. `/` (fresh login with no context)
 */
export function resolveReturnTo(
  fromState: ReturnLocation | null | undefined,
): string {
  if (fromState?.pathname) {
    const safe = sanitizeReturnTo(toPathString(fromState));
    if (safe) return safe;
  }
  const lastPath = peekLastPath();
  if (lastPath) return lastPath;
  return "/";
}

/**
 * Whether the given user has completed the onboarding wizard.
 *
 * Duplicated (by design) from `useOnboarding.ts`'s storage-key
 * convention so that LoginPage can gate its post-login redirect on
 * the same flag without having to instantiate the hook. Keep this in
 * sync with `useOnboarding.ts::getStorageKey`.
 */
export function isOnboardingDone(userId: number | null | undefined): boolean {
  if (userId == null) return false;
  try {
    return localStorage.getItem(`onboarding_v1_${userId}`) === "done";
  } catch {
    return false;
  }
}
