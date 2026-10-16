import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'
import TopicPicker from '../components/TopicPicker'
import type { TopicRef } from './doc'
import type { Topic } from './store'

interface TopicCtx {
  current: Topic | null
  /** The current topic, or prompt for one (resolves once picked). */
  require: () => Promise<Topic>
  /** Prompt even if one is set. */
  choose: () => Promise<Topic>
}

const KEY = 'scythe.topic'
const Ctx = createContext<TopicCtx>({ current: null, require: () => Promise.reject(), choose: () => Promise.reject() })
export const useTopic = () => useContext(Ctx)

export function topicLabel(t: Pick<TopicRef, 'event' | 'season' | 'period'>): string {
  const event = ({ policy: 'Policy', ld: 'LD', pf: 'PF', bq: 'BQ', custom: 'Custom' } as Record<string, string>)[t.event] ?? t.event
  return [event, t.season, t.period].filter(Boolean).join(' · ')
}

function load(): Topic | null {
  try { return JSON.parse(localStorage.getItem(KEY) ?? 'null') } catch { return null }
}

export function TopicProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<Topic | null>(load)
  const [open, setOpen] = useState(false)
  const waiters = useRef<((t: Topic) => void)[]>([])

  const choose = useCallback(() => new Promise<Topic>((resolve) => { waiters.current.push(resolve); setOpen(true) }), [])
  const require = useCallback(() => (current ? Promise.resolve(current) : choose()), [current, choose])

  const pick = (t: Topic) => {
    try { localStorage.setItem(KEY, JSON.stringify(t)) } catch { /* storage blocked */ }
    setCurrent(t)
    setOpen(false)
    waiters.current.splice(0).forEach((w) => w(t))
  }

  return (
    <Ctx.Provider value={{ current, require, choose }}>
      {children}
      <TopicPicker open={open} onPick={pick} onClose={() => { setOpen(false); waiters.current = [] }} />
    </Ctx.Provider>
  )
}
