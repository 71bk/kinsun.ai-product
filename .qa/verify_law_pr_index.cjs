// Read-only verification of the exact staged RAG audit inputs and evidence.
const fs = require('node:fs');
const cp = require('node:child_process');
const crypto = require('node:crypto');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const git = (...args) => cp.execFileSync('git', ['-c', `safe.directory=${root.replaceAll('\\', '/')}`, ...args], { cwd: root, maxBuffer: 32 * 1024 * 1024 });
const hash = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const read = (name) => fs.readFileSync(path.join(root, name));
const inventory = JSON.parse(read('data/rag-v3/governance/source-family-policy/audits/v010/preflight/validation-input-inventory.json'));
const entries = inventory.entries;
if (!Array.isArray(entries)) throw new Error('Unknown audit inventory shape');
const mismatches = entries.filter((entry) => hash(git('show', `:${entry.path}`)) !== entry.sha256).map((entry) => entry.path);
const staged = git('diff', '--cached', '--name-only', '-z').toString('utf8').split('\0').filter(Boolean);
const normalizedDocumentation = [];
const byteDrift = staged.filter((name) => {
  const indexed = git('show', `:${name}`);
  const local = read(name);
  if (indexed.equals(local)) return false;
  if (['AGENTS.md', 'CLAUDE.md'].includes(name) && indexed.equals(Buffer.from(local.toString('utf8').replaceAll('\r\n', '\n')))) {
    normalizedDocumentation.push(name);
    return false;
  }
  return true;
});
const secrets = [];
const env = read('.env').toString('utf8');
const protectedValues = env.split(/\r?\n/).flatMap((line) => {
  const match = line.match(/^([A-Z0-9_]*(?:SECRET|PASSWORD|TOKEN|API_KEY|DATABASE_URL)[A-Z0-9_]*)\s*=\s*(.+)$/);
  if (!match) return [];
  const value = match[2].trim().replace(/^(['"])(.*)\1$/, '$2');
  return value.length >= 12 && !value.includes('${') ? [value] : [];
});
for (const name of staged) {
  const bytes = git('show', `:${name}`);
  if (protectedValues.some((value) => bytes.includes(Buffer.from(value)))) secrets.push(name);
}
console.log(JSON.stringify({ auditInputs: entries.length, stagedFiles: staged.length, mismatches, byteDrift, normalizedDocumentation, secretMatchFiles: secrets }));
if (mismatches.length || byteDrift.length || secrets.length) process.exitCode = 1;
