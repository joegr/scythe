// Every on-screen string a feature quotes in a "see"/"sees" step must be debate language.
import { readFileSync, readdirSync } from 'node:fs'

const BANNED = /\b(repo|repository|commit|commits|issue|issues|spacy|sha|api|server|rebase|main|markdown|token|tokens|entities)\b/i
const dir = new URL('../features/', import.meta.url)
let bad = 0
for (const name of readdirSync(dir).filter((f) => f.endsWith('.feature'))) {
  readFileSync(new URL(name, dir), 'utf8').split('\n').forEach((line, i) => {
    if (!/^\s*(Then|And|But|When|Given)\b.*\bsees?\b/.test(line)) return
    for (const [, quoted] of line.matchAll(/"((?:[^"\\]|\\.)*)"/g)) {
      if (BANNED.test(quoted)) { bad++; console.log(`${name}:${i + 1}: "${quoted}"`) }
    }
  })
}
console.log(bad ? `${bad} on-screen strings use developer words` : 'every quoted on-screen string is debate language')
process.exit(bad ? 1 : 0)
