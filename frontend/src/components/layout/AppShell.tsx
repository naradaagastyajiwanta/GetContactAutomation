import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { MobileNav } from './MobileNav'
import { IgSessionBanner } from './IgSessionBanner'
<<<<<<< HEAD
import { IgPlaywrightBanner } from './IgPlaywrightBanner'
=======
>>>>>>> 831d0ac59127446266432db213cea3cddcb64b25
import { NotificationCenter } from '../notifications/NotificationCenter'

export function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-950">
      <div className="hidden lg:block">
        <Sidebar />
      </div>

      <MobileNav isOpen={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar onMenuClick={() => setMobileNavOpen(true)} />
        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <IgSessionBanner />
          <IgPlaywrightBanner />
          <Outlet />
        </main>
      </div>
    </div>
  )
}
