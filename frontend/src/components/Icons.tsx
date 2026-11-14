import type { SVGProps } from 'react'

/** One icon set (24px grid, 1.75 stroke). Pass `name`; decorative by default (aria-hidden). */
const P = {
  dashboard: 'M4 5a1 1 0 0 1 1-1h5v7H4zM14 4h5a1 1 0 0 1 1 1v3h-6zM14 12h6v7a1 1 0 0 1-1 1h-5zM4 15h6v5H5a1 1 0 0 1-1-1z',
  mic: 'M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6',
  stop: 'M7 7h10v10H7z',
  orders: 'M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3',
  users: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20a6.5 6.5 0 0 1 13 0M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.2a6.5 6.5 0 0 1 3.5 5.8',
  box: 'M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5zM3.5 7.5 12 12l8.5-4.5M12 12v9',
  catalogue: 'M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5zM13 4h5.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H13zM7 8h1.5M7 11.5h1.5M16 8h1.5M16 11.5h1.5',
  chart: 'M4 20V4M4 20h16M8 16v-4M12.5 16V8M17 16v-6',
  chat: 'M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v9a1.5 1.5 0 0 1-1.5 1.5H10l-4.5 4v-4h0A1.5 1.5 0 0 1 4 14.5z',
  wave: 'M3 12h2M7 8v8M11 4.5v15M15 8v8M19 10.5v3',
  gear: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 13.5a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V19a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H5a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1A2 2 0 1 1 9 4.8l.1.1a1.6 1.6 0 0 0 1.8.3h0a1.6 1.6 0 0 0 1-1.5V3.5a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8v0a1.6 1.6 0 0 0 1.5 1h.1a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-3.8-3.8',
  download: 'M12 4v11M7.5 11.5 12 16l4.5-4.5M5 20h14',
  print: 'M7 8V4h10v4M7 17H5a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-2M7 14h10v6H7z',
  monitor: 'M3 5.5A1.5 1.5 0 0 1 4.5 4h15A1.5 1.5 0 0 1 21 5.5v10a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 15.5zM8 21h8M12 17v4',
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  x: 'M6 6l12 12M18 6 6 18',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  alert: 'M12 4 2.8 19.5h18.4zM12 10v4.5M12 17.4v.1',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5M12 7.9v.1',
  chevronLeft: 'M14.5 6 8.5 12l6 6',
  chevronRight: 'M9.5 6l6 6-6 6',
  chevronDown: 'M6 9.5l6 6 6-6',
  chevronUp: 'M6 14.5l6-6 6 6',
  sortUp: 'M12 19V6M6.5 11.5 12 6l5.5 5.5',
  sortDown: 'M12 5v13M6.5 12.5 12 18l5.5-5.5',
  panel: 'M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5zM9.5 4v16',
  menu: 'M4 7h16M4 12h16M4 17h16',
  edit: 'M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17zM14 8l3 3',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M9 7V4h6v3',
  refresh: 'M20 11a8 8 0 0 0-14.5-4M4 4v4h4M4 13a8 8 0 0 0 14.5 4M20 20v-4h-4',
  external: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  filter: 'M4 5h16l-6 7.5V19l-4-2v-4.5z',
  cart: 'M3 4h2.5l2 11h10l2-8H7M9.5 20a.9.9 0 1 0 0-.01M17 20a.9.9 0 1 0 0-.01',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20.5a7.5 7.5 0 0 1 15 0',
  rupee: 'M7 5h10M7 9h10M7 5c5 0 7 1.5 7 4s-2 4-7 4l7 6',
  trend: 'M4 16l5-5 4 4 7-8M15 7h5v5',
  trendDown: 'M4 8l5 5 4-4 7 8M15 17h5v-5',
  database: 'M12 10c4.4 0 8-1.3 8-3s-3.6-3-8-3-8 1.3-8 3 3.6 3 8 3zM4 7v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
  lock: 'M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3M12 15v2',
  key: 'M9 15a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM13 11h8M18 11v3M21 11v2',
  shield: 'M12 3 5 6v5.5c0 4.2 2.8 7.8 7 9.5 4.2-1.7 7-5.3 7-9.5V6z',
  speaker: 'M5 9.5h3l4-3.5v12l-4-3.5H5zM15.5 9a4 4 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11',
  keyboard: 'M3.5 6.5h17a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-17a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zM6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M7.5 14h9',
  tag: 'M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7a1 1 0 0 1 .7.3l7.8 7.8a1 1 0 0 1 0 1.4l-7.7 7.7a1 1 0 0 1-1.4 0L3.8 12.9a1 1 0 0 1-.3-.7zM8 8h.01',
  package: 'M12 3 4 7v10l8 4 8-4V7zM4 7l8 4 8-4M12 11v10M8 5l8 4',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  arrowRight: 'M5 12h14M13 6l6 6-6 6',
  wallet: 'M4 7a2 2 0 0 1 2-2h11a1 1 0 0 1 1 1v2M4 7v11a2 2 0 0 0 2 2h13a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1H6a2 2 0 0 1-2-1zM16 14h.01',
  qr: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 14h2M14 18h2v2M18 18v2h2',
  card: 'M3.5 6.5A1.5 1.5 0 0 1 5 5h14a1.5 1.5 0 0 1 1.5 1.5v11A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5zM3.5 10h17M7 15h3',
  cash: 'M3 7.5h18v9H3zM12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM6.5 10.5h.01M17.5 13.5h.01',
  undo: 'M9 14 4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3',
  logout: 'M9 4H5.5A1.5 1.5 0 0 0 4 5.5v13A1.5 1.5 0 0 0 5.5 20H9M16 8l4 4-4 4M20 12H9',
} as const
export type IconName = keyof typeof P

export function Icon({ name, size = 18, ...rest }: { name: IconName; size?: number } & Omit<SVGProps<SVGSVGElement>, 'name'>) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden focusable="false" {...rest}>
      <path d={P[name]} />
    </svg>
  )
}

// Back-compat named exports used by older pages
export const MicIcon = (p: Omit<SVGProps<SVGSVGElement>, 'name'> & { size?: number }) => <Icon name="mic" {...p} />
export const StopIcon = (p: Omit<SVGProps<SVGSVGElement>, 'name'> & { size?: number }) => <Icon name="stop" {...p} />
