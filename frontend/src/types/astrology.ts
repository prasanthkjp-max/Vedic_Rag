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

export interface KPCusp {
  house: number;
  longitude: number;
  rasi_index: number;
  rasi_name: string;
  degree_in_sign: number;
  rasi_lord: string;
  nakshatra: string;
  star_lord: string;
  sub_lord: string;
  sub_sub_lord: string;
}

export interface KPHouseSignificator {
  level_1_occupants_of_star_of_occupants: string[];
  level_2_occupants: string[];
  level_3_occupants_of_star_of_owner: string[];
  level_4_owner: string;
  all_significators: string[];
}

export interface KPData {
  cusps: KPCusp[];
  planet_significators: Record<
    string,
    {
      occupied_house: number;
      owned_houses: number[];
      star_lord: string;
      sub_lord: string;
      sub_sub_lord: string;
    }
  >;
  house_significators: Record<string, KPHouseSignificator>;
}

export interface JaiminiKarakaInfo {
  code: string;
  name: string;
  meaning: string;
  planet: string;
  degree_in_sign: number;
  rasi_index: number;
  rasi_name: string;
  navamsha_rasi_index: number;
  navamsha_rasi_name: string;
}

export interface CharaAntardasa {
  rasi_index: number;
  rasi_name: string;
  rasi_short: string;
  start_date: string;
  end_date: string;
}

export interface CharaDasaPeriod {
  rasi_index: number;
  rasi_name: string;
  rasi_short: string;
  lord: string;
  duration_years: number;
  start_date: string;
  end_date: string;
  bhuktis: CharaAntardasa[];
}

export interface JaiminiData {
  karakas: Record<string, JaiminiKarakaInfo>;
  atmakaraka: JaiminiKarakaInfo;
  amatyakaraka: JaiminiKarakaInfo;
  darakaraka: JaiminiKarakaInfo;
  karakamsa_rasi_index: number;
  karakamsa_rasi_name: string;
  karakamsa_lord: string;
  swamsa_house_from_d9_lagna: number;
  rasi_drishti: Record<string, string[]>;
  argala_on_lagna: Record<string, { house_from_ref: number; rasi_short: string; planets: string[] }>;
  argala_on_atmakaraka: Record<string, { house_from_ref: number; rasi_short: string; planets: string[] }>;
  chara_dasas: CharaDasaPeriod[];
}

export interface AshtottariBhukti {
  bhukti_lord: string;
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
  applicable: boolean;
  applicability_reason: string;
  total_cycle_years: number;
  dasas: AshtottariMaha[];
}

export interface ArudhaPadaItem {
  code: string;
  house: number;
  bhava_rasi_index: number;
  bhava_rasi_name: string;
  bhava_lord: string;
  lord_rasi_index: number;
  pada_rasi_index: number;
  pada_rasi_name: string;
  pada_rasi_short: string;
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
  baladi_meaning: string;
  jagradadi: string;
  deeptadi: string;
  sayanadi: string;
  sayanadi_index: number;
  cheshta_sub_state: string;
  proportion_multiplier: number;
}

export interface KharaDrekkana {
  rasi_index: number;
  rasi_name: string;
  rasi_short: string;
  decanate: number;
  degree_span: string;
  lord: string;
  nature: string;
}

export interface NadiLink {
  planet: string;
  rasi_short: string;
  nakshatra: string;
  pada: number;
  star_lord: string;
  star_lord_houses_owned: number[];
  dispositor: string;
  element_trine: string;
  trine_connected_planets: string[];
}

export interface NadiData {
  elemental_trines: Record<
    string,
    {
      signs: string[];
      planets: string[];
      significance: string;
    }
  >;
  nakshatra_nadi_links: Record<string, NadiLink>;
}

export interface VimsopakaBalaItem {
  score: number;
  max_score: number;
  percentage: number;
  tier: string;
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
