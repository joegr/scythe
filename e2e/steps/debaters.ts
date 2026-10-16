/** Two debaters, one card: same-second saves and the three ways to settle a stopped save. */
import { expect, type Page } from '@playwright/test'
import { card, commits, spanText } from '../github'
import { Given, Then, When, select } from '../world'

const LABEL_KEY: Record<string, string> = { underline: '1', highlight: '2', emphasis: '3' }
const stopped = (p: Page) => p.locator('dialog[open]', { has: p.locator('pre.md') })
const settled = async (p: Page) => !(await p.getByText('committing…').isVisible())

async function openCard(p: Page, n: number) {
  await p.goto(`/#/cards/${n}`)
  await expect(p.locator('.card .token-text')).toBeVisible()
  await expect(p.getByText(/^at [0-9a-f]{7}$/)).toBeVisible()
}

/**
 * Hold a page at the card version it loaded: while the Action hasn't processed the card, the page
 * re-reads it every 6s, which would quietly move it onto the partner's save. A debater who
 * started editing before that refresh is exactly the case under test.
 */
async function holdVersion(p: Page, n: number) {
  let first: { status: number; headers: Record<string, string>; body: string } | null = null
  await p.route(`https://api.github.com/repos/*/*/contents/cards/${n}.md*`, async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    if (!first) {
      const res = await route.fetch()
      first = { status: res.status(), headers: res.headers(), body: await res.text() }
    }
    await route.fulfill(first)
  })
}
const release = (p: Page, n: number) => p.unroute(`https://api.github.com/repos/*/*/contents/cards/${n}.md*`)

Given('Ana and Ben are signed in to the team\'s evidence', async ({ debaters }) => {
  expect(debaters.ana).toBeTruthy()
})

Given('Ana and Ben both have the card open at the same version', async ({ debaters, world }) => {
  await Promise.all([holdVersion(debaters.ana, world.card!), holdVersion(debaters.ben, world.card!)])
  await Promise.all([openCard(debaters.ana, world.card!), openCard(debaters.ben, world.card!)])
})

When('Ana selects {string} and Ben selects {string}', async ({ debaters }, a: string, b: string) => {
  await select(debaters.ana, '.card .token-text', a)
  await select(debaters.ben, '.card .token-text', b)
})

When('Ana presses {string} and Ben presses {string} in the same second', async ({ debaters, world }, a: string, b: string) => {
  await Promise.all([release(debaters.ana, world.card!), release(debaters.ben, world.card!)])
  await Promise.all([debaters.ana.keyboard.press(a), debaters.ben.keyboard.press(b)])
})

Then('exactly one of their saves lands', async ({ debaters, world }) => {
  const { ana, ben } = debaters
  await expect(async () => {
    expect(await settled(ana) && await settled(ben)).toBe(true)
    expect(await stopped(ana).count() + await stopped(ben).count()).toBe(1)
  }).toPass({ timeout: 30_000 })
  const f = await card(world.card!)
  const marks = f.spans.map((s) => `${s.label} ${spanText(f, s)}`)
  expect(marks.length).toBe(1)
  world.notes.winner = (await stopped(ana).count()) ? 'ben' : 'ana'
  world.notes.landed = marks[0]
})

Then('the other is shown the change that landed and their own unsaved change', async ({ debaters, world }) => {
  const loser = world.notes.winner === 'ana' ? debaters.ben : debaters.ana
  const [landedLabel, ...words] = world.notes.landed!.split(' ')
  const lists = stopped(loser).locator('pre.md')
  await expect(lists.nth(0)).toContainText(`+ ${landedLabel} “${words.join(' ')}”`)
  await expect(lists.nth(1)).toContainText('+ ')
  await expect(lists.nth(1)).not.toContainText(words.join(' '))
})

Given('Ana\'s {string} over {string} landed first and Ben\'s {string} over {string} was stopped', async ({ debaters, world }, aLabel: string, aWords: string, bLabel: string, bWords: string) => {
  const { ana, ben } = debaters
  await release(ana, world.card!)
  await select(ana, '.card .token-text', aWords)
  await ana.keyboard.press(LABEL_KEY[aLabel])
  await expect(async () => expect((await commits(`cards/${world.card}.md`))[0].message.startsWith(`${aLabel}:`)).toBe(true)).toPass({ timeout: 30_000 })
  await select(ben, '.card .token-text', bWords)
  await ben.keyboard.press(LABEL_KEY[bLabel])
  await expect(stopped(ben)).toBeVisible({ timeout: 30_000 })
  await release(ben, world.card!)
})

When('Ben takes the {word} choice', async ({ debaters }, which: string) => {
  const buttons = stopped(debaters.ben).getByRole('button')
  await buttons.nth({ first: 0, second: 1, third: 2 }[which]!).click()
  await expect(stopped(debaters.ben)).toHaveCount(0, { timeout: 30_000 })
})

Then('the card\'s history has both commits', async ({ world }) => {
  const log = (await commits(`cards/${world.card}.md`)).map((c) => c.message)
  expect(log.some((m) => m.startsWith('highlight:'))).toBe(true)
  expect(log.some((m) => m.startsWith('underline:'))).toBe(true)
})

Then('the card\'s history still has Ana\'s commit', async ({ world }) => {
  const log = (await commits(`cards/${world.card}.md`)).map((c) => c.message)
  expect(log.some((m) => m.startsWith('highlight:'))).toBe(true)
})

Then('Ben\'s page shows the card as Ana saved it', async ({ debaters }) => {
  await expect(debaters.ben.locator('.card .t-hl')).toHaveText('block sunlight')
  await expect(debaters.ben.locator('.card .t-u')).toHaveCount(0)
})
