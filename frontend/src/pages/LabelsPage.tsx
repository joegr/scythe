import { useState } from 'react'
import type { LabelDef } from '../lib/doc'
import { useLabels } from '../lib/hooks'
import { updateSettings } from '../lib/store'
import { useSignedIn } from '../lib/session'

const STYLES = ['underline', 'highlight', 'emphasis', 'custom']

/** Labels live in scythe.json in the repo, so everyone using it shares them (and git versions them). */
export default function LabelsPage() {
  const { labels, reload } = useLabels()
  const signedIn = useSignedIn()
  const [draft, setDraft] = useState<LabelDef>({ name: '', key: 'sc', style: 'custom', hotkey: '' })
  const [error, setError] = useState<string | null>(null)
  const save = async (next: LabelDef[]) => {
    try { await updateSettings('labels', (s) => ({ ...s, labels: next })); reload() } catch (e) { setError((e as Error).message) }
  }

  return (
    <div className="stack">
      <section className="gap">
        <h1>Labels</h1>
        <p>Each label is a spaCy span group key (sc for card formatting). Custom labels draw as a plain underline.</p>
        {error && <p className="error">{error}</p>}
        <ul className="list">
          {labels.map((l, i) => (
            <li key={`${l.key}-${l.name}`} className="row">
              <span style={{ minWidth: '8rem' }}>{l.name}</span><span>{l.key}</span><span>{l.style}</span>
              <span>{l.hotkey ? <>key <kbd>{l.hotkey}</kbd></> : 'no key'}</span>
              {signedIn && <button className="link spacer" onClick={() => save(labels.filter((_, j) => j !== i))}>remove</button>}
            </li>
          ))}
        </ul>
      </section>
      {signedIn && (
        <section className="row">
          <input className="field" style={{ width: '10rem' }} placeholder="New label" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          <input className="field" style={{ width: '6rem' }} placeholder="spans key" value={draft.key} onChange={(e) => setDraft({ ...draft, key: e.target.value })} />
          <select className="field" style={{ width: '8rem' }} value={draft.style} onChange={(e) => setDraft({ ...draft, style: e.target.value })}>
            {STYLES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <input className="field" style={{ width: '3rem' }} maxLength={1} placeholder="key" value={draft.hotkey ?? ''} onChange={(e) => setDraft({ ...draft, hotkey: e.target.value })} />
          <button className="link" disabled={!draft.name.trim()} onClick={() => { save([...labels, { ...draft, hotkey: draft.hotkey || null }]); setDraft({ ...draft, name: '', hotkey: '' }) }}>add</button>
        </section>
      )}
    </div>
  )
}
