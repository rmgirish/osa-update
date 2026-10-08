/**
 * Mentors API client — the backend source of truth for the Redeem catalog.
 */

export type MentorTier = 'beginner' | 'intermediate' | 'advanced' | 'expert'

export interface Mentor {
  id: number
  name: string
  role: string
  company: string
  tier: MentorTier
  cost: number
  rating: number
  sessions: number
  languages: string[]
  timezone: string
  tags: string[]
  bio: string
}

export interface MentorListResponse {
  mentors: Mentor[]
  total: number
  /** Tier -> points cost, ordered beginner to expert. */
  tiers: Record<string, number>
}

export async function fetchMentors(tag?: string): Promise<MentorListResponse> {
  const qs = tag ? `?tag=${encodeURIComponent(tag)}` : ''
  const response = await fetch(`/api/v1/mentors${qs}`)
  if (!response.ok) {
    throw new Error('Could not load the mentor catalog')
  }
  return (await response.json()) as MentorListResponse
}
