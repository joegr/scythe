import { defineConfig, devices } from '@playwright/test'
import { defineBddConfig } from 'playwright-bdd'
import { REPO } from './env'

/**
 * Runs every scenario in ../features against real GitHub: the app (Vite, :5174) and the
 * passthrough (:8082) are started here and point at the test evidence repo, joegr/scythe-test.
 * SCYTHE_TEST_TOKEN is a GitHub token with Contents + Issues write there (make e2e passes `gh auth token`).
 * @slow scenarios wait on the GitHub Actions (spaCy worker, article fetcher); SCYTHE_E2E_SLOW=1 adds them.
 */
const slow = !!process.env.SCYTHE_E2E_SLOW
if (!process.env.SCYTHE_TEST_TOKEN) throw new Error('Set SCYTHE_TEST_TOKEN (e.g. SCYTHE_TEST_TOKEN=$(gh auth token) npm run e2e)')

const testDir = defineBddConfig({
  features: '../features/*.feature',
  featuresRoot: '../features',
  steps: ['steps/*.ts', 'world.ts'],
  // Every scenario runs. @partly and @missing are expected to fail until built (see world.ts).
  tags: slow ? undefined : 'not @slow',
  missingSteps: 'fail-on-gen',
})

export default defineConfig({
  testDir,
  timeout: slow ? 8 * 60_000 : 2 * 60_000,
  expect: { timeout: 20_000 },
  // Every scenario writes to GitHub; a few at a time stays clear of its secondary rate limits.
  workers: 3,
  retries: 0,
  reporter: [['list']],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:5174',
    permissions: ['clipboard-read', 'clipboard-write'],
    // A missing control should fail its step quickly, not hang to the test timeout.
    actionTimeout: 15_000,
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      // Only the passthrough's own three dependencies, not the backend's spaCy stack.
      command: 'uv run --no-project --with-requirements ../server/requirements.txt uvicorn --app-dir ../server main:app --port 8082',
      url: 'http://localhost:8082/healthz',
      env: { SCYTHE_REPOS: REPO, ALLOWED_ORIGINS: 'http://localhost:5174' },
      reuseExistingServer: false,
    },
    {
      command: 'cd ../frontend && ./node_modules/.bin/vite --port 5174 --strictPort',
      url: 'http://localhost:5174',
      env: { VITE_SCYTHE_REPO: REPO, VITE_SERVER_URL: 'http://localhost:8082' },
      reuseExistingServer: false,
    },
  ],
})
