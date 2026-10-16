import { useEffect, useMemo, useRef, useState } from 'react'
import { useDebounced } from '../lib/hooks'
import { createTopic, customTopics, NSDA_TOPICS, type Topic } from '../lib/store'
import { topicLabel } from '../lib/topic'

const EVENTS = [['', 'all'], ['policy', 'policy'], ['ld', 'LD'], ['pf', 'PF'], ['bq', 'BQ'], ['custom', 'custom']] as const

/** Every card is filed under a debate topic: NSDA national topics are built in; write your own below. */
export default function TopicPicker({ open, onPick, onClose }: { open: boolean; onPick: (t: Topic) => void; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const search = useRef<HTMLInputElement>(null)
  const [q, setQ] = useState('')
  const [event, setEvent] = useState('')
  const [custom, setCustom] = useState<Topic[]>([])
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const dq = useDebounced(q, 150)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) { d.showModal(); search.current?.focus(); customTopics().then(setCustom).catch(() => {}) }
    if (!open && d.open) d.close()
  }, [open])

  const topics = useMemo(() => {
    const words = dq.toLowerCase().split(/\s+/).filter(Boolean)
    return [...custom, ...NSDA_TOPICS]
      .filter((t) => !event || t.event === event)
      .filter((t) => words.every((w) => `${t.resolution} ${t.season} ${t.period} ${t.slug}`.toLowerCase().includes(w)))
      .slice(0, 80)
  }, [custom, dq, event])

  const create = async () => {
    try { onPick(await createTopic(draft)) } catch (e) { setError((e as Error).message) }
  }

  return (
    <dialog ref={ref} className="sheet" onCancel={onClose}>
      <div className="sheet-inner stack">
        <div className="row">
          <h1>Which topic is this card for?</h1>
          <button className="link spacer" onClick={onClose}>close</button>
        </div>
        <div className="gap">
          <input ref={search} className="field" placeholder="Search resolutions" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="row">
            {EVENTS.map(([value, label]) => (
              <button key={value} className={`link ${event === value ? 'on' : ''}`} onClick={() => setEvent(value)}>{label}</button>
            ))}
          </div>
        </div>
        <ul className="list">
          {topics.map((t) => (
            <li key={t.slug}>
              <button className="link plain" onClick={() => onPick(t)}>{t.resolution}<br />{topicLabel(t)}</button>
            </li>
          ))}
          {topics.length === 0 && <li>No matching topics.</li>}
        </ul>
        <div className="gap">
          <p>Not listed? Write the resolution. It's saved as a topic issue in the repo.</p>
          {error && <p className="error">{error}</p>}
          <input className="field" placeholder="Resolved: …" value={draft} onChange={(e) => setDraft(e.target.value)} />
          <button className="action" disabled={draft.trim().length < 3} onClick={create}>Use this topic</button>
        </div>
      </div>
    </dialog>
  )
}
