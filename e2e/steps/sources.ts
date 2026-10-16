/** Sources and the reader: pasting, fetching by link, finding a passage, cutting. */
import { expect, type Page } from '@playwright/test'
import { card, createSource, issue, source } from '../github'
import { Given, Then, When, cardNumberFrom, eventually, open, select } from '../world'

const reader = (page: Page) => page.locator('dialog[open]')

Given('a pasted source {string} by {string} in {string} on {string} with text:', async ({ world }, title: string, author: string, publisher: string, date: string, text: string) => {
  const t = world.sub(title)
  // No stored cite: the reader drafts one from these details, as it does for a debater's paste.
  world.source = await createSource({ title: t, authors: [author], publisher, published: date }, world.sub(text))
})

When('I open the reader', async ({ page, world }) => {
  await open(page, world, '/')
  await page.getByRole('button', { name: 'Open a source' }).click()
  await expect(reader(page)).toBeVisible()
})

When('I open that source in the reader', async ({ page, world }) => {
  const { title } = (await source(world.source!)).head
  await open(page, world, '/')
  await expect(async () => {
    if (await reader(page).isVisible()) await reader(page).getByRole('button', { name: 'close' }).click()
    await page.getByRole('button', { name: 'Open a source' }).click()
    await reader(page).getByRole('button', { name: title }).click({ timeout: 4_000 })
  }).toPass({ timeout: 60_000 })
  await expect(reader(page).locator('.reader-text')).toBeVisible()
})

When('I select {string} in the source', async ({ page, world }, phrase: string) => {
  await select(page, 'dialog[open] .reader-text', world.sub(phrase))
})

When('I write the tag {string}', async ({ page, world }, tag: string) => {
  await reader(page).locator('input[placeholder="Tag"]').fill(world.sub(tag))
})

When('I cut the card', async ({ page }) => {
  await reader(page).getByRole('button', { name: 'Cut', exact: true }).click()
})

Then('I am on the new card', async ({ page, world }) => {
  await expect(page).toHaveURL(/#\/cards\/\d+/, { timeout: 30_000 })
  world.card = cardNumberFrom(page.url())
  await expect(page.locator('.card .token-text')).toBeVisible()
})

Then('the cut button is disabled', async ({ page }) => {
  await expect(reader(page).getByRole('button', { name: 'Cut', exact: true })).toBeDisabled()
})

Then('the cut button is enabled', async ({ page }) => {
  await expect(reader(page).getByRole('button', { name: 'Cut', exact: true })).toBeEnabled()
})

Then('the cite field reads {string}', async ({ page, world }, cite: string) => {
  await expect(reader(page).locator('input[placeholder="Cite"]')).toHaveValue(world.sub(cite))
})

When('I find the copied passage {string}', async ({ page }, passage: string) => {
  await reader(page).locator('input[placeholder="Paste a copied passage to find it"]').fill(passage)
  await reader(page).getByRole('button', { name: 'find', exact: true }).click()
})

Then('the selection is {int} characters', async ({ page }, n: number) => {
  await expect(reader(page).getByText(`${n.toLocaleString()} characters`)).toBeVisible()
})

// ------------------------------------------------------------ pasting

When('I paste the article text:', async ({ page, world }, text: string) => {
  await reader(page).locator('textarea').fill(world.sub(text))
})

When('I fill in the title {string}, link {string}, authors {string}, publication {string} and date {string}', async ({ page, world }, title: string, link: string, authors: string, publication: string, date: string) => {
  const r = reader(page)
  await r.locator('input[placeholder="Title"]').fill(world.sub(title))
  await r.locator('input[placeholder="Link"]').fill(link)
  await r.locator('input[placeholder="Authors, separated by commas"]').fill(authors)
  await r.locator('input[placeholder="Publication"]').fill(publication)
  await r.locator('input[placeholder="Date, YYYY-MM-DD"]').fill(date)
})

When('I read the pasted article', async ({ page }) => {
  await reader(page).getByRole('button', { name: 'Read', exact: true }).click()
})

/** The reader's byline links the source's issue as "#n"; remember n. */
async function rememberSource(page: Page, world: { source?: number }) {
  const n = await reader(page).locator('p a', { hasText: /^#\d+$/ }).first().textContent()
  world.source = Number(n!.slice(1))
}

Then('the reader shows the source {string}', async ({ page, world }, title: string) => {
  await expect(reader(page).locator('h1')).toHaveText(world.sub(title), { timeout: 30_000 })
  await rememberSource(page, world)
})

Then('within 5 minutes the reader shows the source {string}', async ({ page, world }, title: string) => {
  await expect(reader(page).locator('h1')).toHaveText(world.sub(title), { timeout: 5 * 60_000 })
  await rememberSource(page, world)
})

Then('the reader shows {string}', async ({ page, world }, text: string) => {
  await expect(reader(page).locator('.reader-text')).toContainText(world.sub(text))
})

Then('the source\'s front matter has "authors" [{string}], "publisher" {string} and "published" {string}', async ({ world }, author: string, publisher: string, published: string) => {
  const { head } = await source(world.source!)
  expect(head.authors).toEqual([author])
  expect(head.publisher).toBe(publisher)
  expect(head.published).toBe(published)
})

Then('the source\'s text in git is exactly:', async ({ world }, text: string) => {
  expect((await source(world.source!)).text.trimEnd()).toBe(world.sub(text).trimEnd())
})

Then('the source\'s file in git has {string} {string}', async ({ world }, field: string, value: string) => {
  expect(((await source(world.source!)).head as unknown as Record<string, unknown>)[field]).toBe(value)
})

Then('the source\'s text in git has no blank line inside a paragraph and exactly one between paragraphs', async ({ world }) => {
  const { text } = await source(world.source!)
  expect(text).not.toMatch(/\n{3,}/)
  expect(text.split('\n\n').every((p) => p.trim() && !p.includes('\n'))).toBe(true)
})

Then('the source\'s issue has the label {string}', async ({ world }, label: string) => {
  await eventually(async () => expect((await issue(world.source!)).labelNames).toContain(label), 60_000)
})

// ------------------------------------------------------------ fetching and the shelf

When('I fetch the link {string}', async ({ page }, url: string) => {
  await reader(page).getByRole('button', { name: 'fetch a link' }).click()
  await reader(page).locator('input[type="url"]').fill(url)
  await reader(page).locator('input[type="url"]').press('Enter')
})

When('I open the card\'s source', async ({ page, world }) => {
  await page.getByRole('button', { name: `source #${world.source}` }).click()
  await expect(reader(page).locator('.reader-text')).toBeVisible()
})

Then('the recent sources include {string}', async ({ page, world }, title: string) => {
  await expect(async () => {
    if (await reader(page).isVisible()) await reader(page).getByRole('button', { name: 'close' }).click()
    await page.getByRole('button', { name: 'Open a source' }).click()
    await expect(reader(page).getByRole('button', { name: world.sub(title) })).toBeVisible({ timeout: 4_000 })
  }).toPass({ timeout: 60_000 })
})

Then('within 5 minutes the card\'s issue is a sub-issue of the source\'s issue', async ({ world }) => {
  const { api } = await import('../github')
  await eventually(async () => {
    const subs = await api<{ number: number }[]>('GET', `/repos/{repo}/issues/${world.source}/sub_issues`)
    expect(subs.map((s) => s.number)).toContain(world.card)
  }, 5 * 60_000)
  expect((await card(world.card!)).source).toBe(world.source)
})
