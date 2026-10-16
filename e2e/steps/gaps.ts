/**
 * Steps for @partly and @missing scenarios. Each one drives the debate-language screen or the
 * behavior the feature promises, so it fails today (an expected failure) and starts passing as
 * soon as that piece is built, which is the cue to retag the scenario @built.
 */
import { expect, type Page } from '@playwright/test'
import { api, card, changeCard, commits, createCard, createSource, issue, readFile, source, spanText } from '../github'
import { REPO } from '../env'
import { Given, Then, When, cardNumberFrom, eventually, notBuilt, open, select } from '../world'

const reader = (page: Page) => page.locator('dialog[open]')
const FIVE_MIN = 5 * 60_000

async function openSource(page: Page, world: { source?: number }, worldRef: Parameters<typeof open>[1]) {
  const { title } = (await source(world.source!)).head
  await open(page, worldRef, '/')
  await expect(async () => {
    if (await reader(page).isVisible()) await reader(page).getByRole('button', { name: 'close' }).click()
    await page.getByRole('button', { name: 'Open a source' }).click()
    await reader(page).getByRole('button', { name: title }).click({ timeout: 4_000 })
  }).toPass({ timeout: 60_000 })
}

/** Wait until the spaCy Action has stamped the card's issue with the file version in git. */
async function checked(n: number) {
  await eventually(async () => {
    const [i, f] = await Promise.all([issue(n), card(n)])
    expect(i.meta?.processed?.file_sha).toBe(f.sha)
  }, FIVE_MIN)
}

// ------------------------------------------------------------ 01 cutting

Given('I cut {string} from that source into file {string} block {string}', async ({ page, world }, passage: string, file: string, block: string) => {
  await openSource(page, world, world)
  await reader(page).locator('input[placeholder="Paste a copied passage to find it"]').fill(passage)
  await reader(page).getByRole('button', { name: 'find', exact: true }).click()
  await reader(page).locator('input[placeholder="Tag"]').fill(`Carry ${world.run}`)
  await reader(page).locator('input[placeholder="File"]').fill(file)
  await reader(page).locator('input[placeholder="Block"]').fill(block)
  world.notes.cite = await reader(page).locator('input[placeholder="Cite"]').inputValue()
  await reader(page).getByRole('button', { name: 'Cut', exact: true }).click()
  await expect(page).toHaveURL(/#\/cards\/\d+/, { timeout: 30_000 })
  world.card = cardNumberFrom(page.url())
})

When('I return to that source', async ({ page, world }) => {
  await page.getByRole('button', { name: `source #${world.source}` }).click()
  await expect(reader(page).locator('.reader-text')).toBeVisible()
})

Then('the cite still reads the source\'s cite', async ({ page, world }) => {
  await expect(reader(page).locator('input[placeholder="Cite"]')).toHaveValue(world.notes.cite)
})

Then('the file still reads {string} and the block {string}', async ({ page }, file: string, block: string) => {
  await expect(reader(page).locator('input[placeholder="File"]')).toHaveValue(file)
  await expect(reader(page).locator('input[placeholder="Block"]')).toHaveValue(block)
})

Then('the tag is empty', async ({ page }) => {
  await expect(reader(page).locator('input[placeholder="Tag"]')).toHaveValue('')
})

When('I move the cursor to {string} and extend the selection with Shift and the arrow keys', async ({ page }, phrase: string) => {
  await page.locator('dialog[open] .reader-text').evaluate((root, p) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    while (walker.nextNode()) {
      const t = walker.currentNode as Text
      const i = t.data.indexOf(p)
      if (i >= 0) { const r = document.createRange(); r.setStart(t, i); r.collapse(true); getSelection()!.removeAllRanges(); getSelection()!.addRange(r); return }
    }
    throw new Error(`"${p}" isn't on the page`)
  }, phrase)
  for (let i = 0; i < phrase.length; i++) await page.keyboard.press('Shift+ArrowRight')
})

When('I press Cmd+Enter', async ({ page }) => {
  await page.keyboard.press('Meta+Enter')
})

When('I paste a clip {string} tagged {string} with cite {string}', async ({ page, world }, text: string, tag: string, cite: string) => {
  world.notes.tag = world.sub(tag)
  await open(page, world, '/')
  await page.getByRole('button', { name: 'paste a clip' }).click()
  await page.locator('input[placeholder="Tag"]').fill(world.notes.tag)
  await page.locator('textarea[placeholder="Any text to label"]').fill(text)
  await page.locator('input[placeholder="Cite"]').fill(cite)
})

When('I press {string} twice quickly', async ({ page }, button: string) => {
  await page.getByRole('button', { name: button }).dblclick()
  await expect(page).toHaveURL(/#\/cards\/\d+/, { timeout: 30_000 })
})

Then('exactly one card is created', async ({ page, world }) => {
  world.card = cardNumberFrom(page.url())
  await page.waitForTimeout(5_000)
  const recent = await api<{ title: string }[]>('GET', '/repos/{repo}/issues?labels=scythe:card&sort=created&direction=desc&per_page=30')
  expect(recent.filter((i) => i.title === world.notes.tag)).toHaveLength(1)
})

// ------------------------------------------------------------ 02 marks

When('I select only the space after {string} in the card', async ({ page }, word: string) => {
  await page.locator('.card .token-text').evaluate((root, w) => {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    while (walker.nextNode()) {
      const t = walker.currentNode as Text
      const i = t.data.indexOf(`${w} `)
      if (i >= 0) {
        const r = document.createRange(); r.setStart(t, i + w.length); r.setEnd(t, i + w.length + 1)
        getSelection()!.removeAllRanges(); getSelection()!.addRange(r)
        root.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
        return
      }
    }
    throw new Error(`"${w} " isn't on the page`)
  }, word)
})

Then('no commit is made to the card', async ({ world }) => {
  await new Promise((r) => setTimeout(r, 5_000))
  expect((await commits(`cards/${world.card}.md`)).map((c) => c.message)).toEqual([expect.stringMatching(/^card: /)])
})

When('the team adds a mark {string} on key {string}', async ({ page, world }, name: string, key: string) => {
  await open(page, world, '/labels')
  await page.getByRole('textbox', { name: 'Mark name' }).fill(name)
  await page.getByRole('textbox', { name: 'Key' }).fill(key)
  await page.getByRole('button', { name: 'Add mark' }).click()
})

When('I select {string} in the card and press {string}', async ({ page, world }, phrase: string, key: string) => {
  await open(page, world, `/cards/${world.card}`)
  await select(page, '.card .token-text', phrase)
  await page.keyboard.press(key)
})

Then('I see the mark {string} named when I point at those words', async ({ page }, name: string) => {
  await page.locator('.card .token-text span[data-span]').filter({ hasText: 'block sunlight' }).first().hover()
  await expect(page.getByRole('tooltip')).toHaveText(name)
})

// ------------------------------------------------------------ 03 tag and cite

When('I clear the tag', async ({ page }) => {
  const input = page.locator('.card-tag input')
  await input.fill('')
  await input.press('Tab')
})

Then('the tag field reads {string} again', async ({ page, world }, tag: string) => {
  await expect(page.locator('.card-tag input')).toHaveValue(world.sub(tag))
})

Given('the card\'s text names {string} and {string}', async ({ world }, a: string, b: string) => {
  world.card = await createCard({ title: `Quals ${world.run}`, text: `${a} of ${b} found that soot from burning cities would block sunlight.`, source: world.source })
})

When('I ask for quals', async ({ page, world }) => {
  await open(page, world, `/cards/${world.card}`)
  await page.getByRole('button', { name: 'quals' }).click()
})

Then('the cite offers {string} as the quals to insert after the short cite', async ({ page }, quals: string) => {
  await expect(page.getByRole('button', { name: `Insert “${quals}”` })).toBeVisible()
})

Given('a source by {string} in {string} on {string}', async ({ world }, author: string, publication: string, date: string) => {
  world.source = await createSource({ title: `Cite pieces ${world.run}`, authors: author ? [author] : [], publisher: publication, published: date || null },
    'Soot from burning cities would block sunlight for a decade.')
})

Then('the drafted cite starts with {string}', async ({ page }, start: string) => {
  await expect(reader(page).locator('input[placeholder="Cite"]')).toHaveValue(new RegExp(`^${start.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`))
})

// ------------------------------------------------------------ 04 reading

When('I look at the latest cards', async ({ page, world }) => {
  await open(page, world, '/')
})

Then('the card {string} shows {string}', async ({ page, world }, tag: string, text: string) => {
  await expect(page.locator('article.card', { has: page.locator('.card-tag', { hasText: world.sub(tag) }) }).locator('.card-body')).toContainText(text)
})

Then('{string} is drawn with a highlight color, not only a heavier underline', async ({ page }, words: string) => {
  const bg = await page.locator('.card .t-hl', { hasText: words }).first().evaluate((el) => getComputedStyle(el).backgroundColor)
  expect(bg).not.toMatch(/rgba\(0, 0, 0, 0\)|transparent/)
})

// ------------------------------------------------------------ 05 signing in

Given('I have a GitHub key that can read but not write the team\'s evidence', async ({ page, world }) => {
  world.storage['scythe.gh.token'] = null
  // GitHub would say: this key reads the repo but has no push permission on it.
  await page.route('https://api.github.com/user', (r) => r.fulfill({ json: { login: 'reader-only', name: null, avatar_url: '' } }))
  await page.route(`https://api.github.com/repos/${REPO}`, (r) => r.fulfill({ json: { full_name: REPO, permissions: { pull: true, push: false } } }))
})

When('I sign in with it', async ({ page, world }) => {
  await open(page, world, '/')
  await page.locator('nav.top').getByRole('button', { name: 'sign in' }).click()
  await page.locator('input[type="password"]').fill('github_pat_readonly_test_value')
  await page.locator('input[type="password"]').press('Enter')
})

Then('I am still signed out', async ({ page }) => {
  await expect.poll(() => page.evaluate(() => localStorage.getItem('scythe.gh.token'))).toBeNull()
})

When('I switch to the evidence {string}', async ({ page, world }, repo: string) => {
  await open(page, world, '/')
  await page.locator('nav.top').getByRole('button', { name: REPO }).click()
  await page.getByRole('textbox', { name: 'Team’s evidence on GitHub' }).fill(repo)
  await page.getByRole('button', { name: 'Switch' }).click()
})

Then('the latest cards are from {string}', async ({ page }, repo: string) => {
  await expect(page.locator(`.card-meta a[href^="https://github.com/${repo}/issues/"]`).first()).toBeVisible()
})

Then('my GitHub key is kept', async ({ page }) => {
  expect(await page.evaluate(() => localStorage.getItem('scythe.gh.token'))).not.toBeNull()
})

When('I click my name', async ({ page, world }) => {
  await open(page, world, '/')
  const login = (await api<{ login: string }>('GET', '/user')).login
  await page.locator('nav.top').getByRole('button', { name: login }).click()
})

Then('I am still signed in until I confirm', async ({ page }) => {
  expect(await page.evaluate(() => localStorage.getItem('scythe.gh.token'))).not.toBeNull()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
})

// ------------------------------------------------------------ 06, 07 Scythe reads the card

Then('within 5 minutes I see {string}', async ({ page, world }, text: string) => {
  await expect(page.getByText(world.sub(text)).first()).toBeVisible({ timeout: FIVE_MIN })
})

Given('the Action takes 4 minutes to check the card', async ({ world }) => {
  world.notes.slowAction = '1'
})

When('I keep the card open', async ({ page, world }) => {
  await open(page, world, `/cards/${world.card}`)
  // The worker usually finishes in about a minute; the page must still notice after its polling window.
  await page.waitForTimeout(4 * 60_000)
})

Then('I see {string} without reloading', async ({ page }, text: string) => {
  await expect(page.getByText(text).first()).toBeVisible({ timeout: 60_000 })
})

Given('the card has a {string} span whose browser snapping differs from spaCy\'s tokens', async ({ world }, label: string) => {
  // Mid-word offsets: spaCy expands "lan Robo" to "Alan Robock".
  await changeCard(world.card!, `${label}: "lan Robo"`, (f) => {
    const a = f.text.indexOf('lan Robo')
    return { ...f, spans: [...f.spans, { label, key: 'sc', style: label, start_char: a, end_char: a + 8, src: 'manual' }] }
  })
})

Given('Scythe has checked the card', async ({ world }) => {
  await checked(world.card!)
})

Then('cards\\/<n>.md holds the spaCy-snapped character offsets', async ({ world }) => {
  await eventually(async () => {
    const f = await card(world.card!)
    expect(f.spans.map((s) => spanText(f, s))).toContain('Alan Robock')
  }, FIVE_MIN)
})

When('I show names and places', async ({ page }) => {
  await page.getByRole('button', { name: 'names and places' }).click()
})

Then('pointing at {string} says {string}', async ({ page }, words: string, kind: string) => {
  await expect(page.locator('.card .t-ner', { hasText: words }).first()).toHaveAttribute('title', kind)
})

When('I choose {string} and {string} as quals', async ({ page }, a: string, b: string) => {
  await page.getByRole('button', { name: 'quals' }).click()
  await page.getByRole('checkbox', { name: a }).check()
  await page.getByRole('checkbox', { name: b }).check()
  await page.getByRole('button', { name: 'Insert quals' }).click()
})

Then('the cite reads {string}', async ({ world }, cite: string) => {
  const prefix = cite.replace(/…$/, '')
  await eventually(async () => expect((await card(world.card!)).cite.startsWith(prefix)).toBe(true))
})

Given('two checked cards both name {string}', async ({ world }, person: string) => {
  world.card = await createCard({ title: `Person A ${world.run}`, text: `${person} warned of famine.` })
  world.other = await createCard({ title: `Person B ${world.run}`, text: `${person} modeled the soot.` })
  await Promise.all([checked(world.card), checked(world.other)])
})

When('I search for the person {string}', async ({}, _person: string) => {
  notBuilt('searching by a person named in cards (needs the names index in the app)')
})

Then('both cards are listed', async ({ page, world }) => {
  for (const t of [`Person A ${world.run}`, `Person B ${world.run}`]) await expect(page.getByText(t)).toBeVisible()
})

// ------------------------------------------------------------ 08 suggested highlights (local API only today)

Given('the team has approved at least 50 cut cards', async () => {
  notBuilt('suggested highlighting in the app (training runs only on the local API today)')
})
Given('a model has been trained on the team\'s accepted spans', async () => notBuilt('a trained model the app can reach'))
When('the coach starts training from the team page', async () => notBuilt('training from the app'))
Given('a new card {string} with no marks', async ({ world }, title: string) => { world.card = await createCard({ title: world.sub(title), text: 'Soot from burning cities would block sunlight for a decade.' }) })
When('I ask for suggestions', async ({ page }) => { await page.getByRole('button', { name: 'suggest' }).click() })
When('I ask for suggestions again', async ({ page }) => { await page.getByRole('button', { name: 'suggest' }).click() })
Then('suggested highlights are drawn as dotted underlines', async ({ page }) => { await expect(page.locator('.card .t-suggested').first()).toBeVisible() })
Then('none of them is in the card in git until I accept it', async ({ world }) => { expect((await card(world.card!)).spans).toEqual([]) })
Given('the card shows a suggested {string} over {string}', async ({ page }, label: string, words: string) => {
  await expect(page.locator(`.card .t-suggested[data-label="${label}"]`, { hasText: words })).toBeVisible()
})
When('I click the suggestion', async ({ page }) => { await page.locator('.card .t-suggested').first().click() })
Then('{string} is not suggested again', async ({ page }, words: string) => { await expect(page.locator('.card .t-suggested', { hasText: words })).toHaveCount(0) })
Given('an unapproved card with a {string} over every word', async ({}, _label: string) => notBuilt('training data export from the app'))
When('the model is trained', async () => notBuilt('training from the app'))
Then('that card is not in the training data', async () => notBuilt('training data export from the app'))

// ------------------------------------------------------------ 09, 10, 11, 12 sources

When('I fetch a link to a page with no readable article', async ({ page, world }) => {
  world.notes.url = `https://httpbin.org/bytes/64?scythe=${world.run}`
  await reader(page).getByRole('button', { name: 'fetch a link' }).click()
  await reader(page).locator('input[type="url"]').fill(world.notes.url)
  await reader(page).locator('input[type="url"]').press('Enter')
})

Then('within 5 minutes the source\'s issue has the label {string}', async ({ world }, label: string) => {
  await eventually(async () => {
    const recent = await api<{ number: number; title: string; labels: { name: string }[] }[]>('GET', '/repos/{repo}/issues?sort=created&direction=desc&per_page=30&state=all')
    const mine = recent.find((i) => i.title === world.notes.url)
    expect(mine?.labels.map((l) => l.name)).toContain(label)
  }, FIVE_MIN)
})

Then('the paste form is open with the link already filled in', async ({ page, world }) => {
  await expect(reader(page).locator('input[placeholder="Link"]')).toHaveValue(world.notes.url)
})

Given('the source for {string} is already in the team\'s evidence', async ({ world }, url: string) => {
  world.source = await createSource({ title: `Already here ${world.run}`, url }, 'Nuclear winter text.')
  world.notes.sources = String((await api<unknown[]>('GET', '/repos/{repo}/issues?labels=scythe:source&state=all&per_page=100')).length)
})

Then('the reader opens that source at once', async ({ page, world }) => {
  await expect(reader(page).locator('h1')).toHaveText(`Already here ${world.run}`, { timeout: 10_000 })
})

Then('no new source is made', async ({ world }) => {
  const now = (await api<unknown[]>('GET', '/repos/{repo}/issues?labels=scythe:source&state=all&per_page=100')).length
  expect(String(now)).toBe(world.notes.sources)
})

When('the article has been fetched', async () => {
  notBuilt('a drafted cite on fetched sources (the fetcher writes cite: "")')
})

Then('the cite field starts with the first author\'s last name and the two-digit year', async ({ page }) => {
  await expect(reader(page).locator('input[placeholder="Cite"]')).toHaveValue(/^\p{L}+ \d\d,/u)
})

async function pasteArticle(page: Page, world: Parameters<typeof open>[1], fields: { authors?: string; date?: string; text?: string }) {
  await open(page, world, '/')
  await page.getByRole('button', { name: 'Open a source' }).click()
  await reader(page).locator('textarea').fill(fields.text ?? 'Soot from burning cities would block sunlight for a decade.')
  await reader(page).locator('input[placeholder="Title"]').fill(`Pasted ${world.run}`)
  if (fields.authors) await reader(page).locator('input[placeholder="Authors, separated by commas"]').fill(fields.authors)
  if (fields.date) await reader(page).locator('input[placeholder="Date, YYYY-MM-DD"]').fill(fields.date)
  await reader(page).getByRole('button', { name: 'Read', exact: true }).click()
}

When('I paste an article with authors {string}', async ({ page, world }, authors: string) => {
  await pasteArticle(page, world, { authors })
  await expect(reader(page).locator('h1')).toHaveText(`Pasted ${world.run}`, { timeout: 30_000 })
  world.source = Number((await reader(page).locator('p a', { hasText: /^#\d+$/ }).first().textContent())!.slice(1))
})

Then('the source\'s front matter has "authors" [{string}, {string}]', async ({ world }, a: string, b: string) => {
  expect((await source(world.source!)).head.authors).toEqual([a, b])
})

When('I paste an article with the date {string}', async ({ page, world }, date: string) => {
  await pasteArticle(page, world, { date })
})

Then('nothing is saved', async ({ page }) => {
  await expect(reader(page).getByRole('button', { name: 'Read', exact: true })).toBeVisible()
})

When('I paste text copied from a PDF with a line break every 80 characters and hyphenated words split across lines', async ({ page, world }) => {
  const text = 'Nuclear winter would collapse global agri-\nculture for a decade, starving billions of people within two years of\na regional war.'
  await pasteArticle(page, world, { text })
  await expect(reader(page).locator('h1')).toHaveText(`Pasted ${world.run}`, { timeout: 30_000 })
  world.source = Number((await reader(page).locator('p a', { hasText: /^#\d+$/ }).first().textContent())!.slice(1))
})

Then('each paragraph is one line and {string} reads {string}', async ({ world }, _broken: string, mended: string) => {
  const { text } = await source(world.source!)
  expect(text).toContain(mended)
  expect(text.split('\n\n').every((p) => !p.includes('\n'))).toBe(true)
})

Given('that source is a full-length article', async ({ world }) => {
  const para = 'Soot from burning cities would block sunlight for a decade, and the resulting winter would collapse global agriculture.'
  world.source = await createSource({ title: `Long article ${world.run}` }, Array.from({ length: 40 }, () => para).join('\n\n'))
})

Then('the message is visible without scrolling', async ({ page }) => {
  await expect(reader(page).locator('.error')).toBeInViewport()
})

Given('the source contains {string} twice', async ({ world }, phrase: string) => {
  world.source = await createSource({ title: `Twice ${world.run}` }, `First, ${phrase}. Then again, ${phrase}.`)
})

Then('I see {string} and can step between them', async ({ page }, text: string) => {
  await expect(page.getByText(text)).toBeVisible()
  await page.getByRole('button', { name: 'next' }).click()
})

Then('I see a {string} section listing {string}', async ({ page, world }, heading: string, title: string) => {
  const section = page.locator('section', { has: page.getByRole('heading', { name: heading }) })
  await expect(section.getByText(world.sub(title))).toBeVisible()
})

Then('under it the card {string}', async ({ page, world }, title: string) => {
  await expect(page.locator('section', { has: page.getByRole('heading', { name: 'Sources' }) }).getByText(world.sub(title))).toBeVisible()
})

Given('a source with no cards', async ({ world }) => {
  world.source = await createSource({ title: `Lonely ${world.run}` }, 'Nobody cut from this.')
})

When('I remove the source', async ({ page, world }) => {
  await openSource(page, world, world)
  await reader(page).getByRole('button', { name: 'Remove source' }).click()
})

Then('its file is deleted and its issue is closed', async ({ world }) => {
  await eventually(async () => {
    expect(await readFile(`sources/${world.source}.md`)).toBeNull()
    expect((await issue(world.source!)).state).toBe('closed')
  }, FIVE_MIN)
})

// ------------------------------------------------------------ 13 resolutions

Given('a pasted source {string} by {string} in {string} on {string} with text {string}', async ({ world }, title: string, author: string, publisher: string, date: string, text: string) => {
  world.source = await createSource({ title: world.sub(title), authors: [author], publisher, published: date }, text)
})

When('I close the resolution picker without choosing', async ({ page }) => {
  await page.locator('dialog[open]').filter({ hasText: 'Which topic is this card for?' }).getByRole('button', { name: 'close' }).click()
})

Then('my selection and tag are still there', async ({ page, world }) => {
  await expect(reader(page).locator('.reader-sel')).toBeVisible()
  await expect(reader(page).locator('input[placeholder="Tag"]')).toHaveValue(`Picker ${world.run}`)
})

Then('I can scroll through all {int} LD resolutions', async ({ page }, n: number) => {
  await expect(page.locator('dialog[open] button.plain')).toHaveCount(n)
})

Given('a card filed under a custom resolution {string}', async ({ world }, resolution: string) => {
  const slug = `custom-schools-ban-phones-${world.run}`
  const raw = await readFile('scythe.json')
  const settings = raw ? JSON.parse(raw.text) : { labels: [], topics: [] }
  settings.topics = [...(settings.topics ?? []), { slug, event: 'custom', season: '', period: '', resolution }]
  await api('PUT', '/repos/{repo}/contents/scythe.json', { message: `topic: ${slug}`, content: Buffer.from(JSON.stringify(settings, null, 2) + '\n').toString('base64'), ...(raw ? { sha: raw.sha } : {}) })
  world.card = await createCard({ title: `Custom ${world.run}`, text: 'Phones distract students.' })
  await changeCard(world.card, `topic: ${slug}`, (f) => ({ ...f, topic: { slug, event: 'custom', season: '', period: '', resolution } }))
  await api('POST', `/repos/{repo}/issues/${world.card}/labels`, { labels: [`topic:${slug}`] })
})

When('I look at the library', async ({ page, world }) => {
  await open(page, world, '/library')
})

// ------------------------------------------------------------ 14 files

When('I file it under file {string} and no block', async ({ page, world }, file: string) => {
  await page.locator('input[placeholder="File"]').fill(world.sub(file))
  await page.getByRole('button', { name: 'file it' }).click()
})

Then('within 5 minutes the card\'s issue has the label {string}', async ({ world }, label: string) => {
  await eventually(async () => expect((await issue(world.card!)).labelNames).toContain(world.sub(label)), FIVE_MIN)
})

Then('the library shows {string} with the card under {string}', async ({ page, world }, file: string, block: string) => {
  await open(page, world, '/library')
  await page.getByRole('button', { name: world.sub(file), exact: true }).click()
  await expect(page.locator('section', { has: page.locator('h2', { hasText: block }) }).locator('.card-tag')).toBeVisible()
})

When('I file a card under {string}', async ({ world }, file: string) => {
  world.notes.file = file
  await changeCard(world.card!, `file: ${file} / Links`, (f) => ({ ...f, file, block: 'Links' }))
})

Then('the library shows the whole name', async ({ page, world }) => {
  await expect(async () => {
    await open(page, world, '/library')
    await expect(page.getByRole('button', { name: world.notes.file, exact: true })).toBeVisible({ timeout: 10_000 })
  }).toPass({ timeout: FIVE_MIN, intervals: [20_000] })
})

Then('the approve button explains {string}', async ({ page }, text: string) => {
  await expect(page.locator('.card-meta').getByRole('button', { name: 'approve', exact: true })).toHaveAttribute('title', text)
})

// ------------------------------------------------------------ 15 links

Given('three cards answer the first card', async ({ world }) => {
  for (const i of [1, 2, 3]) {
    const n = await createCard({ title: `Answer ${i} ${world.run}`, text: `Answer number ${i}.` })
    await changeCard(n, `answers #${world.card}`, (f) => ({ ...f, links: [{ rel: 'answers', to: world.card! }] }))
  }
})

When('I print the first card\'s frontlines', async ({ page, world }) => {
  await open(page, world, `/print/${world.card}/frontlines`)
})

Then('the print shows the first card followed by its three answers', async ({ page, world }) => {
  const tags = await page.locator('.print-sheet h4').allTextContents()
  expect(tags[0]).toContain('Nuclear winter is real')
  expect(tags.slice(1).filter((t) => t.includes(`Answer`) && t.includes(world.run))).toHaveLength(3)
})

// ------------------------------------------------------------ 16 history and removing

When('I open the version before the highlight', async ({ page, world }) => {
  await open(page, world, `/cards/${world.card}`)
  await page.getByRole('button', { name: 'history', exact: true }).click()
  await page.locator('li', { hasText: /^.*card: / }).getByRole('button', { name: 'open this version' }).click()
})

Then('the card shows no highlight', async ({ page }) => {
  await expect(page.locator('.card .t-hl')).toHaveCount(0)
})

Then('I can put that version back, which saves it as a new change', async ({ page, world }) => {
  await page.getByRole('button', { name: 'Put this version back' }).click()
  await eventually(async () => expect((await card(world.card!)).spans).toEqual([]))
})

When('I remove the card', async ({ page }) => {
  await page.getByRole('button', { name: 'remove' }).click()
})

When('I confirm', async ({ page }) => {
  await page.getByRole('button', { name: 'Remove', exact: true }).click()
})

Then('cards\\/<n>.md is deleted with the commit {string}', async ({ world }, message: string) => {
  await eventually(async () => {
    expect(await readFile(`cards/${world.card}.md`)).toBeNull()
    expect((await commits(`cards/${world.card}.md`))[0].message).toBe(world.sub(message))
  })
})

Given('the card was removed', async ({ world }) => {
  const f = (await readFile(`cards/${world.card}.md`))!
  await api('DELETE', `/repos/{repo}/contents/cards/${world.card}.md`, { message: `archive: History ${world.run} (#${world.card})`, sha: f.sha })
})

When('I search the removed cards and open it', async ({ page, world }) => {
  await open(page, world, '/search?archived=1')
  await page.getByRole('link', { name: `History ${world.run}` }).click()
})

When('I bring it back', async ({ page }) => {
  await page.getByRole('button', { name: 'bring back' }).click()
})

Then('cards\\/<n>.md is restored from its last version and its issue reopens', async ({ world }) => {
  await eventually(async () => {
    expect(await readFile(`cards/${world.card}.md`)).not.toBeNull()
    expect((await issue(world.card!)).state).toBe('open')
  }, FIVE_MIN)
})

// ------------------------------------------------------------ 17 the stopped save speaks debate

Then('Ben sees {string}', async ({ debaters }, text: string) => {
  const login = (await api<{ login: string }>('GET', '/user')).login
  await expect(debaters.ben.getByText(text.replace(/^Ana\b/, login)).first()).toBeVisible()
})

Then('Ben sees the choices {string}, {string} and {string}', async ({ debaters }, a: string, b: string, c: string) => {
  for (const name of [a, b, c]) await expect(debaters.ben.getByRole('button', { name, exact: true })).toBeVisible()
})

Given('Ben\'s save was stopped', async ({ debaters, world }) => {
  await changeCard(world.card!, 'highlight: "block sunlight"', (f) => ({ ...f, spans: [{ label: 'highlight', key: 'sc', style: 'highlight', start_char: f.text.indexOf('block sunlight'), end_char: f.text.indexOf('block sunlight') + 14, src: 'manual' }] }))
  await debaters.ben.unroute(`https://api.github.com/repos/*/*/contents/cards/${world.card}.md*`)
  await select(debaters.ben, '.card .token-text', 'Soot from burning')
  await debaters.ben.keyboard.press('1')
  await expect(debaters.ben.locator('dialog[open]')).toBeVisible({ timeout: 30_000 })
})

Given('the network drops', async ({ debaters }) => {
  await debaters.ben.context().setOffline(true)
})

Then('Ben sees the problem inside the dialog', async ({ debaters }) => {
  await expect(debaters.ben.locator('dialog[open] .error')).toBeVisible()
})

// ------------------------------------------------------------ 18 search, print

Then('the address includes the search', async ({ page, world }) => {
  await expect(page).toHaveURL(new RegExp(`q=${encodeURIComponent(`Searchable soot ${world.run}`).replace(/%20/g, '(\\+|%20)')}`))
})

Then('opening that address shows the same results', async ({ page }) => {
  const url = page.url()
  await page.goto(url)
  await expect(page.locator('input[placeholder]').first()).not.toHaveValue('')
})

Given('cards filed under file {string} in blocks {string} and {string}', async ({ world }, file: string, a: string, b: string) => {
  world.notes.file = `${file} ${world.run}`
  for (const block of [a, b]) {
    const n = await createCard({ title: `${block} ${world.run}`, text: 'Soot from burning cities would block sunlight.' })
    await changeCard(n, `file: ${world.notes.file} / ${block}`, (f) => ({ ...f, file: world.notes.file, block }))
  }
})

When('I print the file {string}', async ({ page, world }, _file: string) => {
  await expect(async () => {
    await open(page, world, `/print/file/${encodeURIComponent(world.notes.file)}`)
    await expect(page.locator('.print-sheet h4')).toHaveCount(2, { timeout: 10_000 })
  }).toPass({ timeout: FIVE_MIN, intervals: [20_000] })
})

Then('the print has the file name, then each block, then each card with its tag, cite and marked text', async ({ page, world }) => {
  await expect(page.locator('.print-sheet h1')).toHaveText(world.notes.file)
  await expect(page.locator('.print-sheet h3')).toHaveText(['Inherency', 'Solvency'])
})

Then('highlighted words print with a highlight color', async ({ page }) => {
  const bg = await page.locator('.print-sheet mark').first().evaluate((el) => getComputedStyle(el).backgroundColor)
  expect(bg).not.toMatch(/rgba\(0, 0, 0, 0\)|transparent/)
})

Then('I see how often the suggestions match the team\'s own highlighting', async ({ page }) => {
  await expect(page.getByText(/match the team’s highlighting \d+% of the time/)).toBeVisible()
})
