import React from 'react';
import { ChartResponse } from '../types/astrology';
import { firstWord, isCurrentPeriod } from '../lib/format';

interface Props {
  chart: ChartResponse;
}

export const RagCorpusInspector: React.FC<Props> = ({ chart }) => {
  const calcType = (chart.metadata?.calc_type || 'drik').toUpperCase();
  const dasaSys = (chart.metadata?.dasa_system || 'vimshottari').toUpperCase();
  const ayanamsa = chart.metadata?.ayanamsa_name || 'Lahiri';

  const queries: string[] = [];
  const jaimini = chart.jaimini;
  const kp = chart.kp;
  const arudha = chart.arudha_padas;
  const khara = chart.khara_drekkana;
  const pada = (a?: { pada_rasi_short?: string }) => a?.pada_rasi_short || '';

  if (calcType === 'JAIMINI' || dasaSys === 'CHARA') {
    const ak = jaimini?.atmakaraka;
    const krasi = firstWord(jaimini?.karakamsa_rasi_name);
    if (ak?.planet) queries.push(`Atmakaraka Karakamsa ${ak.planet} ${krasi} (BPHS Ch. 32–33)`);
    queries.push('Chara Dasa Jaimini rasi periods (BPHS Ch. 46)');
  }

  if (dasaSys === 'ASHTOTTARI') {
    const ashDasas = chart.ashtottari_dasas?.dasas || [];
    const running = ashDasas.find((d) => isCurrentPeriod(d.start_date, d.end_date)) || ashDasas[0];
    queries.push(`Astottari dasa ${running?.dasa_lord || 'Sun'} mahadasa bhukti (BPHS Vol. 2 Ch. 46)`);
  }

  if (calcType === 'KP' && kp && Array.isArray(kp.cusps) && kp.cusps.length >= 10) {
    const c1 = kp.cusps[0];
    const c10 = kp.cusps[9];
    const c7 = kp.cusps[6];
    queries.push(`${c1.star_lord} nakshatra ${c1.sub_lord} ascendant lagna`);
    queries.push(`${c10.sub_lord} tenth house karma bhava career profession`);
    queries.push(`${c7.sub_lord} seventh house kalatra bhava marriage spouse`);
  }

  if (calcType === 'NADI') {
    const moonNaks = chart.placements?.Moon?.nakshatra || 'Ashwini';
    queries.push(`nakshatra ${moonNaks} pada trine linkage`);
  }

  const lagnaRasi = firstWord(chart.placements?.Lagna?.rasi_name) || 'Mesha';
  queries.push(`${lagnaRasi} lagna ascendant personality (Saravali & Phaladeepika)`);
  queries.push('planetary avastha Sayanadi Deepta Kumara Yuva (BPHS Ch. 45)');
  if (arudha?.arudha_lagna) {
    queries.push(`Arudha Pada ${pada(arudha.arudha_lagna)} Upapada ${pada(arudha.upapada_lagna)} (BPHS Ch. 29)`);
  }
  if (khara?.rasi_short && khara.nature) {
    queries.push(`22nd Drekkana Khara ${firstWord(khara.nature)} (Saravali Ch. 10 & Jataka Parijata)`);
  }

  return (
    <div className="vx-panel-section" id="react-rag-inspector-panel">
      <div className="vx-panel-header">
        <div>
          <h4>
            <i className="fa-solid fa-book-journal-whills" /> Classical Corpus RAG Grounding Engine (3,710 Pages · 8 Scriptures)
          </h4>
          <p>
            Active Pipeline: <strong>{calcType}</strong> System · <strong>{dasaSys}</strong> Dasa ·{' '}
            <strong>{ayanamsa}</strong> Ayanamsa. Hybrid Dense (1536-dim) + FTS5 BM25 search across{' '}
            <em>Brihat Parasara Hora Sastra (Vol 1 & 2), Jataka Parijata (Vol 1–3), Saravali (Vol 1–2),</em> and{' '}
            <em>Phaladeepika</em>.
          </p>
        </div>
        <div className="vx-rag-actions">
          <button
            type="button"
            className="btn-primary"
            style={{ fontSize: '11px', padding: '7px 14px' }}
            onClick={() => {
              if (typeof window.openScriptureDrawer === 'function' && queries.length > 0) {
                window.openScriptureDrawer(queries[0], `${calcType} Classical Scripture Grounding`);
              }
            }}
          >
            <i className="fa-solid fa-scroll" /> Open Classical Scripture Drawer
          </button>
          <button
            type="button"
            className="btn-primary"
            style={{ fontSize: '11px', padding: '7px 14px' }}
            onClick={() => {
              if (typeof window.generateJyothiAIReading === 'function') {
                window.generateJyothiAIReading();
              }
            }}
          >
            <i className="fa-solid fa-wand-magic-sparkles" /> Generate AI Reading ({calcType})
          </button>
          <button
            type="button"
            className="btn-ghost"
            style={{ fontSize: '11px', padding: '7px 14px' }}
            onClick={() => {
              if (typeof window.navigateToPage === 'function') {
                window.navigateToPage('ai');
              }
            }}
          >
            <i className="fa-solid fa-comments" /> Ask Ganesha AI in Chat
          </button>
        </div>
      </div>

      <div className="vx-rag-query-list">
        {queries.map((q, idx) => (
          <div
            key={idx}
            className="vx-rag-query-chip interactive"
            onClick={() => {
              if (typeof window.openScriptureDrawer === 'function') {
                window.openScriptureDrawer(q, `Scripture Passage Q${idx + 1}`);
              }
            }}
            title="Click to preview original Sanskrit Shlokas & English translation from the 8 classical texts"
          >
            <span className="vx-rag-q-num">Q{idx + 1}</span>
            <span style={{ flex: 1 }}>{q}</span>
            <i className="fa-solid fa-book-open" style={{ color: 'var(--accent-gold, #b45309)', fontSize: '10px' }} />
          </div>
        ))}
      </div>
    </div>
  );
};
