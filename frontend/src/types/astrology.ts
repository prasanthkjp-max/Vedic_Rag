export type LangCode = 'en' | 'ta' | 'te' | 'ml' | 'kn' | 'hi';

export type AyanamsaName =
  | 'Lahiri'
  | 'Raman'
  | 'KP'
  | 'DP'
  | 'Yukteshwar'
  | 'Fagan-Bradley'
  | 'Tropical';

export type AstroSystem = 'Parashara' | 'KP' | 'Jaimini' | 'Nadi' | 'Vakya';
export type DasaSystem = 'Vimshottari' | 'Ashtottari' | 'Chara';

export interface PlacementInfo {
  longitude: number;
  degree: number;
  rasi_index: number;
  rasi_name: string;
  rasi_lord: string;
  nakshatra?: string;
  nakshatra_lord?: string;
  pada?: number;
  dignity?: string;
  is_retrograde?: boolean;
  is_combust?: boolean;
  hora_rasi_index?: number;
  hora_rasi_name?: string;
  drekkana_rasi_index?: number;
  drekkana_rasi_name?: string;
  chaturthamsha_rasi_index?: number;
  chaturthamsha_rasi_name?: string;
  saptamsha_rasi_index?: number;
  saptamsha_rasi_name?: string;
  navamsha_rasi_index?: number;
  navamsha_rasi_name?: string;
  dashamsha_rasi_index?: number;
  dashamsha_rasi_name?: string;
  dwadashamsha_rasi_index?: number;
  dwadashamsha_rasi_name?: string;
  trishamsha_rasi_index?: number;
  trishamsha_rasi_name?: string;
  shastiamsha_rasi_index?: number;
  shastiamsha_rasi_name?: string;
  kp_star_lord?: string;
  kp_sub_lord?: string;
  kp_sub_sub_lord?: string;
  kp_house?: number;
}

/** Shapes below mirror what `get_astrological_chart` actually returns
 *  (src/engines/astro_engine.py). tests/test_react_panels.py renders every panel
 *  against real engine output, so drift between this file and the engine fails CI. */

export interface KPCusp {
  house: number;
  longitude: number;
  rasi_index: number;
  rasi_name: string;
  degree: number;
  dms: string;
  nakshatra: string;
  sign_lord: string;
  star_lord: string;
  sub_lord: string;
  sub_sub_lord: string;
}

export interface KPHouseSignificator {
  house: number;
  cusp_star_lord: string;
  cusp_sub_lord: string;
  level_1_star_of_occupant: string[];
  level_2_occupant: string[];
  level_3_star_of_owner: string[];
  level_4_owner: string[];
  all_significators: string[];
}

export interface KPData {
  cusps: KPCusp[];
  planets?: Record<string, any>;
  house_significators: Record<string, KPHouseSignificator>;
}

export interface JaiminiKarakaInfo {
  code: string;
  /** e.g. "Atmakaraka (Soul & King of Chart)" */
  role: string;
  planet: string;
  degree: number;
  rasi_name: string;
  navamsha_rasi_index: number;
  navamsha_rasi_name: string;
}

export interface ArgalaItem {
  type: string;
  argala_sign: string;
  argala_planets: string[];
  virodha_sign: string;
  virodha_planets: string[];
  status: string;
}

export interface CharaAntardasa {
  /** e.g. "Vrishabha (Venus)" */
  bhukti_lord: string;
  rasi_index: number;
  duration_years: number;
  start_date: string;
  end_date: string;
}

export interface CharaDasaPeriod {
  /** e.g. "Mesha (Mars)" */
  dasa_lord: string;
  rasi_index: number;
  rasi_name: string;
  duration_years: number;
  start_date: string;
  end_date: string;
  bhuktis: CharaAntardasa[];
}

export interface JaiminiData {
  karakas: JaiminiKarakaInfo[];
  atmakaraka: JaiminiKarakaInfo;
  amatyakaraka: JaiminiKarakaInfo;
  darakaraka: JaiminiKarakaInfo;
  karakamsa_rasi_index: number;
  karakamsa_rasi_name: string;
  karakamsa_lord: string;
  swamsa_house_from_d9_lagna: number;
  rasi_drishti: Record<string, { aspected_signs: string[]; occupants: string[]; aspected_planets: string[] }>;
  argala_on_lagna: ArgalaItem[];
  argala_on_atmakaraka: ArgalaItem[];
  chara_dasas: CharaDasaPeriod[];
}

export interface AshtottariBhukti {
  bhukti_lord: string;
  duration_years: number;
  start_date: string;
  end_date: string;
}

export interface AshtottariMaha {
  dasa_lord: string;
  duration_years: number;
  start_date: string;
  end_date: string;
  bhuktis: AshtottariBhukti[];
}

export interface AshtottariDasaData {
  cycle_years: number;
  is_bphs_applicable: boolean;
  applicability_note: string;
  dasas: AshtottariMaha[];
}

export interface ArudhaPadaItem {
  code: string;
  alias: string;
  house: number;
  house_rasi: string;
  house_lord: string;
  pada_rasi_index: number;
  pada_rasi_name: string;
  pada_rasi_short: string;
  pada_lord: string;
  house_from_lagna: number;
  exception_applied: boolean;
}

export interface ArudhaPadasData {
  padas: Record<string, ArudhaPadaItem>;
  arudha_lagna: ArudhaPadaItem;
  upapada_lagna: ArudhaPadaItem;
}

export interface GrahaAvastha {
  baladi: string;
  baladi_result_pct: number;
  jagradadi: string;
  deeptadi: string;
  sayanadi: string;
}

export interface KharaDrekkana {
  rasi_index: number;
  rasi_name: string;
  rasi_short: string;
  lord: string;
  decanate: number;
  decanate_label: string;
  nature: string;
}

export interface NadiTrine {
  tattva: string;
  signs: string[];
  planets: string[];
}

export interface NadiLink {
  planet: string;
  nakshatra: string;
  pada: number;
  purushartha: string;
  star_lord: string;
  sub_lord: string;
  signified_houses: number[];
}

export interface NadiData {
  elemental_trines: NadiTrine[];
  nakshatra_links: Record<string, NadiLink>;
}

export interface VimsopakaBalaItem {
  score: number;
  max_score: number;
  percentage: number;
  status: string;
}

export interface ChartResponse {
  metadata: {
    datetime: string;
    longitude: number;
    latitude: number;
    gender: string;
    ayanamsa_name: string;
    ayanamsa_degrees: number;
    ayanamsa_dms: string;
    julian_date: number;
    timezone: string;
    calc_type: string;
    dasa_system: string;
  };
  panchangam: Record<string, any>;
  placements: Record<string, PlacementInfo>;
  dasas: any[];
  ashtottari_dasas?: AshtottariDasaData;
  jaimini?: JaiminiData;
  kp?: KPData;
  nadi?: NadiData;
  arudha_padas?: ArudhaPadasData;
  avasthas?: Record<string, GrahaAvastha>;
  khara_drekkana?: KharaDrekkana;
  vimsopaka_bala?: Record<string, VimsopakaBalaItem>;
  shadbala?: Record<string, any>;
  ashtakavarga?: Record<string, any>;
}
