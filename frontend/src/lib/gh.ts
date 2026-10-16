/**
 * The browser talks to GitHub directly: issues are the database.
 *
 * Repo: VITE_SCYTHE_REPO at build time, else derived from the Pages URL (<owner>.github.io/<repo>/),
 * overridable per browser. Sign-in: a fine-grained token created from a pre-filled GitHub link
 * (Issues: write on this one repo), stored only in this browser. Reads work without a token
 * because the repo is public.
 */

const KEYS = { token: 'scythe.gh.token', repo: 'scythe.gh.repo', api: 'scythe.gh.api', localApi: 'scythe.api', server: 'scythe.server' }

function get(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
function put(key: string, value: string | null) {
  try { if (value) localStorage.setItem(key, value); else localStorage.removeItem(key) } catch { /* storage blocked */ }
}

function repoFromLocation(): string | null {
  const m = /^([^.]+)\.github\.io$/.exec(location.hostname)
  const first = location.pathname.split('/').filter(Boolean)[0]
  return m && first ? `${m[1]}/${first}` : m ? `${m[1]}/${m[1]}.github.io` : null
}

export const config = {
  repo: () => get(KEYS.repo) || import.meta.env.VITE_SCYTHE_REPO || repoFromLocation() || '',
  setRepo: (r: string | null) => put(KEYS.repo, r?.trim() || null),
  /** https://api.github.com, or the local fake (http://localhost:8000/fakegh) for offline work. */
  apiBase: () => (get(KEYS.api) || import.meta.env.VITE_GITHUB_API || 'https://api.github.com').replace(/\/$/, ''),
  setApiBase: (u: string | null) => put(KEYS.api, u?.trim() || null),
  /** Optional local Scythe API (article fetching, index, training). */
  localApi: () => (get(KEYS.localApi) || import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, ''),
  setLocalApi: (u: string | null) => put(KEYS.localApi, u?.trim() || null),
  /** The Fly passthrough that commits cards and spans (VITE_SERVER_URL at build time). */
  server: () => (get(KEYS.server) || import.meta.env.VITE_SERVER_URL || 'http://localhost:8080').replace(/\/$/, ''),
  setServer: (u: string | null) => put(KEYS.server, u?.trim() || null),
  token: () => get(KEYS.token),
  setToken: (t: string | null) => put(KEYS.token, t?.trim() || null),
  isFake: () => /\/fakegh$/.test((get(KEYS.api) || import.meta.env.VITE_GITHUB_API || '').replace(/\/$/, '')),
}

/** GitHub's pre-filled fine-grained token page: Contents + Issues read & write, 30 days. Pick the repo there. */
export function tokenUrl(): string {
  const [owner, name] = config.repo().split('/')
  const p = new URLSearchParams({
    name: 'scythe',
    description: `Scythe: commit cards and write issues in ${owner}/${name}. Under Repository access choose Only select repositories → ${name}.`,
    expires_in: '30',
    contents: 'write',
    issues: 'write',
  })
  if (owner) p.set('target_name', owner)
  return `https://github.com/settings/personal-access-tokens/new?${p}`
}

export class GitHubError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function gh<T>(method: string, path: string, body?: unknown, { auth = true } = {}): Promise<{ data: T; headers: Headers }> {
  const headers: Record<string, string> = { Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' }
  const token = config.token()
  if (auth && token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let res: Response
  try {
    res = await fetch(`${config.apiBase()}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new GitHubError(0, `Can't reach ${config.apiBase()}.`)
  }
  if (!res.ok) {
    let message = res.statusText
    try { message = (await res.json()).message ?? message } catch { /* not json */ }
    if (res.status === 401) message = 'GitHub rejected the token. It may have expired; create a new one.'
    if (res.status === 403 && res.headers.get('x-ratelimit-remaining') === '0') message = 'GitHub rate limit reached. Sign in to raise it.'
    if (res.status === 404 && method !== 'GET') message = 'Not allowed. Check that the token has Issues: write on this repo.'
    throw new GitHubError(res.status, message)
  }
  const data = res.status === 204 ? (undefined as T) : ((await res.json()) as T)
  return { data, headers: res.headers }
}

export const repoPath = (suffix = '') => `/repos/${config.repo()}${suffix}`

/** Follow page numbers until a short page. */
export async function pages<T>(path: string, params: Record<string, string>, max = 10): Promise<T[]> {
  const out: T[] = []
  for (let page = 1; page <= max; page++) {
    const q = new URLSearchParams({ ...params, per_page: '100', page: String(page) })
    const { data } = await gh<T[]>('GET', `${path}?${q}`)
    out.push(...data)
    if (data.length < 100) break
  }
  return out
}

export interface GhUser { login: string; name: string | null; avatar_url: string }
export const me = () => gh<GhUser>('GET', '/user').then((r) => r.data)

// ---------------------------------------------------------------- git files

const decode = (b64: string) => new TextDecoder().decode(Uint8Array.from(atob(b64.replace(/\n/g, '')), (c) => c.charCodeAt(0)))
function encode(text: string): string {
  const bytes = new TextEncoder().encode(text)
  let bin = ''
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(bin)
}

/** A file at main (or `ref`), with its blob sha: the version a save must build on. */
export async function readFile(path: string, ref?: string): Promise<{ text: string; sha: string } | null> {
  try {
    const { data } = await gh<{ content: string; sha: string }>('GET', repoPath(`/contents/${path}${ref ? `?ref=${ref}` : ''}`))
    return { text: decode(data.content), sha: data.sha }
  } catch (e) {
    if (e instanceof GitHubError && e.status === 404) return null
    throw e
  }
}

/** Direct commit (shared settings). 409 means someone else committed first. */
export async function writeFile(path: string, text: string, message: string, sha?: string) {
  const { data } = await gh<{ content: { sha: string } }>('PUT', repoPath(`/contents/${path}`), { message, content: encode(text), ...(sha ? { sha } : {}) })
  return data.content.sha
}

export interface Commit { sha: string; message: string; author: string; date: string; url: string }
export async function history(path: string): Promise<Commit[]> {
  const { data } = await gh<{ sha: string; html_url: string; commit: { message: string; author: { name: string; date: string } }; author: { login: string } | null }[]>(
    'GET', repoPath(`/commits?path=${encodeURIComponent(path)}&per_page=50`))
  return data.map((c) => ({ sha: c.sha, message: c.commit.message, author: c.author?.login ?? c.commit.author.name, date: c.commit.author.date, url: c.html_url }))
}

// ---------------------------------------------------------------- the passthrough

export interface Theirs { content: string; sha: string; commit: { sha: string | null; message: string | null; author: string | null; date: string | null } }
export class Diverged extends Error {
  theirs: Theirs
  constructor(theirs: Theirs) { super('Someone else saved this card first.'); this.theirs = theirs }
}

export async function server<T>(method: string, path: string, body: unknown): Promise<T> {
  const token = config.token()
  let res: Response
  try {
    res = await fetch(`${config.server()}${path}`, {
      method, body: JSON.stringify(body),
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
  } catch {
    throw new GitHubError(0, `Can't reach the Scythe server at ${config.server()}.`)
  }
  if (res.status === 409) throw new Diverged((await res.json()).theirs)
  if (!res.ok) {
    let message = res.statusText
    try { message = (await res.json()).detail ?? message } catch { /* not json */ }
    throw new GitHubError(res.status, typeof message === 'string' ? message : JSON.stringify(message))
  }
  return res.json() as Promise<T>
}
