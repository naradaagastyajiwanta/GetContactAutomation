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
    <div className="flex items-center justify-center gap-1.5">
      {Array.from({ length: totalSteps }, (_, i) => {
        const step = i + 1;
        const isActive = step === currentStep;
        const isCompleted = step < currentStep;

        if (isActive) {
          return (
            <span
              key={step}
              className="block h-2 w-8 rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-300 ease-out"
            />
          );
        }

        if (isCompleted) {
          return (
            <button
              key={step}
              onClick={() => onGoToStep(step)}
              className="block h-2 w-2 rounded-full bg-indigo-300 transition-all duration-300 ease-out hover:scale-125 hover:bg-indigo-400 dark:bg-indigo-700 dark:hover:bg-indigo-500"
              aria-label={`Kembali ke langkah ${step}`}
            />
          );
        }

        return (
          <span
            key={step}
            className="block h-2 w-2 rounded-full bg-gray-200 transition-all duration-300 ease-out dark:bg-gray-700"
          />
        );
      })}
    </div>
  );
}
