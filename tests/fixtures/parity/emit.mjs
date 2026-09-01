/**
 * Emisor de paridad — runtime JS.
 *
 * Resuelve el fixture canónico e imprime en stdout el JSON de valores,
 * ordenado por clave y con indentación de 2. Nada más va a stdout.
 *
 * Solo usa API pública común a ambos runtimes (`ConfigManager`, `load`,
 * `get`). Ver la fila D7 de PARITY.md.
 *
 * Requiere `npm run build` previo. Uso, desde la raíz del repo:
 *     node tests/fixtures/parity/emit.mjs
 */
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { parse } from 'yaml';

const fixtureDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(fixtureDir, '..', '..', '..');

const { ConfigManager } = await import(join(repoRoot, 'dist', 'index.js'));

process.chdir(fixtureDir);

const names = Object.keys(parse(readFileSync('config.yaml', 'utf8')).variables).sort();

const manager = new ConfigManager('config.yaml');
await manager.load();

const values = {};
for (const name of names) values[name] = manager.get(name);
console.log(JSON.stringify(values, null, 2));
