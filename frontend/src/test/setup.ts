import '@testing-library/jest-dom/vitest'

// jsdom has no object-URL support; the pages create them for audio previews.
if (!URL.createObjectURL) URL.createObjectURL = () => 'blob:test'
if (!URL.revokeObjectURL) URL.revokeObjectURL = () => undefined
if (!Element.prototype.scrollTo) Element.prototype.scrollTo = () => undefined

import { afterEach } from 'vitest'
import { clearApiCache } from '../api/client'
// The client de-dupes and briefly caches GETs. Tests must not see each other's responses.
afterEach(() => { clearApiCache() })
