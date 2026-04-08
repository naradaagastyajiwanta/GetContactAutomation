import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "../ui/Button";
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
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Panel */}
      <div
        className={`relative w-full max-w-2xl rounded-2xl bg-white shadow-2xl transition-all duration-300 dark:bg-gray-800 ${
          visible ? "scale-100 opacity-100" : "scale-95 opacity-0"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4 dark:border-gray-700">
          <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
            Langkah {currentStep} dari {totalSteps} —{" "}
            {STEP_TITLES[currentStep - 1]}
          </span>
          {!isLastStep && (
            <button
              onClick={onSkip}
              className="text-sm text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
            >
              Lewati
            </button>
          )}
        </div>

        {/* Progress dots */}
        <div className="px-6 pt-4">
          <OnboardingProgressDots
            currentStep={currentStep}
            totalSteps={totalSteps}
            onGoToStep={onGoToStep}
          />
        </div>

        {/* Step content */}
        <div
          key={currentStep}
          className="min-h-[360px] overflow-y-auto px-6 py-4"
        >
          <StepComponent
            user={user}
            onNavigateAway={onComplete}
            onStartTour={onStartTour}
          />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-gray-100 px-6 py-4 dark:border-gray-700">
          <Button
            variant="secondary"
            size="md"
            onClick={onPrev}
            disabled={currentStep === 1}
          >
            ← Kembali
          </Button>

          <Button variant="primary" size="md" onClick={handleNext}>
            {isLastStep ? "Selesai ✓" : "Lanjut →"}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
