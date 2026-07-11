// frontend/src/components/PageLayout.tsx
'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Sidebar } from './Sidebar'
import { useAuth } from '@/lib/auth-context'

export function PageLayout({
  children,
  title,
  subtitle,
}: {
  children: React.ReactNode
  title: string
  subtitle?: string
}) {
  const { session, staff, loading, signOut } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && !session) {
      router.replace('/login')
    }
  }, [loading, session, router])

  if (loading || !session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 text-gray-400 text-sm">
        Loading...
      </div>
    )
  }

  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar role={staff?.role} />
      <main className="ml-56 flex-1 p-8 min-h-screen">
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
            {subtitle && (
              <p className="text-sm text-gray-500 mt-1">{subtitle}</p>
            )}
          </div>
          <div className="flex items-center gap-3 text-sm">
            {staff && (
              <div className="text-right">
                <p className="font-medium text-gray-900">{staff.full_name}</p>
                <p className="text-gray-400 text-xs capitalize">
                  {staff.role.replace('_', ' ')}
                </p>
              </div>
            )}
            <button
              onClick={signOut}
              className="text-xs text-gray-400 hover:text-gray-700 border border-gray-200 rounded-lg px-3 py-1.5"
            >
              Sign out
            </button>
          </div>
        </div>
        {children}
      </main>
    </div>
  )
}
