import { useMemo } from 'react'
import { api } from '../api/client'
import type { ApiError } from '../api/client'
import type { Lang, LanguageInfo, LanguageMode, LanguagesResponse } from '../types'
import { useAsync } from './hooks'
import { LANG_META, type LangMeta } from './languages'

export interface LangOption extends LangMeta {
  /** switched on at the server (DISABLED_LANGUAGES / Settings). True until the server says otherwise. */
  enabled: boolean
  /** the server's details for this language; missing while loading or if the server could not be reached */
  info?: LanguageInfo
}

export interface LanguagesState {
  options: LangOption[]
  enabledKeys: Lang[]
  modes: LanguageMode[]
  data: LanguagesResponse | null
  loading: boolean
  error: ApiError | null
  reload: () => void
}

/** The language registry from the server joined to the names the screens already know, so the selector still lists every language if the request fails. */
export function useLanguages(): LanguagesState {
  const q = useAsync(() => api.languages(), [])
  return useMemo(() => {
    const rows = Array.isArray(q.data?.languages) ? q.data.languages : []   // a malformed reply must not blank the whole screen
    const byKey = new Map(rows.map((l) => [l.key, l]))
    const options = LANG_META.map<LangOption>((m) => {
      const info = byKey.get(m.key)
      return { ...m, enabled: info ? info.enabled : true, info }
    })
    const modes: LanguageMode[] = Array.isArray(q.data?.modes) ? q.data.modes : [
      { key: 'auto', name: 'Auto-detect', available: false, reason: 'Checking what this server supports.' },
    ]
    return { options, enabledKeys: options.filter((o) => o.enabled).map((o) => o.key), modes, data: q.data, loading: q.loading, error: q.error, reload: q.reload }
  }, [q.data, q.loading, q.error, q.reload])
}

/** The first language that is switched on, for when a saved choice has since been switched off. English can never be switched off. */
export const firstEnabled = (options: LangOption[]): Lang => options.find((o) => o.enabled)?.key ?? 'en'
