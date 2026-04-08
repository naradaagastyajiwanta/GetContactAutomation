import { WebSocketProvider } from "../../context/WebSocketContext";
import { AppShell } from "../layout/AppShell";
import { OnboardingModal } from "../onboarding/OnboardingModal";
import { useOnboarding } from "../../hooks/useOnboarding";
import { useAuth } from "../../context/AuthContext";
import { useTour } from "../../hooks/useTour";

export function ProtectedLayout() {
  const { user, hasPermission } = useAuth();
  const onboarding = useOnboarding();
  const { startTour } = useTour(hasPermission);

  // Start tour: close wizard first, then launch spotlight tour
  const handleStartTour = () => {
    onboarding.completeOnboarding();
    startTour();
  };

  return (
    <WebSocketProvider>
      <AppShell />
      {user && (
        <OnboardingModal
          isOpen={onboarding.isOpen}
          currentStep={onboarding.currentStep}
          totalSteps={onboarding.totalSteps}
          onNext={onboarding.goNext}
          onPrev={onboarding.goPrev}
          onGoToStep={onboarding.goToStep}
          onSkip={onboarding.skipOnboarding}
          onComplete={onboarding.completeOnboarding}
          onStartTour={handleStartTour}
          user={user}
        />
      )}
    </WebSocketProvider>
  );
}
