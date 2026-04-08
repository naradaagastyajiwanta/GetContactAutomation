import { useEffect } from "react";
import { driver } from "driver.js";
import type { DriveStep } from "driver.js";
import { useAuth } from "../context/AuthContext";

export interface PageTourStep extends DriveStep {
  permission?: string;
}

function getKey(pageId: string, userId: number) {
  return `page_tour_v1_${pageId}_${userId}`;
}

interface PageTourOptions {
  /** Called only when user reaches the last step (tour completed). */
  onComplete?: () => void | Promise<void>;
}

export function usePageTour(
  pageId: string,
  steps: PageTourStep[],
  options?: PageTourOptions,
) {
  const { user, hasPermission } = useAuth();

  useEffect(() => {
    if (!user) return;

    const key = getKey(pageId, user.dms_user_id);
    if (localStorage.getItem(key)) return;

    const timer = setTimeout(() => {
      const filtered = steps.filter(
        (s) => !s.permission || hasPermission(s.permission),
      );

      if (filtered.length === 0) {
        localStorage.setItem(key, "done");
        return;
      }

      let lastStepReached = false;

      const d = driver({
        animate: true,
        overlayOpacity: 0.55,
        stagePadding: 8,
        popoverOffset: 14,
        showProgress: true,
        progressText: "{{current}} / {{total}}",
        nextBtnText: "Lanjut →",
        prevBtnText: "← Kembali",
        doneBtnText: "Selesai ✓",
        allowClose: true,
        onHighlightStarted: () => {
          if ((d.getActiveIndex() ?? 0) === filtered.length - 1) {
            lastStepReached = true;
          }
        },
        onDestroyed: () => {
          localStorage.setItem(key, "done");
          if (lastStepReached) {
            options?.onComplete?.();
          }
        },
        steps: filtered,
      });

      d.drive();
    }, 800);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.dms_user_id, pageId]);
}
