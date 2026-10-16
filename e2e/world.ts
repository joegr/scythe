/** Fixtures shared by every step: who is signed in, what this scenario created, and page helpers. */
import { expect, type Browser, type Page } from '@playwright/test'
import { createBdd, test as base } from 'playwright-bdd'
import { DEFAULT_TOPIC, topic } from './github'

const TOKEN = process.env.SCYTHE_TEST_TOKEN!

export interface World {
  /** Unique per scenario; replaces <run> in step text so scenarios never see each other's cards. */
  run: string
  card?: number
  other?: number
  source?: number
  /** localStorage the app should start with, applied once per page before its first load. */
  storage: Record<string, string | null>
  /** Values a later step compares against (a tag typed, a cite seen, who won a race). */
  notes: Record<string, string>
  /** Expand <run>, <n>, <first>, <other>, <source> in step text. */
  sub: (s: string) => string
}

export interface Debaters { ana: Page; ben: Page }

export const test = base.extend<{ world: World; debaters: Debaters }>({
  world: async ({}, use) => {
    const w: World = {
      run: Math.random().toString(36).slice(2, 8),
      notes: {},
      // Test pages read as the test key by default: signed-out reads share GitHub's 60-an-hour
      // limit per network (and CI runners share networks). "I am not signed in" clears it.
      storage: { 'scythe.topic': JSON.stringify({ ...topic(DEFAULT_TOPIC), origin: 'nsda' }), 'scythe.gh.token': TOKEN },
      sub: (s) => s
        .replace(/<run>/g, w.run)
        .replace(/<n>|<first>/g, () => String(w.card ?? '<n>'))
        .replace(/<other>/g, () => String(w.other ?? '<other>'))
        .replace(/<source>/g, () => String(w.source ?? '<source>')),
    }
    await use(w)
  },
  debaters: async ({ browser, world }, use) => {
    const open = async (b: Browser) => {
      const ctx = await b.newContext({ baseURL: 'http://localhost:5174' })
      const page = await ctx.newPage()
      await prime(page, { ...world.storage, 'scythe.gh.token': TOKEN })
      return page
    }
    const d = { ana: await open(browser), ben: await open(browser) }
    await use(d)
    await d.ana.context().close()
    await d.ben.context().close()
  },
})

export const { Given, When, Then, Before } = createBdd(test)

/** A gap in the features is an expected failure; when it starts passing, retag it @built. */
Before({ tags: '@partly or @missing' }, async ({ $test }) => {
  $test.fail()
})

/** For steps that describe a screen or behavior Scythe doesn't have yet. */
export function notBuilt(what: string): never {
  throw new Error(`not built yet: ${what}`)
}

const primed = new WeakSet<Page>()

/** Set the app's localStorage once, before the page's first load (later loads keep what the app wrote). */
export async function prime(page: Page, storage: Record<string, string | null>) {
  if (primed.has(page)) return
  primed.add(page)
  await page.addInitScript((s) => {
    if (sessionStorage.getItem('e2e-primed')) return
    sessionStorage.setItem('e2e-primed', '1')
    for (const [k, v] of Object.entries(s)) { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v) }
  }, storage)
}

export async function open(page: Page, world: World, path: string) {
  await prime(page, world.storage)
  await page.goto(`/#${path}`)
}

/** Select `phrase` inside `container` the way a mouse drag does, then release the mouse there. */
export async function select(page: Page, container: string, phrase: string) {
  await expect(page.locator(container).first()).toContainText(phrase.trim())
  await page.locator(container).first().evaluate((root, p) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    const nodes: [Text, number][] = []
    let full = ''
    while (walker.nextNode()) { const t = walker.currentNode as Text; nodes.push([t, full.length]); full += t.data }
    const i = full.indexOf(p)
    if (i < 0) throw new Error(`"${p}" isn't on the page`)
    const at = (pos: number, end: boolean): [Text, number] => {
      for (const [t, off] of nodes) if (pos < off + t.data.length || (end && pos === off + t.data.length)) return [t, pos - off]
      const [t, off] = nodes[nodes.length - 1]
      return [t, pos - off]
    }
    const r = document.createRange()
    r.setStart(...at(i, false))
    r.setEnd(...at(i + p.length, true))
    const sel = window.getSelection()!
    sel.removeAllRanges()
    sel.addRange(r)
    root.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
  }, phrase)
}

/** Wait for an assertion about GitHub state (commits, the Action's issue writes) to come true. */
export async function eventually(fn: () => Promise<void>, timeout = 30_000) {
  await expect(async () => { await fn() }).toPass({ timeout, intervals: [1_000, 2_000, 5_000] })
}

export const cardNumberFrom = (url: string) => Number(/#\/cards\/(\d+)/.exec(url)?.[1])
