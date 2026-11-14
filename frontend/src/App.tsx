import { lazy, Suspense, useEffect } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import { ErrorBoundary } from './components/ErrorBoundary'
import { Shell } from './components/Shell'
import { ToastProvider } from './components/Toast'
import { SkeletonCard } from './components/ui'
import { AuthProvider, RequireAuth } from './lib/auth'
import { DataScopeProvider } from './lib/scope'
import Landing from './pages/Landing'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const OrderDesk = lazy(() => import('./pages/OrderDesk'))
const Orders = lazy(() => import('./pages/Orders'))
const Payments = lazy(() => import('./pages/Payments'))
const PaymentDetail = lazy(() => import('./pages/PaymentDetail'))
const PaymentAnalytics = lazy(() => import('./pages/PaymentAnalytics'))
const Invoice = lazy(() => import('./pages/Invoice'))
const Customers = lazy(() => import('./pages/Customers'))
const Inventory = lazy(() => import('./pages/Inventory'))
const Catalogue = lazy(() => import('./pages/Catalogue'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Performance = lazy(() => import('./pages/Performance'))
const Diagnostics = lazy(() => import('./pages/Diagnostics'))
const Live = lazy(() => import('./pages/Live'))
const NoiseLab = lazy(() => import('./pages/NoiseLab'))
const Settings = lazy(() => import('./pages/Settings'))
const Account = lazy(() => import('./pages/Account'))
const SignIn = lazy(() => import('./pages/auth/SignIn'))
const SignUp = lazy(() => import('./pages/auth/SignUp'))
const ForgotPassword = lazy(() => import('./pages/auth/ForgotPassword'))
const ResetPassword = lazy(() => import('./pages/auth/ResetPassword'))
const VerifyEmail = lazy(() => import('./pages/auth/VerifyEmail'))
const Terms = lazy(() => import('./pages/Legal').then((m) => ({ default: m.Terms })))
const Privacy = lazy(() => import('./pages/Legal').then((m) => ({ default: m.Privacy })))
const NotFound = lazy(() => import('./pages/NotFound'))

/** Only the public pages belong in a search engine. Everything else (the app, sign-in, account recovery, unknown addresses) says noindex. */
const PUBLIC_PATHS = new Set(['/', '/terms', '/privacy'])
function RouteMeta() {
  const { pathname } = useLocation()
  useEffect(() => {
    let tag = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]')
    if (PUBLIC_PATHS.has(pathname)) { tag?.remove(); return }
    if (!tag) { tag = document.createElement('meta'); tag.name = 'robots'; document.head.appendChild(tag) }
    tag.content = 'noindex, nofollow'
  }, [pathname])
  return null
}

const Fallback = () => <div style={{ padding: 28, maxWidth: 720 }}><SkeletonCard lines={4} height={160} /></div>

export default function App() {
  return (
      <AuthProvider>
        <DataScopeProvider>
          <ToastProvider>
            <ErrorBoundary>
              <RouteMeta />
              <Suspense fallback={<Fallback />}>
                <Routes>
                  <Route path="/" element={<Landing />} />
                  <Route path="/sign-in" element={<SignIn />} />
                  <Route path="/sign-up" element={<SignUp />} />
                  <Route path="/forgot-password" element={<ForgotPassword />} />
                  <Route path="/reset-password" element={<ResetPassword />} />
                  <Route path="/verify-email" element={<VerifyEmail />} />
                  <Route path="/terms" element={<Terms />} />
                  <Route path="/privacy" element={<Privacy />} />
                  <Route element={<RequireAuth />}>
                    <Route element={<Shell />}>
                      <Route path="/dashboard" element={<Dashboard />} />
                      <Route path="/order" element={<OrderDesk />} />
                      <Route path="/orders" element={<Orders />} />
                      <Route path="/payments" element={<Payments />} />
                      <Route path="/payments/:id" element={<PaymentDetail />} />
                      <Route path="/payment-analytics" element={<PaymentAnalytics />} />
                      <Route path="/invoices/:orderId" element={<Invoice />} />
                      <Route path="/customers" element={<Customers />} />
                      <Route path="/inventory" element={<Inventory />} />
                      <Route path="/catalogue" element={<Catalogue />} />
                      <Route path="/analytics" element={<Analytics />} />
                      <Route path="/performance" element={<Performance />} />
                      <Route path="/diagnostics" element={<Diagnostics />} />
                      <Route path="/live" element={<Live />} />
                      <Route path="/noise" element={<NoiseLab />} />
                      <Route path="/settings" element={<Settings />} />
                      <Route path="/account" element={<Account />} />
                    </Route>
                  </Route>
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          </ToastProvider>
        </DataScopeProvider>
      </AuthProvider>
  )
}
