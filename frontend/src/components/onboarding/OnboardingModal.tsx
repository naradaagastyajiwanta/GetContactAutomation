import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { OnboardingProgressDots } from "./OnboardingProgressDots";
import { OnboardingStep1Welcome } from "./steps/OnboardingStep1Welcome";
import { OnboardingStep2FeatureTour } from "./steps/OnboardingStep2FeatureTour";
import { OnboardingStep3Profile } from "./steps/OnboardingStep3Profile";
import { OnboardingStep4SetupChecklist } from "./steps/OnboardingStep4SetupChecklist";
import { OnboardingStep5Done } from "./steps/OnboardingStep5Done";
import type { AuthUser } from "../../lib/types";

interface OnboardingModalProps {
  isOpen: boolean;
  currentStep: number;
  totalSteps: number;
  onNext: () => void;
  onPrev: () => void;
  onGoToStep: (step: number) => void;
  onSkip: () => void;
  onComplete: () => void;
  onStartTour: () => void;
  user: AuthUser;
}

// All step components receive this superset of props; each picks what it needs
type StepProps = {
  user: AuthUser;
  onNavigateAway: () => void;
  onStartTour: () => void;
};

const STEP_COMPONENTS: Array<React.ComponentType<StepProps>> = [
  OnboardingStep1Welcome as React.ComponentType<StepProps>,
  OnboardingStep2FeatureTour as React.ComponentType<StepProps>,
  OnboardingStep3Profile as React.ComponentType<StepProps>,
  OnboardingStep4SetupChecklist as React.ComponentType<StepProps>,
  OnboardingStep5Done,
];

const STEP_TITLES = [
  "Selamat Datang",
  "Fitur Utama",
  "Profil Kamu",
  "Setup Awal",
  "Siap Mulai!",
];

export function OnboardingModal({
  isOpen,
  currentStep,
  totalSteps,
  onNext,
  onPrev,
  onGoToStep,
  onSkip,
  onComplete,
  onStartTour,
  user,
}: OnboardingModalProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (isOpen) {
      requestAnimationFrame(() => setVisible(true));
    } else {
      setVisible(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const StepComponent = STEP_COMPONENTS[currentStep - 1];
  const isLastStep = currentStep === totalSteps;

  const handleNext = () => {
    if (isLastStep) {
      onComplete();
    } else {
      onNext();
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
      {/* Backdrop — intentionally non-dismissable */}
      <div className="onboarding-backdrop fixed inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Panel */}
      <div
        className={`onboarding-panel relative w-full max-w-2xl overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-gray-900 ${
          visible ? "" : "opacity-0"
        }`}
      >
        {/* Top accent line */}
        <div className="h-[3px] w-full bg-gradient-to-r from-indigo-500 via-violet-500 to-purple-500" />

        {/* Header */}
        <div className="flex items-center justify-between px-8 pb-3 pt-5">
          <div className="flex flex-col gap-0.5">
            <span className="text-[11px] font-semibold uppercase tracking-widest text-indigo-400 dark:text-indigo-400">
              Langkah {currentStep} / {totalSteps}
            </span>
            <span className="text-base font-semibold text-gray-900 dark:text-gray-100">
              {STEP_TITLES[currentStep - 1]}
            </span>
          </div>
          {!isLastStep && (
            <button
              onClick={onSkip}
              className="rounded-full px-3 py-1 text-xs font-medium text-gray-400 transition-all duration-150 hover:bg-gray-100 hover:text-gray-600 dark:text-gray-500 dark:hover:bg-gray-800 dark:hover:text-gray-300"
            >
              Lewati
            </button>
          )}
        </div>

        {/* Progress dots */}
        <div className="px-8 pb-2 pt-1">
          <OnboardingProgressDots
            currentStep={currentStep}
            totalSteps={totalSteps}
            onGoToStep={onGoToStep}
          />
        </div>

        {/* Divider */}
        <div className="mx-8 h-px bg-gray-100 dark:bg-gray-800" />

        {/* Step content */}
        <div
          key={currentStep}
          className="onboarding-step-content min-h-[360px] overflow-y-auto px-8 py-6"
        >
          <StepComponent
            user={user}
            onNavigateAway={onComplete}
            onStartTour={onStartTour}
          />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-gray-100 px-8 py-4 dark:border-gray-800">
          <button
            onClick={onPrev}
            disabled={currentStep === 1}
            className="rounded-full border border-gray-200 px-5 py-2 text-sm font-medium text-gray-500 transition-all duration-150 hover:scale-105 hover:border-gray-300 hover:bg-gray-50 hover:text-gray-700 disabled:pointer-events-none disabled:opacity-30 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800"
          >
            ← Kembali
          </button>

          <button
            onClick={handleNext}
            className="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-6 py-2 text-sm font-medium text-white shadow-md shadow-indigo-200 transition-all duration-150 hover:scale-105 hover:from-indigo-600 hover:to-violet-600 hover:shadow-indigo-300 active:scale-100 dark:shadow-indigo-900/40"
          >
            {isLastStep ? "Selesai ✓" : "Lanjut →"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
