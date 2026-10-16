import { useEffect, useState } from 'react'
import { history, type Commit } from '../lib/gh'

/** git log for one card's file; each entry opens the commit's diff on GitHub. */
export default function History({ path, refreshKey }: { path: string; refreshKey: string | null }) {
  const [commits, setCommits] = useState<Commit[] | null>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { if (open) history(path).then(setCommits).catch(() => setCommits([])) }, [open, path, refreshKey])
  return (
    <section className="gap">
      <button className="link" onClick={() => setOpen(!open)}>{open ? 'hide history' : 'history'}</button>
      {open && commits && (
        <ul className="list">
          {commits.map((c) => (
            <li key={c.sha} className="row">
              <a href={c.url} target="_blank" rel="noreferrer">{c.sha.slice(0, 7)}</a>
              <span style={{ flex: 1 }}>{c.message.split('\n')[0]}</span>
              <span>{c.author}, {new Date(c.date).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
