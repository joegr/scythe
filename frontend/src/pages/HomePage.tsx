import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import CardView from '../components/CardView'
import Reader from '../components/Reader'
import { sanitizeText } from '../lib/local'
import { createCard, listCards, type CardDoc } from '../lib/store'
import { topicLabel, useTopic } from '../lib/topic'
import { useSignedIn } from '../lib/session'

export default function HomePage() {
  const navigate = useNavigate()
  const signedIn = useSignedIn()
  const { current, require, choose } = useTopic()
  const [reader, setReader] = useState(false)
  const [clip, setClip] = useState<{ text: string; title: string } | null>(null)
  const [recent, setRecent] = useState<CardDoc[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { listCards({ limit: 15 }).then(setRecent).catch((e) => setError(e.message)) }, [])

  const saveClip = async () => {
    try {
      const t = await require()
      navigate(`/cards/${await createCard({ text: sanitizeText(clip!.text), title: clip!.title, cite: '', topic: t })}`)
    } catch (e) { setError((e as Error).message) }
  }

  return (
    <div className="stack">
      {signedIn && (
        <section className="gap">
          <p>
            <button className="link" onClick={() => setReader(true)}>Open a source</button> to cut a card from it, or{' '}
            <button className="link" onClick={() => setClip(clip ? null : { text: '', title: '' })}>paste a clip</button>.
          </p>
          <p>Topic: <button className="link" onClick={() => choose()}>{current ? `${topicLabel(current)}: ${current.resolution}` : 'none yet, choose one'}</button></p>
          {clip && (
            <div className="gap">
              <input className="field" placeholder="Tag" value={clip.title} onChange={(e) => setClip({ ...clip, title: e.target.value })} style={{ fontWeight: 600 }} />
              <textarea className="field" rows={5} autoFocus placeholder="Any text to label" value={clip.text} onChange={(e) => setClip({ ...clip, text: e.target.value })} />
              <button className="action" disabled={!clip.text.trim() || !clip.title.trim()} onClick={saveClip}>Create card</button>
            </div>
          )}
        </section>
      )}
      {error && <p className="error">{error}</p>}
      {recent?.length === 0 && <p>No cards yet.</p>}
      {recent?.map((c) => <CardView key={c.number} card={c} mode="read" />)}
      <Reader open={reader} onClose={() => setReader(false)} onCut={(n) => navigate(`/cards/${n}`)} />
    </div>
  )
}
