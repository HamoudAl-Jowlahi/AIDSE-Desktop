/**
 * Auth route group layout — no sidebar, no top bar.
 * Redirects to dashboard if already authenticated.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
