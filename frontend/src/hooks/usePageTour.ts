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

    // Core logic: build and start the driver.js tour.
    function startTour() {
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
    }

    const onboardingKey = `onboarding_v1_${user.dms_user_id}`;
    const onboardingDone = !!localStorage.getItem(onboardingKey);

    if (!onboardingDone) {
      // Onboarding wizard is still in progress — defer this page tour until
      // the wizard completes. Listen for the "onboarding-complete" event
      // dispatched by useOnboarding.completeOnboarding().
      const handler = () => {
        // Re-check in case the tour was somehow marked done during onboarding
        if (localStorage.getItem(key)) return;
        const timer = setTimeout(startTour, 800);
        // No cleanup needed: handler fires once and timer is short-lived
        return () => clearTimeout(timer);
      };
      window.addEventListener("onboarding-complete", handler, { once: true });
      return () => window.removeEventListener("onboarding-complete", handler);
    }

    // Onboarding already done — start tour normally after 800ms
    const timer = setTimeout(startTour, 800);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.dms_user_id, pageId]);
}
