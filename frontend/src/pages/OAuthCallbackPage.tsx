import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";

/**
 * Receives the OAuth redirect from the backend after token exchange.
 *
 * The backend (ephemeral server on localhost:1455 for dev, or the persistent
 * /auth/codex-callback endpoint for prod) exchanges the authorization code,
 * saves the tokens, then redirects the browser tab here with:
 *   ?oauth=success         — login was successful
 *   ?error=...             — something went wrong
 *
 * On success this page attempts to close itself (works when opened via
 * window.open). The original settings tab is polling /health/codex-oauth
 * and will detect the new logged_in status on its own.
 */
export default function OAuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">(
    "loading",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const oauth = searchParams.get("oauth");
    const error = searchParams.get("error");
    const errorDesc = searchParams.get("error_description");

    if (oauth === "success") {
      setStatus("success");
      // Close this tab — the opener polls status independently
      const t = setTimeout(() => window.close(), 1500);
      return () => clearTimeout(t);
    }

    if (error) {
      setStatus("error");
      setErrorMessage(errorDesc || error);
      return;
    }

    setStatus("error");
    setErrorMessage("Unexpected callback — missing oauth or error parameter.");
  }, [searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8 max-w-sm w-full text-center space-y-4">
        {status === "loading" && (
          <>
            <Loader2 className="h-12 w-12 text-indigo-500 animate-spin mx-auto" />
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Processing…
            </p>
          </>
        )}

        {status === "success" && (
          <>
            <CheckCircle2 className="h-12 w-12 text-green-500 mx-auto" />
            <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Login Successful
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              You can close this tab and return to the dashboard.
            </p>
          </>
        )}

        {status === "error" && (
          <>
            <XCircle className="h-12 w-12 text-red-500 mx-auto" />
            <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Login Failed
            </h1>
            {errorMessage && (
              <p className="text-sm text-red-600 dark:text-red-400 break-words">
                {errorMessage}
              </p>
            )}
            <button
              onClick={() => window.close()}
              className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline"
            >
              Close this tab
            </button>
          </>
        )}
      </div>
    </div>
  );
}
