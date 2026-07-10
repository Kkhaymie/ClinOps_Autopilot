// frontend/src/lib/utils.ts
import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { Severity, Channel } from './types'
import { formatDistanceToNow, format } from 'date-fns'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function severityColour(s: Severity) {
  return {
    'Life-threatening': 'bg-red-600 text-white',
    'Severe':           'bg-orange-500 text-white',
    'Moderate':         'bg-yellow-500 text-black',
    'Mild':             'bg-green-500 text-white',
  }[s] ?? 'bg-gray-400 text-white'
}

export function severityDot(s: Severity) {
  return {
    'Life-threatening': 'bg-red-500',
    'Severe':           'bg-orange-500',
    'Moderate':         'bg-yellow-400',
    'Mild':             'bg-green-500',
  }[s] ?? 'bg-gray-400'
}

export function severityBorder(s: Severity) {
  return {
    'Life-threatening': 'border-l-red-600',
    'Severe':           'border-l-orange-500',
    'Moderate':         'border-l-yellow-400',
    'Mild':             'border-l-green-500',
    }[s] ?? 'border-l-gray-400'
}

export function channelIcon(c: Channel) {
  return {
    'whatsapp':     '💬',
    'sms':          '📱',
    'telegram':     '✈️',
    'email':        '📧',
    'physical_mail':'📬',
  }[c] ?? '💬'
}

export function channelLabel(c: Channel) {
  return {
    'whatsapp':     'WhatsApp',
    'sms':          'SMS',
    'telegram':     'Telegram',
    'email':        'Email',
    'physical_mail':'Physical Mail',
  }[c] ?? c
}

export function timeAgo(date: string) {
  return formatDistanceToNow(new Date(date), { addSuffix: true })
}

export function formatDate(date: string) {
  return format(new Date(date), 'dd MMM yyyy, HH:mm')
}

export function deadlineStatus(deadline: string) {
  const hrs = (new Date(deadline).getTime() - Date.now()) / 3_600_000
  if (hrs <= 0)    return { label: 'OVERDUE',   colour: 'text-red-600',    bg: 'bg-red-50' }
  if (hrs <= 24)   return { label: `${Math.round(hrs)}h`, colour: 'text-red-500',    bg: 'bg-red-50' }
  if (hrs <= 48)   return { label: `${Math.round(hrs)}h`, colour: 'text-orange-500', bg: 'bg-orange-50' }
  const days = Math.round(hrs / 24)
  return { label: `${days}d`, colour: 'text-green-600', bg: 'bg-green-50' }
}
