interface OnboardingProgressDotsProps {
  currentStep: number;
  totalSteps: number;
  onGoToStep: (step: number) => void;
}

export function OnboardingProgressDots({
  currentStep,
  totalSteps,
  onGoToStep,
}: OnboardingProgressDotsProps) {
  return (
    <div className="flex items-center justify-center gap-2">
      {Array.from({ length: totalSteps }, (_, i) => {
        const step = i + 1;
        const isActive = step === currentStep;
        const isCompleted = step < currentStep;

        if (isActive) {
          return (
            <span
              key={step}
              className="h-2.5 w-6 rounded-full bg-indigo-600 transition-all duration-200"
            />
          );
        }

        if (isCompleted) {
          return (
            <button
              key={step}
              onClick={() => onGoToStep(step)}
              className="h-2.5 w-2.5 rounded-full bg-indigo-300 transition-all duration-200 dark:bg-indigo-700"
              aria-label={`Kembali ke langkah ${step}`}
            />
          );
        }

        return (
          <span
            key={step}
            className="h-2.5 w-2.5 rounded-full bg-gray-200 transition-all duration-200 dark:bg-gray-700"
          />
        );
      })}
    </div>
  );
}
