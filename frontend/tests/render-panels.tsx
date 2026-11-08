// Server-renders every React panel against real engine output (JSON files in argv[2]).
// Bundled + run by tests/test_react_panels.py. Exits 1 on any crash or any
// "undefined" / "NaN" / "[object" leaking into the markup.
import React from 'react';
import { renderToString } from 'react-dom/server';
import fs from 'fs';
import path from 'path';
import { ClassicalDepthPanel } from '../src/components/ClassicalDepthPanel';
import { KPSystemPanel } from '../src/components/KPSystemPanel';
import { JaiminiSystemPanel } from '../src/components/JaiminiSystemPanel';
import { AshtottariDasaPanel } from '../src/components/AshtottariDasaPanel';
import { RagCorpusInspector } from '../src/components/RagCorpusInspector';

const panels: Record<string, React.ComponentType<any>> = {
  ClassicalDepthPanel,
  KPSystemPanel,
  JaiminiSystemPanel,
  AshtottariDasaPanel,
  RagCorpusInspector,
};
const BAD = /undefined|NaN|\[object|>null</;

const dir = process.argv[2];
const files = fs.readdirSync(dir).filter((f) => f.startsWith('chart_') && f.endsWith('.json')).sort();
if (files.length === 0) {
  console.error('no chart_*.json fixtures found in', dir);
  process.exit(1);
}

let failed = 0;
for (const f of files) {
  const chart = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
  const light = f.includes('light');
  for (const [name, Panel] of Object.entries(panels)) {
    try {
      const html = renderToString(<Panel chart={chart} />);
      const m = BAD.exec(html);
      // Light charts legitimately have no advanced data: the panels must degrade
      // to an empty state, never crash — but they may not print "undefined" either.
      if (m) {
        const at = html.slice(Math.max(0, m.index - 70), m.index + 40).replace(/\s+/g, ' ');
        console.log(`FAIL ${f} ${name}: "${m[0]}" in output …${at}…`);
        failed++;
      } else {
        console.log(`ok   ${f} ${name}${light ? ' (light)' : ''}`);
      }
    } catch (e: any) {
      console.log(`FAIL ${f} ${name}: threw ${e?.message}`);
      failed++;
    }
  }
}
process.exit(failed ? 1 : 0);
