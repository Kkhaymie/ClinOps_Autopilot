// frontend/src/lib/auth-context.tsx
'use client'
import { createContext, useContext, useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from './supabase'

export type StaffRole = 'admin' | 'coordinator' | 'pi' | 'sponsor' | 'site_staff'

export interface StaffProfile {
  id: string
  full_name: string
  role: StaffRole
  email: string
}

interface AuthContextValue {
  session: Session | null
  staff: StaffProfile | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<{ error: string | null }>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [staff, setStaff] = useState<StaffProfile | null>(null)
  const [loading, setLoading] = useState(true)

  async function loadStaffProfile(userId: string) {
    // Uses the anon key, so this is subject to the staff_read_own RLS
    // policy: a logged-in user can only ever read their own row.
    const { data } = await supabase
      .from('staff')
      .select('id, full_name, role, email')
      .eq('id', userId)
      .eq('active', true)
      .single()
    setStaff((data as StaffProfile) ?? null)
  }

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      if (session?.user) {
        loadStaffProfile(session.user.id).finally(() => setLoading(false))
      } else {
        setLoading(false)
      }
    })

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
      if (session?.user) {
        loadStaffProfile(session.user.id)
      } else {
        setStaff(null)
      }
    })

    return () => listener.subscription.unsubscribe()
  }, [])

  async function signIn(email: string, password: string) {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    return { error: error ? error.message : null }
  }

  async function signOut() {
    await supabase.auth.signOut()
  }

  return (
    <AuthContext.Provider value={{ session, staff, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
