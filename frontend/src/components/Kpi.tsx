import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icons'
import { Sparkline } from './charts'
import { Skeleton } from './ui'

export function Delta({ value, suffix = 'vs previous', invert = false }: { value: number | null; suffix?: string; invert?: boolean }) {
  if (value === null) return <span className="delta flat">Not enough earlier data to compare</span>
  const rounded = Math.round(value * 10) / 10
  const up = rounded > 0, flat = rounded === 0
  const good = invert ? !up : up
  return (
    <span className={`delta ${flat ? 'flat' : good ? 'up' : 'down'}`}>
      <Icon name={flat ? 'minus' : up ? 'trend' : 'trendDown'} size={13} />
      {flat ? 'No change' : `${up ? '+' : ''}${rounded}%`} <span className="faint" style={{ fontWeight: 400 }}>{suffix}</span>
    </span>
  )
}

export function KpiCard({ label, icon, value, foot, spark, sparkLabel, loading }: {
  label: string; icon?: IconName; value: ReactNode; foot?: ReactNode; spark?: number[]; sparkLabel?: string; loading?: boolean
}) {
  return (
    <div className="card kpi" role="group" aria-label={label}>
      <div className="l">{icon && <Icon name={icon} size={15} />}{label}</div>
      {loading ? <><Skeleton h={30} w="55%" /><Skeleton h={12} w="80%" /></> : (
        <>
          <div className="vrow"><div className="v">{value}</div>{spark && <Sparkline values={spark} label={sparkLabel ?? `${label} trend`} />}</div>
          {foot && <div className="f">{foot}</div>}
        </>
      )}
    </div>
  )
}
