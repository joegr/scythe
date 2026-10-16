/** Signing in and the team, resolutions, files and blocks, links, history, search, print, copy,
 *  and what the spaCy Action writes to the card's issue. */
import { expect } from '@playwright/test'
import { api, card, changeCard, commits, issue, readFile, TOPICS } from '../github'
import { REPO } from '../env'
import { Given, Then, When, eventually, open } from '../world'

// ------------------------------------------------------------ signing in and the team

When('I open Scythe', async ({ page, world }) => {
  await open(page, world, '/')
  await expect(page.locator('nav.top')).toBeVisible()
})

When('I start signing in', async ({ page }) => {
  await page.locator('nav.top').getByRole('button', { name: 'sign in' }).click()
})

const signInLink = async (page: import('@playwright/test').Page) =>
  new URL((await page.locator('a[href^="https://github.com/settings/personal-access-tokens/new"]').getAttribute('href'))!)

Then('the sign-in link opens GitHub\'s new fine-grained token page', async ({ page }) => {
  expect((await signInLink(page)).pathname).toBe('/settings/personal-access-tokens/new')
})

Then('the link asks for {string} {string} and {string} {string}', async ({ page }, a: string, av: string, b: string, bv: string) => {
  const q = (await signInLink(page)).searchParams
  expect(q.get(a)).toBe(av)
  expect(q.get(b)).toBe(bv)
})

Then('the link sets the key to expire in {string} days and belong to {string}', async ({ page }, days: string, owner: string) => {
  const q = (await signInLink(page)).searchParams
  expect(q.get('expires_in')).toBe(days)
  expect(q.get('target_name')).toBe(owner)
})

When('I open the team settings', async ({ page }) => {
  await page.locator('nav.top').getByRole('button', { name: REPO }).click()
})

Then('the settings have exactly one field, for the team\'s evidence', async ({ page }) => {
  await expect(page.locator('input, textarea, select')).toHaveCount(1)
  await expect(page.locator('input')).toHaveValue(REPO)
})

Then('the settings have no field for where Scythe saves', async ({ page }) => {
  await expect(page.getByText(/GitHub API|Scythe server|Local Scythe API/)).toHaveCount(0)
})

Given('this browser still has old saved addresses for the GitHub API and the passthrough', async ({ world }) => {
  Object.assign(world.storage, { 'scythe.gh.api': 'http://127.0.0.1:9', 'scythe.server': 'http://127.0.0.1:9', 'scythe.api': 'http://127.0.0.1:9' })
})

// ------------------------------------------------------------ resolutions

Given('my resolution is {string}', async ({ world }, slug: string) => {
  const t = TOPICS.find((x) => x.slug === slug)!
  world.storage['scythe.topic'] = JSON.stringify({ ...t, origin: 'nsda' })
})

Given('I have not chosen a resolution yet', async ({ world }) => {
  world.storage['scythe.topic'] = null
})

When('I paste a clip {string} tagged {string}', async ({ page, world }, text: string, tag: string) => {
  await open(page, world, '/')
  await page.getByRole('button', { name: 'paste a clip' }).click()
  await page.locator('input[placeholder="Tag"]').fill(world.sub(tag))
  await page.locator('textarea[placeholder="Any text to label"]').fill(world.sub(text))
  await page.getByRole('button', { name: 'Create card' }).click()
})

When('I open the resolution picker', async ({ page, world }) => {
  await open(page, world, '/')
  await page.locator('p', { hasText: 'Topic:' }).getByRole('button').click()
  await expect(page.locator('dialog[open] h1')).toBeVisible()
})

When('I search resolutions for {string}', async ({ page }, q: string) => {
  await page.locator('dialog[open] input[placeholder="Search resolutions"]').fill(q)
})

When('I filter to {string}', async ({ page }, event: string) => {
  await page.locator('dialog[open]').getByRole('button', { name: event, exact: true }).click()
})

When('I choose the resolution with slug {string}', async ({ page }, slug: string) => {
  const t = TOPICS.find((x) => x.slug === slug)!
  await page.locator('dialog[open] button.plain', { hasText: t.resolution }).first().click()
})

Then('the list includes {string}', async ({ page }, resolution: string) => {
  await expect(page.locator('dialog[open] button.plain', { hasText: resolution }).first()).toBeVisible()
})

Then('the next card I make uses that resolution without asking', async ({ page, world }) => {
  const slug = (await card(world.card!)).topic?.slug
  expect(JSON.parse((await page.evaluate(() => localStorage.getItem('scythe.topic')))!).slug).toBe(slug)
})

When('I write my own resolution {string}', async ({ page, world }, resolution: string) => {
  await page.locator('dialog[open] input[placeholder="Resolved: …"]').fill(world.sub(resolution))
  await page.locator('dialog[open]').getByRole('button', { name: 'Use this topic' }).click()
  await expect(page.locator('dialog[open]')).toHaveCount(0, { timeout: 30_000 })
})

Then('scythe.json lists a topic with resolution {string} and a slug starting {string}', async ({ world }, resolution: string, prefix: string) => {
  await eventually(async () => {
    const topics = JSON.parse((await readFile('scythe.json'))!.text).topics as { slug: string; resolution: string }[]
    const t = topics.find((x) => x.resolution === world.sub(resolution))
    expect(t?.slug.startsWith(prefix)).toBe(true)
  })
})

// ------------------------------------------------------------ files, blocks, approval

When('I file it under file {string} and block {string}', async ({ page, world }, file: string, block: string) => {
  await page.locator('input[placeholder="File"]').fill(world.sub(file))
  await page.locator('input[placeholder="Block"]').fill(world.sub(block))
  await page.getByRole('button', { name: 'file it' }).click()
})

Then('the card\'s front matter has "file" {string} and "block" {string}', async ({ world }, file: string, block: string) => {
  await eventually(async () => {
    const f = await card(world.card!)
    expect([f.file, f.block]).toEqual([world.sub(file), world.sub(block)])
  })
})

When('I approve the card', async ({ page }) => {
  await page.locator('.card-meta').getByRole('button', { name: 'approve', exact: true }).click()
})

When('I unapprove the card', async ({ page }) => {
  await page.locator('.card-meta').getByRole('button', { name: 'unapprove', exact: true }).click()
})

Then('the card\'s front matter has "approved" {word}', async ({ world }, value: string) => {
  await eventually(async () => expect((await card(world.card!)).approved).toBe(value === 'true'))
})

Given('the card is filed under file {string} and block {string}', async ({ world }, file: string, block: string) => {
  await changeCard(world.card!, `file: ${world.sub(file)} / ${block}`, (f) => ({ ...f, file: world.sub(file), block }))
})

When('I open the library', async ({ page, world }) => {
  await open(page, world, '/library')
})

When('I open the file {string}', async ({ page, world }, file: string) => {
  await page.getByRole('button', { name: world.sub(file), exact: true }).click()
})

Then('I see the block {string} with the card {string}', async ({ page, world }, block: string, title: string) => {
  const section = page.locator('section', { has: page.locator('h2', { hasText: block }) })
  await expect(section.getByText(world.sub(title))).toBeVisible()
})

// ------------------------------------------------------------ links

When('I open the other card', async ({ page, world }) => {
  await open(page, world, `/cards/${world.other}`)
  await expect(page.locator('.card .token-text')).toBeVisible()
})

When('I open the first card', async ({ page, world }) => {
  await open(page, world, `/cards/${world.card}`)
  await expect(page.locator('.card .token-text')).toBeVisible()
})

When('I link it with {string} to {string}', async ({ page, world }, relation: string, title: string) => {
  await page.locator('select').selectOption({ label: relation })
  const box = page.locator('input[placeholder="Search cards to link…"]')
  const pick = page.getByRole('button', { name: `${relation} #${world.card}` })
  // GitHub's search index takes a little while to see a new card; retype until it does.
  await expect(async () => {
    await box.fill('')
    await box.fill(world.sub(title))
    await expect(pick).toBeVisible({ timeout: 5_000 })
  }).toPass({ timeout: 3 * 60_000 })
  await pick.click()
})

Given('the other card links {string} to the first card', async ({ world }, rel: string) => {
  await changeCard(world.other!, `${rel.replace('_', ' ')} #${world.card}`, (f) => ({ ...f, links: [...f.links, { rel, to: world.card! }] }))
})

Then('the other card\'s front matter links {string} to the first card', async ({ world }, rel: string) => {
  await eventually(async () => expect((await card(world.other!)).links).toContainEqual({ rel, to: world.card }))
})

Then('the other card\'s front matter has no links', async ({ world }) => {
  await eventually(async () => expect((await card(world.other!)).links).toEqual([]))
})

Then('the latest commit to the other card reads {string}', async ({ world }, message: string) => {
  await eventually(async () => expect((await commits(`cards/${world.other}.md`))[0].message).toBe(world.sub(message)))
})

Then('the other card shows {string}', async ({ page }, text: string) => {
  await expect(page.locator('section', { has: page.locator('h3', { hasText: 'Links' }) })).toContainText(text)
})

When('I unlink {string} to the first card', async ({ page, world }, rel: string) => {
  const words: Record<string, string> = { supports: 'Supports', answers: 'Answers', contradicts: 'Contradicts' }
  const row = page.locator('li.row', { hasText: words[rel] }).filter({ has: page.getByRole('link', { name: `#${world.card}` }) })
  await row.getByRole('button', { name: 'unlink' }).click()
})

Then('within 5 minutes the first card\'s page lists {string}', async ({ page, world }, title: string) => {
  await expect(async () => {
    await open(page, world, `/cards/${world.card}`)
    await expect(page.locator('section', { has: page.locator('h3', { hasText: 'Links' }) }).getByText(world.sub(title))).toBeVisible({ timeout: 10_000 })
  }).toPass({ timeout: 5 * 60_000, intervals: [15_000] })
})

// ------------------------------------------------------------ history

When('I open the card\'s history', async ({ page }) => {
  await page.getByRole('button', { name: 'history', exact: true }).click()
})

const historyRows = (page: import('@playwright/test').Page) =>
  page.locator('section', { has: page.getByRole('button', { name: 'hide history' }) }).locator('li')

Then('the history lists, newest first:', async ({ page, world }, table: { raw: () => string[][] }) => {
  const expected = table.raw().map((r) => world.sub(r[0]))
  await expect(async () => {
    const rows = await historyRows(page).allTextContents()
    expect(rows.length).toBe(expected.length)
    expected.forEach((m, i) => expect(rows[i]).toContain(m))
  }).toPass({ timeout: 30_000 })
})

Then('each history entry names who made it', async ({ page }) => {
  const login = (await api<{ login: string }>('GET', '/user')).login
  for (const row of await historyRows(page).allTextContents()) expect(row).toContain(`${login},`)
})

// ------------------------------------------------------------ search, print, copy

When('I search the team\'s evidence for {string}', async ({ page, world }, q: string) => {
  await open(page, world, '/search')
  await page.locator('input[placeholder="Search cards on GitHub"]').fill(world.sub(q))
})

Then('within 3 minutes the results include {string}', async ({ page, world }, title: string) => {
  const box = page.locator('input.field').first()
  await expect(async () => {
    const q = await box.inputValue()
    await box.fill(''); await box.fill(q)
    await expect(page.locator('.card-tag', { hasText: world.sub(title) })).toBeVisible({ timeout: 8_000 })
  }).toPass({ timeout: 3 * 60_000, intervals: [10_000] })
})

When('I open the card\'s print page', async ({ page, world }) => {
  await open(page, world, `/print/${world.card}`)
})

Then('the print shows the tag {string}', async ({ page, world }, tag: string) => {
  await expect(page.locator('.print-sheet h4')).toHaveText(world.sub(tag))
})

Then('the print shows {string} highlighted', async ({ page }, text: string) => {
  await expect(page.locator('.print-sheet mark')).toHaveText(text)
})

When('I copy the card', async ({ page }) => {
  await page.locator('.card-meta').getByRole('button', { name: 'copy' }).click()
  await expect(page.locator('.card-meta').getByRole('button', { name: 'copied' })).toBeVisible()
})

const clipboardHtml = (page: import('@playwright/test').Page) => page.evaluate(async () => {
  const [item] = await navigator.clipboard.read()
  return (await item.getType('text/html')).text()
})

Then('the clipboard\'s HTML draws {string} with background {string}', async ({ page }, text: string, color: string) => {
  expect(await clipboardHtml(page)).toMatch(new RegExp(`<span style="[^"]*background:${color}[^"]*">${text}</span>`))
})

Then('the clipboard\'s HTML draws unmarked words at {string}', async ({ page }, size: string) => {
  expect(await clipboardHtml(page)).toContain(`font-size:${size}`)
})

// ------------------------------------------------------------ the spaCy Action's issue writes (@slow)

const FIVE_MIN = 5 * 60_000

Then('within 5 minutes the card\'s issue records processed.file_sha equal to the card\'s blob sha', async ({ world }) => {
  await eventually(async () => {
    const [i, f] = await Promise.all([issue(world.card!), card(world.card!)])
    expect(i.meta?.processed?.file_sha).toBe(f.sha)
  }, FIVE_MIN)
})

Then('the issue\'s {string} span over {string} has token offsets with start before end', async ({ world }, label: string, phrase: string) => {
  const { meta } = await issue(world.card!)
  const s = meta!.spans.find((x) => x.label === label && meta!.text.slice(x.start_char, x.end_char) === phrase)
  expect(s && s.start !== undefined && s.end !== undefined && s.start < s.end).toBe(true)
})

Then('within 5 minutes the card\'s issue body contains {string}', async ({ world }, text: string) => {
  await eventually(async () => expect((await issue(world.card!)).body).toContain(text), FIVE_MIN)
})

Then('the card\'s issue body contains {string}', async ({ world }, text: string) => {
  expect((await issue(world.card!)).body).toContain(text)
})

Then('the card\'s issue has the labels {string} and {string}', async ({ world }, a: string, b: string) => {
  expect((await issue(world.card!)).labelNames).toEqual(expect.arrayContaining([world.sub(a), world.sub(b)]))
})

Then('within 5 minutes the card\'s issue has the labels {string} and {string}', async ({ world }, a: string, b: string) => {
  await eventually(async () => expect((await issue(world.card!)).labelNames).toEqual(expect.arrayContaining([world.sub(a), world.sub(b)])), FIVE_MIN)
})

Then('within 5 minutes the card\'s issue lists these entities:', async ({ world }, table: { hashes: () => { label: string; text: string }[] }) => {
  await eventually(async () => {
    const { meta } = await issue(world.card!)
    const ents = (meta?.spans ?? []).filter((s) => s.key === 'ents').map((s) => ({ label: s.label, text: meta!.text.slice(s.start_char, s.end_char) }))
    for (const e of table.hashes()) expect(ents).toContainEqual(e)
  }, FIVE_MIN)
})
