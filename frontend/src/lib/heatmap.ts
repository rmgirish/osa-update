export interface HeatmapDay {
  date: string
  count: number
  level: number
}

export type HeatmapCell = HeatmapDay | null

export interface HeatmapWeek {
  cells: HeatmapCell[]
  monthLabel: string | null
  yearLabel: string | null
}

export const HEATMAP_MONTH_LABELS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
]

/** Rows run Sunday→Saturday; label the standard Mon/Wed/Fri rows. */
export const HEATMAP_WEEKDAY_LABELS = ['', 'Mon', '', 'Wed', '', 'Fri', '']

const DAY_MS = 86_400_000

export function heatLevelColor(level: number): string {
  switch (level) {
    case 1:
      return 'rgba(249, 115, 22, 0.25)'
    case 2:
      return 'rgba(249, 115, 22, 0.50)'
    case 3:
      return 'rgba(249, 115, 22, 0.75)'
    case 4:
      return 'rgba(249, 115, 22, 1.0)'
    default:
      return 'rgba(255, 255, 255, 0.03)'
  }
}

function toIsoDate(date: Date): string {
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const day = String(date.getUTCDate()).padStart(2, '0')
  return `${date.getUTCFullYear()}-${month}-${day}`
}

/**
 * Lay a rolling list of days (oldest→newest) out as calendar weeks so columns
 * line up with real week boundaries. Each column is Sunday→Saturday; the first
 * and last weeks are padded with empty cells. Month labels are emitted on the
 * week a new month begins, and year labels whenever the year changes — so the
 * previous-year and current-year sections stay clearly separated.
 */
export function buildHeatmapWeeks(days: HeatmapDay[]): HeatmapWeek[] {
  if (days.length === 0) return []

  const byDate = new Map(days.map((day) => [day.date, day]))
  const start = new Date(`${days[0].date}T00:00:00Z`)
  const startDayOfWeek = start.getUTCDay() // 0 = Sunday
  const weekCount = Math.ceil((startDayOfWeek + days.length) / 7)

  const weeks: HeatmapWeek[] = []
  let lastMonth = -1
  let lastYear = -1

  for (let week = 0; week < weekCount; week += 1) {
    const cells: HeatmapCell[] = []
    let firstDate: Date | null = null

    for (let day = 0; day < 7; day += 1) {
      const offset = week * 7 + day - startDayOfWeek
      if (offset < 0 || offset >= days.length) {
        cells.push(null)
        continue
      }
      const current = new Date(start.getTime() + offset * DAY_MS)
      const iso = toIsoDate(current)
      cells.push(byDate.get(iso) ?? { date: iso, count: 0, level: 0 })
      if (firstDate === null) firstDate = current
    }

    let monthLabel: string | null = null
    let yearLabel: string | null = null
    if (firstDate !== null) {
      const month = firstDate.getUTCMonth()
      if (month !== lastMonth) {
        monthLabel = HEATMAP_MONTH_LABELS[month]
        lastMonth = month
      }
      const year = firstDate.getUTCFullYear()
      if (year !== lastYear) {
        yearLabel = String(year)
        lastYear = year
      }
    }

    weeks.push({ cells, monthLabel, yearLabel })
  }

  return weeks
}
