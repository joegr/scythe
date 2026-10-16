import { useEffect, useRef } from 'react'
import type { CardFile, SpanRec } from '../lib/doc'
import type { Divergence as D } from '../lib/store'

const show = (f: CardFile, s: SpanRec) => `${s.label} “${f.text.slice(s.start_char, s.end_char).slice(0, 50)}”`
const keyOf = (s: SpanRec) => `${s.key}|${s.label}|${s.start_char}|${s.end_char}`

/** What changed on each side, git style: theirs (on main) vs mine (unsaved). */
function changes(base: CardFile, side: CardFile): string[] {
  const out: string[] = []
  const was = new Set(base.spans.map(keyOf))
  const now = new Set(side.spans.map(keyOf))
  for (const s of side.spans) if (!was.has(keyOf(s))) out.push(`+ ${show(side, s)}`)
  for (const s of base.spans) if (!now.has(keyOf(s))) out.push(`- ${show(base, s)}`)
  for (const k of ['title', 'cite', 'approved', 'file', 'block'] as const) if (JSON.stringify(base[k]) !== JSON.stringify(side[k])) out.push(`~ ${k}: ${JSON.stringify(side[k])}`)
  if (base.topic?.slug !== side.topic?.slug) out.push(`~ topic: ${side.topic?.slug}`)
  const links = (f: CardFile) => new Set(f.links.map((l) => `${l.rel} #${l.to}`))
  for (const l of links(side)) if (!links(base).has(l)) out.push(`+ ${l}`)
  for (const l of links(base)) if (!links(side).has(l)) out.push(`- ${l}`)
  return out
}

interface Props { d: D; base: CardFile; onRebase: () => void; onTheirs: () => void; onForce: () => void; busy: boolean }

export default function Divergence({ d, base, onRebase, onTheirs, onForce, busy }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { if (!ref.current?.open) ref.current?.showModal() }, [])
  const theirs = changes(base, d.theirs)
  const mine = changes(base, d.mine)
  const when = d.commit.date ? new Date(d.commit.date).toLocaleString() : ''
  return (
    <dialog ref={ref} className="sheet" onCancel={(e) => e.preventDefault()}>
      <div className="sheet-inner stack">
        <section className="gap">
          <h1>Your save and main have diverged</h1>
          <p>
            {d.commit.author ?? 'Someone'} committed to this card after you opened it
            {d.commit.message ? <>: <strong>{d.commit.message}</strong></> : null}{when && ` (${when})`}.
          </p>
        </section>
        <section className="gap">
          <h3>Theirs, on main</h3>
          <pre className="md">{theirs.length ? theirs.join('\n') : '(no visible change)'}</pre>
          <h3>Yours, not saved</h3>
          <pre className="md">{mine.join('\n') || d.op.message}</pre>
        </section>
        <section className="gap">
          <div className="row">
            <button className="action" disabled={busy} onClick={onRebase}>Rebase mine onto theirs</button>
            <button className="link" disabled={busy} onClick={onTheirs}>Keep theirs, drop mine</button>
            <button className="link" disabled={busy} onClick={onForce}>Force mine</button>
          </div>
          <p>Rebase replays “{d.op.message}” on their version, the usual choice. Force replaces their version with yours; theirs stays in the history.</p>
        </section>
      </div>
    </dialog>
  )
}
