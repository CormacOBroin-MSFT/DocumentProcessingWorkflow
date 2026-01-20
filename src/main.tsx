import { createRoot } from 'react-dom/client'
import { ErrorBoundary } from "react-error-boundary";
import { Toaster } from 'sonner'

import App from './App.tsx'
import { ErrorFallback } from './ErrorFallback.tsx'
import { QueryProvider } from './providers/QueryProvider.tsx'

import "./main.css"

createRoot(document.getElementById('root')!).render(
  <ErrorBoundary FallbackComponent={ErrorFallback}>
    <QueryProvider>
      <App />
      <Toaster position="bottom-right" richColors />
    </QueryProvider>
  </ErrorBoundary>
)
