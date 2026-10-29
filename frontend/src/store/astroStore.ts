import { useSyncExternalStore } from 'react';
import {
  AstroSystem,
  AyanamsaName,
  ChartResponse,
  DasaSystem,
  LangCode,
} from '../types/astrology';

export interface AstroStoreState {
  chart: ChartResponse | null;
  lang: LangCode;
  system: AstroSystem;
  timing: DasaSystem;
  ayanamsa: AyanamsaName;
  activePanelTab: 'kp' | 'jaimini' | 'classical' | 'dasa' | 'rag';
}

declare global {
  interface Window {
    calculatedChartData?: ChartResponse | null;
    currentLang?: LangCode;
    generateBirthChart?: () => Promise<void>;
    generateJyothiAIReading?: () => Promise<void>;
    navigateToPage?: (page: string) => void;
    __notifyReactChartUpdated?: (chart?: ChartResponse | null, lang?: LangCode) => void;
  }
}

let state: AstroStoreState = {
  chart: null,
  lang: 'en',
  system: 'Parashara',
  timing: 'Vimshottari',
  ayanamsa: 'Lahiri',
  activePanelTab: 'classical',
};

const listeners = new Set<() => void>();

function emitChange() {
  for (const listener of listeners) {
    listener();
  }
}

export const astroStore = {
  getState(): AstroStoreState {
    return state;
  },

  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  setChart(chart: ChartResponse | null, lang?: LangCode) {
    const calcType = (chart?.metadata?.calc_type || '').toLowerCase();
    const dasaSys = (chart?.metadata?.dasa_system || '').toLowerCase();

    let nextTab: AstroStoreState['activePanelTab'] = state.activePanelTab;
    if (calcType === 'kp') nextTab = 'kp';
    else if (calcType === 'jaimini' || dasaSys === 'chara') nextTab = 'jaimini';
    else if (dasaSys === 'ashtottari') nextTab = 'dasa';
    else if (calcType === 'nadi') nextTab = 'classical';

    state = {
      ...state,
      chart,
      lang: lang || (window.currentLang as LangCode) || state.lang,
      activePanelTab: nextTab,
    };
    emitChange();
  },

  setLang(lang: LangCode) {
    if (state.lang === lang) return;
    state = { ...state, lang };
    emitChange();
  },

  setSystemConfig(partial: Partial<Pick<AstroStoreState, 'system' | 'timing' | 'ayanamsa'>>) {
    state = { ...state, ...partial };
    const sysSelect = document.getElementById('in-system') as HTMLSelectElement | null;
    const timSelect = document.getElementById('in-timing') as HTMLSelectElement | null;
    const ayanSelect = document.getElementById('in-ayanamsa') as HTMLSelectElement | null;

    if (partial.system && sysSelect) sysSelect.value = partial.system;
    if (partial.timing && timSelect) timSelect.value = partial.timing;
    if (partial.ayanamsa && ayanSelect) ayanSelect.value = partial.ayanamsa;

    if (partial.system === 'KP') state.activePanelTab = 'kp';
    else if (partial.system === 'Jaimini' || partial.timing === 'Chara')
      state.activePanelTab = 'jaimini';
    else if (partial.timing === 'Ashtottari') state.activePanelTab = 'dasa';
    else if (partial.system === 'Nadi') state.activePanelTab = 'classical';

    emitChange();
  },

  setActivePanelTab(tab: AstroStoreState['activePanelTab']) {
    state = { ...state, activePanelTab: tab };
    emitChange();
  },
};

export function useAstroStore(): AstroStoreState {
  return useSyncExternalStore(astroStore.subscribe, astroStore.getState, astroStore.getState);
}
