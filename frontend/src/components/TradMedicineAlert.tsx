// frontend/src/components/TradMedicineAlert.tsx
import { AlertTriangle } from 'lucide-react'

interface Props {
  type: string
  risk: string
}

export function TradMedicineAlert({ type, risk }: Props) {
  const colour = risk === 'HIGH'
    ? 'bg-red-50 border-red-400 text-red-800'
    : risk === 'MODERATE'
    ? 'bg-orange-50 border-orange-400 text-orange-800'
    : 'bg-yellow-50 border-yellow-400 text-yellow-800'

  return (
    <div className={`flex items-start gap-2 px-3 py-2
                     rounded-lg border ${colour} text-sm`}>
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <div>
        <span className="font-semibold">
          Traditional Medicine Detected:
        </span>{' '}
        <span className="capitalize">{type}</span>
        {' '}&mdash; Risk:{' '}
        <span className="font-semibold">{risk}</span>
          </div>
        </div>
    )
}
