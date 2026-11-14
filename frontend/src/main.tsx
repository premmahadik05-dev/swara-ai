import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@fontsource-variable/geist/wght.css'
import '@fontsource-variable/geist-mono/wght.css'
import '@fontsource-variable/newsreader/opsz.css'
import '@fontsource-variable/noto-sans-gujarati/wght.css'
import '@fontsource-variable/noto-sans-devanagari/wght.css'
import '@fontsource-variable/noto-sans-bengali/wght.css'
import '@fontsource-variable/noto-sans-tamil/wght.css'
import '@fontsource-variable/noto-sans-telugu/wght.css'
import '@fontsource-variable/noto-sans-kannada/wght.css'
import '@fontsource-variable/noto-sans-malayalam/wght.css'
import '@fontsource-variable/noto-sans-gurmukhi/wght.css'
import './styles/tokens.css'
import './styles/ui.css'
import './styles/app.css'
import './styles/auth.css'
import './styles/landing.css'
import App from './App'
import { migrateLegacyStorage } from './lib/legacy'

migrateLegacyStorage()   // carry over settings saved under the previous product name, before anything reads them

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
