// frontend/src/components/SeverityBadge.tsx
import { Severity } from '@/lib/types'
import { severityColour } from '@/lib/utils'
export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`
      inline-flex items-center px-2.5 py-0.5 rounded-full
      text-xs font-semibold ${severityColour(severity)}
    `}>
      {severity}
    </span>
  )
}
