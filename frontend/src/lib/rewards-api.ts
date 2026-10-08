/**
 * Rewards API client — points earned from GitHub activity and learning
 * modules, redeemable for 1:1 mentor sessions.
 *
 * All endpoints are authenticated with the bearer token persisted by the
 * auth store under `osa-token`.
 */

const API_BASE = '/api/v1/rewards'
const TOKEN_KEY = 'osa-token'

export interface RewardEntry {
  id: number
  source: 'github' | 'learning' | 'redemption' | 'adjustment'
  activity: string
  points: number
  reference_key: string | null
  description: string | null
  extra_metadata: Record<string, unknown> | null
  occurred_at: string | null
  created_at: string
}

export interface RewardsSummary {
  balance: number
  breakdown: Record<string, number>
  rules: Record<string, Record<string, number>>
  recent: RewardEntry[]
}

export interface GithubSyncResponse {
  balance: number
  total_awarded: number
  events_scanned: number
  awarded: RewardEntry[]
}

export interface TutorialAwardResponse {
  awarded: boolean
  points: number
  balance: number
}

export interface RedeemPayload {
  amount: number
  mentor_id?: number
  mentor_name?: string
  tier?: string
  date?: string
  time?: string
  topic?: string
}

export interface RedeemResponse {
  balance: number
  redemption: RewardEntry
}

export interface CancelRedemptionResponse {
  refunded: boolean
  balance: number
}

export interface ClaimState {
  id: string
  label: string
  points: number
  available: boolean
  next_available_at: string | null
}

export interface ClaimsResponse {
  claims: ClaimState[]
}

export interface ClaimResult {
  awarded: boolean
  points: number
  balance: number
  next_available_at: string | null
}

/** Centralized query keys for TanStack Query. */
export const rewardsKeys = {
  all: ['rewards'] as const,
  summary: ['rewards', 'summary'] as const,
  ledger: (limit: number, offset: number) => ['rewards', 'ledger', limit, offset] as const,
}

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  }
  const token = readToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null)
    const message =
      typeof errorBody?.detail === 'string'
        ? errorBody.detail
        : `Rewards API error (${response.status})`
    throw new Error(message)
  }

  return response.json() as Promise<T>
}

/** Fetch the signed-in user's balance, breakdown, rules, and recent ledger rows. */
export function fetchRewardsSummary(): Promise<RewardsSummary> {
  return request<RewardsSummary>('/me')
}

/** Fetch a page of the signed-in user's full points ledger. */
export function fetchRewardsLedger(limit = 50, offset = 0): Promise<{ items: RewardEntry[]; total: number }> {
  return request(`/ledger?limit=${limit}&offset=${offset}`)
}

/** List the manual point claims available to the signed-in user. */
export function fetchClaims(): Promise<ClaimsResponse> {
  return request<ClaimsResponse>('/claims')
}

/** Claim the once-per-day check-in points (idempotent per UTC day). */
export function claimDailyPoints(): Promise<ClaimResult> {
  return request<ClaimResult>('/claims/daily', { method: 'POST' })
}

/**
 * Replay the user's recent public GitHub activity into the points ledger.
 * Idempotent server-side: only genuinely new events are credited.
 */
export function syncGithubRewards(): Promise<GithubSyncResponse> {
  return request<GithubSyncResponse>('/sync-github', { method: 'POST' })
}

/** Award points for completing a guided learning tutorial (idempotent). */
export function awardTutorialCompletion(payload: {
  tutorial_id: string
  tutorial_title?: string
}): Promise<TutorialAwardResponse> {
  return request<TutorialAwardResponse>('/tutorial-completed', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** Spend points on a 1:1 mentor session. */
export function redeemPoints(payload: RedeemPayload): Promise<RedeemResponse> {
  return request<RedeemResponse>('/redeem', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** Cancel a booked mentor session and refund its points. */
export function cancelRedemption(referenceKey: string): Promise<CancelRedemptionResponse> {
  return request<CancelRedemptionResponse>('/redemptions/cancel', {
    method: 'POST',
    body: JSON.stringify({ reference_key: referenceKey }),
  })
}
