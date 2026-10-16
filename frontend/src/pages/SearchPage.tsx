import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import CardView from '../components/CardView'
import { useDebounced } from '../lib/hooks'
import { listCards, NSDA_TOPICS, searchCards, type CardDoc } from '../lib/store'
import { topicLabel } from '../lib/topic'

/** GitHub issue search over card titles, cites, text and metadata. */
export default function SearchPage() {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const topic = params.get('topic')
  const approved = params.get('approved') === '1'
  const archived = params.get('archived') === '1'
  const dq = useDebounced(q, 400)
  const [results, setResults] = useState<CardDoc[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const topicInfo = topic ? NSDA_TOPICS.find((t) => t.slug === topic) : null

  useEffect(() => {
    const labels = [...(topic ? [`topic:${topic}`] : []), ...(approved ? ['approved'] : [])]
    setError(null)
    const run = dq.trim() || archived ? searchCards(dq, labels, archived ? 'closed' : 'open') : listCards({ labels })
    run.then(setResults).catch((e) => setError(e.message))
  }, [dq, topic, approved, archived])

  const toggle = (key: string, on: boolean) => setParams((p) => { if (on) p.set(key, '1'); else p.delete(key); return p })

  return (
    <div className="stack">
      <div className="gap">
        <input className="field" autoFocus placeholder="Search cards on GitHub" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="row">
          <button className={`link ${approved ? 'on' : ''}`} onClick={() => toggle('approved', !approved)}>approved only</button>
          <button className={`link ${archived ? 'on' : ''}`} onClick={() => toggle('archived', !archived)}>archived</button>
          {topic && <span>In {topicInfo ? `${topicLabel(topicInfo)}: ${topicInfo.resolution}` : topic}{' '}
            <button className="link" onClick={() => setParams((p) => { p.delete('topic'); return p })}>clear</button></span>}
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {results && <p>{results.length} cards</p>}
      {results?.map((c) => <CardView key={c.number} card={c} mode="read" />)}
    </div>
  )
}
