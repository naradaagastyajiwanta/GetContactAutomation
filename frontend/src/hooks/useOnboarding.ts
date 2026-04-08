import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../context/AuthContext";

const TOTAL_STEPS = 5;

function getStorageKey(userId: number): string {
  return `onboarding_v1_${userId}`;
}

export interface UseOnboardingReturn {
  isOpen: boolean;
  currentStep: number;
  totalSteps: number;
  goNext: () => void;
  goPrev: () => void;
  goToStep: (step: number) => void;
  completeOnboarding: () => void;
  skipOnboarding: () => void;
}

export function useOnboarding(): UseOnboardingReturn {
  const { user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState(1);

  useEffect(() => {
    if (!user) return;
    const key = getStorageKey(user.dms_user_id);
    if (!localStorage.getItem(key)) {
      setIsOpen(true);
    }
  }, [user]);

  const completeOnboarding = useCallback(() => {
    if (user) {
      localStorage.setItem(getStorageKey(user.dms_user_id), "done");
    }
    setIsOpen(false);
    window.dispatchEvent(new CustomEvent("onboarding-complete"));
  }, [user]);

  const goNext = useCallback(() => {
    setCurrentStep((s) => {
      if (s < TOTAL_STEPS) return s + 1;
      return s;
    });
    if (currentStep >= TOTAL_STEPS) {
      completeOnboarding();
    }
  }, [currentStep, completeOnboarding]);

  const goPrev = useCallback(() => {
    setCurrentStep((s) => (s > 1 ? s - 1 : s));
  }, []);

  const goToStep = useCallback((step: number) => {
    setCurrentStep((prev) => (step < prev ? step : prev));
  }, []);

  return {
    isOpen,
    currentStep,
    totalSteps: TOTAL_STEPS,
    goNext,
    goPrev,
    goToStep,
    completeOnboarding,
    skipOnboarding: completeOnboarding,
  };
}
