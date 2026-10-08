import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from './auth-store'
import { useEffect } from 'react'

export interface GitHubUserProfile {
  username: string
  name: string
  avatar_url: string
  html_url: string
  bio: string | null
  company?: string | null
  location?: string | null
  public_repos: number
  followers: number
  following: number
  created_at: string | null
}

export interface GitHubUserStats {
  total_points: number
  streak_days: number
  merged_prs: number
  rank: string
  tier: string
  total_commits: number
  total_contributions: number
  total_repos: number
}

export interface GitHubLanguage {
  name: string
  count: number
  percentage: number
  color: string
}

export interface GitHubTopRepo {
  name: string
  full_name: string
  html_url: string
  description: string
  language: string
  stars: number
  forks: number
  updated_at: string
}

export interface GitHubBadge {
  id: string
  title: string
  description: string
  icon: string
  tier: 'Bronze' | 'Silver' | 'Gold' | 'Diamond'
  unlocked: boolean
  progress: number
  unlocked_at?: string | null
}

export interface GitHubRecentActivity {
  id: string
  type: string
  title: string
  repo: string
  repo_url: string
  detail: string
  timestamp: string
  time_display: string
  icon: string
}

export interface GitHubHeatmapDay {
  date: string
  count: number
  level: number
}

export interface GitHubUserFullData {
  profile: GitHubUserProfile
  stats: GitHubUserStats
  languages: GitHubLanguage[]
  top_repos: GitHubTopRepo[]
  badges: GitHubBadge[]
  recent_activity: GitHubRecentActivity[]
  heatmap: GitHubHeatmapDay[]
  /** True when GitHub rate limiting degraded this snapshot to stale data. */
  rate_limited?: boolean
}

export function useGitHubUserProfile() {
  const user = useAuthStore((s) => s.user)
  const updateUser = useAuthStore((s) => s.updateUser)
  // Resolve the GitHub handle strictly from the signed-in user's own data.
  // Never fall back to a hardcoded account — that would show someone else's
  // stats to users who have not connected GitHub yet.
  const username =
    user?.github_username?.trim() ||
    (user?.username && !user.username.includes('@') ? user.username.trim() : null) ||
    null

  const query = useQuery<GitHubUserFullData>({
    queryKey: ['github-user-profile', username ?? 'not-connected'],
    queryFn: async () => {
      if (!username) throw new Error('No GitHub account connected')
      const res = await fetch(`/api/v1/github/user-profile/${encodeURIComponent(username)}`)
      if (!res.ok) {
        throw new Error(`Failed to load GitHub user profile (HTTP ${res.status})`)
      }
      return await res.json()
    },
    enabled: !!username,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  })

  // Synchronize avatar_url into user store if available
  useEffect(() => {
    if (query.data?.profile?.avatar_url && user && user.avatar_url !== query.data.profile.avatar_url) {
      updateUser({ avatar_url: query.data.profile.avatar_url })
    }
  }, [query.data?.profile?.avatar_url, user, updateUser])

  return query
}
