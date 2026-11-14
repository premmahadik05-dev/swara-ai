import { useState } from 'react'
import type { CsvFile } from '../api/client'
import { useToast } from './Toast'
import { Button } from './ui'

/** Save a downloaded CSV through the browser's own download. */
export function saveFile(file: CsvFile) {
  const url = URL.createObjectURL(file.blob)
  const a = document.createElement('a')
  a.href = url
  a.download = file.filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

/** "Export CSV" for a list screen. The caller passes a function that fetches the file for the filters currently on screen. */
export function ExportButton({ fetchFile, what, label = 'Export CSV' }: { fetchFile: () => Promise<CsvFile>; what: string; label?: string }) {
  const { toast } = useToast()
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true)
    try {
      const file = await fetchFile()
      saveFile(file)
      toast(file.truncated ? `Saved ${file.filename}. It holds the first rows only; narrow the filters to export the rest.` : `Saved ${file.filename}.`, file.truncated ? 'info' : 'ok')
    } catch (e) {
      toast((e as Error).message || `Could not export ${what}.`, 'bad')
    } finally { setBusy(false) }
  }
  return <Button variant="secondary" icon="download" onClick={() => void run()} loading={busy} title={`Download ${what} as a spreadsheet file (CSV) with the filters on this screen`}>{label}</Button>
}
