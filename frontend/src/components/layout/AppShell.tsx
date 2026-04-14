import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { MobileNav } from "./MobileNav";
import { IgSessionBanner } from "./IgSessionBanner";
import { IgPlaywrightBanner } from "./IgPlaywrightBanner";
import { IGStatusPopup } from "../ui/IGStatusPopup";
import { NotificationCenter } from "../notifications/NotificationCenter";

export function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-950">
      <div className="hidden lg:block">
        <Sidebar />
      </div>

      <MobileNav
        isOpen={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar onMenuClick={() => setMobileNavOpen(true)} />
        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>

      {/* Floating banners — bottom-right */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-3 w-[400px] max-w-[calc(100vw-2rem)]">
        <IgPlaywrightBanner />
        <IgSessionBanner />
      </div>

      {/* IG status popup — top-right, above banners */}
      <IGStatusPopup />
    </div>
  );
}
