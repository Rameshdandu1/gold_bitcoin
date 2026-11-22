import type { CSSProperties } from 'react'

export type IconName = 'grid' | 'sweep' | 'spark' | 'research' | 'pulse' | 'chevron' | 'arrow' | 'refresh' | 'clock' | 'shield' | 'search' | 'close' | 'menu' | 'link' | 'layers' | 'check' | 'info' | 'chart' | 'external'
const paths: Record<IconName, string[]> = {
  grid: ['M3 3h7v7H3z', 'M14 3h7v7h-7z', 'M3 14h7v7H3z', 'M14 14h7v7h-7z'],
  sweep: ['M3 6h18', 'M3 18h18', 'M3 12h4l3 8 4-16 3 8h4'],
  spark: ['m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6z'],
  research: ['M9 3h6', 'M10 3v6l-6 10a1.3 1.3 0 0 0 1.2 2h13.6a1.3 1.3 0 0 0 1.2-2L14 9V3', 'M8 14h8'],
  pulse: ['M3 12h4l3-8 4 16 3-8h4'],
  chevron: ['m9 5 7 7-7 7'],
  arrow: ['M5 17 19 3', 'M7 3h12v12'],
  refresh: ['M20 8a8 8 0 0 0-13-3L3 9', 'M3 3v6h6', 'M4 16a8 8 0 0 0 13 3l4-4', 'M15 15h6v6'],
  clock: ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18', 'M12 7v5l3 2'],
  shield: ['m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z', 'm8 12 3 3 5-6'],
  search: ['M10.5 3a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15', 'm16 16 5 5'],
  close: ['m5 5 14 14', 'm19 5-14 14'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  link: ['m10 13 4-4', 'M8 16H6a4 4 0 0 1 0-8h3', 'M15 8h3a4 4 0 0 1 0 8h-3'],
  layers: ['m12 3 10 5-10 5L2 8z', 'm2 12 10 5 10-5', 'm2 16 10 5 10-5'],
  check: ['m5 12 4 4L19 6'],
  info: ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18', 'M12 11v6', 'M12 7h.01'],
  chart: ['M4 3v17h17', 'm7 14 4-4 4 3 6-8'],
  external: ['M14 3h7v7', 'm10 14 11-11', 'M10 3H3v18h18v-7'],
}

export function Icon({ name, size = 20, style }: { name: IconName; size?: number; style?: CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}>{paths[name].map((path, index) => <path d={path} key={index}/>)}</svg>
}
