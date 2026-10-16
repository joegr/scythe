import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import CardView from '../components/CardView'
import { listCards, NSDA_TOPICS, repoLabels, type CardDoc } from '../lib/store'
import { topicLabel } from '../lib/topic'

/** Topics and files are just issue labels (topic:…, file:…, block:…). */
export default function LibraryPage() {
  const [labels, setLabels] = useState<string[]>([])
  const [openFile, setOpenFile] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { repoLabels().then(setLabels).catch((e) => setError(e.message)) }, [])

  const topics = labels.filter((l) => l.startsWith('topic:')).map((l) => l.slice(6))
  const files = labels.filter((l) => l.startsWith('file:')).map((l) => l.slice(5))

  return (
    <div className="stack">
      {error && <p className="error">{error}</p>}
      <section className="gap">
        <h1>Topics</h1>
        {topics.length === 0 && <p>No cards filed under a topic yet.</p>}
        <ul className="list">
          {topics.map((slug) => {
            const t = NSDA_TOPICS.find((x) => x.slug === slug)
            return <li key={slug}><Link to={`/search?topic=${slug}`}>{t ? t.resolution : slug}</Link>{t && <><br />{topicLabel(t)}</>}</li>
          })}
        </ul>
      </section>
      <section className="gap">
        <h1>Files</h1>
        {files.length === 0 && <p>File a card from its page to start a file.</p>}
        <ul className="list">
          {files.map((f) => (
            <li key={f}>
              <button className="link" onClick={() => setOpenFile(openFile === f ? null : f)}>{f}</button>
              {openFile === f && <FileCards file={f} />}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

function FileCards({ file }: { file: string }) {
  const [cards, setCards] = useState<CardDoc[] | null>(null)
  useEffect(() => { listCards({ labels: [`file:${file}`] }).then(setCards).catch(() => setCards([])) }, [file])
  const blocks = useMemo(() => {
    const m = new Map<string, CardDoc[]>()
    for (const c of cards ?? []) m.set(c.block ?? '', [...(m.get(c.block ?? '') ?? []), c])
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [cards])
  if (!cards) return null
  return (
    <div className="stack" style={{ marginTop: '1.5rem' }}>
      <Link to={`/print/file/${encodeURIComponent(file)}`}>print this file</Link>
      {blocks.map(([block, cs]) => (
        <section key={block} className="stack">
          <h2>{block}</h2>
          {cs.map((c) => <CardView key={c.number} card={c} mode="read" />)}
        </section>
      ))}
    </div>
  )
}
