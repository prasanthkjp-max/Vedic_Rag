import React from 'react';
import { createRoot, Root } from 'react-dom/client';
import { astroStore } from './store/astroStore';
import { SystemSelectorBar } from './components/SystemSelectorBar';
import { AdvancedAstrologyWorkspace } from './components/AdvancedAstrologyWorkspace';
import { AstroSystem, AyanamsaName, ChartResponse, DasaSystem, LangCode } from './types/astrology';
import './styles/react-astrology.css';

let selectorRoot: Root | null = null;
let workspaceRoot: Root | null = null;

function mountReactRoots() {
  const selectorEl = document.getElementById('react-system-selector-root');
  if (selectorEl && !selectorRoot) {
    selectorRoot = createRoot(selectorEl);
    selectorRoot.render(
      <React.StrictMode>
        <SystemSelectorBar />
      </React.StrictMode>
    );
  }

  const workspaceEl = document.getElementById('react-advanced-astrology-root');
  if (workspaceEl && !workspaceRoot) {
    workspaceRoot = createRoot(workspaceEl);
    workspaceRoot.render(
      <React.StrictMode>
        <AdvancedAstrologyWorkspace />
      </React.StrictMode>
    );
  }

  // Bind legacy select changes (#in-system, #in-timing, #in-ayanamsa) to React store
  const sysSelect = document.getElementById('in-system') as HTMLSelectElement | null;
  const timSelect = document.getElementById('in-timing') as HTMLSelectElement | null;
  const ayanSelect = document.getElementById('in-ayanamsa') as HTMLSelectElement | null;

  sysSelect?.addEventListener('change', () => {
    astroStore.setSystemConfig({ system: sysSelect.value as AstroSystem });
  });
  timSelect?.addEventListener('change', () => {
    astroStore.setSystemConfig({ timing: timSelect.value as DasaSystem });
  });
  ayanSelect?.addEventListener('change', () => {
    astroStore.setSystemConfig({ ayanamsa: ayanSelect.value as AyanamsaName });
  });
}

window.__notifyReactChartUpdated = (chart?: ChartResponse | null, lang?: LangCode) => {
  mountReactRoots();
  if (chart !== undefined) {
    astroStore.setChart(chart, lang);
  } else if (lang) {
    astroStore.setLang(lang);
  }
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mountReactRoots);
} else {
  mountReactRoots();
}
