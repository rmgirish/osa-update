import { lazy, Suspense, useEffect, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/lib/auth-store'

// Route-level code splitting: each persona (guest / member / admin) only
// downloads the bundle for the page it actually renders.
const HomePage = lazy(() => import('@/page/HomePage').then((m) => ({ default: m.HomePage })))
const DashboardPage = lazy(() => import('@/page/DashboardPage'))
const AdminPage = lazy(() => import('@/page/AdminPage'))

function PageFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center" role="status" aria-label="Loading page">
      <div className="h-10 w-10 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
    </div>
  )
}

export default function App() {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 5 * 60 * 1000, retry: (failureCount, error) => { if (error instanceof Error && error.message.toLowerCase().includes('rate limit')) return false; return failureCount < 1 } } } }))
  const user = useAuthStore((s) => s.user)
  const oauthError = useAuthStore((s) => s.oauthError)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const oauthToken = params.get('oauth_token') || params.get('token')
    const username = params.get('username') || undefined
    const email = params.get('email') || undefined
    const avatarUrl = params.get('avatar_url') || undefined
    const oauthErrorParam = params.get('oauth_error')
    const oauthState = params.get('state')

    const cleanUrl = () => {
      const url = new URL(window.location.href)
      for (const key of ['oauth_token', 'token', 'username', 'email', 'avatar_url', 'oauth_error', 'state']) {
        url.searchParams.delete(key)
      }
      window.history.replaceState({}, document.title, url.pathname + url.search)
    }

    if (oauthToken) {
      // CSRF check: the state we generated before redirecting must round-trip.
      let savedState: string | null = null
      try {
        savedState = sessionStorage.getItem('osa-oauth-state')
        sessionStorage.removeItem('osa-oauth-state')
      } catch {
        /* storage unavailable */
      }
      if (savedState && oauthState && oauthState !== savedState) {
        useAuthStore
          .getState()
          .setOAuthError('Sign-in could not be verified (invalid OAuth state). Please try again.')
      } else {
        useAuthStore
          .getState()
          .loginWithToken(oauthToken, { username, email, avatar_url: avatarUrl })
          .catch((err: unknown) => {
            useAuthStore.getState().setOAuthError(
              err instanceof Error ? err.message : 'GitHub sign-in failed. Please try again.'
            )
          })
      }
      cleanUrl()
    } else if (oauthErrorParam) {
      useAuthStore.getState().setOAuthError(`GitHub sign-in failed: ${oauthErrorParam}`)
      cleanUrl()
    } else {
      void useAuthStore.getState().refreshCurrentUser()
    }
  }, [])

  const handleLogout = () => {
    useAuthStore.getState().logout()
    window.scrollTo({ top: 0 })
    if (typeof window !== 'undefined' && window.location.pathname.startsWith('/admin')) {
      window.location.assign('/')
    }
  }

  const isAdminRoute = typeof window !== 'undefined' && window.location.pathname.startsWith('/admin')

  return (
    <QueryClientProvider client={queryClient}>
      {oauthError && (
        <div
          role="alert"
          className="fixed inset-x-0 top-0 z-[60] flex items-center justify-center gap-3 border-b border-red-500/30 bg-red-500/10 px-4 py-2 text-xs font-medium text-red-400 backdrop-blur"
        >
          <span className="max-w-xl text-center">{oauthError}</span>
          <button
            type="button"
            onClick={() => useAuthStore.getState().setOAuthError(null)}
            aria-label="Dismiss"
            className="text-red-400/80 hover:text-red-300"
          >
            ×
          </button>
        </div>
      )}
      <Suspense fallback={<PageFallback />}>
        {isAdminRoute ? (
          <AdminPage onLogout={handleLogout} />
        ) : user ? (
          <DashboardPage onLogout={handleLogout} />
        ) : (
          <HomePage />
        )}
      </Suspense>
    </QueryClientProvider>
  )
}
