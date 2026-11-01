// The shape of public/data/proof.json (tools/extract_data.py). Only the fields the compositions read are typed;
// everything else rides along untyped so a richer export does not break the build.

export type Translation = {english: string; language: string; t_ms: number; aside: boolean; last_t_ms?: number};

export type Turn = {
  turn: number;
  speaker: string;
  start_ms: number;
  end_ms: number;
  text: string;
  az: number | null;
  el: number | null;
  conf3d: number | null;
  level_db: number | null;
  gain_db: number | null;
  kind: string | null;
  translation: Translation | null;
};

// Who is who by speaker label, as the log says it (tools/extract_data.py cast_of): colours in order of first
// appearance, the owner from the owner event, "a voice" for a label nobody named.
export type CastEntry = {label: string; name: string; short: string; p: number | 'owner'; key: string | null};
export type PersonLog = {t_ms: number; type: 'person' | 'person_removed'; key: string; name: string | null; company: string | null; speakers: string[] | null};

export type LevelerParams = {rate: number; target_db: number; ratio: number; max_boost_db: number; max_cut_db: number; ceiling_db: number; speech_above_floor_db: number; knee_above_floor_db: number; hold_ms: number; floor_percentile: number; block_ms: number};

export type Rec3 = {
  id: string;
  event: string;
  venue: string;
  device: string;
  sample_rate: number;
  channels: number;
  channel_names: string[];
  layout: string;
  frame: string | null;
  block_ms: number;
  duration_ms: number;
  date: string;
  owner_name: string;
  freeze_ms: number;
  freeze_turn: number;
  at_freeze: {regions: string[]; named: Record<string, string>};
  turns: Turn[];
  speaker_positions: Record<string, {azimuth: number; spread: number; turns: number; level_db: number; low_confidence: boolean; t_ms: number}>;
  wearer: {medians: Record<string, number>; found: [string, number] | null; constants: {min_elevation: number; margin: number; min_turns: number; min_confidence: number}} | null;
  owner_event: {t_ms: number; speakers: string[]; source: string} | null;
  cast: Record<string, CastEntry>;
  people_log: PersonLog[];
  leveler: {gain_min: number; gain_max: number; floor_median: number; per_speaker: Record<string, {mean: number; min: number; max: number; turns: number}>; params: LevelerParams};
  window: {
    t0: number;
    t1: number;
    step_ms: number;
    rms_db: Record<string, (number | null)[]>;
    gain_db: (number | null)[];
    speech: number[];
    floor_step_ms: number;
    floor_db: (number | null)[];
  };
  win400: {t_ms: number[]; az_room: (number | null)[]; elevation: (number | null)[]; conf3d: (number | null)[]; level_db: (number | null)[]};
  people: Record<string, {name: string; company: string; preferred_language: string; speakers: string[]; evidence_turns: number[]}>;
  promises: Record<string, {what: string; due: string; replaces: string; owed_to: string; evidence_turns: number[]; t_ms: number; replaced_at?: number}>;
};

export type Hook = {
  t_ms: number;
  person_key: string;
  kind: string;
  title: string;
  tag: string;
  reason: string;
  promise_key: string;
  evidence: {recording: string; event: string; turn: number; quote: string}[];
  provisional?: boolean;
};

export type SecondRun = {t_ms: number; model: string; call: number; final: boolean; upto_turn: number; seconds: number; usage: {total_tokens: number; prompt_tokens: number; completion_tokens: number}; people: number; promises: number; agreed: number; disagreed: number};

export type Run1 = {
  id: string;
  event: string;
  venue: string;
  date: string;
  now: string | null;
  now_date: string;
  turns: {turn: number; speaker: string; start_ms: number; end_ms: number; text: string}[];
  hooks: Hook[];
  edges_final: {person: string; turns: number[]; said: string; act: string; t_ms: number}[];
  second_runs: SecondRun[];
  person_history: {t_ms: number; key: string; name: string; company: string; matched?: string; provisional?: boolean; turn?: number; encounters: {recording: string; event: string}[]}[];
  confirmed: {t_ms: number; kind: string; key: string; by: string[]}[];
  confirmed_removed: {type: string; t_ms: number; kind: string; key: string}[];
  disagreement: {t_ms: number; field: string; key: string; turn: number; a: {by: string; text: string}; b: {by: string; text: string}} | null;
  next_moves: {t_ms: number; kind: string; body: string; person_key: string; when: string}[];
  removals: Record<string, number>;
  people_final: Record<string, {name: string; company: string}>;
  people_log: PersonLog[];
  promises_final: Record<string, {what: string; due: string; replaces: string; evidence_turns: number[]; t_ms: number}>;
  owner: {t_ms: number; speakers: string[]} | null;
  cast: Record<string, CastEntry>;
  index_evenings: string[];
  checks?: {source: string; file: string; edges: {t_ms: number; person: string; turns: number[]; said: string; kept: boolean; in_turn: number | null; reason: string | null}[]};
};

export type FinderEdge = {person: string; turns: number[]; language: string; said: string; english: string; text: string; act: string};
export type FinderCall = {call: number; raw: number; seconds: number; usage: {prompt_tokens: number; completion_tokens: number; total_tokens: number}; kept: FinderEdge[]; dropped: {person: string; turns: number[]; said: string}[]; model: string; name: string};
export type FinderCheck = {aside_turn: string; people: {key: string; speakers: string[]}[]; calls: FinderCall[]; spark_own: {seconds: number; usage: {total_tokens: number}; kept: FinderEdge[]} | null; file: string};

export type Aside = {
  take: string;
  aside_turn: string;
  people: {key: string; name: string; company: string; speakers: string[]; preferred_language: string}[];
  cast: Record<string, CastEntry>;
  spark: {
    raw_edges: {person: string; turns: number[]; said: string; act: string}[];
    kept_edges: FinderEdge[];
    calls: {name: string; prompt_tokens: number; completion_tokens: number; total_tokens: number}[];
    files: string[];
  };
  finder: {c: FinderCheck; c_final: FinderCheck};
};

export type OnePager = {
  person_key: string;
  acts: string[];
  slides: string[];
  dropped: unknown[];
  retried: boolean;
  usage: {total_tokens: number};
  seconds: number;
  model: string;
  file: string;
  deck: string;
  page: {
    title: string;
    lede: string;
    shape?: string;
    figures: {value: string; label: string}[];
    sections: {heading: string; points: string[]}[];
    close: string;
  };
  deck_slides: {title: string; numbers: string[]}[];
  links: {numbers: string[]; in_deck: boolean; slides: number[]}[];
};

// The `rebuilt` event as onepager.rebuilt_event composes it for a cued page (tools/extract_data.py)
export type Rebuilt = {person_key: string; name: string; status: string; title: string; shape: string; acts: string[]; slides: string[]; format: string; url: string; cued: boolean};

export type AppLabels = {
  rebuilt_headline: string;
  rebuilt_subline: string;
  rebuilt_source: string;
  rebuilt_name_source: string;
  partial_note: string;
  partial_note_source: string;
  partial_pill: string;
  partial_pill_source: string;
  no_record_line: string;
  no_record_line_source: string;
  hook_tag_source: string;
  hook_row_source: string;
  radar_tag_source: string;
  script_confirm_line: string;
  script_confirm_source: string;
};

export type RecMeta = {id: string; event: string; venue: string; date: string; started: number};

export type ProofData = {
  generated_from: Record<string, unknown>;
  rec3f3e: Rec3;
  run1: Run1;
  aside: Aside;
  accent: {
    file: string;
    accents: string[];
    voices: number;
    name_nohints: number;
    name_hints: number;
    company_nohints: number;
    company_hints: number;
    exact_nohints: number;
    exact_hints: number;
    rows: {id: string; accent: string; nohints: {name: string; text: string}; hints: {name: string; text: string}}[];
  };
  onepager: OnePager;
  rebuilt: Rebuilt;
  research: {status: string; tokens: number; corpus?: boolean; file: string; findings: {kind: string; text: string; source: string}[]};
  decoy: {title?: string; url?: string} | null;
  meetup: {title: string; url: string; date: string; short: string; name: string} | null;
  evidence: {
    chloe: RecMeta & {turn: {turn: number; text: string}; person: {name: string; company: string}};
    lena: {key: string; name: string; company: string} | null;
    lena_promise: RecMeta;
    lena_asks: RecMeta;
    hardware_meetup: RecMeta;
    kenji_japanese: RecMeta & {
      turns: {turn: number; text: string; speaker: string; start_ms: number; end_ms: number}[];
      names: Record<string, string>;
      cast: Record<string, CastEntry>;
      translation: Translation | null;
      turn_kind: string | null;
    };
  };
  app_labels: AppLabels;
  code: {
    WEARER_MIN_ELEVATION: number;
    WEARER_MARGIN: number;
    WEARER_MIN_TURNS: number;
    WEARER_MIN_CONFIDENCE: number;
    BLOCK_MS: number;
    ASR_RATE: number;
    leveler: LevelerParams;
    hints: {MAX_HINT_NAMES: number; MAX_HINT_MENTIONS: number; MAX_HINT_COMPANIES: number};
  };
};
