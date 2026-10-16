/** Cards: making them, marking words, tag and cite, the three views, and what lands in git. */
import { expect } from '@playwright/test'
import { addSpan, card, commits, createCard, source, spanText } from '../github'
import { Given, Then, When, eventually, open, select } from '../world'

const TOKEN = process.env.SCYTHE_TEST_TOKEN!

// ------------------------------------------------------------ who is here

Given('I am signed in to the team\'s evidence', async ({ world }) => {
  world.storage['scythe.gh.token'] = TOKEN
})

Given('I am not signed in', async ({ world }) => {
  world.storage['scythe.gh.token'] = null
})

// ------------------------------------------------------------ cards made through the passthrough

Given('a card {string} with the text:', async ({ world }, title: string, text: string) => {
  world.card = await createCard({ title: world.sub(title), text: world.sub(text) })
})

Given('a card {string} with the text {string}', async ({ world }, title: string, text: string) => {
  world.card = await createCard({ title: world.sub(title), text: world.sub(text) })
})

Given('another card {string} with the text {string}', async ({ world }, title: string, text: string) => {
  world.other = await createCard({ title: world.sub(title), text: world.sub(text) })
})

Given('a card {string} cut from that source', async ({ world }, title: string) => {
  const s = await source(world.source!)
  world.card = await createCard({ title: world.sub(title), text: s.text.trim(), source: world.source, cite: s.head.cite })
})

Given('the card has a {string} span over {string}', async ({ world }, label: string, phrase: string) => {
  await addSpan(world.card!, label, world.sub(phrase))
})

// ------------------------------------------------------------ on the card page

When('I open the card', async ({ page, world }) => {
  await open(page, world, `/cards/${world.card}`)
  await expect(page.locator('.card .token-text, .card pre.md').first()).toBeVisible()
})

When('I select {string} in the card', async ({ page, world }, phrase: string) => {
  await select(page, '.card .token-text', world.sub(phrase))
})

When('I press {string}', async ({ page }, key: string) => {
  await page.keyboard.press(key)
})

When('I click the marked words {string}', async ({ page, world }, phrase: string) => {
  await page.locator('.card .token-text span[data-span]').filter({ hasText: world.sub(phrase) }).first().click()
})

When('I change the tag to {string}', async ({ page, world }, tag: string) => {
  const input = page.locator('.card-tag input')
  await input.fill(world.sub(tag))
  await input.press('Tab')
})

When('I change the cite to {string}', async ({ page, world }, cite: string) => {
  const input = page.locator('input.card-cite')
  await input.fill(world.sub(cite))
  await input.press('Tab')
})

When('I switch to the read-aloud view', async ({ page }) => {
  await page.locator('.card-meta button', { hasText: /^read$/ }).click()
})

When('I switch to the plain text view', async ({ page }) => {
  await page.locator('.card-meta button', { hasText: /^md$/ }).click()
})

Then('the card shows {string}', async ({ page, world }, text: string) => {
  await expect(page.locator('.card').first()).toContainText(world.sub(text))
})

Then('the card does not show {string}', async ({ page, world }, text: string) => {
  await expect(page.locator('.card .card-body').first()).not.toContainText(world.sub(text))
})

Then('the plain text reads {string}', async ({ page, world }, md: string) => {
  await expect(page.locator('.card pre.md')).toContainText(world.sub(md))
})

Then('the short cite {string} is shown in bold', async ({ page, world }, short: string) => {
  await open(page, world, `/print/${world.card}`)
  await expect(page.locator('.print-sheet strong').first()).toHaveText(world.sub(short))
})

Then('I see {string}', async ({ page, world }, text: string) => {
  await expect(page.getByText(world.sub(text), { exact: false }).first()).toBeVisible()
})

// ------------------------------------------------------------ what git holds

Then('the card in git gains a {string} span over {string}', async ({ world }, label: string, phrase: string) => {
  await eventually(async () => {
    const f = await card(world.card!)
    expect(f.spans.filter((s) => s.label === label).map((s) => spanText(f, s))).toContain(world.sub(phrase))
  })
})

Then('the card in git has a {string} span over {string}', async ({ world }, label: string, phrase: string) => {
  await eventually(async () => {
    const f = await card(world.card!)
    expect(f.spans.filter((s) => s.label === label).map((s) => spanText(f, s))).toContain(world.sub(phrase))
  })
})

Then('the card in git has no {string} span over {string}', async ({ world }, label: string, phrase: string) => {
  await eventually(async () => {
    const f = await card(world.card!)
    expect(f.spans.filter((s) => s.label === label).map((s) => spanText(f, s))).not.toContain(world.sub(phrase))
  })
})

Then('the card\'s text in git is exactly {string}', async ({ world }, text: string) => {
  expect((await card(world.card!)).text).toBe(world.sub(text))
})

Then('the card\'s front matter has {string} {string}', async ({ world }, field: string, value: string) => {
  await eventually(async () => expect((await card(world.card!) as Record<string, unknown>)[field]).toBe(world.sub(value)))
})

Then('the card\'s front matter has "source" set to that source', async ({ world }) => {
  expect((await card(world.card!)).source).toBe(world.source)
})

Then('the card\'s front matter has the topic slug {string}', async ({ world }, slug: string) => {
  expect((await card(world.card!)).topic?.slug).toBe(slug)
})

Then('the first commit to the card reads {string}', async ({ world }, message: string) => {
  const log = await commits(`cards/${world.card}.md`)
  expect(log[log.length - 1].message).toBe(world.sub(message))
})

Then('the latest commit to the card reads {string}', async ({ world }, message: string) => {
  await eventually(async () => expect((await commits(`cards/${world.card}.md`))[0].message).toBe(world.sub(message)))
})

Then('the latest commit to the card starts with {string}', async ({ world }, prefix: string) => {
  await eventually(async () => expect((await commits(`cards/${world.card}.md`))[0].message.startsWith(world.sub(prefix))).toBe(true))
})
