// frontend/src/components/Sidebar.tsx
'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  Inbox, CheckSquare, Clock, FolderOpen,
  AlertTriangle, BarChart2, Mail, Microscope
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { StaffRole } from '@/lib/auth-context'

// Adjust freely, this is the one place nav visibility per role is defined.
const NAV: { href: string; icon: any; label: string; roles: StaffRole[] }[] = [
  { href: '/',           icon: Inbox,         label: 'Live Inbox',        roles: ['admin', 'coordinator', 'pi', 'sponsor'] },
  { href: '/approvals',  icon: CheckSquare,   label: 'Pending Approvals', roles: ['admin', 'coordinator', 'pi'] },
  { href: '/clock',      icon: Clock,         label: 'Compliance Clock',  roles: ['admin', 'coordinator', 'pi', 'sponsor'] },
  { href: '/tmf',        icon: FolderOpen,    label: 'Trial Master File', roles: ['admin', 'coordinator', 'pi', 'sponsor'] },
  { href: '/signals',    icon: AlertTriangle, label: 'Safety Signals',    roles: ['admin', 'coordinator', 'pi', 'sponsor'] },
  { href: '/analytics',  icon: BarChart2,     label: 'Analytics',         roles: ['admin', 'coordinator', 'pi', 'sponsor'] },
  { href: '/letters',    icon: Mail,          label: 'Physical Letters',  roles: ['admin', 'coordinator', 'site_staff'] },
]

export function Sidebar({ role }: { role?: StaffRole }) {
  const path = usePathname()
  const items = role ? NAV.filter(item => item.roles.includes(role)) : NAV

  return (
    <aside className="fixed left-0 top-0 h-screen w-56 bg-[#0A0F2C] flex flex-col z-40">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-white/10">
        <div className="flex items-center gap-2">
          <Microscope className="text-[#F5C518]" size={22} />
          <div>
            <p className="text-white font-bold text-sm leading-tight">
                 ClinOps Autopilot
               </p>
               <p className="text-white/40 text-[10px]">
                 Sentara Health Technologies
               </p>
             </div>
           </div>
         </div>

         {/* Nav links */}
         <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
           {items.map(({ href, icon: Icon, label }) => {
             const active = path === href
             return (
               <Link
                 key={href}
                 href={href}
                 className={cn(
                   'flex items-center gap-3 px-3 py-2.5 rounded-lg',
                   'text-sm font-medium transition-colors',
                   active
                     ? 'bg-[#F5C518]/15 text-[#F5C518]'
                     : 'text-white/60 hover:text-white hover:bg-white/5'
                 )}
               >
                 <Icon size={17} />
                 {label}
               </Link>
             )
           })}
         </nav>

          {/* Footer */}
          <div className="px-5 py-4 border-t border-white/10">
            <p className="text-white/30 text-[10px]">v1.0.0 — Nigeria & Asia</p>
          </div>
        </aside>
    )
}
