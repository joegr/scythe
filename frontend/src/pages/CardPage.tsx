import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import CardView from '../components/CardView'
import Divergence from '../components/Divergence'
import History from '../components/History'
import Links from '../components/Links'
import Reader from '../components/Reader'
import { snapChars, type SpanRec } from '../lib/doc'
import { useCard, useLabels } from '../lib/hooks'
import { useSignedIn } from '../lib/session'
import { archiveCard, DivergedSave, force, ops, rebase, save, spanKey, type Divergence as D, type Op } from '../lib/store'
import { topicLabel, useTopic } from '../lib/topic'

/** Select text, press a label's key. Every change is a git commit to cards/<n>.md. */
export default function CardPage() {
  const n = Number(useParams().id)
  const navigate = useNavigate()
  const signedIn = useSignedIn()
  const { card, setCard, reload, error } = useCard(n)
  const { labels } = useLabels()
  const { choose } = useTopic()
  const [selection, setSelection] = useState<[number, number] | null>(null)
  const [active, setActive] = useState<SpanRec | null>(null)
  const [entities, setEntities] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [diverged, setDiverged] = useState<D | null>(null)
  const [reader, setReader] = useState(false)
  const [place, setPlace] = useState({ file: '', block: '' })

  useEffect(() => { if (card) setPlace({ file: card.file ?? '', block: card.block ?? '' }) }, [card?.file, card?.block]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = useCallback(async (fn: () => ReturnType<typeof save>) => {
    setSaving(true); setMessage(null)
    try { setCard(await fn()); setDiverged(null) } catch (e) {
      if (e instanceof DivergedSave) setDiverged(e.d)
      else setMessage((e as Error).message)
    } finally { setSaving(false) }
  }, [setCard])

  const commit = useCallback((op: Op) => { if (card) run(() => save(card, op)) }, [card, run])

  const apply = useCallback((name: string) => {
    const label = labels.find((l) => l.name === name)
    if (!selection || !label || !card) return
    window.getSelection()?.removeAllRanges()
    setSelection(null)
    try { commit(ops.addSpan(card.meta.text, label, selection[0], selection[1])) } catch (e) { setMessage((e as Error).message) }
  }, [selection, labels, card, commit])

  const editable = signedIn && card?.state === 'open' && !saving && !diverged

  useEffect(() => {
    if (!editable || !card) return
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t?.closest?.('input, textarea, select, dialog') || e.metaKey || e.ctrlKey || e.altKey) return
      const label = labels.find((l) => l.hotkey && l.hotkey === e.key)
      if (label && selection) { e.preventDefault(); apply(label.name); return }
      if ((e.key === 'Backspace' || e.key === 'Delete') && active) { e.preventDefault(); setActive(null); commit(ops.removeSpan(card.meta.text, active)); return }
      if (e.key === 'Escape') { setActive(null); setSelection(null); window.getSelection()?.removeAllRanges() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [editable, labels, selection, active, apply, card, commit])

  if (error) return <p className="error">{error}</p>
  if (!card) return null

  const pick = (spans: SpanRec[]) => {
    if (window.getSelection()?.isCollapsed === false) return
    const sorted = spans.filter((s) => s.key !== 'ents').sort((a, b) => (a.end_char - a.start_char) - (b.end_char - b.start_char))
    if (!sorted.length) return
    const i = active ? sorted.findIndex((s) => spanKey(s) === spanKey(active)) : -1
    setActive(sorted[(i + 1) % sorted.length])
  }

  return (
    <div className="stack">
      {signedIn && card.state === 'open' && (
        <div className="row no-print">
          {labels.map((l) => (
            <button key={`${l.key}-${l.name}`} className="link" disabled={!selection || !editable} onMouseDown={(e) => e.preventDefault()} onClick={() => apply(l.name)}>
              {l.hotkey && <kbd>{l.hotkey}</kbd>} {l.name}
            </button>
          ))}
          <span className="spacer">{saving ? 'committing…' : card.sha ? `at ${card.sha.slice(0, 7)}` : ''}</span>
        </div>
      )}

      <CardView card={card} link={false} editable={!!editable} showEntities={entities}
        activeKey={active ? spanKey(active) : null} mark={selection} onSpanClick={pick}
        onSelect={(r) => { const s = r ? snapChars(card.meta.text, r[0], r[1]) : null; setSelection(s); if (s) setActive(null) }}
        onChange={(patch) => {
          if (patch.title !== undefined && patch.title.trim()) commit(ops.set('title', patch.title.trim()))
          if (patch.cite !== undefined) commit(ops.set('cite', patch.cite))
        }}
        meta={editable && <button className="link" onClick={() => commit(ops.approve(!card.approved))}>{card.approved ? 'unapprove' : 'approve'}</button>} />

      <p className="no-print">
        {message ? message : active ? (
          <>{active.label}: “{card.meta.text.slice(active.start_char, active.end_char).slice(0, 60)}”. <kbd>⌫</kbd> removes it, <kbd>Esc</kbd> clears.</>
        ) : selection ? 'Snapped to whole words; spaCy refines it to tokens on GitHub. Press a label key.'
          : signedIn ? 'Select text, then press a label key. Each change is a commit.' : 'Sign in to edit.'}
      </p>
      <div className="row no-print">
        <button className={`link ${entities ? 'on' : ''}`} onClick={() => setEntities(!entities)}>entities</button>
        <span>{card.processed ? 'spaCy is up to date with this version' : 'spaCy is processing this version'}</span>
      </div>

      <Links card={card} commit={commit} canEdit={!!editable} />

      <section className="gap">
        <h3>Filed under</h3>
        <p>
          {editable
            ? <button className="link" onClick={async () => {
                const t = await choose()
                commit(ops.topic({ slug: t.slug, event: t.event, season: t.season, period: t.period, resolution: t.resolution }))
              }}>{card.meta.topic ? `${topicLabel(card.meta.topic)}: ${card.meta.topic.resolution}` : 'choose a topic'}</button>
            : card.meta.topic ? `${topicLabel(card.meta.topic)}: ${card.meta.topic.resolution}` : 'no topic'}
        </p>
        {editable && (
          <div className="row">
            <input className="field" style={{ flex: 1 }} placeholder="File" value={place.file} onChange={(e) => setPlace({ ...place, file: e.target.value })} />
            <input className="field" style={{ flex: 1 }} placeholder="Block" value={place.block} onChange={(e) => setPlace({ ...place, block: e.target.value })} />
            <button className="link" disabled={place.file === (card.file ?? '') && place.block === (card.block ?? '')}
              onClick={() => commit(ops.place(place.file.trim() || null, place.block.trim() || null))}>file it</button>
          </div>
        )}
      </section>

      <History path={`cards/${card.number}.md`} refreshKey={card.sha} />

      <section className="row">
        {card.meta.source && <button className="link" onClick={() => setReader(true)}>source #{card.meta.source}</button>}
        <Link to={`/print/${card.number}`}>print</Link>
        <a href={card.url} target="_blank" rel="noreferrer">issue #{card.number}</a>
        {editable && <button className="link spacer" onClick={async () => { await archiveCard(card); navigate('/') }}>archive</button>}
      </section>

      {diverged && card.record && (
        <Divergence d={diverged} base={card.record} busy={saving}
          onRebase={() => run(() => rebase(card.number, diverged))}
          onTheirs={() => { setDiverged(null); reload() }}
          onForce={() => run(() => force(card.number, diverged))} />
      )}

      <Reader open={reader} onClose={() => setReader(false)} sourceNumber={card.meta.source}
        onCut={(c) => { setReader(false); navigate(`/cards/${c}`) }} />
    </div>
  )
}
