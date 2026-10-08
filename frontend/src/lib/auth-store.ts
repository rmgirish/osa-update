import { create } from 'zustand'

export type UserRole = 'user' | 'admin'
export type AccountStatus = 'active' | 'suspended' | 'banned'

export interface User {
  id?: string
  username: string
  email: string
  role?: UserRole
  account_status?: AccountStatus
  accountStatus?: AccountStatus
  skill_level?: string
  user_context?: string
  github_username?: string
  avatar_url?: string
  token?: string
}

interface AuthState {
  user: User | null
  token: string | null
  /** Error surfaced from the GitHub OAuth redirect (?oauth_error=...). */
  oauthError: string | null
  login: (email: string, password: string, rememberMe?: boolean) => Promise<User>
  refreshCurrentUser: () => Promise<User | null>
  requestSignup: (
    username: string,
    email: string,
    password: string,
    confirmPassword: string
  ) => Promise<{ message: string }>
  verifySignupOtp: (email: string, otp: string, username?: string) => Promise<User>
  requestPasswordReset: (email: string) => Promise<{ message: string }>
  resetPassword: (email: string, otp: string, newPassword: string) => Promise<{ message: string }>
  loginWithToken: (token: string, partialUser?: Partial<User>) => Promise<User>
  loginWithConnectedGitHub: () => Promise<User>
  getGitHubOAuthUrl: (state?: string) => Promise<{ configured: boolean; url: string | null; has_pat: boolean }>
  updateUser: (partial: Partial<User>) => void
  setOAuthError: (message: string | null) => void
  logout: () => void
}

function toUser(parsed: Partial<User>): User | null {
  if (typeof parsed.username !== 'string' || typeof parsed.email !== 'string') return null
  const status = parsed.account_status || parsed.accountStatus || 'active'
  return {
    id: parsed.id,
    username: parsed.username,
    email: parsed.email,
    token: parsed.token,
    role: parsed.role === 'admin' ? 'admin' : 'user',
    account_status: status === 'suspended' || status === 'banned' ? status : 'active',
    accountStatus: status === 'suspended' || status === 'banned' ? status : 'active',
    skill_level: parsed.skill_level,
    user_context: parsed.user_context,
    github_username: parsed.github_username,
    avatar_url: parsed.avatar_url,
  }
}

function loadUser(): User | null {
  try {
    const raw = localStorage.getItem('osa-user')
    if (!raw) return null
    return toUser(JSON.parse(raw) as Partial<User>)
  } catch {
    return null
  }
}

function loadToken(): string | null {
  try {
    return localStorage.getItem('osa-token')
  } catch {
    return null
  }
}

/** Persisted UTC ms timestamp at which the access token expires. */
const TOKEN_EXPIRY_KEY = 'osa-token-expires-at'

function readTokenExpiresAt(): number | null {
  try {
    const raw = localStorage.getItem(TOKEN_EXPIRY_KEY)
    if (!raw) return null
    const parsed = Number.parseInt(raw, 10)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null
  } catch {
    return null
  }
}

function isSessionExpired(): boolean {
  const expiresAt = readTokenExpiresAt()
  return expiresAt !== null && Date.now() >= expiresAt
}

function clearExpiredSession(): void {
  if (!isSessionExpired()) return
  try {
    localStorage.removeItem('osa-user')
    localStorage.removeItem('osa-token')
    localStorage.removeItem(TOKEN_EXPIRY_KEY)
  } catch {
    // best effort
  }
}

function persistTokenExpiry(expiresAtMs: number | null): void {
  try {
    if (expiresAtMs !== null) localStorage.setItem(TOKEN_EXPIRY_KEY, String(expiresAtMs))
    else localStorage.removeItem(TOKEN_EXPIRY_KEY)
  } catch {
    // best effort
  }
}

function persistSession(user: User | null, token: string | null, expiresAtMs: number | null = null) {
  try {
    if (user && token) {
      localStorage.setItem('osa-user', JSON.stringify({ ...user, token }))
      localStorage.setItem('osa-token', token)
      if (expiresAtMs !== null) persistTokenExpiry(expiresAtMs)
    } else {
      localStorage.removeItem('osa-user')
      localStorage.removeItem('osa-token')
      persistTokenExpiry(null)
    }
  } catch {
    // best effort
  }
}

function extractErrorMessage(data: unknown, fallback: string): string {
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (typeof data === 'object') {
    const errObj = data as Record<string, unknown>
    if (typeof errObj.detail === 'string') return errObj.detail
    if (Array.isArray(errObj.detail) && errObj.detail.length > 0) {
      return errObj.detail.map((item) => (typeof item === 'object' && item && 'msg' in item ? String(item.msg) : String(item))).join(', ')
    }
    if (typeof errObj.message === 'string') return errObj.message
  }
  return fallback
}

/** Fetch /me and throw on failure — used when a token must be verified. */
async function fetchProfileStrict(accessToken: string): Promise<User> {
  const response = await fetch('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  if (!response.ok) {
    throw new Error('Sign-in could not be verified. Please log in again.')
  }
  const profile = await response.json()
  const status = profile.account_status || profile.accountStatus || 'active'
  return {
    id: profile.id,
    username: profile.username || 'contributor',
    email: profile.email || '',
    token: accessToken,
    role: profile.role === 'admin' ? 'admin' : 'user',
    account_status: status === 'suspended' || status === 'banned' ? status : 'active',
    accountStatus: status === 'suspended' || status === 'banned' ? status : 'active',
    skill_level: profile.skill_level || undefined,
    user_context: profile.user_context || undefined,
    github_username: profile.github_username || undefined,
    avatar_url: profile.avatar_url || undefined,
  }
}

async function fetchProfile(accessToken: string, fallback: User): Promise<User> {
  const response = await fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${accessToken}` } })
  if (!response.ok) return fallback
  const profile = await response.json()
  const status = profile.account_status || profile.accountStatus || fallback.account_status || 'active'
  return {
    id: profile.id,
    username: profile.username || fallback.username,
    email: profile.email || fallback.email,
    token: accessToken,
    role: profile.role === 'admin' ? 'admin' : 'user',
    account_status: status === 'suspended' || status === 'banned' ? status : 'active',
    accountStatus: status === 'suspended' || status === 'banned' ? status : 'active',
    skill_level: profile.skill_level || fallback.skill_level,
    user_context: profile.user_context || fallback.user_context,
    github_username: profile.github_username || fallback.github_username,
    avatar_url: profile.avatar_url || fallback.avatar_url,
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  // Drop any session whose token has already expired before trusting storage.
  user: (clearExpiredSession(), loadUser()),
  token: loadToken(),
  oauthError: null,

  updateUser: (partial: Partial<User>) => {
    const current = get().user
    if (!current) return
    const updated: User = { ...current, ...partial }
    persistSession(updated, get().token, readTokenExpiresAt())
    set({ user: updated })
  },

  setOAuthError: (message: string | null) => set({ oauthError: message }),

  login: async (email, password, rememberMe = false) => {
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim().toLowerCase(), password, remember_me: rememberMe }),
    })
    if (!res.ok) throw new Error(extractErrorMessage(await res.json().catch(() => null), 'Invalid email or password'))
    const data = await res.json()
    const { access_token } = data
    // Server-provided expiry wins; otherwise estimate from the chosen mode.
    const expiresAtMs = data.expires_at
      ? new Date(data.expires_at).getTime()
      : Date.now() + (rememberMe ? 24 : 2) * 60 * 60 * 1000
    let user: User
    if (data.user) {
      const p = data.user
      const status = p.account_status || p.accountStatus || 'active'
      user = {
        id: p.id,
        username: p.username || email.split('@')[0] || 'contributor',
        email: p.email || email,
        token: access_token,
        role: p.role === 'admin' ? 'admin' : 'user',
        account_status: status === 'suspended' || status === 'banned' ? status : 'active',
        accountStatus: status === 'suspended' || status === 'banned' ? status : 'active',
        skill_level: p.skill_level || undefined,
        user_context: p.user_context || undefined,
        github_username: p.github_username || undefined,
        avatar_url: p.avatar_url || undefined,
      }
    } else {
      const fallback: User = {
        username: email.split('@')[0] || 'contributor',
        email,
        token: access_token,
        role: 'user',
        account_status: 'active',
        accountStatus: 'active',
      }
      user = await fetchProfile(access_token, fallback)
    }
    persistSession(user, access_token, expiresAtMs)
    set({ user, token: access_token })
    return user
  },

  refreshCurrentUser: async () => {
    if (isSessionExpired()) {
      persistSession(null, null)
      set({ user: null, token: null })
      return null
    }
    const token = loadToken()
    if (!token) {
      set({ user: null, token: null })
      return null
    }

    try {
      const res = await fetch('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        persistSession(null, null)
        set({ user: null, token: null })
        return null
      }

      const profile = await res.json()
      const status = profile.account_status || profile.accountStatus || 'active'
      const user: User = {
        id: profile.id,
        username: profile.username,
        email: profile.email,
        role: profile.role === 'admin' ? 'admin' : 'user',
        account_status: status === 'suspended' || status === 'banned' ? status : 'active',
        accountStatus: status === 'suspended' || status === 'banned' ? status : 'active',
        skill_level: profile.skill_level || undefined,
        user_context: profile.user_context || undefined,
        github_username: profile.github_username || undefined,
        avatar_url: profile.avatar_url || undefined,
        token,
      }
      persistSession(user, token)
      set({ user, token })
      return user
    } catch {
      return loadUser()
    }
  },

  requestSignup: async (username, email, password, confirmPassword) => {
    const res = await fetch('/api/v1/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.trim() || undefined,
        email: email.trim().toLowerCase(),
        password,
        confirm_password: confirmPassword,
      }),
    })
    if (!res.ok) throw new Error(extractErrorMessage(await res.json().catch(() => null), 'Could not initiate registration'))
    return await res.json()
  },

  verifySignupOtp: async (email, otp, username) => {
    const res = await fetch('/api/v1/auth/verify-signup-otp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim().toLowerCase(), otp: otp.trim() }),
    })
    if (!res.ok) throw new Error(extractErrorMessage(await res.json().catch(() => null), 'Invalid or expired verification code'))
    const { access_token } = await res.json()
    const fallback: User = {
      username: username?.trim() || email.split('@')[0] || 'contributor',
      email: email.trim().toLowerCase(),
      token: access_token,
      role: 'user',
      account_status: 'active',
      accountStatus: 'active',
    }
    const user = await fetchProfile(access_token, fallback)
    persistSession(user, access_token, Date.now() + 2 * 60 * 60 * 1000)
    set({ user, token: access_token })
    return user
  },

  requestPasswordReset: async (email) => {
    const res = await fetch('/api/v1/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim().toLowerCase() }),
    })
    if (!res.ok) throw new Error(extractErrorMessage(await res.json().catch(() => null), 'Could not send reset code'))
    return await res.json()
  },

  resetPassword: async (email, otp, newPassword) => {
    const res = await fetch('/api/v1/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: email.trim().toLowerCase(),
        otp: otp.trim(),
        new_password: newPassword,
      }),
    })
    if (!res.ok) throw new Error(extractErrorMessage(await res.json().catch(() => null), 'Could not reset password'))
    return await res.json()
  },

  loginWithToken: async (token: string, partialUser?: Partial<User>) => {
    // Verify the token against /me before trusting it — never keep the user
    // "logged in" on an unverifiable token.
    const user = await fetchProfileStrict(token)
    const merged: User = {
      ...user,
      username: user.username || partialUser?.username || 'developer',
      avatar_url: user.avatar_url || partialUser?.avatar_url,
    }
    // OAuth-issued sessions follow the same 1-day window as remember-me.
    const expiresAtMs = Date.now() + 24 * 60 * 60 * 1000
    persistSession(merged, token, expiresAtMs)
    set({ user: merged, token })
    return merged
  },

  getGitHubOAuthUrl: async (state?: string) => {
    const suffix = state ? `?state=${encodeURIComponent(state)}` : ''
    const res = await fetch(`/api/v1/auth/github/url${suffix}`)
    if (!res.ok) {
      return { configured: false, url: null, has_pat: false }
    }
    return await res.json()
  },

  loginWithConnectedGitHub: async () => {
    const res = await fetch('/api/v1/auth/github/pat-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => null)
      throw new Error(extractErrorMessage(err, 'Failed to sign in via connected GitHub account'))
    }
    const { access_token } = await res.json()
    const fallback: User = {
      username: 'developer',
      email: '',
      token: access_token,
      role: 'user',
      account_status: 'active',
      accountStatus: 'active',
    }
    const user = await fetchProfile(access_token, fallback)
    persistSession(user, access_token, Date.now() + 24 * 60 * 60 * 1000)
    set({ user, token: access_token })
    return user
  },

  logout: () => {
    persistSession(null, null)
    set({ user: null, token: null })
  },
}))
