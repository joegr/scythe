import { useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { config, me, tokenUrl, type GhUser } from './lib/gh'
import { LabelsContext, useLabelsLoader } from './lib/hooks'
import { SessionContext } from './lib/session'
import { TopicProvider } from './lib/topic'
import CardPage from './pages/CardPage'
import DataPage from './pages/DataPage'
import HomePage from './pages/HomePage'
import LabelsPage from './pages/LabelsPage'
import LibraryPage from './pages/LibraryPage'
import PrintPage from './pages/PrintPage'
import SearchPage from './pages/SearchPage'

export default function App() {
  const [user, setUser] = useState<GhUser | null | undefined>(config.token() ? undefined : null)
  const [settings, setSettings] = useState(!config.repo())
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!config.token()) return
    me().then(setUser).catch((e) => { setError(e.message); setUser(null) })
  }, [])

  if (user === undefined) return null
  if (settings) return <Settings onDone={() => window.location.reload()} />
  return (
    <SessionContext.Provider value={user}>
      <Shell user={user} error={error} openSettings={() => setSettings(true)} />
    </SessionContext.Provider>
  )
}

function Shell({ user, error, openSettings }: { user: GhUser | null; error: string | null; openSettings: () => void }) {
  const labels = useLabelsLoader()
  const [signIn, setSignIn] = useState(false)
  return (
    <LabelsContext.Provider value={labels}>
      <TopicProvider>
        <div className="page">
          <nav className="top no-print">
            <Link to="/" className="brand">scythe</Link>
            <NavLink to="/" end>cut</NavLink>
            <NavLink to="/search">search</NavLink>
            <NavLink to="/library">library</NavLink>
            <NavLink to="/data">data</NavLink>
            <NavLink to="/labels">labels</NavLink>
            <button className="link" onClick={openSettings}>{config.repo()}</button>
            {user
              ? <button className="link" onClick={() => { config.setToken(null); window.location.reload() }} title="Sign out">{user.login}</button>
              : <button className="link" onClick={() => setSignIn(true)}>sign in</button>}
          </nav>
          {error && <p className="error">{error}</p>}
          {signIn && !user && <SignIn />}
          <main>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/cards/:id" element={<CardPage />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/library" element={<LibraryPage />} />
              <Route path="/print/file/:file" element={<PrintPage />} />
              <Route path="/print/:id" element={<PrintPage />} />
              <Route path="/data" element={<DataPage />} />
              <Route path="/labels" element={<LabelsPage />} />
            </Routes>
          </main>
        </div>
      </TopicProvider>
    </LabelsContext.Provider>
  )
}

function SignIn() {
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)
  const save = async () => {
    config.setToken(token)
    try { await me(); window.location.reload() } catch (e) { config.setToken(null); setError((e as Error).message) }
  }
  return (
    <section className="gap note" style={{ marginBottom: '3rem' }}>
      <p>Scythe commits cards to <strong>{config.repo()}</strong> and keeps their issues, using a token that only this browser keeps.</p>
      <ol style={{ paddingLeft: '1.25rem' }}>
        <li><a href={tokenUrl()} target="_blank" rel="noreferrer">Create the token on GitHub</a>. It's pre-filled with Contents and Issues: read and write, and a 30-day expiry.</li>
        <li>Under Repository access, choose Only select repositories, then {config.repo().split('/')[1]}.</li>
        <li>Generate it and paste it here.</li>
      </ol>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <input className="field" style={{ flex: 1 }} type="password" placeholder="github_pat_…" value={token} onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && token.trim() && save()} />
        <button className="action" disabled={!token.trim()} onClick={save}>Sign in</button>
      </div>
    </section>
  )
}

function Settings({ onDone }: { onDone: () => void }) {
  const [repo, setRepo] = useState(config.repo())
  const [api, setApi] = useState(config.apiBase())
  const [localApi, setLocalApi] = useState(config.localApi())
  const [srv, setSrv] = useState(config.server())
  return (
    <div className="page stack" style={{ paddingTop: '15vh' }}>
      <h1>scythe</h1>
      <p>Debate cards as GitHub issues: cut them from sources, label them for spaCy, and keep their history in git.</p>
      <div className="gap">
        <label>Repository (public; cards are its issues)</label>
        <input className="field" placeholder="owner/repo" value={repo} onChange={(e) => setRepo(e.target.value)} />
        <label>GitHub API</label>
        <input className="field" value={api} onChange={(e) => setApi(e.target.value)} />
        <label>Scythe server (commits cards and spans)</label>
        <input className="field" value={srv} onChange={(e) => setSrv(e.target.value)} />
        <label>Local Scythe API (optional: search index, training; e.g. http://localhost:8000)</label>
        <input className="field" value={localApi} onChange={(e) => setLocalApi(e.target.value)} />
        <button className="action" disabled={!/^[\w.-]+\/[\w.-]+$/.test(repo.trim())} onClick={() => {
          const switchedApi = api.trim() !== config.apiBase()
          config.setRepo(repo); config.setApiBase(api === 'https://api.github.com' ? null : api); config.setLocalApi(localApi); config.setServer(srv)
          if (switchedApi) config.setToken(null)
          onDone()
        }}>Save</button>
      </div>
    </div>
  )
}
