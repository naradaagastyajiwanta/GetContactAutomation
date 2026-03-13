import { useEffect, useRef, useState } from 'react'
import { cn } from '../../lib/utils'

export interface SectionItem {
  id: string
  label: string
  icon: React.ReactNode
}

interface Props {
  sections: SectionItem[]
}

export function SectionNav({ sections }: Props) {
  const [active, setActive] = useState(sections[0]?.id ?? '')
  const navRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const observers: IntersectionObserver[] = []
    for (const section of sections) {
      const el = document.getElementById(`settings-${section.id}`)
      if (!el) continue
      const obs = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) setActive(section.id)
        },
        { rootMargin: '-20% 0px -60% 0px', threshold: 0 },
      )
      obs.observe(el)
      observers.push(obs)
    }
    return () => observers.forEach((o) => o.disconnect())
  }, [sections])

  const handleClick = (id: string) => {
    const el = document.getElementById(`settings-${id}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      setActive(id)
    }
  }

  return (
    <div
      ref={navRef}
      className="sticky top-0 z-20 -mx-1 mb-6 flex gap-1 overflow-x-auto rounded-xl bg-gray-100/80 p-1 backdrop-blur dark:bg-gray-800/80"
    >
      {sections.map((s) => (
        <button
          key={s.id}
          onClick={() => handleClick(s.id)}
          className={cn(
            'flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-all',
            active === s.id
              ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-gray-100'
              : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200',
          )}
        >
          {s.icon}
          {s.label}
        </button>
      ))}
    </div>
  )
}
