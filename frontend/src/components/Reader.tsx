import { useEffect, useMemo, useRef, useState } from 'react'
import { htmlToText, sanitizeText } from '../lib/local'
import { selectionRange } from '../lib/render'
import { createCard, createSource, defaultCite, fetchSource, getSource, listSources, locate, type SourceDoc } from '../lib/store'
import { topicLabel, useTopic } from '../lib/topic'

interface Props { open: boolean; onClose: () => void; onCut: (card: number) => void; sourceNumber?: number | null }

/** Reader: a source as clean text. Select a passage (or paste one to find it) and cut it verbatim. */
export default function Reader({ open, onClose, onCut, sourceNumber }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const textRef = useRef<HTMLDivElement>(null)
  const { current: topic, require, choose } = useTopic()
  const [mode, setMode] = useState<'paste' | 'url'>('paste')
  const [url, setUrl] = useState('')
  const [paste, setPaste] = useState({ text: '', title: '', url: '', authors: '', publisher: '', published: '' })
  const [source, setSource] = useState<SourceDoc | null>(null)
  const [recent, setRecent] = useState<{ number: number; title: string }[]>([])
  const [range, setRange] = useState<[number, number] | null>(null)
  const [passage, setPassage] = useState('')
  const [form, setForm] = useState({ title: '', cite: '', file: '', block: '' })
  const [busy, setBusy] = useState(false)
  const [waited, setWaited] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
    if (!open) return
    setError(null)
    setRange(null)
    if (sourceNumber) run(async () => load(await getSource(sourceNumber)))
    else { setSource(null); listSources().then(setRecent).catch(() => {}) }
  }, [open, sourceNumber])

  useEffect(() => { textRef.current?.querySelector('.reader-sel')?.scrollIntoView({ block: 'center' }) }, [range])

  function load(s: SourceDoc) {
    setSource(s)
    setForm((f) => ({ ...f, cite: s.head.cite || defaultCite(s.head) }))
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(null)
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const openSource = () => run(async () => {
    if (mode === 'url') {
      setWaited(0)
      try { load(await getSource(await fetchSource(url.trim(), setWaited))) } finally { setWaited(null) }
      return
    }
    const isHtml = /^\s*</.test(paste.text)
    const parsed = isHtml ? htmlToText(paste.text) : { title: '', text: sanitizeText(paste.text) }
    const authors = paste.authors.split(/;|,/).map((a) => a.trim()).filter(Boolean)
    const meta = { title: paste.title || parsed.title || parsed.text.slice(0, 80), url: paste.url || null, publisher: paste.publisher,
      published: paste.published || null, authors }
    load(await getSource(await createSource({ ...meta, text: parsed.text, cite: defaultCite(meta) })))
  })

  const find = () => {
    if (!source) return
    const r = locate(source.text, passage)
    if (r) setRange(r); else setError('That passage isn’t in this source.')
  }

  const cut = () => run(async () => {
    if (!source || !range) return
    const t = await require()
    let [a, b] = range
    while (a < b && /\s/.test(source.text[a])) a++
    while (b > a && /\s/.test(source.text[b - 1])) b--
    const card = await createCard({ text: source.text.slice(a, b), title: form.title, cite: form.cite, url: source.head.url ?? '',
      source: source.number, topic: t, file: form.file || null, block: form.block || null })
    setForm((f) => ({ ...f, title: '' })); setPassage(''); setRange(null)
    onCut(card)
  })

  const paragraphs = useMemo(() => {
    if (!source) return []
    let pos = 0
    return source.text.split('\n\n').map((text) => { const p = { start: pos, text }; pos += text.length + 2; return p })
  }, [source])

  return (
    <dialog ref={ref} className="sheet" onCancel={onClose}>
      <div className="sheet-inner stack">
        <div className="row">
          <h1>{source ? source.title || 'Untitled source' : 'Open a source'}</h1>
          <button className="link spacer" onClick={onClose}>close</button>
        </div>
        {error && <p className="error">{error}</p>}

        {!source ? (
          <div className="stack">
            <div className="gap">
              <div className="row">
                <button className={`link ${mode === 'paste' ? 'on' : ''}`} onClick={() => setMode('paste')}>paste text or page HTML</button>
                <button className={`link ${mode === 'url' ? 'on' : ''}`} onClick={() => setMode('url')}>fetch a link</button>
              </div>
              {mode === 'url' ? (
                <input className="field" type="url" placeholder="https://" value={url} onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && url.trim() && openSource()} />
              ) : (
                <>
                  <textarea className="field" rows={8} placeholder="Article text, or the page's HTML" value={paste.text} onChange={(e) => setPaste({ ...paste, text: e.target.value })} />
                  <input className="field" placeholder="Title" value={paste.title} onChange={(e) => setPaste({ ...paste, title: e.target.value })} />
                  <input className="field" placeholder="Link" value={paste.url} onChange={(e) => setPaste({ ...paste, url: e.target.value })} />
                  <input className="field" placeholder="Authors, separated by commas" value={paste.authors} onChange={(e) => setPaste({ ...paste, authors: e.target.value })} />
                  <div className="row">
                    <input className="field" style={{ flex: 2 }} placeholder="Publication" value={paste.publisher} onChange={(e) => setPaste({ ...paste, publisher: e.target.value })} />
                    <input className="field" style={{ flex: 1 }} placeholder="Date, YYYY-MM-DD" value={paste.published} onChange={(e) => setPaste({ ...paste, published: e.target.value })} />
                  </div>
                </>
              )}
              <p>{mode === 'url'
                ? 'A GitHub Action opens the page in headless Chromium, strips it to clean text and commits it. About a minute; paywalled pages fail.'
                : 'The source becomes a public issue, and its full text a file in the repo.'}</p>
              <button className="action" disabled={busy || (mode === 'url' ? !url.trim() : !paste.text.trim())} onClick={openSource}>
                {waited !== null ? `Fetching on GitHub… ${waited}s` : busy ? 'Saving…' : 'Read'}
              </button>
            </div>
            {recent.length > 0 && (
              <ul className="list">
                {recent.slice(0, 8).map((s) => (
                  <li key={s.number}><button className="link" onClick={() => run(async () => load(await getSource(s.number)))}>{s.title}</button> #{s.number}</li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <>
            <p>
              {[source.head.authors.join(', '), source.head.publisher, source.head.published].filter(Boolean).join(' · ')}
              {source.head.url && <> · <a href={source.head.url} target="_blank" rel="noreferrer">original</a></>}
              {' · '}<a href={source.url} target="_blank" rel="noreferrer">#{source.number}</a>
            </p>
            <div ref={textRef} className="reader-text" onMouseUp={(e) => { const r = selectionRange(e.currentTarget); if (r) setRange(r) }}>
              {paragraphs.map((p) => <Para key={p.start} {...p} range={range} />)}
            </div>
            <div className="cut-bar">
              <div className="inner gap">
                <div className="row">
                  <input className="field" style={{ flex: 1, minWidth: '12rem' }} placeholder="Paste a copied passage to find it" value={passage}
                    onChange={(e) => setPassage(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && passage.trim() && find()} />
                  <button className="link" disabled={!passage.trim()} onClick={find}>find</button>
                </div>
                <input className="field" style={{ fontWeight: 600 }} placeholder="Tag" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
                <input className="field" placeholder="Cite" value={form.cite} onChange={(e) => setForm({ ...form, cite: e.target.value })} />
                <div className="row">
                  <button className="link" onClick={() => choose()} title={topic?.resolution}>{topic ? topicLabel(topic) : 'choose a topic'}</button>
                  <input className="field" style={{ flex: 1, minWidth: '6rem' }} placeholder="File" value={form.file} onChange={(e) => setForm({ ...form, file: e.target.value })} />
                  <input className="field" style={{ flex: 1, minWidth: '6rem' }} placeholder="Block" value={form.block} onChange={(e) => setForm({ ...form, block: e.target.value })} />
                  <span>{range ? `${(range[1] - range[0]).toLocaleString()} characters` : 'select text above'}</span>
                  <button className="action" disabled={!range || busy || !form.title.trim()} onClick={cut}>Cut</button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </dialog>
  )
}

function Para({ start, text, range }: { start: number; text: string; range: [number, number] | null }) {
  const end = start + text.length
  if (!range || range[1] <= start || range[0] >= end) return <p><span data-start={start}>{text}</span></p>
  const a = Math.max(start, range[0]) - start
  const b = Math.min(end, range[1]) - start
  return (
    <p>
      {a > 0 && <span data-start={start}>{text.slice(0, a)}</span>}
      <span data-start={start + a} className="reader-sel">{text.slice(a, b)}</span>
      {b < text.length && <span data-start={start + b}>{text.slice(b)}</span>}
    </p>
  )
}
