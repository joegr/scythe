// Count scenarios per feature by status tag (@built / @partly / @missing), expanding Scenario
// Outline examples, and print the Markdown table used in features/README.md.
import { readFileSync, readdirSync } from 'node:fs'

const dir = new URL('../features/', import.meta.url)
const STATUSES = ['built', 'partly', 'missing']
const rows = []
for (const name of readdirSync(dir).filter((f) => f.endsWith('.feature')).sort()) {
  const counts = { built: 0, partly: 0, missing: 0 }
  let tags = []
  let outline = null // { tags } while inside a Scenario Outline
  let examples = null // { tags } while inside an Examples table
  let header = false
  for (const raw of readFileSync(new URL(name, dir), 'utf8').split('\n')) {
    const line = raw.trim()
    if (line.startsWith('@')) { tags.push(...line.split(/\s+/)); continue }
    if (/^Scenario Outline:/.test(line)) { outline = { tags }; examples = null; tags = []; continue }
    if (/^Scenario:/.test(line)) {
      const s = STATUSES.find((t) => tags.includes(`@${t}`))
      if (s) counts[s]++
      outline = null; examples = null; tags = []; continue
    }
    if (/^Examples:/.test(line) && outline) { examples = { tags: [...outline.tags, ...tags] }; header = true; tags = []; continue }
    if (line.startsWith('|') && examples) {
      if (header) { header = false; continue }
      const s = STATUSES.find((t) => examples.tags.includes(`@${t}`))
      if (s) counts[s]++
      continue
    }
    if (line && !line.startsWith('#')) tags = []
  }
  rows.push([name, counts])
}
const total = { built: 0, partly: 0, missing: 0 }
console.log('| Feature | Built | Partly | Missing |\n| --- | ---: | ---: | ---: |')
for (const [name, c] of rows) {
  STATUSES.forEach((s) => (total[s] += c[s]))
  console.log(`| \`${name}\` | ${c.built} | ${c.partly} | ${c.missing} |`)
}
console.log(`| **All 18** | **${total.built}** | **${total.partly}** | **${total.missing}** |`)
