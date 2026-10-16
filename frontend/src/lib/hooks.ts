import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { DEFAULT_LABELS, type LabelDef } from './doc'
import { getCard, readSettings, type CardDoc } from './store'

export interface LabelsCtx { labels: LabelDef[]; reload: () => void }
export const LabelsContext = createContext<LabelsCtx>({ labels: DEFAULT_LABELS, reload: () => {} })
export const useLabels = () => useContext(LabelsContext)

export function useLabelsLoader(): LabelsCtx {
  const [labels, setLabels] = useState<LabelDef[]>(DEFAULT_LABELS)
  const reload = useCallback(() => { readSettings().then((r) => setLabels(r.settings.labels)).catch(() => {}) }, [])
  useEffect(reload, [reload])
  return { labels, reload }
}

/** Load a card from git; until the spaCy Action has processed this exact file version, re-check:
 *  6s, then backing off to once a minute (the Action usually takes about one), for up to 15 minutes. */
export function useCard(n: number) {
  const [card, setCard] = useState<CardDoc | null>(null)
  const [error, setError] = useState<string | null>(null)
  const reload = useCallback(() => getCard(n).then(setCard).catch((e) => setError(e.message)), [n])
  useEffect(() => { setCard(null); setError(null); reload() }, [reload])
  const waiting = card !== null && !card.processed && card.state === 'open'
  useEffect(() => {
    if (!waiting) return
    const started = Date.now()
    let delay = 6_000
    let t: ReturnType<typeof setTimeout>
    const tick = () => {
      if (Date.now() - started > 15 * 60_000) return
      reload()
      delay = Math.min(delay * 1.5, 60_000)
      t = setTimeout(tick, delay)
    }
    t = setTimeout(tick, delay)
    return () => clearTimeout(t)
  }, [waiting, reload])
  return { card, setCard, reload, error }
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}
