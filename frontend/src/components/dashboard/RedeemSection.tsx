import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import {
  BadgeCheck,
  CalendarClock,
  CalendarPlus,
  CheckCircle2,
  Crown,
  Globe,
  GraduationCap,
  Gift,
  Hourglass,
  Info,
  Lock,
  Medal,
  MessageSquare,
  Rocket,
  Sparkles,
  Trophy,
  Users,
  Video,
  X,
  Zap,
} from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Dialog,
  EmptyState,
  Input,
} from '@/components/ui'
import type { BadgeProps } from '@/components/ui'
import { cn } from '@/lib/utils'
import {
  cancelRedemption,
  claimDailyPoints,
  fetchClaims,
  fetchRewardsSummary,
  redeemPoints,
  syncGithubRewards,
} from '@/lib/rewards-api'
import { fetchMentors, type Mentor, type MentorTier } from '@/lib/mentors-api'
import { useAuthStore } from '@/lib/auth-store'

/**
 * Redeem Points module — spend contribution points on 1:1 mentor sessions.
 *
 * Both the mentor catalog and the points balance come from the backend; there
 * is no local preview state, so what you see is the authoritative account.
 */

export type { Mentor, MentorTier } from '@/lib/mentors-api'

export interface MentorBooking {
  id: number
  mentorId: number
  mentorName: string
  tier: MentorTier
  date: string
  time: string
  topic: string
  cost: number
  /** Server ledger reference — set when the booking is synced to the backend. */
  referenceKey?: string | null
}

/** Point cost per mentor tier — the core redeem pricing table. */
const TIER_COSTS: Record<MentorTier, number> = {
  beginner: 100,
  intermediate: 300,
  advanced: 600,
  expert: 1000,
}

const TIER_META: Record<
  MentorTier,
  { label: string; blurb: string; badge: NonNullable<BadgeProps['variant']>; Icon: typeof Medal }
> = {
  beginner: {
    label: 'Beginner Mentor',
    blurb: 'First PR walkthroughs, Git basics and environment setup help.',
    badge: 'success',
    Icon: Medal,
  },
  intermediate: {
    label: 'Intermediate Mentor',
    blurb: 'Code review coaching, architecture questions and OSS workflow.',
    badge: 'accent',
    Icon: Zap,
  },
  advanced: {
    label: 'Advanced Mentor',
    blurb: 'Deep dives: performance, testing strategy and project leadership.',
    badge: 'warning',
    Icon: Trophy,
  },
  expert: {
    label: 'Expert Mentor',
    blurb: 'Maintainers & staff engineers. Career guidance and community leadership.',
    badge: 'default',
    Icon: Crown,
  },
}


function formatClaimReset(iso: string): string {
  try {
    return new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(
      new Date(iso),
    )
  } catch {
    return 'later today'
  }
}

export function RedeemSection() {
  const queryClient = useQueryClient()
  const token = useAuthStore((state) => state.token)
  const signedIn = Boolean(token)

  // Everything is backend-backed — no local preview state.
  const { data: summary, isError: summaryError } = useQuery({
    queryKey: ['rewards', 'summary'],
    queryFn: fetchRewardsSummary,
    enabled: signedIn,
    retry: false,
    staleTime: 30_000,
  })
  const { data: mentorsData, isLoading: mentorsLoading } = useQuery({
    queryKey: ['mentors'],
    queryFn: () => fetchMentors(),
    staleTime: 5 * 60_000,
  })
  const { data: claims } = useQuery({
    queryKey: ['rewards', 'claims'],
    queryFn: fetchClaims,
    enabled: signedIn,
    retry: false,
    staleTime: 30_000,
  })

  const mentors = mentorsData?.mentors ?? []
  const tierCosts = (mentorsData?.tiers ?? TIER_COSTS) as Record<MentorTier, number>
  const dailyClaim = claims?.claims.find((claim) => claim.id === 'daily')

  const [activeTag, setActiveTag] = useState<string | null>(null)
  const [selectedMentor, setSelectedMentor] = useState<Mentor | null>(null)
  const [redeemed, setRedeemed] = useState<MentorBooking | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [syncInfo, setSyncInfo] = useState<string | null>(null)
  const [claimInfo, setClaimInfo] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const points = summary?.balance ?? 0

  // Server bookings are rebuilt from the redemption ledger so the session
  // list survives reloads and matches the authoritative balance.
  const serverBookings: MentorBooking[] = useMemo(
    () =>
      (summary?.recent ?? [])
        .filter((entry) => entry.source === 'redemption' && entry.points < 0)
        .map((entry) => {
          const meta = (entry.extra_metadata ?? {}) as Record<string, unknown>
          const tier =
            typeof meta.tier === 'string' && meta.tier in TIER_COSTS
              ? (meta.tier as MentorTier)
              : 'beginner'
          return {
            id: entry.id,
            mentorId: typeof meta.mentor_id === 'number' ? meta.mentor_id : 0,
            mentorName: typeof meta.mentor_name === 'string' ? meta.mentor_name : 'Mentor',
            tier,
            date: typeof meta.date === 'string' ? meta.date : 'TBD',
            time: typeof meta.time === 'string' ? meta.time : 'TBD',
            topic: typeof meta.topic === 'string' ? meta.topic : '',
            cost: -entry.points,
            referenceKey: entry.reference_key,
          }
        }),
    [summary],
  )
  const allBookings = serverBookings

  const tagOptions = useMemo(
    () => [...new Set(mentors.flatMap((m) => m.tags))].sort(),
    [mentors],
  )

  const filtered = useMemo(
    () => (activeTag ? mentors.filter((m) => m.tags.includes(activeTag)) : mentors),
    [activeTag, mentors],
  )

  const upcoming = useMemo(
    () =>
      [...allBookings]
        .sort((a, b) => `${a.date}${a.time}`.localeCompare(`${b.date}${b.time}`))
        .slice(0, 3),
    [allBookings],
  )

  const startRedeem = (mentor: Mentor) => setSelectedMentor(mentor)

  const handleGithubSync = async () => {
    if (busy) return
    setBusy(true)
    setActionError(null)
    setSyncInfo(null)
    try {
      const res = await syncGithubRewards()
      await queryClient.invalidateQueries({ queryKey: ['rewards'] })
      setSyncInfo(
        res.total_awarded > 0
          ? `+${res.total_awarded} pts from ${res.events_scanned} GitHub events`
          : `Up to date — ${res.events_scanned} events already credited`,
      )
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'GitHub sync failed. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const handleClaim = async () => {
    if (busy || !dailyClaim?.available) return
    setBusy(true)
    setActionError(null)
    setClaimInfo(null)
    try {
      const res = await claimDailyPoints()
      await queryClient.invalidateQueries({ queryKey: ['rewards'] })
      setClaimInfo(res.awarded ? `+${res.points} pts claimed` : 'Already claimed today')
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not claim points.')
    } finally {
      setBusy(false)
    }
  }

  const confirmRedeem = async (date: string, time: string, topic: string) => {
    const mentor = selectedMentor
    if (!mentor || points < mentor.cost || busy) return
    setBusy(true)
    setActionError(null)
    const booking: MentorBooking = {
      id: Date.now(),
      mentorId: mentor.id,
      mentorName: mentor.name,
      tier: mentor.tier,
      date,
      time,
      topic: topic.trim(),
      cost: mentor.cost,
    }
    try {
      const res = await redeemPoints({
        amount: mentor.cost,
        mentor_id: mentor.id,
        mentor_name: mentor.name,
        tier: mentor.tier,
        date,
        time,
        topic: topic.trim(),
      })
      booking.referenceKey = res.redemption.reference_key
      await queryClient.invalidateQueries({ queryKey: ['rewards'] })
      setRedeemed(booking)
      setSelectedMentor(null)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Redemption failed. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const cancelBooking = async (id: number) => {
    const booking = allBookings.find((b) => b.id === id)
    if (!booking) return
    if (!window.confirm(`Cancel the session with ${booking.mentorName}? Points will be refunded.`)) return
    if (!booking.referenceKey) return
    setBusy(true)
    setActionError(null)
    try {
      await cancelRedemption(booking.referenceKey)
      await queryClient.invalidateQueries({ queryKey: ['rewards'] })
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not cancel the session.')
    } finally {
      setBusy(false)
    }
  }

  const nextTier = useMemo(() => {
    const unlocked = (Object.entries(tierCosts) as [MentorTier, number][]).filter(
      ([, cost]) => points >= cost,
    ).length
    const order: MentorTier[] = ['beginner', 'intermediate', 'advanced', 'expert']
    const next = order.find((tier) => points < tierCosts[tier])
    return { unlocked, next, nextCost: next ? tierCosts[next] : null }
  }, [points, tierCosts])

  const totalSpent = useMemo(
    () => allBookings.reduce((sum, b) => sum + b.cost, 0),
    [allBookings],
  )

  return (
    <div className="animate-fade-up space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow">Rewards / Redeem</p>
          <h1 className="section-h2">Redeem Points</h1>
          <div className="section-underline" aria-hidden="true" />
          <p className="section-body">
            Turn your contribution points into 1:1 mentor sessions. Higher-tier mentors cost
            more points but bring deeper experience to the table.
          </p>
        </div>
        <div className="flex flex-col items-start gap-1.5 rounded-lg border border-accent/30 bg-accent/5 px-4 py-3 sm:items-end sm:text-right">
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Your balance
          </p>
          <p className="flex items-center gap-1.5 font-mono text-2xl font-bold text-accent-text">
            <Sparkles className="size-4" aria-hidden="true" />
            {points.toLocaleString()} pts
          </p>
          <p className="font-mono text-[10px] text-muted-foreground">
            {signedIn ? 'synced with backend' : 'sign in to redeem'}
          </p>
          {signedIn && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleGithubSync}
              disabled={busy}
              className="gap-1.5"
            >
              <RefreshCw className={cn('size-3.5', busy && 'animate-spin')} aria-hidden="true" />
              Sync GitHub points
            </Button>
          )}
          {syncInfo && (
            <p className="font-mono text-[10px] font-semibold text-emerald-400">{syncInfo}</p>
          )}
        </div>
      </div>

      {/* Sign-in / load error notices */}
      {!signedIn && (
        <div className="flex items-center gap-2.5 rounded-lg border border-accent/20 bg-accent/5 px-4 py-2.5 text-xs text-muted-foreground">
          <Badge variant="accent" className="shrink-0 text-[10px]">
            Sign in required
          </Badge>
          <span className="flex-1">
            Redeeming mentor sessions needs an account. Sign in to see your balance, claim daily points, and book sessions.
          </span>
        </div>
      )}
      {signedIn && summaryError && (
        <div
          role="alert"
          className="flex items-center gap-2.5 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-2.5 text-xs text-red-400"
        >
          Could not load your rewards balance. Please try again.
        </div>
      )}
      {actionError && (
        <div role="alert" className="flex items-center gap-2.5 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-2.5 text-xs text-red-400">
          {actionError}
        </div>
      )}

      {/* Daily claim */}
      {signedIn && dailyClaim && (
        <Card className="border-accent/30">
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-md border border-accent/40 bg-accent/10 text-accent-text">
                <Gift className="size-5" aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-semibold text-foreground">{dailyClaim.label}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {dailyClaim.available
                    ? `Claim ${dailyClaim.points} points for today.`
                    : `Already claimed — next claim ${
                        dailyClaim.next_available_at
                          ? formatClaimReset(dailyClaim.next_available_at)
                          : 'tomorrow'
                      }.`}
                </p>
                {claimInfo && (
                  <p className="mt-0.5 font-mono text-[11px] font-semibold text-emerald-400">
                    {claimInfo}
                  </p>
                )}
              </div>
            </div>
            <Button
              size="sm"
              onClick={() => void handleClaim()}
              disabled={busy || !dailyClaim.available}
              className="shrink-0 gap-1.5"
            >
              <Sparkles className="size-3.5" aria-hidden="true" />
              {dailyClaim.available ? `Claim +${dailyClaim.points} pts` : 'Claimed'}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Tier summary + progress */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between gap-4">
              <div>
                <CardTitle>MENTOR TIERS</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {nextTier.unlocked} of {Object.keys(tierCosts).length} tiers unlocked with your current balance.
                </p>
              </div>
              <Gift className="size-5 text-accent-text" aria-hidden="true" />
            </div>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 p-4 sm:p-5 xl:grid-cols-4">
            {(Object.entries(TIER_META) as [MentorTier, (typeof TIER_META)[MentorTier]][]).map(
              ([tier, meta]) => {
                const affordable = points >= tierCosts[tier]
                const Icon = meta.Icon
                return (
                  <div
                    key={tier}
                    className={cn(
                      'rounded-lg border p-3.5 transition-all duration-200',
                      affordable
                        ? 'border-accent/40 bg-accent/5'
                        : 'border-border bg-background opacity-70',
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <Icon
                        className={cn('size-5', affordable ? 'text-accent-text' : 'text-muted-foreground')}
                        aria-hidden="true"
                      />
                      {affordable ? (
                        <BadgeCheck className="size-4 text-emerald-400" aria-hidden="true" />
                      ) : (
                        <Lock className="size-3.5 text-muted-foreground" aria-hidden="true" />
                      )}
                    </div>
                    <p className="mt-2.5 text-xs font-semibold">{meta.label}</p>
                    <p className="mt-1 font-mono text-sm font-bold text-accent-text">
                      {tierCosts[tier]} pts
                    </p>
                    <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">
                      {meta.blurb}
                    </p>
                  </div>
                );
              },
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b border-border">
            <CardTitle>POINTS OVERVIEW</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 p-4 sm:p-5">
            <div className="flex items-baseline justify-between">
              <span className="text-xs text-muted-foreground">Balance</span>
              <span className="font-mono text-lg font-bold">{points.toLocaleString()}</span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-xs text-muted-foreground">Spent on sessions</span>
              <span className="font-mono text-lg font-bold">{totalSpent.toLocaleString()}</span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-xs text-muted-foreground">Sessions booked</span>
              <span className="font-mono text-lg font-bold">{allBookings.length}</span>
            </div>
            {nextTier.next && nextTier.nextCost && (
              <div className="rounded-lg border border-border bg-background p-3">
                <p className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                  <Rocket className="size-3.5 text-accent-text" aria-hidden="true" />
                  Next unlock
                </p>
                <p className="mt-1 text-xs text-foreground">
                  <span className="font-semibold">{TIER_META[nextTier.next].label}</span> at{' '}
                  <span className="font-mono font-semibold text-accent-text">{nextTier.nextCost} pts</span>
                </p>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {nextTier.nextCost - points} points to go.
                </p>
              </div>
            )}
            {totalSpent > 0 && (
              <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <Sparkles className="size-3.5 text-accent-text" aria-hidden="true" />
                Contributing to open source is literally paying for your growth.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Upcoming sessions */}
      {upcoming.length > 0 && (
        <Card>
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between gap-4">
              <div>
                <CardTitle>UPCOMING SESSIONS</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  Your next {upcoming.length} booked mentor {upcoming.length === 1 ? 'session' : 'sessions'}.
                </p>
              </div>
              <CalendarClock className="size-5 text-accent-text" aria-hidden="true" />
            </div>
          </CardHeader>
          <CardContent className="space-y-3 p-4 sm:p-5">
            {upcoming.map((booking) => {
              const meta = TIER_META[booking.tier]
              const Icon = meta.Icon
              return (
                <div
                  key={booking.id}
                  className="flex flex-col gap-3 rounded-lg border border-border bg-background p-4 transition-all hover:border-accent/40 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold">{booking.mentorName}</p>
                      <Badge variant={meta.badge} className="text-[10px]">
                        <Icon className="mr-1 size-3" aria-hidden="true" />
                        {meta.label}
                      </Badge>
                    </div>
                    <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1.5">
                        <CalendarClock className="size-3.5" aria-hidden="true" />
                        {booking.date} at {booking.time}
                      </span>
                      {booking.topic && (
                        <span className="flex items-center gap-1.5">
                          <MessageSquare className="size-3.5" aria-hidden="true" />
                          {booking.topic}
                        </span>
                      )}
                      <span className="flex items-center gap-1.5">
                        <Video className="size-3.5" aria-hidden="true" />
                        Meeting link arrives by email
                      </span>
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge variant="outline" className="font-mono text-[10px]">
                      −{booking.cost} pts
                    </Badge>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => cancelBooking(booking.id)}
                      className="gap-1.5 text-muted-foreground hover:border-accent/70 hover:text-accent-text"
                    >
                      <X className="size-3.5" aria-hidden="true" />
                      Cancel
                    </Button>
                  </div>
                  {/* Redeemed mentor sessions cannot be rescheduled here */}
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}

      {/* Mentor catalog */}
      <Card className="rounded-xl">
        <CardHeader className="border-b border-border">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>MENTOR CATALOG</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                {filtered.length} mentor{filtered.length === 1 ? '' : 's'} available{activeTag ? ` for #${activeTag}` : ''}.
              </p>
            </div>
            <GraduationCap className="size-5 text-accent-text" aria-hidden="true" />
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-4 sm:p-5">
          {/* Tag filter chips */}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setActiveTag(null)}
              className={cn(
                'rounded-full border px-3 py-1 text-[11px] font-medium transition-colors',
                activeTag === null
                  ? 'border-accent bg-accent text-on-accent'
                  : 'border-border bg-surface text-muted-foreground hover:border-accent/60 hover:text-foreground',
              )}
            >
              All mentors
            </button>
            {tagOptions.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => setActiveTag(activeTag === tag ? null : tag)}
                className={cn(
                  'rounded-full border px-3 py-1 text-[11px] font-medium transition-colors',
                  activeTag === tag
                    ? 'border-accent bg-accent text-on-accent'
                    : 'border-border bg-surface text-muted-foreground hover:border-accent/60 hover:text-foreground',
                )}
              >
                {tag}
              </button>
            ))}
          </div>

          {mentorsLoading ? (
            <p className="py-6 text-center text-xs text-muted-foreground">Loading mentors…</p>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No mentors for this topic"
              description="Try a different topic chip, or clear the filter to see the full catalog."
              action={
                <Button size="sm" variant="secondary" onClick={() => setActiveTag(null)}>
                  Clear filter
                </Button>
              }
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {filtered.map((mentor) => {
                const meta = TIER_META[mentor.tier]
                const TierIcon = meta.Icon
                const affordable = points >= mentor.cost
                return (
                  <div
                    key={mentor.id}
                    className="rounded-lg border border-border bg-background p-4 transition-all hover:border-accent/40 sm:p-5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-gradient-program font-mono text-base font-bold text-white">
                          {mentor.name.charAt(0)}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold">{mentor.name}</p>
                          <p className="truncate text-xs text-muted-foreground">
                            {mentor.role} · {mentor.company}
                          </p>
                        </div>
                      </div>
                      <Badge variant={meta.badge} className="shrink-0 text-[10px]">
                        <TierIcon className="mr-1 size-3" aria-hidden="true" />
                        {meta.label}
                      </Badge>
                    </div>

                    <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{mentor.bio}</p>

                    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <StarIcon /> {mentor.rating.toFixed(1)} ({mentor.sessions} sessions)
                      </span>
                      <span className="flex items-center gap-1">
                        <Globe className="size-3.5" aria-hidden="true" /> {mentor.timezone}
                      </span>
                      <span className="flex items-center gap-1">
                        <MessageSquare className="size-3.5" aria-hidden="true" />{' '}
                        {mentor.languages.join(', ')}
                      </span>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {mentor.tags.map((tag) => (
                        <Badge key={tag} variant="outline" className="text-[10px]">
                          {tag}
                        </Badge>
                      ))}
                    </div>

                    <div className="mt-4 flex items-center justify-between gap-3 border-t border-border pt-3.5">
                      <p className="font-mono text-sm font-bold text-accent-text">
                        {mentor.cost} pts
                      </p>
                      {affordable ? (
                        <Button size="sm" onClick={() => startRedeem(mentor)} className="gap-1.5">
                          <CalendarPlus className="size-3.5" aria-hidden="true" />
                          Redeem session
                        </Button>
                      ) : (
                        <Button size="sm" variant="secondary" disabled className="gap-1.5">
                          <Lock className="size-3.5" aria-hidden="true" />
                          Need {mentor.cost - points} pts
                        </Button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Booking history */}
      {allBookings.length > 0 && (
        <Card>
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between gap-4">
              <div>
                <CardTitle>REDEMPTION HISTORY</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  All sessions booked with your points.
                </p>
              </div>
              <Hourglass className="size-5 text-accent-text" aria-hidden="true" />
            </div>
          </CardHeader>
          <CardContent className="space-y-2.5 p-4 sm:p-5">
            {[...allBookings]
              .sort((a, b) => b.id - a.id)
              .map((booking) => (
                <div
                  key={booking.id}
                  className="flex flex-col gap-2 rounded-lg border border-border bg-background px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {booking.mentorName}{' '}
                      <span className="font-normal text-muted-foreground">
                        · {TIER_META[booking.tier].label}
                      </span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {booking.date} at {booking.time}
                      {booking.topic ? ` · ${booking.topic}` : ''}
                    </p>
                  </div>
                  <Badge variant="outline" className="shrink-0 font-mono text-[10px]">
                    −{booking.cost} pts
                  </Badge>
                </div>
              ))}
          </CardContent>
        </Card>
      )}

      {/* Redeem dialog */}
      {selectedMentor && (
        <RedeemDialog
          mentor={selectedMentor}
          points={points}
          onClose={() => setSelectedMentor(null)}
          onConfirm={confirmRedeem}
        />
      )}

      {/* Success dialog */}
      <Dialog
        open={redeemed !== null}
        onClose={() => setRedeemed(null)}
        ariaLabel="Session redeemed"
        title="$ osa redeem --success"
      >
        <div className="space-y-4 px-5 py-5">
          <div className="flex items-center gap-3">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-emerald-500/15">
              <CheckCircle2 className="size-6 text-emerald-400" aria-hidden="true" />
            </span>
            <div>
              <p className="text-base font-bold">Session redeemed!</p>
              <p className="text-xs text-muted-foreground">
                {redeemed && `${TIER_META[redeemed.tier].label} · −${redeemed.cost} points`}
              </p>
            </div>
          </div>
          {redeemed && (
            <div className="space-y-1.5 rounded-lg border border-border bg-background p-3.5 text-xs">
              <p>
                <span className="text-muted-foreground">Mentor:</span>{' '}
                <span className="font-semibold">{redeemed.mentorName}</span>
              </p>
              <p>
                <span className="text-muted-foreground">When:</span>{' '}
                <span className="font-semibold">
                  {redeemed.date} at {redeemed.time}
                </span>
              </p>
              {redeemed.topic && (
                <p>
                  <span className="text-muted-foreground">Topic:</span>{' '}
                  <span className="font-semibold">{redeemed.topic}</span>
                </p>
              )}
            </div>
          )}
          <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            A calendar invite with the video call link will arrive in your email. You can cancel
            from this page any time before the session for a full refund.
          </p>
          <div className="flex justify-end border-t border-border pt-4">
            <Button size="sm" onClick={() => setRedeemed(null)}>
              Done
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}

function RedeemDialog({
  mentor,
  points,
  onClose,
  onConfirm,
}: {
  mentor: Mentor
  points: number
  onClose: () => void
  onConfirm: (date: string, time: string, topic: string) => void
}) {
  const today = new Date().toISOString().slice(0, 10)
  const [date, setDate] = useState(today)
  const [time, setTime] = useState('17:00')
  const [topic, setTopic] = useState('')
  const affordable = points >= mentor.cost
  const meta = TIER_META[mentor.tier]
  const TierIcon = meta.Icon

  return (
    <Dialog open onClose={onClose} ariaLabel={`Redeem session with ${mentor.name}`} title="$ osa redeem --session">
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (affordable) onConfirm(date, time, topic)
        }}
        className="flex flex-col overflow-hidden"
      >
        {/* Scrollable body */}
        <div className="space-y-4 overflow-y-auto px-5 py-4">
          {/* Mentor summary */}
          <div className="flex items-center gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-gradient-program font-mono text-sm font-bold text-white">
              {mentor.name.charAt(0)}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{mentor.name}</p>
              <p className="truncate text-xs text-muted-foreground">
                {mentor.role} · {mentor.company}
              </p>
            </div>
            <Badge variant={meta.badge} className="ml-auto shrink-0 text-[10px]">
              <TierIcon className="mr-1 size-3" aria-hidden="true" />
              {meta.label}
            </Badge>
          </div>

          {/* Price + balance */}
          <div className="grid grid-cols-2 gap-2.5">
            <div className="rounded-lg border border-border bg-background p-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Cost</p>
              <p className="mt-1 flex items-center gap-1.5 font-mono text-lg font-bold text-accent-text">
                <Sparkles className="size-4" aria-hidden="true" />
                {mentor.cost} pts
              </p>
            </div>
            <div className="rounded-lg border border-border bg-background p-3">
              <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                After redeem
              </p>
              <p className={cn('mt-1 font-mono text-lg font-bold', affordable ? 'text-foreground' : 'text-muted-foreground')}>
                {Math.max(0, points - mentor.cost).toLocaleString()} pts
              </p>
            </div>
          </div>

          {/* Schedule */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label htmlFor="redeem-date" className="text-xs font-mono font-medium text-muted-foreground">
                Date
              </label>
              <Input
                id="redeem-date"
                type="date"
                min={today}
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="redeem-time" className="text-xs font-mono font-medium text-muted-foreground">
                Time
              </label>
              <Input
                id="redeem-time"
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                required
              />
            </div>
          </div>

          {/* Topic */}
          <div className="space-y-1.5">
            <label htmlFor="redeem-topic" className="text-xs font-mono font-medium text-muted-foreground">
              What do you want help with?{' '}
              <span className="font-normal text-muted-foreground/70">(optional)</span>
            </label>
            <Input
              id="redeem-topic"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder={`e.g. Review my first PR to ${mentor.company}`}
              maxLength={120}
            />
          </div>

          <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            Sessions run 45 minutes. Cancel any time before the session for a full point refund.
          </p>
        </div>

        {/* Sticky footer */}
        <div className="flex shrink-0 items-center justify-end gap-2 border-t border-border px-5 py-3.5">
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={!affordable} className="gap-1.5">
            {affordable ? (
              <>
                <Sparkles className="size-3.5" aria-hidden="true" />
                Confirm redeem
              </>
            ) : (
              <>
                <Lock className="size-3.5" aria-hidden="true" />
                Not enough points
              </>
            )}
          </Button>
        </div>
      </form>
    </Dialog>
  )
}

/** Inline star glyph (lucide `Star` conflicts with nothing, but keeps markup tiny). */
function StarIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="size-3.5" aria-hidden="true">
      <path d="M12 2l2.94 6.32 6.91.8-5.1 4.72 1.36 6.86L12 17.27l-6.11 3.43 1.36-6.86-5.1-4.72 6.91-.8L12 2z" />
    </svg>
  )
}

export default RedeemSection
