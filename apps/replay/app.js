/* Hallwise replay: one recording's event log played back on the badge-audio clock.
   Everything on screen is a fold of the events whose t_ms is at or before the current time, so scrubbing,
   jumping and playing all show exactly what the server had said by that moment. */
(() => {
  'use strict';

  // ---------------------------------------------------------------- constants and small helpers
  const CAPTION_LIFE = 5200;   // ms of playback a caption stays up
  const CAPTION_GAP = 750;     // captions from one model run are spaced out so each can be read
  const MAX_CAPTIONS = 3;
  const END_SETTLE = 3400;     // playback continues this long after the last caption appears
  const KIND_LABEL = { incidental: 'small talk', ambient: 'background chatter', stage: 'stage talk', noise: 'noise' };
  const MODEL = {
    transcribe: 'Muse Voice Transcribe', spark: 'Muse Spark', array: 'Four microphones',
    index: 'People index', sam: 'SAM 3.1', badge: 'Badge',
  };
  const NUMBER = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve'];
  const SCRIPTS = [
    [/[぀-ヿ]/, 'Japanese'], [/[가-힯]/, 'Korean'], [/[一-鿿]/, 'Chinese'],
    [/[Ѐ-ӿ]/, 'Russian'], [/[؀-ۿ]/, 'Arabic'], [/[ऀ-ॿ]/, 'Hindi'],
    [/[฀-๿]/, 'Thai'], [/[֐-׿]/, 'Hebrew'],
  ];
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  const $ = (id) => document.getElementById(id);
  const word = (n) => NUMBER[n] || String(n);
  const plural = (n, one, many) => (n === 1 ? one : many || one + 's');
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const wrap180 = (a) => { const x = ((((a + 180) % 360) + 360) % 360) - 180; return x === -180 ? 180 : x; };
  const mmss = (ms) => { const s = Math.max(0, Math.floor(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  const gid = (session, label) => `${session || 1}:${label || '?'}`;
  const pcol = (i) => (i == null || i < 0 ? 'var(--ink-soft)' : `var(--p${i % 8})`);
  const firstName = (name) => String(name || '').split(/\s+/)[0] || String(name || '');
  /** A short way to say a name: whole when it is short ("Wei Ling"), else the first word ("Kenji"). */
  const shortName = (name) => (String(name || '').length <= 9 ? String(name || '') : firstName(name));
  const truncate = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1).trimEnd() + '…' : String(s));
  const scriptLanguage = (text) => { for (const [re, name] of SCRIPTS) if (re.test(text)) return name; return ''; };
  const skey = (e) => `${String(e.heard || '').toLowerCase()}|${e.turn}`;
  const lsGet = (k) => { try { return window.localStorage.getItem(k); } catch (_) { return null; } };
  const lsSet = (k, v) => { try { if (v == null) window.localStorage.removeItem(k); else window.localStorage.setItem(k, v); } catch (_) { /* storage blocked */ } };
  const reduceMotion = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function circMean(angles) {
    let x = 0, y = 0;
    for (const a of angles) { x += Math.cos((a * Math.PI) / 180); y += Math.sin((a * Math.PI) / 180); }
    return (Math.atan2(y, x) * 180) / Math.PI;
  }
  /** Direction in words only: a chest badge tells left from right roughly and front from back not at all, so a
   *  voice is "to your left", never a number of degrees; "?" when the array itself was unsure. */
  function bearingWords(a, low) {
    const side = a > 12 ? 'to your left' : a < -12 ? 'to your right' : 'about ahead';
    return low ? `${side}, not sure` : side;
  }
  function durationWords(ms) {
    const s = Math.floor(ms / 1000);
    if (s < 60) return `${s} s`;
    const m = Math.floor(s / 60), r = s % 60;
    if (m >= 60) return `${Math.floor(m / 60)} h ${m % 60} min`;
    return r ? `${m} min ${r} s` : `${m} min`;
  }

  // ---------------------------------------------------------------- the fold
  function freshState() {
    return {
      i: 0, t: -1, rev: 0, yaw: 0,
      speakers: new Map(), owner: new Set(), ownerT: null,
      people: new Map(), positions: new Map(), turns: new Map(), partial: new Map(), kinds: new Map(),
      translations: new Map(), suspects: new Map(), promises: new Map(), history: new Map(),
      topics: [], moves: new Map(), photos: [], ended: false, endT: null,
      x: freshXray(),
    };
  }

  /** What the X-ray folds on top of the replay's own state: the machinery events the panels never showed. */
  function freshXray() {
    return {
      positions: new Map(), firstPos: null, edges: new Map(), edgesRemoved: 0, hooks: new Map(), runs: [],
      confirmed: new Map(), unconfirmed: [], disagreements: [], rebuilt: [], recall: new Map(),
      spark: [], firstSpark: null, lastCheckT: null, lastWordsT: null,
    };
  }

  /** Runs before the replay's own fold of the same event (so a promise's previous due date is still readable). */
  function applyXray(S, e) {
    const x = S.x;
    const push = (kind, text) => { x.spark.push({ t: e.t_ms, kind, text }); if (x.spark.length > 16) x.spark.shift(); x.lastWordsT = e.t_ms; };
    switch (e.type) {
      case 'position': x.positions.set(e.turn, e); break;
      case 'speaker_position': if (x.firstPos == null) x.firstPos = e.t_ms; break;
      case 'edge': x.edges.set(`${e.person}|${(e.turns || []).join(',')}`, e); x.lastCheckT = e.t_ms; x.lastWordsT = e.t_ms; break;
      case 'edge_removed': x.edges.delete(`${e.person}|${(e.turns || []).join(',')}`); x.edgesRemoved++; break;
      case 'hook': x.hooks.set(`${e.person_key}|${e.title}`, e); break;
      case 'hook_removed': x.hooks.delete(`${e.person_key}|${e.title}`); break;
      case 'second_run': x.runs.push(e); x.lastWordsT = e.t_ms; break;
      case 'confirmed': x.confirmed.set(`${e.kind}:${e.key}`, e); x.lastCheckT = e.t_ms; break;
      case 'confirmed_removed': x.confirmed.delete(`${e.kind}:${e.key}`); x.unconfirmed.push(e); x.lastCheckT = e.t_ms; break;
      case 'disagreement': x.disagreements.push(e); x.lastCheckT = e.t_ms; break;
      case 'rebuilt': x.rebuilt.push(e); break;
      case 'person_history': { const r = x.recall.get(e.key); if (r) r.last = e; else x.recall.set(e.key, { first: e, last: e }); break; }
      case 'person_history_removed': x.recall.delete(e.key); break;
      case 'person': {
        if (x.firstSpark == null) x.firstSpark = e.t_ms;
        const prev = S.people.get(e.key);
        if (!prev) push('person', [e.name, e.company].filter(Boolean).join(' · '));
        else if (['company', 'role', 'preferred_language', 'introduced_by', 'name'].some((k) => e[k] && e[k] !== prev[k])) push('details', [e.name, e.company, e.role].filter(Boolean).join(' · '));
        break;
      }
      case 'promise': {
        const prev = S.promises.get(e.key);
        const c = correction(prev, e);
        if (c) { x.lastCheckT = e.t_ms; push('promise corrected', `${e.what} · ${c.from} → ${c.to}`); }
        else if (!prev) push('promise', `${e.what}${e.due ? ' · ' + e.due : ''}`);
        break;
      }
      case 'translation': if (!S.translations.has(e.turn)) push(`translation · ${e.language || ''}`, e.english || ''); break;
      case 'suspect_word': if (!S.suspects.has(skey(e))) push('misheard?', `${e.heard} → ${e.likely}`); break;
      case 'room_topics': { const now = (e.topics || []).join(' · '); if (now && now !== S.topics.join(' · ')) push('overheard', now); break; }
      case 'turn_kind': if (KIND_LABEL[e.kind] && S.kinds.get(e.turn) !== e.kind) push('set aside', `turn ${e.turn} · ${KIND_LABEL[e.kind]}`); break;
      default: break;
    }
  }

  /** What a promise event changes about the date, if anything: "Thursday" -> "Friday". */
  function correction(prev, e) {
    const due = e.due || '';
    if (e.replaces && e.replaces !== due) {
      if (prev && prev.replaces === e.replaces && (prev.due || '') === due) return null;
      return { from: e.replaces, to: due || 'no date' };
    }
    if (prev && prev.due && due && prev.due !== due) return { from: prev.due, to: due };
    return null;
  }

  function apply(S, e) {
    applyXray(S, e);
    switch (e.type) {
      case 'device_pose':
        if (typeof e.yaw === 'number') S.yaw = e.yaw;
        break;
      case 'speech_start':
        if (!S.turns.has(e.turn)) S.turns.set(e.turn, { turn: e.turn, start: e.t_ms, done: false, speaker: null, text: '' });
        break;
      case 'speaker': {
        const id = gid(e.session, e.label);
        if (!S.speakers.has(id)) S.speakers.set(id, { id, label: e.label, session: e.session || 1, firstT: e.t_ms });
        const tr = S.turns.get(e.turn) || { turn: e.turn, start: e.t_ms, done: false, text: '' };
        tr.speaker = id;
        S.turns.set(e.turn, tr);
        break;
      }
      case 'partial':
        if (e.text) S.partial.set(e.turn, e.text);
        break;
      case 'turn': {
        const id = gid(e.session, e.speaker);
        const tr = S.turns.get(e.turn) || { turn: e.turn };
        tr.speaker = id;
        tr.text = e.text || '';
        tr.start = typeof e.start_ms === 'number' ? e.start_ms : (tr.start ?? e.t_ms);
        tr.end = typeof e.end_ms === 'number' ? e.end_ms : e.t_ms;
        tr.done = true;
        S.turns.set(e.turn, tr);
        if (!S.speakers.has(id)) S.speakers.set(id, { id, label: e.speaker, session: e.session || 1, firstT: tr.start });
        break;
      }
      case 'turn_kind':
        S.kinds.set(e.turn, e.kind);
        break;
      case 'owner':
        S.owner = new Set(e.speakers || []);
        S.ownerT = e.t_ms;
        break;
      case 'speaker_position':
        S.positions.set(e.speaker, { az: Number(e.azimuth) || 0, level: e.level_db, spread: e.spread, turns: e.turns, low: e.low_confidence === true });
        break;
      case 'person': {
        const prev = S.people.get(e.key);
        S.people.set(e.key, { ...e, firstT: prev ? prev.firstT : e.t_ms });
        break;
      }
      case 'person_removed':
        S.people.delete(e.key);
        break;
      case 'person_history':
        S.history.set(e.key, e);
        break;
      case 'promise': {
        const prev = S.promises.get(e.key);
        const struck = prev ? prev.struck.slice() : [];
        const c = correction(prev, e);
        if (c && !struck.includes(c.from)) struck.push(c.from);
        if (e.replaces && e.replaces !== e.due && !struck.includes(e.replaces)) struck.push(e.replaces);
        S.promises.set(e.key, {
          ...e, struck: struck.filter((s) => s && s !== e.due),
          firstT: prev ? prev.firstT : e.t_ms, correctedT: c ? e.t_ms : prev ? prev.correctedT : null,
        });
        break;
      }
      case 'promise_removed':
        S.promises.delete(e.key);
        break;
      case 'translation':
        S.translations.set(e.turn, e);
        break;
      case 'translation_removed':
        S.translations.delete(e.turn);
        break;
      case 'suspect_word':
        S.suspects.set(skey(e), e);
        break;
      case 'suspect_word_removed':
        S.suspects.delete(skey(e));
        break;
      case 'room_topics':
        S.topics = e.topics || [];
        break;
      case 'next_move':
        S.moves.set(e.promise_key || `m${S.moves.size}`, e);
        break;
      case 'photo':
        S.photos.push(e);
        break;
      case 'recording_end':
        S.ended = true;
        S.endT = e.t_ms;
        break;
      default:
        break;
    }
  }

  // ---------------------------------------------------------------- preparing one recording
  function findOffsetMinutes(evs) {
    for (const e of evs) {
      for (const k of ['when', 'remind_at']) {
        const m = typeof e[k] === 'string' && e[k].match(/([+-])(\d{2}):?(\d{2})$/);
        if (m) return (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3]));
      }
    }
    return null;
  }

  function prepare(rec) {
    const meta = rec.meta || {};
    const evs = (rec.events || [])
      .map((e, i) => ({ ...e, _i: i, t_ms: Number(e.t_ms) || 0 }))
      .sort((a, b) => a.t_ms - b.t_ms || a._i - b._i);
    const P = { rec, meta, evs, id: rec.id || meta.id || '', ownerName: meta.owner_name || 'You' };
    const F = freshState();
    for (const e of evs) apply(F, e);
    P.final = F;
    P.endT = F.endT ?? (evs.length ? evs[evs.length - 1].t_ms : 0);
    P.started = Number(meta.started) || 0;
    P.layout = meta.layout || '';
    P.hasDirection = evs.some((e) => e.type === 'speaker_position');
    P.multiSession = new Set([...F.speakers.values()].map((s) => s.session)).size > 1;
    P.xPersonOf = personBySpeaker(F);  // the X-ray colours a voice by who it turned out to be, like the transport

    P.colour = new Map();
    for (const e of evs) if (e.type === 'person' && !P.colour.has(e.key)) P.colour.set(e.key, P.colour.size);

    P.turnLang = new Map();
    for (const [turn, tr] of F.translations) P.turnLang.set(turn, tr.language || '');
    for (const [turn, tr] of F.turns) {
      if (!P.turnLang.has(turn) && tr.text) { const l = scriptLanguage(tr.text); if (l) P.turnLang.set(turn, l); }
    }

    if (!P.hasDirection) {
      // No direction on this recording: voices sit around the wearer in the order they arrived, front first.
      const order = [...F.speakers.values()].sort((a, b) => a.firstT - b.firstT).map((s) => s.id);
      const n = Math.max(order.length, 1);
      const slots = Array.from({ length: n }, (_, k) => wrap180(((k + 0.5) * 360) / n - 180));
      slots.sort((a, b) => Math.abs(a) - Math.abs(b) || b - a);
      P.slots = new Map(order.map((id, k) => [id, slots[k]]));
    }

    // People met at an earlier evening, as the people index knows them (used when the log has no
    // person_history event for them).
    P.earlier = new Map();
    for (const entry of (rec.people_index && rec.people_index.people) || []) {
      const here = (entry.encounters || []).find((x) => x.recording === P.id);
      if (!here) continue;
      const before = entry.encounters
        .filter((x) => x.recording !== P.id && (x.started || 0) < P.started - 1)
        .sort((a, b) => (b.started || 0) - (a.started || 0));
      if (before.length) P.earlier.set(here.record_key, before);
    }

    P.spans = [...F.turns.values()]
      .filter((tr) => tr.done && tr.speaker && typeof tr.start === 'number' && tr.end > tr.start)
      .map((tr) => ({ start: tr.start, end: tr.end, speaker: tr.speaker }))
      .sort((a, b) => a.start - b.start);
    P.turnStart = new Map();
    for (const [turn, tr] of F.turns) if (typeof tr.start === 'number') P.turnStart.set(turn, tr.start);
    P.tzOffset = findOffsetMinutes(evs);
    P.captions = buildCaptions(P);
    P.markers = buildMarkers(P);
    const lastCaption = P.captions.length ? P.captions[P.captions.length - 1].show : 0;
    P.audioMs = rec.audio ? Number(rec.audio.duration_ms) || 0 : 0;
    P.total = Math.max(1000, Number(rec.duration_ms) || 0, P.endT + 1500, P.audioMs, lastCaption + END_SETTLE);
    return P;
  }

  function evidenceStart(P, turns) {
    const list = (turns || []).filter((n) => P.turnStart.has(n)).sort((a, b) => a - b);
    return list.length ? { turn: list[0], t: P.turnStart.get(list[0]) } : null;
  }

  function metBefore(P, S, key) {
    const h = S.history.get(key);
    if (h && h.encounters && h.encounters.length) {
      return h.encounters.slice().sort((a, b) => (b.started || 0) - (a.started || 0));
    }
    return P.earlier.get(key) || [];
  }

  // ---------------------------------------------------------------- captions: which model acted, from event types
  function buildCaptions(P) {
    const S = freshState();
    const caps = [];
    const seenVoice = new Set();
    const placed = new Set();
    let maxSession = 0;
    let prevTurn = null;
    const nameOf = (key) => (key === 'owner' ? 'you' : (S.people.get(key) && S.people.get(key).name) || key);
    const add = (t, model, what, detail) => caps.push({ t, model, what, detail: detail || '' });
    const loggedHistory = new Set(P.final.history.keys());

    const evs = P.evs;
    let i = 0;
    while (i < evs.length) {
      const t = evs[i].t_ms;
      const batch = [];
      while (i < evs.length && evs[i].t_ms === t) batch.push(evs[i++]);
      const g = {
        named: [], updated: [], history: [], caught: [], corrected: [], withdrawn: 0, translations: [],
        suspects: [], filtered: {}, owner: false, topics: null, moves: [], photos: [], merged: 0, end: false,
      };
      for (const e of batch) {
        switch (e.type) {
          case 'speaker': {
            const id = gid(e.session, e.label);
            const session = e.session || 1;
            if (session > maxSession) {
              if (maxSession) add(t, 'transcribe', `session ${session}, voices relabelled`, esc('Muse Spark keeps each person across the new labels'));
              maxSession = session;
            }
            if (!seenVoice.has(id)) {
              seenVoice.add(id);
              const n = seenVoice.size;
              if (!S.owner.has(id)) add(t, 'transcribe', n === 1 ? 'first voice' : `a new voice · ${word(n)} kept apart`);
            }
            break;
          }
          case 'turn': {
            const lang = P.turnLang.get(e.turn) || '';
            const id = gid(e.session, e.speaker);
            if (!seenVoice.has(id)) {
              seenVoice.add(id);
              if (!S.owner.has(id)) add(t, 'transcribe', seenVoice.size === 1 ? 'first voice' : `a new voice · ${word(seenVoice.size)} kept apart`);
            }
            if (lang && lang !== 'English') {
              add(t, 'transcribe', `${lang}, transcribed as spoken`);
            } else if (prevTurn && prevTurn.lang && prevTurn.lang !== 'English') {
              add(t, 'transcribe', prevTurn.speaker === id
                ? 'same voice, followed through the switch to English'
                : 'two voices, still apart after the switch to English');
            }
            prevTurn = { lang, speaker: id };
            break;
          }
          case 'speaker_position':
            if (!placed.has(e.speaker)) {
              placed.add(e.speaker);
              if (!S.owner.has(e.speaker)) add(t, 'array', `a voice placed, roughly ${bearingWords(wrap180((Number(e.azimuth) || 0) - S.yaw), e.low_confidence === true)}`, 'a soft region, never a degree');
            }
            break;
          case 'person': {
            const prev = S.people.get(e.key);
            if (!prev) g.named.push(e);
            else if (['company', 'role', 'preferred_language', 'introduced_by', 'name'].some((k) => e[k] && e[k] !== prev[k])) g.updated.push(e);
            break;
          }
          case 'person_removed': g.merged++; break;
          case 'person_history': g.history.push({ name: e.name, event: (e.encounters && e.encounters[0] && e.encounters[0].event) || '' }); break;
          case 'promise': {
            const prev = S.promises.get(e.key);
            const c = correction(prev, e);
            if (c) g.corrected.push({ e, c });
            else if (!prev) g.caught.push(e);
            break;
          }
          case 'promise_removed': g.withdrawn++; break;
          case 'translation': if (!S.translations.has(e.turn)) g.translations.push(e); break;
          case 'suspect_word': if (!S.suspects.has(skey(e))) g.suspects.push(e); break;
          case 'turn_kind':
            if (KIND_LABEL[e.kind] && S.kinds.get(e.turn) !== e.kind) g.filtered[e.kind] = (g.filtered[e.kind] || 0) + 1;
            break;
          case 'owner': if ((e.speakers || []).some((s) => !S.owner.has(s))) g.owner = true; break;
          case 'room_topics': if ((e.topics || []).length) g.topics = e.topics; break;
          case 'next_move': g.moves.push(e); break;
          case 'photo': g.photos.push(e); break;
          case 'recording_end': g.end = true; break;
          default: break;
        }
        apply(S, e);
      }

      if (g.end) add(t, 'badge', 'recording stopped');
      if (g.owner) add(t, 'spark', 'your own voice recognised', esc(P.meta.owner_name ? `${P.meta.owner_name} is the wearer, now at the centre` : 'the wearer, now at the centre'));
      if (g.named.length === 1) {
        const p = g.named[0];
        const by = p.introduced_by && p.introduced_by !== 'owner' ? nameOf(p.introduced_by) : '';
        add(t, 'spark', by ? `${p.name} named, introduced by ${shortName(by)}` : `${p.name} named from the introduction`,
          esc([p.company, p.role].filter(Boolean).join(' · ')));
      } else if (g.named.length > 1) {
        add(t, 'spark', `${word(g.named.length)} people named`, esc(g.named.map((p) => p.name).join(', ')));
      }
      for (const p of g.named) {
        if (!loggedHistory.has(p.key) && P.earlier.has(p.key)) g.history.push({ name: p.name, event: P.earlier.get(p.key)[0].event });
      }
      if (g.history.length === 1) {
        add(t, 'index', `${shortName(g.history[0].name)} met before`, esc(`at ${g.history[0].event}`));
      } else if (g.history.length > 1) {
        add(t, 'index', `${word(g.history.length)} people met before`, esc(g.history.map((h) => `${shortName(h.name)} at ${h.event}`).join('; ')));
      }
      for (const { e, c } of g.corrected) {
        add(t, 'spark', 'promise corrected', `${esc(e.what)}: <s>${esc(c.from)}</s> → ${esc(c.to)}`);
      }
      if (g.caught.length === 1) {
        const q = g.caught[0];
        const by = nameOf(q.owed_by), to = nameOf(q.owed_to);
        add(t, 'spark', 'promise caught', esc(`${by === 'you' ? 'You' : by} → ${to}: ${q.what}${q.due ? ', ' + q.due : ''}`));
      } else if (g.caught.length > 1) {
        add(t, 'spark', `${word(g.caught.length)} promises caught`, esc(g.caught.map((q) => q.what).join(' · ')));
      }
      if (g.withdrawn) add(t, 'spark', g.withdrawn === 1 ? 'promise withdrawn' : `${word(g.withdrawn)} promises withdrawn`, esc('a later pass no longer hears it'));
      if (g.translations.length === 1) {
        const tr = g.translations[0];
        add(t, 'spark', `translation from ${tr.language || 'another language'}`, esc(`“${truncate(tr.english || '', 96)}”`));
      } else if (g.translations.length > 1) {
        add(t, 'spark', `${word(g.translations.length)} translations`, esc([...new Set(g.translations.map((x) => x.language))].join(', ')));
      }
      if (g.suspects.length === 1) {
        const s = g.suspects[0];
        add(t, 'spark', 'misheard word flagged', `<s>${esc(s.heard)}</s> → ${esc(s.likely)}?`);
      } else if (g.suspects.length > 1) {
        add(t, 'spark', `${word(g.suspects.length)} misheard words flagged`, esc(g.suspects.map((s) => `${s.heard} → ${s.likely}`).join(' · ')));
      }
      const kinds = Object.entries(g.filtered);
      if (kinds.length) {
        const n = kinds.reduce((a, [, v]) => a + v, 0);
        add(t, 'spark', kinds.length === 1 ? `${KIND_LABEL[kinds[0][0]]} filtered` : `${word(n)} lines filtered`,
          esc(kinds.map(([k, v]) => `${word(v)} ${plural(v, 'line')} of ${KIND_LABEL[k]}`).join(', ') + ', set aside and kept in the log'));
      }
      if (g.topics) add(t, 'spark', 'overheard nearby', esc(g.topics.join(' · ')));
      if (g.merged) add(t, 'spark', g.merged === 1 ? 'two voices merged into one person' : `${word(g.merged)} duplicates merged`);
      if (g.updated.length && caps.filter((c) => c.t === t).length < 4) {
        add(t, 'spark', g.updated.length === 1 ? `${shortName(g.updated[0].name)}'s details filled in` : `${word(g.updated.length)} people's details filled in`,
          esc(g.updated.length === 1 ? [g.updated[0].company, g.updated[0].role].filter(Boolean).join(' · ') : ''));
      }
      if (g.photos.length) {
        const faces = g.photos.reduce((a, ph) => a + (ph.faces || []).length, 0);
        add(t, 'sam', `${word(faces)} ${plural(faces, 'face')} found in ${g.photos.length === 1 ? 'a photo' : word(g.photos.length) + ' photos'}`);
        const who = [...new Set(g.photos.flatMap((ph) => (ph.faces || []).filter((f) => f.person_key).map((f) => shortName(nameOf(f.person_key)))))];
        if (who.length) add(t, 'spark', 'who is who in the photos', esc(who.join(', ')));
      }
      if (g.moves.length) {
        const langs = [...new Set(g.moves.map((m) => m.language).filter((l) => l && l !== 'English'))];
        add(t, 'spark', `${word(g.moves.length)} ${plural(g.moves.length, 'follow-up')} drafted`,
          esc(langs.length ? `in English and ${langs.join(' and ')}` : 'one for each promise'));
      }
    }
    let last = -Infinity;
    caps.forEach((c, k) => { c.show = Math.max(c.t, last + CAPTION_GAP); last = c.show; c.id = `c${k}`; });
    return caps;
  }

  function buildMarkers(P) {
    const S = freshState();
    const out = [];
    for (const e of P.evs) {
      if (e.type === 'person' && !S.people.has(e.key)) {
        out.push({ lane: 'person', t: e.t_ms, colour: P.colour.get(e.key), label: `${e.name} named` });
      } else if (e.type === 'promise') {
        const prev = S.promises.get(e.key);
        const c = correction(prev, e);
        if (c) out.push({ lane: 'promise', t: e.t_ms, corrected: true, label: `Corrected: ${e.what}, ${c.from} → ${c.to}` });
        else if (!prev) out.push({ lane: 'promise', t: e.t_ms, label: `Promise: ${e.what}${e.due ? ', ' + e.due : ''}` });
      } else if (e.type === 'translation' && !S.translations.has(e.turn)) {
        out.push({ lane: 'translation', t: e.t_ms, label: `Translated from ${e.language || 'another language'}` });
      } else if (e.type === 'edge' && e.new && !S.x.edges.has(`${e.person}|${(e.turns || []).join(',')}`)) {
        out.push({ lane: 'edge', t: e.t_ms, label: `Edge: “${truncate(e.said || '', 60)}” → ${e.act || ''}` });
      } else if (e.type === 'hook' && !S.x.hooks.has(`${e.person_key}|${e.title}`)) {
        out.push({ lane: 'hook', t: e.t_ms, label: `Reason to write: ${e.title}` });
      }
      apply(S, e);
    }
    return out;
  }

  // ---------------------------------------------------------------- formatting dates
  function wallDate(epochSec, offsetMin) {
    if (offsetMin == null) {
      const d = new Date(epochSec * 1000);
      return { y: d.getFullYear(), mo: d.getMonth(), d: d.getDate(), wd: d.getDay(), h: d.getHours(), mi: d.getMinutes() };
    }
    const d = new Date(epochSec * 1000 + offsetMin * 60000);
    return { y: d.getUTCFullYear(), mo: d.getUTCMonth(), d: d.getUTCDate(), wd: d.getUTCDay(), h: d.getUTCHours(), mi: d.getUTCMinutes() };
  }
  const hhmm = (w) => `${String(w.h).padStart(2, '0')}:${String(w.mi).padStart(2, '0')}`;
  const dayLabel = (w) => `${DAYS[w.wd]} ${w.d} ${MONTHS[w.mo]}`;

  /** "2026-11-03T11:00:00+0800" -> wall-clock parts as written, plus the zone. */
  function parseIso(s) {
    const m = typeof s === 'string' && s.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/);
    if (!m) return null;
    const base = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
    let zone = '';
    if (m[6] === 'Z') zone = 'UTC';
    else if (m[6]) {
      const z = m[6].replace(':', '');
      const h = Number(z.slice(1, 3)), mi = Number(z.slice(3, 5));
      zone = `UTC${z[0]}${h}${mi ? ':' + String(mi).padStart(2, '0') : ''}`;
    }
    return { base, zone };
  }
  function partsOf(ms) {
    const d = new Date(ms);
    return { y: d.getUTCFullYear(), mo: d.getUTCMonth(), d: d.getUTCDate(), wd: d.getUTCDay(), h: d.getUTCHours(), mi: d.getUTCMinutes() };
  }
  function fmtSlot(iso, minutes) {
    const p = parseIso(iso);
    if (!p) return iso || '';
    const a = partsOf(p.base);
    const b = partsOf(p.base + (Number(minutes) || 30) * 60000);
    return `${dayLabel(a)} · ${hhmm(a)}–${hhmm(b)}${p.zone ? ' ' + p.zone : ''}`;
  }
  function fmtWhen(iso) {
    const p = parseIso(iso);
    if (!p) return iso || '';
    const a = partsOf(p.base);
    return `${dayLabel(a)} · ${hhmm(a)}${p.zone ? ' ' + p.zone : ''}`;
  }

  // ---------------------------------------------------------------- the page
  const els = {};
  [
    'app', 'radar', 'radar-static', 'radar-wedges', 'blips', 'wearer', 'wearer-mark', 'new-voice', 'new-voice-label', 'radar-note',
    'captions', 'people', 'intro', 'evening-name', 'evening-meta', 'evening-stats', 'play-big', 'play-len',
    'audio-note', 'skip-end', 'skip-end-2', 'transcript', 'promises', 'suspects', 'suspects-box', 'after',
    'waiting', 'moves', 'morning', 'morning-when', 'morning-count', 'm-hooks-part', 'm-hooks', 'm-redrafts-part',
    'm-redrafts', 'm-checks-box', 'm-checks', 'm-due-box', 'm-due', 'morning-cost', 'week', 'week-sub', 'chips', 'places-box', 'places', 'places-note', 'map', 'foot-id', 'bar', 'pp', 'pp-icon', 'time', 'scrub',
    'track', 'segs', 'fill', 'head', 'lane-person', 'lane-promise', 'lane-translation', 'lane-edge', 'lane-hook', 'tip', 'toast', 'pick',
    'theme', 'theme-label', 'brand', 'mute', 'mute-waves', 'mute-cross',
    'xray', 'xray-btn', 'x-stamp', 'x-legend', 'x-close', 'x-caption', 'x-cols', 'x-tape',
  ].forEach((id) => { els[id] = $(id); });

  let P = null;            // the prepared recording
  let S = freshState();    // the fold at the current time
  let mode = 'intro';
  let lastRender = { t: -1, rev: -1 };
  const blipEls = new Map();
  const lineEls = new Map();
  const promiseEls = new Map();
  const personEls = new Map();
  const captionEls = new Map();
  let markerEls = [];
  let movesSig = '';
  let stickTranscript = true;
  let endScrolled = false;
  let flashTurn = null;
  let weekFilter = null;
  let weekDrawn = false;
  let morningDrawn = false;
  const redraftEls = new Map();  // promise key -> this morning's card, for the evening card's link to it

  // ---------------------------------------------------------------- player: audio when there is some, else a clock
  const player = {
    audio: null, audioOk: false, usingAudio: false, playing: false, rate: 1, muted: false,
    t0: 0, wall0: 0, paused: 0,
    now() {
      if (!this.playing) return this.paused;
      if (this.usingAudio && this.audio) {
        const ct = this.audio.currentTime * 1000;
        if (this.want) return Math.min(this.expected(), P.total);  // a jump the sound has not taken yet
        if (!this.audio.ended && ct < P.audioMs - 40) {
          const wall = performance.now();
          if (ct !== this.lastCt) { this.lastCt = ct; this.lastCtWall = wall; }
          else if (wall - this.lastCtWall > 6000) {
            // the sound has not moved for six seconds: carry on silently rather than freeze the evening
            this.usingAudio = false;
            try { this.audio.pause(); } catch (_) { /* ignore */ }
            this.startClock(ct);
            setAudioNote('The sound stalled, so the replay carries on silently. Pause and play to try the sound again.');
            return ct;
          }
          return ct;
        }
        // the sound is over; the log goes on (follow-ups are written after the recording stops)
        this.usingAudio = false;
        this.t0 = Math.max(this.audio.currentTime * 1000, P.audioMs);
        this.wall0 = performance.now();
      }
      return this.t0 + (performance.now() - this.wall0) * this.rate;
    },
    startClock(t) { this.usingAudio = false; this.want = null; this.t0 = t; this.wall0 = performance.now(); },
    hasSource() { return !!(this.audio && this.audio.getAttribute('src') && this.audio.readyState >= 1); },
    useAudioFrom(t) {
      const audio = this.audio;
      this.usingAudio = true;
      this.lastCt = -1;
      this.lastCtWall = performance.now();
      this.want = { t, wall: performance.now(), tries: 0 };
      try { audio.currentTime = t / 1000; } catch (_) { /* not seekable yet */ }
      audio.playbackRate = this.rate;
      const pr = audio.paused ? audio.play() : null;
      if (pr && pr.catch) {
        pr.catch(() => {
          if (!this.playing || this.audio !== audio) return;
          this.audioOk = false;
          this.startClock(t);
          setAudioNote('The browser would not play the sound, so the replay runs on the badge clock.');
        });
      }
      this.checkSeek(0);
    },
    /** Where the sound should be by now, after the last jump. */
    expected() {
      if (!this.want) return null;
      return this.want.t + (this.playing ? (performance.now() - this.want.wall) * this.rate : 0);
    },
    /** A jump asked for before the sound could take it: ask again once it can (a few times at most). */
    reapply() {
      const audio = this.audio;
      if (!audio || !this.want || !this.usingAudio) return;
      const exp = this.expected();
      if (Math.abs(audio.currentTime * 1000 - exp) <= 800) { this.want = null; return; }
      if (this.want.tries++ < 3) { try { audio.currentTime = exp / 1000; } catch (_) { /* ignore */ } }
    },
    /** Where the host cannot seek inside the file the sound snaps back; run on the clock rather than drift. */
    checkSeek(attempt) {
      const audio = this.audio;
      setTimeout(() => {
        if (!this.playing || !this.usingAudio || this.audio !== audio || !this.want) return;
        if (audio.readyState < 2 && attempt < 8) { this.checkSeek(attempt + 1); return; }
        const exp = this.expected();
        if (Math.abs(audio.currentTime * 1000 - exp) > 2500) {
          this.usingAudio = false;
          this.audioOk = false;
          this.want = null;
          try { audio.pause(); } catch (_) { /* ignore */ }
          this.startClock(exp);
          els.mute.hidden = true;
          setAudioNote('This host cannot jump inside the sound, so the replay runs silently on the badge clock.');
        } else {
          this.reapply();
          if (this.want) this.checkSeek(attempt + 1);
        }
      }, 900);
    },
    /** The sound finished loading while the clock was already running. */
    adopt() {
      if (this.playing && this.audioOk && !this.usingAudio) {
        const t = this.now();
        if (t < P.audioMs - 60) this.useAudioFrom(t);
      }
    },
    play() {
      let t = this.paused;
      if (t >= P.total - 50) t = 0;
      this.playing = true;
      this.paused = t;
      if (this.audioOk && this.hasSource() && t < P.audioMs - 60) this.useAudioFrom(t);
      else this.startClock(t);
      syncPlayButton();
    },
    pause(at) {
      const t = at != null ? at : this.now();
      this.playing = false;
      this.paused = clamp(t, 0, P.total);
      this.usingAudio = false;
      this.want = null;
      if (this.audio) { try { this.audio.pause(); } catch (_) { /* ignore */ } }
      syncPlayButton();
    },
    seek(t) {
      t = clamp(t, 0, P.total);
      this.paused = t;
      if (this.playing && this.audioOk && this.hasSource() && t < P.audioMs - 60) {
        this.useAudioFrom(t);
        return;
      }
      if (this.audio && this.hasSource() && t < P.audioMs - 60) {
        try { this.audio.currentTime = t / 1000; } catch (_) { /* ignore */ }
      }
      if (this.playing) {
        if (this.audio) { try { this.audio.pause(); } catch (_) { /* ignore */ } }
        this.startClock(t);
      }
    },
    setRate(r) {
      const t = this.now();
      this.rate = r;
      if (this.audio) this.audio.playbackRate = r;
      if (this.playing && !this.usingAudio) this.startClock(t);
    },
  };

  function setAudioNote(text) { els['audio-note'].textContent = text; }

  function setupAudio(rec) {
    if (player.audio) { try { player.audio.pause(); player.audio.removeAttribute('src'); player.audio.load(); } catch (_) { /* ignore */ } }
    player.audio = null;
    player.audioOk = false;
    player.usingAudio = false;
    els.mute.hidden = true;
    if (!rec.audio || !rec.audio.file) {
      setAudioNote('Text-only recording: there is no sound, so the replay runs on the badge clock.');
      return;
    }
    const url = `data/${rec.audio.file}`;
    const audio = new Audio();
    audio.preload = 'auto';
    audio.muted = player.muted;
    player.audio = audio;
    player.audioOk = true;
    els.mute.hidden = false;
    setAudioNote((rec.audio.source_channels || 1) >= 3
      ? 'With sound: the omni channel of the badge\'s four microphones.'
      : 'With sound: the badge\'s own microphone.');
    // A blob is seekable even where the host ignores range requests; the plain URL is the fallback.
    let stage = 'blob';
    const direct = () => { if (player.audio !== audio) return; stage = 'direct'; audio.src = url; };
    audio.addEventListener('error', () => {
      if (player.audio !== audio || !audio.getAttribute('src')) return;
      if (stage === 'blob') direct(); else audioFailed();
    });
    audio.addEventListener('loadedmetadata', () => {
      if (player.audio !== audio) return;
      if (Number.isFinite(audio.duration) && audio.duration > 0) P.audioMs = Math.min(P.audioMs || Infinity, audio.duration * 1000);
      player.adopt();  // pressed play before the sound was ready: join the clock where it is
    });
    for (const type of ['loadeddata', 'canplay', 'seeked']) {
      audio.addEventListener(type, () => { if (player.audio === audio) player.reapply(); });
    }
    if (window.fetch && window.URL && URL.createObjectURL) {
      fetch(url)
        .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
        .then((b) => { if (player.audio === audio) audio.src = URL.createObjectURL(b); })
        .catch(direct);
    } else {
      direct();
    }
    function audioFailed() {
      if (player.audio !== audio) return;
      player.audioOk = false;
      els.mute.hidden = true;
      if (player.playing && player.usingAudio) player.startClock(player.now());
      player.usingAudio = false;
      setAudioNote('The sound could not load here, so the replay runs on the badge clock.');
    }
  }

  // ---------------------------------------------------------------- radar
  function drawRadarStatic() {
    const g = els['radar-static'];
    const ring = 40;
    let s = '';
    s += `<circle class="ring-far" cx="50" cy="50" r="${ring + 6}"/>`;
    s += `<path class="wedge" d="M50 50 L${50 - (ring + 5) * Math.sin(Math.PI / 180 * 28)} ${50 - (ring + 5) * Math.cos(Math.PI / 180 * 28)} A${ring + 5} ${ring + 5} 0 0 1 ${50 + (ring + 5) * Math.sin(Math.PI / 180 * 28)} ${50 - (ring + 5) * Math.cos(Math.PI / 180 * 28)} Z"/>`;
    s += `<circle class="ring" cx="50" cy="50" r="${ring}"/>`;
    s += `<circle class="ring-inner" cx="50" cy="50" r="${ring * 0.55}"/>`;
    for (let a = 0; a < 360; a += 10) {
      const major = a % 90 === 0, mid = a % 30 === 0;
      const r1 = ring, r2 = ring + (major ? 2.4 : mid ? 1.5 : 0.8);
      const sa = Math.sin((a * Math.PI) / 180), ca = Math.cos((a * Math.PI) / 180);
      s += `<line class="tick${major || mid ? '' : ' minor'}" x1="${50 - r1 * sa}" y1="${50 - r1 * ca}" x2="${50 - r2 * sa}" y2="${50 - r2 * ca}"/>`;
    }
    const label = (a, text) => {
      const r = ring + 8.3, sa = Math.sin((a * Math.PI) / 180), ca = Math.cos((a * Math.PI) / 180);
      const x = 50 - r * sa, y = 50 - r * ca;
      const turn = a === 90 ? -90 : a === -90 ? 90 : 0;
      return `<text class="compass" x="${x}" y="${y}" text-anchor="middle" dominant-baseline="middle"${turn ? ` transform="rotate(${turn} ${x} ${y})"` : ''}>${text}</text>`;
    };
    // left / right is what a chest badge can tell; front / back it cannot, and the labels say so
    s += label(0, 'ahead · unreliable') + label(180, 'behind · unreliable') + label(90, 'left') + label(-90, 'right');
    s += `<line class="ahead" x1="50" y1="50" x2="50" y2="${50 - ring * 0.3}"/>`;
    g.innerHTML = s;
  }

  /** Who is audible now: the speaker the log gives each turn, over that turn's start..end on the audio clock.
      (The transcriber names the voice when the turn ends; the replay lights it while it is heard.) */
  function talkingSpeakers(st, t) {
    const out = new Set();
    for (const sp of P.spans) {
      if (sp.start > t) break;
      if (t < sp.end) out.add(sp.speaker);
    }
    for (const tr of st.turns.values()) {
      if (!tr.done && tr.speaker && typeof tr.start === 'number' && t - tr.start < 30000) out.add(tr.speaker);
    }
    return out;
  }

  function personBySpeaker(st) {
    const m = new Map();
    for (const p of st.people.values()) for (const sp of p.speakers || []) m.set(sp, p);
    return m;
  }

  function computeBlips(st, t) {
    const personOf = personBySpeaker(st);
    const talking = talkingSpeakers(st, t);
    const others = [];
    for (const [k, v] of st.positions) if (!st.owner.has(k) && Number.isFinite(v.level)) others.push(v.level);
    const loud = others.length ? Math.max(...others) : null;

    const groups = new Map();
    for (const sp of st.speakers.values()) {
      if (st.owner.has(sp.id)) continue;
      const p = personOf.get(sp.id);
      const id = p ? `p:${p.key}` : `v:${sp.id}`;
      if (!groups.has(id)) groups.set(id, { id, person: p, speakers: [] });
      groups.get(id).speakers.push(sp.id);
    }
    for (const p of st.people.values()) {
      const id = `p:${p.key}`;
      const sps = (p.speakers || []).filter((s) => !st.owner.has(s));
      if (!groups.has(id) && sps.length) groups.set(id, { id, person: p, speakers: sps });
    }

    const blips = [];
    const unplaced = [];
    for (const sp of talking) {
      if (!st.speakers.has(sp) && !st.owner.has(sp)) unplaced.push({ id: `v:${sp}`, person: personOf.get(sp), speakers: [sp] });
    }
    for (const gr of groups.values()) {
      let az = null, level = null, spread = 0, low = false;
      if (P.hasDirection) {
        const pos = gr.speakers.map((s) => st.positions.get(s)).filter(Boolean);
        if (pos.length) {
          az = circMean(pos.map((x) => x.az));
          const lv = pos.map((x) => x.level).filter(Number.isFinite);
          level = lv.length ? Math.max(...lv) : null;
          spread = Math.max(...pos.map((x) => Number(x.spread) || 0));
          low = pos.every((x) => x.low === true);
        }
      } else {
        const slot = gr.speakers.map((s) => P.slots.get(s)).find((v) => v != null);
        az = slot != null ? slot : 0;
      }
      const isTalking = gr.speakers.some((s) => talking.has(s));
      if (az == null) { if (isTalking) unplaced.push(gr); continue; }
      const d = P.hasDirection && loud != null && level != null ? clamp((loud - level) / 18, 0, 1) : 0.5;
      const key = gr.person ? gr.person.key : null;
      blips.push({
        id: gr.id, person: gr.person, speakers: gr.speakers, bearing: wrap180(az - st.yaw), d,
        talking: isTalking, known: key ? metBefore(P, st, key).length > 0 : false,
        colour: key ? P.colour.get(key) : null,
        // a soft region, not a point: wider when the turns disagreed, much wider when the array was unsure
        placed: P.hasDirection, half: P.hasDirection ? clamp(Math.max(spread, 10) + (low ? 28 : 12), 16, 60) : 0, low,
      });
    }
    // the wearer's own voice, once recognised, slides into the centre
    if (st.ownerT != null && t - st.ownerT < 1500) {
      for (const sp of st.owner) {
        if (st.speakers.has(sp)) blips.push({ id: `v:${sp}`, absorbing: true, speakers: [sp], bearing: 0, d: 0, talking: false });
      }
    }

    // Close voices on the inner ring, far ones at the edge; named neighbours spread apart so labels stay readable.
    const R = 40;
    for (const b of blips) { b.radius = R * (0.64 + 0.36 * b.d); b.drawn = b.bearing; }
    const named = blips.filter((b) => b.person && !b.absorbing).sort((a, b) => a.bearing - b.bearing);
    if (named.length > 1) {
      const minGap = 36;
      for (let it = 0; it < 14; it++) {
        for (let k = 0; k < named.length; k++) {
          const a = named[k], c = named[(k + 1) % named.length];
          let gap = c.drawn - a.drawn;
          if (k === named.length - 1) gap += 360;
          if (gap < minGap) { const push = (minGap - gap) / 2; a.drawn -= push; c.drawn += push; }
        }
      }
      for (const b of named) b.drawn = wrap180(b.drawn);
    }
    const ownerTalking = [...st.owner].some((s) => talking.has(s));
    return { blips, unplaced, ownerTalking };
  }

  function blipSide(a) {
    if (Math.abs(a) < 40) return 'above';
    if (Math.abs(a) > 140) return 'below';
    return a > 0 ? 'left' : 'right';
  }

  /** The side a name goes on: away from the centre, unless that would run off the radar. */
  function fitLabel(pref, px, py, lw, W) {
    const edge = Math.abs(py - W / 2) < W * 0.09 ? W * 0.045 : 2;  // keep clear of the LEFT / RIGHT words
    const fits = (side) => (side === 'left' ? px - 18 - lw >= edge : side === 'right' ? px + 18 + lw <= W - edge : px - lw / 2 >= 2 && px + lw / 2 <= W - 2);
    const order = { above: ['above', 'below', 'right', 'left'], below: ['below', 'above', 'right', 'left'], left: ['left', 'right', 'above', 'below'], right: ['right', 'left', 'above', 'below'] }[pref];
    for (const side of order) if (fits(side)) return { side, shift: 0 };
    const left = px - lw / 2;
    const shift = left < 2 ? 2 - left : px + lw / 2 > W - 2 ? W - 2 - (px + lw / 2) : 0;
    return { side: pref === 'below' ? 'below' : 'above', shift };
  }

  /** The voices as soft regions on the radar: one blurred wedge per voice in its person's colour, centred where the
   *  array put it, as wide as the array was unsure. Drawn on a canvas under the labels, only when something moved. */
  function renderRadarRegions(blips, W) {
    const c = els['radar-wedges'];
    const sig = blips.map((b) => `${b.id}|${b.drawn.toFixed(1)}|${b.radius.toFixed(1)}|${b.half}|${b.talking ? 1 : 0}|${b.colour}|${b.placed ? 1 : 0}`).join(';') +
      `|${W}|${document.documentElement.getAttribute('data-theme') || ''}|${els.radar.classList.contains('ghost') ? 'g' : ''}`;
    if (c._sig === sig) return;
    c._sig = sig;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    if (c._w !== W || c._dpr !== dpr) { c.width = Math.round(W * dpr); c.height = Math.round(W * dpr); c._w = W; c._dpr = dpr; }
    const ctx = c.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, W);
    const cs = getComputedStyle(els.radar);
    const ghost = els.radar.classList.contains('ghost');
    for (const b of blips) {
      if (!b.placed || b.absorbing) continue;
      const hex = (b.colour == null ? cs.getPropertyValue('--accent') : cs.getPropertyValue(`--p${b.colour % 8}`)).trim() || '#2F7F72';
      const th = rad(-90 - b.drawn);  // the radar's angles run anticlockwise from ahead: left is positive
      const r = (b.radius * W) / 100, half = rad(b.half);
      const a = (ghost ? 0.5 : 1) * (b.talking ? 0.6 : b.person ? 0.34 : 0.22);
      softWedge(ctx, W / 2, W / 2, Math.max(10, r - W * 0.09), r + W * 0.09, th - half, th + half, hex, a);
      if (b.talking) softWedge(ctx, W / 2, W / 2, Math.max(8, r - W * 0.14), r + W * 0.14, th - half * 1.5, th + half * 1.5, hex, a * 0.3);
    }
  }

  function renderRadar(st, t) {
    const { blips, unplaced, ownerTalking } = computeBlips(st, t);
    const W = els.radar.clientWidth || 600;
    const short = W < 480;
    renderRadarRegions(blips, W);
    const keep = new Set();
    for (const b of blips) {
      if (!blipEls.has(b.id) && b.person) {
        for (const sp of b.speakers) {
          const old = blipEls.get(`v:${sp}`);
          if (old) { blipEls.delete(`v:${sp}`); blipEls.set(b.id, old); break; }
        }
      }
    }
    for (const b of blips) {
      let el = blipEls.get(b.id);
      if (!el) {
        el = document.createElement('div');
        el.className = 'blip';
        el.innerHTML = '<span class="ripple"></span><span class="ripple r2"></span><span class="dot"></span><span class="label"></span>';
        blipEls.set(b.id, el);
        els.blips.appendChild(el);
      }
      keep.add(b.id);
      const a = (b.drawn * Math.PI) / 180;
      const x = b.absorbing ? 0 : -Math.sin(a) * b.radius;
      const y = b.absorbing ? 0 : -Math.cos(a) * b.radius;
      let label;
      if (b.person) {
        const name = !short && b.person.name.length <= 15 ? b.person.name : shortName(b.person.name);
        const sub = [b.person.company].filter(Boolean).join('');
        label = `${esc(name)}${b.low ? ' <span class="unsure" title="the array was not sure where">?</span>' : ''}<small>${esc(sub)}${b.known ? `${sub ? ' · ' : ''}<span class="met">met before</span>` : ''}</small>`;
      } else {
        label = b.low ? 'new voice ?' : 'new voice';
      }
      const labelEl = el.querySelector('.label');
      if (el._label !== label) { el._label = label; labelEl.innerHTML = label; el._lw = 0; }
      if (el.classList.contains('named') !== !!b.person) {  // the type size depends on it, so before measuring
        el.classList.toggle('named', !!b.person);
        el.classList.toggle('voice', !b.person);
        el._lw = 0;
      }
      if (!el._lw || el._lwFor !== W) { el._lw = labelEl.offsetWidth; el._lwFor = W; }
      const fit = b.person ? fitLabel(blipSide(b.drawn), W / 2 + (x * W) / 100, W / 2 + (y * W) / 100, el._lw, W) : { side: blipSide(b.drawn), shift: 0 };
      if (el._shift !== fit.shift) { el._shift = fit.shift; el.style.setProperty('--shift', `${fit.shift.toFixed(1)}px`); }
      const cls = ['blip', b.person ? 'named' : 'voice', `side-${fit.side}`];
      if (b.talking) cls.push('talking');
      if (b.known) cls.push('known');
      if (b.absorbing) cls.push('absorbing');
      if (b.placed) cls.push('placed');  // the wedge is the position; the dot shrinks to a label anchor
      const className = cls.join(' ');
      if (el.className !== className) el.className = className;
      const pos = `${x.toFixed(2)}|${y.toFixed(2)}|${b.colour}`;
      if (el._pos !== pos) {
        el._pos = pos;
        el.style.setProperty('--x', x.toFixed(2));
        el.style.setProperty('--y', y.toFixed(2));
        el.style.setProperty('--c', pcol(b.colour));
      }
    }
    for (const [id, el] of blipEls) {
      if (keep.has(id)) continue;
      blipEls.delete(id);
      el.classList.add('leaving');
      setTimeout(() => el.remove(), 650);
    }
    const unplacedOn = unplaced.length > 0;
    els['new-voice'].classList.toggle('on', unplacedOn);
    els['new-voice-label'].classList.toggle('on', unplacedOn);
    if (unplacedOn) {
      const p = unplaced[0].person;
      const text = P.hasDirection ? (p ? `${shortName(p.name)}, placing…` : 'a new voice, placing…') : 'a new voice';
      if (els['new-voice-label'].textContent !== text) els['new-voice-label'].textContent = text;
    }
    els.wearer.classList.toggle('talking', ownerTalking);
  }

  function renderRadarNote(st) {
    const parts = [];
    if (!P.hasDirection) parts.push('No direction on this recording (one microphone), so voices sit in the order they arrived.');
    if (st.topics && st.topics.length) parts.push(`Overheard nearby: <span class="topics">${esc(st.topics.join(' · '))}</span>`);
    const html = parts.join('<br>');
    if (els['radar-note']._html !== html) { els['radar-note']._html = html; els['radar-note'].innerHTML = html; }
  }

  // ---------------------------------------------------------------- captions
  function renderCaptions(t) {
    const visible = [];
    for (const c of P.captions) {
      if (c.show > t) break;
      if (t < c.show + CAPTION_LIFE) visible.push(c);
    }
    const shown = visible.slice(-MAX_CAPTIONS);
    const ids = new Set(shown.map((c) => c.id));
    for (const [id, el] of captionEls) {
      if (ids.has(id)) continue;
      captionEls.delete(id);
      el.classList.add('out');
      setTimeout(() => el.remove(), 450);
    }
    shown.forEach((c, k) => {
      let el = captionEls.get(c.id);
      if (!el) {
        el = document.createElement('div');
        el.className = `caption m-${c.model}`;
        el.innerHTML = `<span class="model">${esc(MODEL[c.model] || c.model)}</span><span class="what">${esc(c.what)}</span>${c.detail ? `<span class="detail">${c.detail}</span>` : ''}`;
        captionEls.set(c.id, el);
        els.captions.appendChild(el);
      }
      el.classList.toggle('old', k < shown.length - 1);
    });
  }

  // ---------------------------------------------------------------- people strip
  function renderPeople(st, t) {
    const talking = talkingSpeakers(st, t);
    const list = [...st.people.values()].sort((a, b) => (P.colour.get(a.key) ?? 99) - (P.colour.get(b.key) ?? 99));
    const keep = new Set();
    for (const p of list) {
      keep.add(p.key);
      let el = personEls.get(p.key);
      if (!el) {
        el = document.createElement('li');
        el.innerHTML = '<button type="button" class="person"></button>';
        const btn = el.firstChild;
        btn.addEventListener('click', () => {
          const cur = S.people.get(p.key) || p;
          const ev = evidenceStart(P, cur.evidence_turns);
          if (ev) { jumpTo(ev.t, ev.turn); if (!player.playing) player.play(); }
        });
        personEls.set(p.key, el);
        els.people.appendChild(el);
      }
      const btn = el.firstChild;
      const before = metBefore(P, st, p.key);
      const by = p.introduced_by && p.introduced_by !== 'owner' ? (st.people.get(p.introduced_by) || {}).name || '' : '';
      const bits = [p.company, p.role].filter(Boolean).map(esc);
      if (before.length) bits.push(`<span class="met">met before · ${esc(before[0].event)}${before.length > 1 ? ` +${before.length - 1}` : ''}</span>`);
      if (by) bits.push(`introduced by ${esc(shortName(by))}`);
      if (p.preferred_language && p.preferred_language !== 'English') bits.push(`speaks ${esc(p.preferred_language)}`);
      const html = `<span class="sw"></span><span class="nm">${esc(p.name)}</span><span class="co">${bits.join(' · ') || 'new tonight'}</span>`;
      if (btn._html !== html) { btn._html = html; btn.innerHTML = html; btn.setAttribute('aria-label', `${p.name}: jump to the introduction`); }
      btn.style.setProperty('--c', pcol(P.colour.get(p.key)));
      btn.classList.toggle('known', before.length > 0);
      btn.classList.toggle('talking', (p.speakers || []).some((s) => talking.has(s)));
    }
    for (const [k, el] of personEls) if (!keep.has(k)) { personEls.delete(k); el.remove(); }
    // keep the strip in appearance order
    list.forEach((p) => { const el = personEls.get(p.key); if (el && el !== els.people.lastChild) els.people.appendChild(el); });
  }

  // ---------------------------------------------------------------- transcript
  function speakerName(st, personOf, sp) {
    if (st.owner.has(sp)) return { name: `${P.ownerName} (you)`, cls: 'owner', colour: null };
    const p = personOf.get(sp);
    if (p) return { name: p.name, cls: 'named', colour: P.colour.get(p.key) };
    const parts = String(sp).split(':');
    const letter = parts[parts.length - 1];
    return { name: `Voice ${letter}${P.multiSession ? ' · ' + parts[0] : ''}`, cls: 'voice', colour: null };
  }

  function highlight(text, suspects) {
    let html = esc(text);
    for (const s of suspects) {
      const needle = esc(s.heard);
      if (!needle) continue;
      const re = new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      html = html.replace(re, (m) => `<mark class="suspect" title="${esc(`may be misheard: likely ${s.likely}`)}">${m}</mark>`);
    }
    return html;
  }

  function renderTranscript(st, t) {
    const box = els.transcript;
    const personOf = personBySpeaker(st);
    const evidence = new Set();
    for (const q of st.promises.values()) for (const n of q.evidence_turns || []) evidence.add(n);
    const suspectsByTurn = new Map();
    for (const s of st.suspects.values()) {
      if (!suspectsByTurn.has(s.turn)) suspectsByTurn.set(s.turn, []);
      suspectsByTurn.get(s.turn).push(s);
    }
    const lines = [...st.turns.values()]
      .filter((tr) => (tr.done ? tr.text : typeof tr.start === 'number' && t - tr.start < 30000))
      .sort((a, b) => a.start - b.start || a.turn - b.turn);

    const stick = stickTranscript || box.scrollHeight - box.scrollTop - box.clientHeight < 60;
    const keep = new Set();
    let prev = null;
    for (const tr of lines) {
      keep.add(tr.turn);
      let el = lineEls.get(tr.turn);
      if (!el) {
        el = document.createElement('li');
        el.addEventListener('click', () => { const start = P.turnStart.get(tr.turn); if (start != null) jumpTo(start - 150, null); });
        lineEls.set(tr.turn, el);
      }
      const who = tr.speaker ? speakerName(st, personOf, tr.speaker) : { name: 'Listening', cls: 'voice', colour: null };
      const kind = st.kinds.get(tr.turn);
      const filtered = !!KIND_LABEL[kind];
      const translation = st.translations.get(tr.turn);
      const sus = suspectsByTurn.get(tr.turn) || [];
      const partial = st.partial.get(tr.turn);
      let html = `<div class="who"><b>${esc(who.name)}</b><time>${mmss(tr.start)}</time>`;
      if (evidence.has(tr.turn)) html += '<span class="tag accent">promise</span>';
      if (filtered) html += `<span class="tag">filtered · ${esc(KIND_LABEL[kind])}</span>`;
      if (sus.length) html += `<span class="tag">misheard? ${esc(sus.map((s) => s.likely).join(', '))}</span>`;
      html += '</div>';
      if (tr.done) {
        html += `<p class="text">${highlight(tr.text, sus)}</p>`;
        if (translation && translation.english) {
          html += `<p class="tr"><span class="tag accent">translated · ${esc(translation.language || '')}</span>${esc(translation.english)}</p>`;
        }
      } else {
        html += `<p class="text">${partial ? esc(partial) + ' ' : ''}<span class="dots" aria-label="speaking"><span></span><span></span><span></span></span></p>`;
      }
      const cls = ['line', who.cls];
      if (filtered) cls.push('filtered');
      if (!tr.done) cls.push('speaking');
      if (flashTurn === tr.turn) cls.push('flash');
      const className = cls.join(' ');
      if (el._html !== html) { el._html = html; el.innerHTML = html; }
      if (el.className !== className) el.className = className;
      el.style.setProperty('--c', pcol(who.colour));
      const want = prev ? prev.nextSibling : box.firstChild;
      if (want !== el) box.insertBefore(el, want);
      prev = el;
    }
    for (const [k, el] of lineEls) if (!keep.has(k)) { lineEls.delete(k); el.remove(); }
    if (stick) box.scrollTop = box.scrollHeight;
    stickTranscript = false;
  }

  // ---------------------------------------------------------------- promises and misheard words
  function nameFor(st, key) {
    if (key === 'owner') return 'You';
    const p = st.people.get(key) || P.final.people.get(key);
    return p ? p.name : key;
  }

  function renderPromises(st, t) {
    const keep = new Set();
    for (const q of st.promises.values()) {
      keep.add(q.key);
      let el = promiseEls.get(q.key);
      if (!el) {
        el = document.createElement('li');
        el.tabIndex = 0;
        el.setAttribute('role', 'button');
        const go = () => {
          const cur = S.promises.get(q.key) || P.final.promises.get(q.key) || q;
          const ev = evidenceStart(P, cur.evidence_turns);
          if (!ev) return;
          jumpTo(ev.t, ev.turn);
          if (!player.playing) player.play();
          toast(`Back to turn ${ev.turn}, where it was said. Muse Spark catches it at ${mmss(cur.firstT ?? cur.t_ms)}.`);
        };
        el.addEventListener('click', go);
        el.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); go(); } });
        promiseEls.set(q.key, el);
        els.promises.appendChild(el);
      }
      const other = q.owed_by === 'owner' ? q.owed_to : q.owed_by;
      const dir = `${esc(nameFor(st, q.owed_by))} → ${esc(nameFor(st, q.owed_to) === 'You' ? 'you' : nameFor(st, q.owed_to))}`;
      const struck = (q.struck || []).map((s) => `<s>${esc(s)}</s>`).join('');
      const due = q.due ? `${struck}<b>${esc(q.due)}</b>` : `${struck}<span class="none">no date</span>`;
      const ev = evidenceStart(P, q.evidence_turns);
      const html = `<span class="dir"><span class="sw"></span>${dir}</span><span class="what">${esc(q.what)}</span><span class="due">${due}</span>` +
        (ev ? `<span class="jump">said in turn ${ev.turn} · ${mmss(ev.t)} · tap to hear it</span>` : '');
      if (el._html !== html) { el._html = html; el.innerHTML = html; el.setAttribute('aria-label', `Promise: ${q.what}. Jump to where it was said.`); }
      el.style.setProperty('--c', other === 'owner' ? 'var(--ink)' : pcol(P.colour.get(other)));
      const fresh = t - (q.correctedT ?? q.firstT ?? 0) < 2500;
      const cls = `promise${q.struck && q.struck.length ? ' corrected strike-in' : ''}${fresh ? ' fresh' : ''}`;
      if (el.className !== cls) el.className = cls;
    }
    for (const [k, el] of promiseEls) if (!keep.has(k)) { promiseEls.delete(k); el.remove(); }

    const sus = [...st.suspects.values()];
    els['suspects-box'].hidden = sus.length === 0;
    const html = sus.map((s) => `<li class="suspect-row" data-turn="${Number(s.turn)}" tabindex="0" role="button"><span class="heard">${esc(s.heard)}</span><span>→</span><span class="likely">${esc(s.likely)}</span><span class="why">turn ${Number(s.turn)} · ${esc(s.reason || '')}</span></li>`).join('');
    if (els.suspects._html !== html) { els.suspects._html = html; els.suspects.innerHTML = html; }
  }

  // ---------------------------------------------------------------- after the evening
  function renderAfter(st) {
    const done = st.ended || st.moves.size > 0;
    els.waiting.hidden = done;
    const sig = done ? [...st.moves.keys()].join('|') : '';
    if (sig !== movesSig) {
      movesSig = sig;
      els.moves.innerHTML = '';
      if (done) {
        let k = 0;
        for (const m of st.moves.values()) els.moves.appendChild(moveCard(st, m, k++));
        if (!st.moves.size) {
          els.moves.innerHTML = st.promises.size
            ? '<div class="empty-state">This recording has no follow-up drafts: it was made before Hallwise wrote them.</div>'
            : '<div class="empty-state">No promises were made this evening, so there is nothing to follow up.</div>';
        }
      }
    }
    const report = P.rec.report;
    els.morning.hidden = !(done && report);
    if (done && report && !morningDrawn) drawMorning(report);
    els.week.hidden = !done;
    if (done && !weekDrawn) drawWeek();
  }

  /** Copy to the clipboard where the host allows it, else select the text so the reader can copy it. */
  function wireCopy(btn, text, bodyEl) {
    const label = btn.textContent;
    btn.addEventListener('click', () => {
      const done = () => { btn.textContent = 'Copied'; setTimeout(() => { btn.textContent = label; }, 1600); };
      const fallback = () => {
        const range = document.createRange();
        range.selectNodeContents(bodyEl);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        btn.textContent = 'Selected, press copy';
      };
      try {
        const pr = navigator.clipboard && navigator.clipboard.writeText(text);
        if (pr && pr.then) pr.then(done, fallback); else fallback();
      } catch (_) { fallback(); }
    });
  }

  function moveCard(st, m, k) {
    const person = st.people.get(m.person_key) || P.final.people.get(m.person_key);
    const promise = st.promises.get(m.promise_key) || P.final.promises.get(m.promise_key);
    const kind = { email: 'Email', message: 'Message', calendar: 'Calendar invite', nudge: 'Reminder for you' }[m.kind] || m.kind || 'Draft';
    const el = document.createElement('article');
    el.className = `move kind-${m.kind}`;
    el.style.setProperty('--c', person ? pcol(P.colour.get(person.key)) : 'var(--accent)');
    el.style.animationDelay = `${k * 90}ms`;
    const translated = m.body_english && m.language && m.language !== 'English';
    const rewritten = !!(P.rec.report && (P.rec.report.redrafted || []).includes(m.promise_key));
    const rows = [];
    if (m.kind === 'calendar' && m.when) rows.push(['Proposed', `<dd class="slot">${esc(fmtSlot(m.when, m.duration_minutes))}</dd>`]);
    if (m.remind_at) rows.push(['Reminder', `<dd class="slot">${esc(fmtWhen(m.remind_at))}</dd>`]);
    if (m.nudge) rows.push(['Nudge', `<dd>${esc(m.nudge)}</dd>`]);
    if (m.attach) rows.push(['Attach', `<dd>${esc(m.attach)}</dd>`]);
    if (promise) rows.push(['Promise', `<dd>${esc(promise.what)}${promise.due ? ` · <b>${esc(promise.due)}</b>` : ''}${promise.struck && promise.struck.length ? ` <s>${esc(promise.struck.join(', '))}</s>` : ''}</dd>`]);
    if (m.why) rows.push(['Why', `<dd class="why">${esc(m.why)}</dd>`]);
    el.innerHTML = `
      <div class="move-top">
        <span class="kind">${esc(kind)}</span>
        <span class="tag${translated ? ' accent' : ''}">${esc(m.language || 'English')}</span>
      </div>
      <div class="to"><span class="sw"></span><b>${esc(person ? person.name : m.person_key)}</b>${person && person.company ? `<span>${esc(person.company)}</span>` : ''}</div>
      ${m.subject ? `<h3>${esc(m.subject)}</h3>` : ''}
      <p class="body">${esc(m.body || '')}</p>
      ${translated ? `<div class="english"><span class="tag">In English</span><p>${esc(m.body_english)}</p></div>` : ''}
      ${rows.length ? `<dl>${rows.map(([dt, dd]) => `<dt>${dt}</dt>${dd}`).join('')}</dl>` : ''}
      <div class="move-actions">
        <button type="button" class="ghost-btn" data-act="copy">Copy text</button>
        ${promise ? '<button type="button" class="ghost-btn" data-act="hear">Hear the promise</button>' : ''}
        ${rewritten ? '<button type="button" class="ghost-btn" data-act="morning">Rewritten next morning ↓</button>' : ''}
      </div>`;
    wireCopy(el.querySelector('[data-act="copy"]'), [m.subject, m.body].filter(Boolean).join('\n\n'), el.querySelector('.body'));
    const later = el.querySelector('[data-act="morning"]');
    if (later) {
      later.addEventListener('click', () => {
        const card = redraftEls.get(m.promise_key);
        if (card) card.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' });
      });
    }
    const hear = el.querySelector('[data-act="hear"]');
    if (hear) {
      hear.addEventListener('click', () => {
        const ev = evidenceStart(P, promise.evidence_turns);
        if (!ev) return;
        jumpTo(ev.t, ev.turn);
        if (!player.playing) player.play();
        document.querySelector('.stage').scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' });
      });
    }
    return el;
  }

  // ---------------------------------------------------------------- the next morning
  /** The morning report the server writes once a recording is over (exported under `report`): the reasons to
   *  write today, the drafts those reasons rewrote, who was checked in public, and what falls due. Drawn once,
   *  shown and hidden with the follow-ups. */
  const MOVE_KIND = { email: 'Email', message: 'Message', calendar: 'Calendar invite', nudge: 'Reminder for you' };
  const HOOK_KIND = { introduction: 'Introduction owed', mutual_connection: 'Mutual connection', open_thread: 'Open thread', timely: 'In public this week' };
  // the status as research reports it, and what it does and does not say
  const CHECK = {
    matched: ['public profile found', 'A public page ties them to the company.'],
    partial: ['company found', 'The company turned up; nothing public ties them to it.'],
    no_public_record: ['no public record found', 'Check before sending.'],
  };

  const offsetLabel = (min) => {
    const a = Math.abs(min);
    return `UTC${min < 0 ? '-' : '+'}${Math.floor(a / 60)}${a % 60 ? ':' + String(a % 60).padStart(2, '0') : ''}`;
  };
  const capital = (s) => String(s || '').replace(/^./, (c) => c.toUpperCase());

  /** "Tue 27 Oct · 08:00 · Taipei, UTC+8": eight in the morning of the report's day, in the report's zone. */
  function morningWhen(report) {
    const m = String(report.day || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return '';
    const local = Date.UTC(+m[1], +m[2] - 1, +m[3], 8, 0);
    const tz = String(report.tz || '');
    let zone = '';
    try {
      if (tz && window.Intl) {
        const at = new Date(local - (P.tzOffset || 0) * 60000);
        const part = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'shortOffset' }).formatToParts(at).find((x) => x.type === 'timeZoneName');
        if (part) zone = part.value.replace(/^GMT/, 'UTC');
      }
    } catch (_) { /* a zone or an option this browser does not know */ }
    if (!zone && P.tzOffset != null) zone = offsetLabel(P.tzOffset);
    const city = tz.includes('/') ? tz.split('/').pop().replace(/_/g, ' ') : tz;
    return [`${dayLabel(partsOf(local))} · 08:00`, [city, zone].filter(Boolean).join(', ')].filter(Boolean).join(' · ');
  }

  function epochLabel(sec) {
    const w = wallDate(Number(sec) || 0, P.tzOffset);
    return `${dayLabel(w)} · ${hhmm(w)}`;
  }

  /** A source as a plain link: http(s) only, shown as host and path. */
  function linkHtml(url) {
    try {
      const u = new URL(String(url));
      if (u.protocol !== 'http:' && u.protocol !== 'https:') return esc(url);
      const shown = truncate(u.host.replace(/^www\./, '') + (u.pathname === '/' ? '' : u.pathname), 46);
      return `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(shown)}</a>`;
    } catch (_) {
      return esc(url);
    }
  }

  function personColour(key) {
    return key && P.colour.has(key) ? pcol(P.colour.get(key)) : 'var(--ink-soft)';
  }

  function evidenceItem(e) {
    if (e.kind === 'research') {
      return `<li><div class="ev"><q>${esc(e.quote)}</q><span class="ev-src">public source${e.source ? ` · ${linkHtml(e.source)}` : ''}</span></div></li>`;
    }
    const turn = Number(e.turn);
    const src = `<b>${esc(e.speaker || 'Someone')}</b> · ${esc([e.event, e.day].filter(Boolean).join(' · '))}`;
    if (e.recording !== P.id || !P.turnStart.has(turn)) {
      return `<li><div class="ev"><q>${esc(e.quote)}</q><span class="ev-src">${src}</span></div></li>`;
    }
    const t = P.turnStart.get(turn);
    return `<li><button type="button" class="ev here" data-turn="${turn}" aria-label="${esc(`${e.speaker || 'Someone'}: ${e.quote}. Play turn ${turn}.`)}">` +
      `<q>${esc(e.quote)}</q><span class="ev-src">${src}</span><span class="jump">turn ${turn} · ${mmss(t)} · tap to hear it</span></button></li>`;
  }

  function hookCard(h, k) {
    const el = document.createElement('article');
    el.className = 'move hook';
    el.style.animationDelay = `${k * 90}ms`;
    const who = (h.people || []).map((ik, i) => {
      const rk = (h.record_keys || {})[ik];
      return `<span class="who-one"><span class="sw" style="background:${personColour(rk)}"></span><b>${esc((h.names || [])[i] || ik)}</b></span>`;
    }).join('');
    const evidence = (h.evidence || []).map(evidenceItem).join('');
    const foreign = h.language && h.language !== 'English';
    el.innerHTML = `
      <div class="move-top">
        <span class="kind">${esc(HOOK_KIND[h.type] || capital(String(h.type || 'reason').replace(/_/g, ' ')))}</span>
        ${h.tonight ? '<span class="tag accent">from last night</span>' : '<span class="tag">earlier this week</span>'}
      </div>
      <div class="to">${who}</div>
      <h4>${esc(h.title)}</h4>
      ${h.tag && h.tag !== h.title ? `<p class="hook-tag">${esc(h.tag)}</p>` : ''}
      ${h.reason ? `<p class="reason">${esc(h.reason)}</p>` : ''}
      ${evidence ? `<ul class="evidence">${evidence}</ul>` : ''}
      ${h.draft ? `<details class="draft"><summary>Draft ready to send${foreign ? ` · ${esc(h.language)}` : ''}</summary>
        <p class="body">${esc(h.draft)}</p>
        ${foreign && h.draft_english ? `<div class="english"><span class="tag">In English</span><p>${esc(h.draft_english)}</p></div>` : ''}
      </details>` : ''}`;
    return el;
  }

  function draftBlock(m, cls, label) {
    const foreign = m.body_english && m.language && m.language !== 'English';
    return `<div class="${cls}">
        ${label}
        ${m.subject ? `<h4>${esc(m.subject)}</h4>` : ''}
        <p class="body">${esc(m.body || '')}</p>
        ${foreign ? `<div class="english"><span class="tag">In English</span><p>${esc(m.body_english)}</p></div>` : ''}
      </div>`;
  }

  function redraftCard(report, key, k) {
    const r = (report.reach_out || []).find((x) => x.followup && x.followup.promise_key === key && x.followup.move);
    if (!r) return null;
    const now = r.followup.move;
    const then = P.final.moves.get(key) || null;
    const pk = now.person_key || (then && then.person_key) || (r.person && r.person.key);
    const person = P.final.people.get(pk);
    const name = person ? person.name : (r.person && r.person.name) || pk;
    const company = person ? person.company : r.person && r.person.company;
    const hooks = [r.hook, ...(r.more_hooks || [])].filter(Boolean);
    const el = document.createElement('article');
    el.className = `move redraft kind-${now.kind}`;
    el.style.setProperty('--c', personColour(pk));
    el.style.animationDelay = `${k * 90}ms`;
    const rows = [];
    const changed = (a, b, f) => (b && a && b !== a ? ` <s>${esc(f(b))}</s>` : '');
    if (now.kind === 'calendar' && now.when) {
      rows.push(['Proposed', `<dd class="slot">${esc(fmtSlot(now.when, now.duration_minutes))}${changed(now.when, then && then.when, (w) => fmtSlot(w, then.duration_minutes))}</dd>`]);
    }
    if (now.remind_at) rows.push(['Reminder', `<dd class="slot">${esc(fmtWhen(now.remind_at))}${changed(now.remind_at, then && then.remind_at, fmtWhen)}</dd>`]);
    if (now.why) rows.push(['Why', `<dd class="why">${esc(now.why)}</dd>`]);
    el.innerHTML = `
      <div class="move-top">
        <span class="kind">${esc(MOVE_KIND[now.kind] || now.kind || 'Draft')}</span>
        <span class="tags"><span class="tag accent">rewritten this morning</span><span class="tag">${esc(now.language || 'English')}</span></span>
      </div>
      <div class="to"><span class="sw"></span><b>${esc(name)}</b>${company ? `<span>${esc(company)}</span>` : ''}</div>
      ${hooks.length ? `<p class="because"><span class="kind">because</span>${hooks.map((h) => `<span class="because-one"><b>${esc(h.title)}</b>${h.tag && h.tag !== h.title ? `<span class="hook-tag">${esc(h.tag)}</span>` : ''}</span>`).join('')}</p>` : ''}
      <div class="pair">
        ${draftBlock(now, 'now', '<span class="pair-label">This morning</span>')}
        ${then ? draftBlock(then, 'then', '<span class="pair-label">Last night, at Stop <span class="tag live">replaced</span></span>')
    : '<div class="then"><span class="pair-label">Last night</span><p class="body">No draft in last night\'s log.</p></div>'}
      </div>
      ${rows.length ? `<dl>${rows.map(([dt, dd]) => `<dt>${dt}</dt>${dd}`).join('')}</dl>` : ''}
      <div class="move-actions"><button type="button" class="ghost-btn" data-act="copy">Copy this morning's text</button></div>`;
    wireCopy(el.querySelector('[data-act="copy"]'), [now.subject, now.body].filter(Boolean).join('\n\n'), el.querySelector('.now .body'));
    redraftEls.set(key, el);
    return el;
  }

  function checkRow(c) {
    const status = String(c.status || 'no_public_record');
    const searched = c.searched !== false;
    const [tag, said] = CHECK[status] || [status.replace(/_/g, ' '), ''];
    const linked = new Set();
    const findings = (c.findings || []).filter((f) => f && f.text).map((f) => {
      if (f.source) linked.add(f.source);
      return `<li><span class="tag">${esc(f.kind || 'found')}</span> ${esc(f.text)}${f.source ? ` · ${linkHtml(f.source)}` : ''}</li>`;
    }).join('');
    const extra = (c.sources || []).filter((u) => u && !linked.has(u)).map(linkHtml);
    const meta = [searched ? 'searched the web' : 'no web search ran', c.checked_at ? `checked ${epochLabel(c.checked_at)}` : ''].filter(Boolean).join(' · ');
    return `<li class="check">
        <div class="check-top"><span class="nm">${esc(c.name)}</span>${c.company ? `<span class="co">${esc(c.company)}</span>` : ''}<span class="tag">${esc(!searched && status === 'no_public_record' ? 'no search ran' : tag)}</span></div>
        ${said ? `<p>${esc(said)}</p>` : ''}
        ${findings ? `<ul class="findings">${findings}</ul>` : ''}
        ${extra.length ? `<p>Sources: ${extra.join(' · ')}</p>` : ''}
        <p class="check-meta">${esc(meta)}</p>
      </li>`;
  }

  function uncheckedRow(u) {
    return `<li class="check">
        <div class="check-top"><span class="nm">${esc(u.name || u.key)}</span><span class="tag">not checked</span></div>
        ${u.reason ? `<p>${esc(capital(u.reason))}.</p>` : ''}
      </li>`;
  }

  function dueRow(d, day) {
    const p = d.person || {};
    const iso = String(d.remind_at || '');
    const parsed = parseIso(iso);
    const at = !parsed ? '' : iso.startsWith(day) ? hhmm(partsOf(parsed.base)) : fmtWhen(iso);
    const sub = [p.name, d.what, d.due ? `due ${d.due}` : ''].filter(Boolean).join(' · ');
    return `<li class="due-row" style="--c:${personColour(p.key)}">
        <span class="sw"></span>
        <span class="due-what"><b>${esc(d.nudge || d.what || '')}</b><span>${esc(sub)}</span></span>
        <span class="due-at">${d.overdue ? '<span class="tag live">overdue</span>' : ''}${esc(at)}</span>
      </li>`;
  }

  function costParts(report) {
    const c = report.cost || {};
    const tokens = (Number(c.hooks_tokens) || 0) + (Number(c.research_tokens) || 0);
    const lookups = Number(c.research_requests) || 0;
    const searches = Number(c.searches) || 0;
    const reused = (report.checked || []).filter((x) => x.cached).length;
    const parts = [`Muse Spark · ${tokens.toLocaleString('en-US')} tokens`];
    if (lookups) parts.push(`${word(lookups)} research ${plural(lookups, 'lookup')}`);
    parts.push(searches ? `${searches} web ${plural(searches, 'search', 'searches')}` : 'no new web searches');
    if (reused) parts.push(`${word(reused)} ${plural(reused, 'check')} reused from the cache`);
    const usd = Number(c.usd);
    if (Number.isFinite(usd)) parts.push(usd > 0 && usd < 0.005 ? 'under $0.01' : `$${usd.toFixed(2)}`);
    return parts;
  }

  function drawMorning(report) {
    morningDrawn = true;
    els['morning-when'].textContent = morningWhen(report);
    const sum = report.summary || {};
    const langs = sum.languages || [];
    const count = [
      [sum.people, plural(Number(sum.people), 'person met', 'people met')],
      [sum.followups, plural(Number(sum.followups), 'follow-up')],
      [langs.length, `${plural(langs.length, 'language')} besides English${langs.length ? ': ' + langs.join(', ') : ''}`],
      [sum.introductions, plural(Number(sum.introductions), 'introduction owed', 'introductions owed')],
      [sum.hooks, plural(Number(sum.hooks), 'reason to write', 'reasons to write')],
      [sum.unverified, 'with no public record found'],
    ].filter(([n]) => Number.isFinite(Number(n)) && n !== '' && n != null);
    els['morning-count'].innerHTML = count.map(([n, l]) => `<span><b>${Number(n)}</b>${esc(l)}</span>`).join('');

    const hooks = report.hooks || [];
    els['m-hooks-part'].hidden = !hooks.length;
    els['m-hooks'].innerHTML = '';
    hooks.forEach((h, k) => els['m-hooks'].appendChild(hookCard(h, k)));

    els['m-redrafts'].innerHTML = '';
    redraftEls.clear();
    let shown = 0;
    for (const key of report.redrafted || []) {
      const card = redraftCard(report, key, shown);
      if (card) { els['m-redrafts'].appendChild(card); shown++; }
    }
    els['m-redrafts-part'].hidden = !shown;

    const checks = (report.checked || []).map(checkRow).concat((report.unchecked || []).map(uncheckedRow));
    els['m-checks-box'].hidden = !checks.length;
    els['m-checks'].innerHTML = checks.join('');

    const due = report.due_today || [];
    els['m-due'].innerHTML = due.length ? due.map((d) => dueRow(d, String(report.day || ''))).join('')
      : '<li class="due-row none">Nothing falls due today.</li>';

    const extra = (report.notes || []).filter(Boolean).map((n) => `<span>${esc(n)}</span>`).join('');
    els['morning-cost'].innerHTML = `<span class="cost-k">This morning's run</span><span>${esc(costParts(report).join(' · '))}</span>${extra}`;
    els['morning-cost'].hidden = !report.cost && !extra;
  }

  function hearTurn(turn) {
    const t = P.turnStart.get(turn);
    if (t == null) return;
    jumpTo(t, turn);
    if (!player.playing) player.play();
    document.querySelector('.stage').scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' });
    toast(`Back to turn ${turn}, at ${mmss(t)}, where it was said.`);
  }
  els['m-hooks'].addEventListener('click', (e) => {
    const b = e.target.closest('.ev.here');
    if (b) hearTurn(Number(b.dataset.turn));
  });

  // ---------------------------------------------------------------- the week map
  function drawWeek() {
    const idx = P.rec.people_index;
    const svg = els.map;
    if (!idx || !(idx.people || []).length) { els.week.hidden = true; weekDrawn = true; return; }
    const since = Number(idx.since) || 0, until = Number(idx.until) || Infinity;
    const events = new Map();
    const people = [];
    for (const p of idx.people) {
      const enc = (p.encounters || []).filter((e) => (e.started || 0) > since && (e.started || 0) <= until + 1);
      if (!enc.length) continue;
      enc.sort((a, b) => (a.started || 0) - (b.started || 0));
      for (const e of enc) {
        if (!events.has(e.recording)) events.set(e.recording, { id: e.recording, name: e.event || 'Untitled evening', venue: e.venue || '', place: e.place || null, started: e.started || 0, people: [] });
      }
      people.push({ ...p, enc, hubs: [...new Set(enc.map((e) => e.recording))] });
    }
    const evList = [...events.values()].sort((a, b) => a.started - b.started);
    evList.forEach((e, k) => { e.colour = k; e.k = k; });
    for (const p of people) {
      p.first = events.get(p.enc[0].recording);
      p.tonight = p.hubs.includes(P.id);
      for (const h of p.hubs) events.get(h).people.push(p);
    }
    const own = events.get(P.id);
    if (own && !own.place && P.rec.meta && P.rec.meta.place) own.place = P.rec.meta.place;
    const days = Math.round((until - since) / 86400) || 7;
    els['week-sub'].textContent = `Everyone met in the ${word(days) === String(days) ? days : word(days)} days up to tonight: ${people.length} ${plural(people.length, 'person', 'people')} at ${evList.length} ${plural(evList.length, 'event')}, from the people index.`;

    // chips
    els.chips.innerHTML = '';
    const mkChip = (label, sub, colour, id, tonight) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = `chip${tonight ? ' tonight' : ''}`;
      b.style.setProperty('--c', colour);
      b.setAttribute('aria-pressed', String(weekFilter === id));
      b.innerHTML = `${id ? '<span class="sw"></span>' : ''}<span>${esc(label)}</span>${sub ? `<small>${esc(sub)}</small>` : ''}`;
      b.addEventListener('click', () => { weekFilter = weekFilter === id ? null : id; applyWeekFilter(); });
      b.dataset.id = id || '';
      els.chips.appendChild(b);
    };
    mkChip('Everyone', `${people.length}`, 'var(--ink)', null, false);
    for (const e of evList) {
      const w = wallDate(e.started, P.tzOffset);
      mkChip(e.id === P.id ? `${e.name} (tonight)` : e.name, `${DAYS[w.wd]} ${w.d} · ${e.people.length}`, pcol(e.colour), e.id, e.id === P.id);
    }

    const box = svg.parentElement;
    const W = Math.max(300, Math.round(box.clientWidth || 900));
    const narrow = W < 640;
    const H = narrow ? Math.round(W * 1.25) : Math.round(clamp(W * 0.52, 420, 620));
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('height', String(H));

    // hubs on an ellipse, in date order clockwise from the left
    const cx = W / 2, cy = H / 2;
    const rx = W * (narrow ? 0.3 : 0.34), ry = H * (narrow ? 0.34 : 0.32);
    const n = evList.length;
    evList.forEach((e, k) => {
      if (n === 1) { e.x = cx; e.y = cy; return; }
      if (n === 2) { e.x = cx + (k === 0 ? -rx : rx) * 0.8; e.y = cy; return; }
      const th = Math.PI - (k * 2 * Math.PI) / n;
      e.x = cx + rx * Math.cos(th);
      e.y = cy - ry * Math.sin(th);
    });

    // people: pulled toward each evening they were at, pushed off each other
    const golden = Math.PI * (3 - Math.sqrt(5));
    people.forEach((p, k) => {
      const hs = p.hubs.map((h) => events.get(h));
      const mx = hs.reduce((a, h) => a + h.x, 0) / hs.length;
      const my = hs.reduce((a, h) => a + h.y, 0) / hs.length;
      const r = hs.length === 1 ? 60 : 12;
      p.x = mx + r * Math.cos(k * golden);
      p.y = my + r * Math.sin(k * golden);
    });
    const margin = { l: 24, r: narrow ? 70 : 110, t: 26, b: 26 };
    for (let it = 0; it < 420; it++) {
      const alpha = 1 - it / 420;
      for (const p of people) {
        for (const h of p.hubs) {
          const e = events.get(h);
          const dx = e.x - p.x, dy = e.y - p.y;
          const d = Math.hypot(dx, dy) || 0.01;
          const L = p.hubs.length === 1 ? (narrow ? 58 : 78) : 30;
          const f = ((d - L) / d) * 0.05 * alpha;
          p.x += dx * f; p.y += dy * f;
        }
        for (const e of evList) {
          const dx = p.x - e.x, dy = p.y - e.y;
          const d = Math.hypot(dx, dy) || 0.01;
          if (d < 46) { const f = ((46 - d) / d) * 0.4; p.x += dx * f; p.y += dy * f; }
        }
      }
      for (let a = 0; a < people.length; a++) {
        for (let b = a + 1; b < people.length; b++) {
          const p = people[a], q = people[b];
          const dx = q.x - p.x, dy = q.y - p.y;
          const d = Math.hypot(dx, dy) || 0.01;
          const min = narrow ? 34 : 42;
          if (d < min) { const f = ((min - d) / d) * 0.5; p.x -= dx * f; p.y -= dy * f; q.x += dx * f; q.y += dy * f; }
        }
      }
      for (const p of people) {
        p.x = clamp(p.x, margin.l, W - margin.r);
        p.y = clamp(p.y, margin.t, H - margin.b);
      }
    }

    // who introduced whom, by name (the index stores the introducer's name as heard)
    const byName = new Map();
    for (const p of people) for (const nm of [p.name, ...(p.aliases || [])]) byName.set(String(nm).toLowerCase(), p);
    const intros = [];
    for (const p of people) {
      for (const e of p.enc) {
        const q = e.introduced_by && byName.get(String(e.introduced_by).toLowerCase());
        if (q && q !== p) intros.push({ from: q, to: p, event: e.recording });
      }
    }

    let s = '';
    for (const p of people) {
      for (const h of p.hubs) {
        const e = events.get(h);
        s += `<line class="edge" data-ev="${esc(h)}" data-p="${esc(p.key)}" x1="${e.x.toFixed(1)}" y1="${e.y.toFixed(1)}" x2="${p.x.toFixed(1)}" y2="${p.y.toFixed(1)}" stroke="${pcol(e.colour)}" stroke-opacity="0.5"/>`;
      }
    }
    for (const it of intros) {
      const mx = (it.from.x + it.to.x) / 2, my = (it.from.y + it.to.y) / 2;
      const dx = it.to.x - it.from.x, dy = it.to.y - it.from.y;
      const cxq = mx - dy * 0.25, cyq = my + dx * 0.25;
      s += `<path class="intro-edge" data-ev="${esc(it.event)}" d="M${it.from.x.toFixed(1)} ${it.from.y.toFixed(1)} Q${cxq.toFixed(1)} ${cyq.toFixed(1)} ${it.to.x.toFixed(1)} ${it.to.y.toFixed(1)}"><title>${esc(`${it.from.name} introduced ${it.to.name}`)}</title></path>`;
    }
    for (const e of evList) {
      const label = truncate(e.name, narrow ? 18 : 26);
      const w = Math.max(label.length * (narrow ? 6.6 : 7.1) + 22, 70);
      const w2 = wallDate(e.started, P.tzOffset);
      s += `<g class="hub" data-ev="${esc(e.id)}" transform="translate(${e.x.toFixed(1)} ${e.y.toFixed(1)})">` +
        `<rect x="${(-w / 2).toFixed(1)}" y="-19" width="${w.toFixed(1)}" height="38" rx="19" stroke="${pcol(e.colour)}"/>` +
        `<text text-anchor="middle" y="-2">${esc(label)}</text>` +
        `<text class="date" text-anchor="middle" y="12">${esc(`${dayLabel(w2)}${e.id === P.id ? ' · tonight' : ''}`)}</text>` +
        `<title>${esc(`${e.name}${e.venue ? ', ' + e.venue : ''}: ${e.people.length} ${plural(e.people.length, 'person', 'people')}`)}</title></g>`;
    }
    for (const p of people) {
      const right = p.x < W - (narrow ? 90 : 130);
      const label = narrow ? shortName(p.name) : p.name;
      const again = (p.met_total || p.enc.length) > 1;
      const where = p.enc.map((e) => events.get(e.recording).name).join(', ');
      s += `<g class="node${p.tonight ? ' tonight' : ''}" data-p="${esc(p.key)}" data-evs="${esc(p.hubs.join(' '))}" transform="translate(${p.x.toFixed(1)} ${p.y.toFixed(1)})">` +
        (again ? `<circle class="again" r="10" stroke="${pcol(p.first.colour)}"/>` : '') +
        `<circle class="dot" r="6.5" fill="${pcol(p.first.colour)}"/>` +
        `<text x="${right ? 14 : -14}" y="4" text-anchor="${right ? 'start' : 'end'}">${esc(label)}</text>` +
        `<title>${esc(`${p.name}${p.company ? ', ' + p.company : ''}. Met at ${where}.`)}</title></g>`;
    }
    svg.innerHTML = s;
    drawPlaces(evList);
    weekDrawn = true;
    applyWeekFilter();
  }

  // ---------------------------------------------------------------- the week's places
  /** Where each evening was, drawn on the paper with no map underneath: the export rounds every place to two
   *  decimals (about a kilometre), the page projects them flat, one dot per evening sized by the people met there,
   *  and a dashed line joins them in date order. Nothing is fetched. */
  function drawPlaces(evList) {
    const svg = els.places;
    const spots = evList.filter((e) => e.place && Number.isFinite(Number(e.place.lat)) && Number.isFinite(Number(e.place.lon)));
    els['places-box'].hidden = !spots.length;
    if (!spots.length) { svg.innerHTML = ''; return; }
    const W = Math.max(300, Math.round(svg.parentElement.clientWidth || 900));
    const narrow = W < 640;

    // a flat projection around the middle of the week: a degree of longitude is cos(latitude) of a degree of latitude
    const lats = spots.map((e) => Number(e.place.lat)), lons = spots.map((e) => Number(e.place.lon));
    const lat0 = (Math.min(...lats) + Math.max(...lats)) / 2, lon0 = (Math.min(...lons) + Math.max(...lons)) / 2;
    const kx = Math.cos((lat0 * Math.PI) / 180);
    const MIN_SPAN = 0.03;  // degrees: a week in one neighbourhood still reads as places, not one blot
    const spanX = Math.max((Math.max(...lons) - Math.min(...lons)) * kx, MIN_SPAN);
    const spanY = Math.max(Math.max(...lats) - Math.min(...lats), MIN_SPAN);
    const pad = { l: narrow ? 46 : 90, r: narrow ? 46 : 90, t: 50, b: 50 };
    // as tall as the week's shape needs at this width, within a strip's limits
    const H = Math.round(clamp(((W - pad.l - pad.r) * spanY) / spanX + pad.t + pad.b, narrow ? 230 : 220, narrow ? 360 : 300));
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('height', String(H));
    const k = Math.min((W - pad.l - pad.r) / spanX, (H - pad.t - pad.b) / spanY);
    const px = (lon) => W / 2 + (lon - lon0) * kx * k;
    const py = (lat) => H / 2 - (lat - lat0) * k;

    let s = '';
    // the rounding grid: each cell is one place as published, about a kilometre a side
    const step = 0.01;
    const lonA = lon0 - W / 2 / (kx * k), lonB = lon0 + W / 2 / (kx * k);
    const latA = lat0 - H / 2 / k, latB = lat0 + H / 2 / k;
    if ((lonB - lonA) / step < 80 && (latB - latA) / step < 80) {
      for (let lon = Math.ceil(lonA / step) * step; lon < lonB; lon += step) s += `<line class="grid" x1="${px(lon).toFixed(1)}" y1="0" x2="${px(lon).toFixed(1)}" y2="${H}"/>`;
      for (let lat = Math.ceil(latA / step) * step; lat < latB; lat += step) s += `<line class="grid" x1="0" y1="${py(lat).toFixed(1)}" x2="${W}" y2="${py(lat).toFixed(1)}"/>`;
    }
    // a kilometre, and north
    const km = k / 111.32;
    s += `<g class="scale" transform="translate(16 ${H - 16})"><path d="M0 -5V0H${km.toFixed(1)}V-5"/><text x="${(km + 6).toFixed(1)}" y="0">1 km</text></g>`;
    s += `<g class="north" transform="translate(${W - 20} 22)"><path d="M0 -9L4 3L0 1L-4 3Z"/><text y="16" text-anchor="middle">N</text></g>`;

    for (const e of spots) { e.px = px(Number(e.place.lon)); e.py = py(Number(e.place.lat)); e.r = 5 + 2.6 * Math.sqrt(e.people.length); }
    // the week as a path, in date order
    if (spots.length > 1) {
      s += `<path class="path" d="${spots.map((e, i) => `${i ? 'L' : 'M'}${e.px.toFixed(1)} ${e.py.toFixed(1)}`).join('')}"/>`;
    }
    // labels: around the dot, the first spot clear of every dot, every label so far and the edges; when none is
    // clear, the one that overlaps least
    const boxes = spots.map((e) => ({ x0: e.px - e.r - 2, x1: e.px + e.r + 2, y0: e.py - e.r - 2, y1: e.py + e.r + 2 }));
    const overlap = (b) => {
      let a = Math.max(0, 4 - b.x0) * 40 + Math.max(0, b.x1 - (W - 4)) * 40 + Math.max(0, 4 - b.y0) * 40 + Math.max(0, b.y1 - (H - 4)) * 40;
      for (const o of boxes) a += Math.max(0, Math.min(b.x1, o.x1) - Math.max(b.x0, o.x0)) * Math.max(0, Math.min(b.y1, o.y1) - Math.max(b.y0, o.y0));
      return a;
    };
    const labelled = [];
    for (const e of spots) {
      const tonight = e.id === P.id;
      const name = truncate(e.name, narrow ? 17 : 28);
      const w2 = wallDate(e.started, P.tzOffset);
      // narrow: the chips' short date; the ring says tonight
      const date = narrow ? `${DAYS[w2.wd]} ${w2.d} · ${e.people.length} met` : `${dayLabel(w2)} · ${e.people.length} met${tonight ? ' · tonight' : ''}`;
      const tw = Math.max(name.length * 6.7, date.length * 6.1);
      const gap = e.r + 6, d = e.r * 0.7;
      const tries = [
        { a: 'middle', x: e.px, y: e.py - gap - 16 },          // above: name, then date, ending over the dot
        { a: 'middle', x: e.px, y: e.py + gap + 11 },          // below
        { a: 'start', x: e.px + gap, y: e.py - 3 },            // right
        { a: 'end', x: e.px - gap, y: e.py - 3 },              // left
        { a: 'start', x: e.px + d, y: e.py - gap - 16 },       // above, leaning right
        { a: 'end', x: e.px - d, y: e.py - gap - 16 },         // above, leaning left
        { a: 'start', x: e.px + d, y: e.py + gap + 11 },       // below, leaning right
        { a: 'end', x: e.px - d, y: e.py + gap + 11 },         // below, leaning left
      ];
      const boxOf = (t) => {
        const x0 = t.a === 'middle' ? t.x - tw / 2 : t.a === 'start' ? t.x : t.x - tw;
        return { x0, x1: x0 + tw, y0: t.y - 12, y1: t.y + 16 };
      };
      let best = null, bestScore = Infinity;
      for (const t of tries) {
        const score = overlap(boxOf(t));
        if (score < bestScore) { best = t; bestScore = score; }
        if (score === 0) break;
      }
      boxes.push(boxOf(best));
      labelled.push({ e, name, date, t: best });
    }
    for (const { e, name, date, t } of labelled) {
      const tonight = e.id === P.id;
      s += `<g class="spot${tonight ? ' tonight' : ''}" data-ev="${esc(e.id)}" tabindex="0" role="button" aria-label="${esc(`${e.name}, ${dayLabel(wallDate(e.started, P.tzOffset))}, ${e.people.length} met${tonight ? ', tonight' : ''}`)}">` +
        (tonight ? `<circle class="ring" cx="${e.px.toFixed(1)}" cy="${e.py.toFixed(1)}" r="${(e.r + 4).toFixed(1)}" stroke="${pcol(e.colour)}"/>` : '') +
        `<circle class="dot" cx="${e.px.toFixed(1)}" cy="${e.py.toFixed(1)}" r="${e.r.toFixed(1)}" fill="${pcol(e.colour)}"/>` +
        `<text class="name" x="${t.x.toFixed(1)}" y="${t.y.toFixed(1)}" text-anchor="${t.a}">${esc(name)}</text>` +
        `<text class="date" x="${t.x.toFixed(1)}" y="${(t.y + 13).toFixed(1)}" text-anchor="${t.a}">${esc(date)}</text>` +
        `<title>${esc(`${e.name}${e.place.name ? ', ' + e.place.name : ''}: ${e.people.length} ${plural(e.people.length, 'person', 'people')} met`)}</title></g>`;
    }
    svg.innerHTML = s;
    svg.querySelectorAll('.spot').forEach((g) => {
      const toggle = () => { weekFilter = weekFilter === g.dataset.ev ? null : g.dataset.ev; applyWeekFilter(); };
      g.addEventListener('click', toggle);
      g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); toggle(); } });
    });
    const missing = evList.length - spots.length;
    els['places-note'].textContent = (spots.length > 1
      ? 'Where each evening was, to about a kilometre: dots grow with the people met, the dashed line is the week in date order.'
      : 'Where the evening was, to about a kilometre.') +
      (missing ? ` ${word(missing)[0].toUpperCase() + word(missing).slice(1)} ${plural(missing, 'evening')} without a place ${missing === 1 ? 'is' : 'are'} left off.` : '');
  }

  function applyWeekFilter() {
    const f = weekFilter;
    els.chips.querySelectorAll('.chip').forEach((b) => b.setAttribute('aria-pressed', String((b.dataset.id || null) === f)));
    els.map.querySelectorAll('.node').forEach((n) => n.classList.toggle('dim', !!f && !n.dataset.evs.split(' ').includes(f)));
    els.map.querySelectorAll('.edge, .intro-edge, .hub').forEach((n) => n.classList.toggle('dim', !!f && n.dataset.ev !== f));
    els.places.querySelectorAll('.spot').forEach((n) => {
      n.classList.toggle('dim', !!f && n.dataset.ev !== f);
      n.setAttribute('aria-pressed', String(f === n.dataset.ev));
    });
  }

  // ---------------------------------------------------------------- transport
  function buildTransport() {
    const total = P.total;
    // speech on the track, coloured by who it turned out to be
    const personOf = personBySpeaker(P.final);
    let segs = '';
    for (const tr of P.final.turns.values()) {
      if (!tr.done || typeof tr.start !== 'number') continue;
      const left = (tr.start / total) * 100;
      const width = Math.max(0.25, ((tr.end - tr.start) / total) * 100);
      const p = personOf.get(tr.speaker);
      const colour = P.final.owner.has(tr.speaker) ? 'var(--ink)' : p ? pcol(P.colour.get(p.key)) : 'var(--ink-soft)';
      const soft = KIND_LABEL[P.final.kinds.get(tr.turn)] ? ' soft' : '';
      segs += `<span class="seg${soft}" style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%;--c:${colour}"></span>`;
    }
    els.segs.innerHTML = segs;
    els.track.setAttribute('aria-valuemax', String(Math.round(total / 1000)));

    // markers, clustered per lane when they would overlap
    markerEls = [];
    for (const lane of ['person', 'promise', 'translation', 'edge', 'hook']) {
      const box = els[`lane-${lane}`];
      box.innerHTML = '';
      const list = P.markers.filter((m) => m.lane === lane).sort((a, b) => a.t - b.t);
      const clusters = [];
      for (const m of list) {
        const last = clusters[clusters.length - 1];
        if (last && ((m.t - last.t) / total) * 100 < 1.3) last.items.push(m);
        else clusters.push({ t: m.t, items: [m] });
      }
      for (const c of clusters) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = `mk${c.items.some((m) => m.corrected) ? ' corrected' : ''}`;
        b.style.left = `${((c.t / total) * 100).toFixed(3)}%`;
        if (lane === 'person') b.style.setProperty('--c', pcol(c.items[0].colour));
        const label = c.items.map((m) => m.label).slice(0, 6).join('\n') + (c.items.length > 6 ? `\n+${c.items.length - 6} more` : '');
        b.innerHTML = `<span class="g"></span>${c.items.length > 1 ? `<span class="n">${c.items.length}</span>` : ''}`;
        b.setAttribute('aria-label', `${mmss(c.t)}: ${label.replace(/\n/g, '; ')}`);
        b.addEventListener('click', (e) => { e.stopPropagation(); enterLive(); jumpTo(c.t, null); });
        b.addEventListener('pointerenter', () => showTip(b, `${mmss(c.t)} · ${label}`));
        b.addEventListener('focus', () => showTip(b, `${mmss(c.t)} · ${label}`));
        b.addEventListener('pointerleave', hideTip);
        b.addEventListener('blur', hideTip);
        box.appendChild(b);
        markerEls.push({ el: b, t: c.t });
      }
    }
  }

  function showTip(anchor, text) {
    const r = anchor.getBoundingClientRect();
    els.tip.innerHTML = esc(text).replace(/\n/g, '<br>');
    const x = clamp(r.left + r.width / 2, 140, window.innerWidth - 140);
    els.tip.style.left = `${x}px`;
    els.tip.style.top = `${r.top}px`;
    els.tip.classList.add('on');
  }
  function hideTip() { els.tip.classList.remove('on'); }

  let toastTimer = null;
  function toast(text) {
    els.toast.textContent = text;
    els.toast.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => els.toast.classList.remove('on'), 4200);
  }

  function renderTransport(t) {
    const pct = clamp((t / P.total) * 100, 0, 100);
    els.fill.style.width = `${pct}%`;
    els.head.style.left = `${pct}%`;
    const txt = `<b>${mmss(t)}</b> / ${mmss(P.total)}`;
    if (els.time._html !== txt) { els.time._html = txt; els.time.innerHTML = txt; }
    els.track.setAttribute('aria-valuenow', String(Math.round(t / 1000)));
    els.track.setAttribute('aria-valuetext', `${mmss(t)} of ${mmss(P.total)}`);
    for (const m of markerEls) m.el.classList.toggle('past', m.t <= t);
    const ppState = `${player.playing}|${!player.playing && player.paused >= P.total - 50}`;
    if (els.pp._state !== ppState) { els.pp._state = ppState; syncPlayButton(); }
  }

  const PLAY_ICON = '<path d="M7 4.5v15l12-7.5z" fill="currentColor"/>';
  const PAUSE_ICON = '<rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor"/><rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor"/>';
  const REPLAY_ICON = '<path d="M12 5a7 7 0 1 1-6.6 4.7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/><path d="M4 4.5v5h5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>';
  function syncPlayButton() {
    const atEnd = !player.playing && P && player.paused >= P.total - 50;
    els['pp-icon'].innerHTML = player.playing ? PAUSE_ICON : atEnd ? REPLAY_ICON : PLAY_ICON;
    els.pp.setAttribute('aria-label', player.playing ? 'Pause' : atEnd ? 'Play again' : 'Play');
    els.app.classList.toggle('is-playing', player.playing);
  }

  // ---------------------------------------------------------------- X-ray: the machinery, in step with the clock
  /** Paper cards over the dimmed replay, one per thing the badge's own code or a model did, each a function of the
   *  fold at t plus the sidecar data/<id>.xray.json (server/scripts/export_xray.py: per-block channel levels, the
   *  leveler's gain and direction recomputed with direction.py, all read-only from audio.wav). Every number on a card
   *  comes from events.jsonl, that sidecar or the saved report, and the card's receipt says which. Direction is words
   *  only (left / ahead / right) and soft regions, never a degree; the direction cards wear PENDING until the FOA
   *  comparison lands; a verdict replayed here rather than logged is stamped as such. */
  const XRAY_LIT = 3200;       // ms a card stays lit after its latest change
  const XRAY_WINDOW = 12000;   // ms of sound the sound cards show
  const XRAY_LEAD = 1500;      // of which this much lies ahead of the playhead
  const XRAY_P = ['#2F7F72', '#C8702F', '#7A4FA3', '#B8862B', '#3B63A8', '#5F8A3C', '#B8475F', '#5B6B78'];
  const XRAY_INK = '#2A2622', XRAY_SOFT = '#6E675E', XRAY_RULE = '#D3CBB9', XRAY_ACCENT = '#2F7F72', XRAY_LIVE = '#C8402F', XRAY_PENDING = '#E0B45A';
  const XRAY_MONO = '500 10px "IBM Plex Mono", ui-monospace, Menlo, monospace';
  const XRAY_SERIF = '600 12px "Newsreader", "New York", Georgia, serif';
  const XRAY_SANS = '500 10px "Instrument Sans", system-ui, sans-serif';
  const PENDING_CHIP = ['pending', 'pending · FOA comparison running'];
  const NO_MODEL_CHIP = ['none', 'no model call'];
  let xrayOn = false;
  let xFocus = null;         // &focus=NN: hold that beat's card large in the centre (phone legibility, a film still)
  let xFit = 'auto';         // &fit / &nofit: scale the columns to the frame so every card is in view (auto: when wide)
  let xLast = '';            // the signature of the last X-ray draw; nothing is redrawn while it holds
  const xCards = new Map();  // beat id -> { el, body, chips, receipt, canv, sig }

  /** '#<id>', '#<id>@<ms>', '#<id>@<ms>&xray' or '#<id>&xray': the recording, a moment to land on, and the X-ray.
   *  Capture flags after it: &still (no transitions), &focus=NN (one card held large), &fit / &nofit. */
  function parseHash(h) {
    const raw = decodeURIComponent(String(h || '').replace(/^#/, ''));
    if (!raw) return { id: '', at: null, xray: false };
    const parts = raw.split('&');
    const [id, at] = parts[0].split('@');
    const flags = new Set(parts.slice(1).map((s) => s.trim().toLowerCase()));
    const ms = at != null && at !== '' && Number.isFinite(Number(at)) ? Number(at) : null;
    let focus = null;
    for (const f of flags) { const m = f.match(/^focus=(\d{1,2})$/); if (m) focus = Number(m[1]); }
    return { id, at: ms, xray: flags.has('xray'), still: flags.has('still'), focus, fit: flags.has('fit') ? 'on' : flags.has('nofit') ? 'off' : 'auto' };
  }

  /** Land on the moment the hash names, paused, with the X-ray open if asked; a plain id changes nothing. */
  function applyHashState(w) {
    if (!P || (w.at == null && !w.xray)) return;
    if (w.still) els.app.classList.add('is-still');  // a composed frame for a headless capture: no transitions
    xFocus = w.focus || null;
    xFit = w.fit || 'auto';
    xLayoutReset();
    enterLive();
    endScrolled = true;
    stickTranscript = true;
    player.pause(clamp(w.at != null ? w.at : 0, 0, P.total));
    if (w.xray) setXray(true);
    xLast = '';
    render(player.paused);
  }

  /** The transport bar's real height, so the overlay's scroll padding ends exactly where the bar begins. */
  function measureBar() {
    const h = els.bar.offsetHeight;
    if (h && els.app._barH !== h) { els.app._barH = h; els.app.style.setProperty('--bar-h', `${h}px`); }
  }
  if (window.ResizeObserver) new ResizeObserver(measureBar).observe(els.bar);

  function setXray(on) {
    on = !!on && !!P;
    if (on === xrayOn) return;
    const wasIntro = mode === 'intro';
    xrayOn = on;
    els.app.classList.toggle('is-xray', on);
    els.xray.hidden = !on;
    els['xray-btn'].setAttribute('aria-pressed', String(on));
    xLayoutReset();
    if (!on) { xFocus = null; els.app.classList.remove('is-focus', 'is-compact'); render(player.now()); return; }
    enterLive();
    measureBar();
    if (wasIntro) { endScrolled = false; player.seek(0); player.play(); }
    ensureSidecar();
    render(player.now());
  }

  function ensureSidecar() {
    if (!P || P.xrayState !== 'idle') return;
    const id = P.id;
    P.xrayState = 'loading';
    loadJSON(`data/${id}.xray.json`)
      .then((x) => { if (P && P.id === id) { P.xray = x; P.xrayState = 'ok'; } })
      .catch(() => { if (P && P.id === id) { P.xray = null; P.xrayState = 'none'; } });
  }

  function resetXray() {
    for (const c of xCards.values()) c.el.remove();
    xCards.clear();
    els['x-caption']._html = '';
    els['x-caption'].innerHTML = '';
    els['x-tape'].innerHTML = '';
  }

  // ---- small helpers for the cards
  /** extract.fold_words, for the fallback when the sidecar carries no verdicts: casefold (so ß is ss), NFKD, every
   *  combining mark dropped (Japanese dakuten included), words of letters, digits and underscores. */
  const foldWords = (s) => (String(s || '').toLowerCase().replace(/ß/g, 'ss').normalize('NFKD').replace(/\p{M}/gu, '').match(/[\p{L}\p{N}_]+/gu) || []).join(' ');
  const xchip = (kind, text, colour) => `<span class="xchip ${kind}"${colour ? ` style="--c:${colour}"` : ''}>${esc(text)}</span>`;
  const xchips = (list) => list.map((c) => xchip(c[0], c[1], c[2])).join('');
  const xrec = (parts) => parts.filter((p) => p != null && p !== '').map((p) => esc(p)).join('<span class="sep">·</span>');
  const secs = (ms, d = 1) => `${(ms / 1000).toFixed(d)} s`;
  const sdb = (v) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)} dB`;
  const row = (mark, html, src) => `<div class="xr"><span class="xmk ${mark === '✓' ? 'ok' : mark === '✕' || mark === '!' ? 'no' : 'soft'}">${mark}</span><span class="tx">${html}</span>${src ? `<span class="src">${esc(src)}</span>` : ''}</div>`;
  const rad = (d) => (d * Math.PI) / 180;
  const hexA = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`; };
  const sideWord = (az) => (az > 12 ? 'left' : az < -12 ? 'right' : 'ahead');
  const laneOf = (az) => (az > 12 ? 0 : az < -12 ? 2 : 1);
  const colourHex = (key) => XRAY_P[(P.colour.get(key) ?? 7) % 8];
  const xName = (st, key) => (st.people.get(key) || P.final.people.get(key) || {}).name || key;

  function xColourOf(spk) {
    if (P.final.owner.has(spk)) return XRAY_INK;
    const p = P.xPersonOf.get(spk);
    return p ? colourHex(p.key) : XRAY_SOFT;
  }
  /** Index of the last span starting at or before ms (spans are sorted by start), -1 if none. */
  function xSpanBefore(ms) {
    const sp = P.spans;
    let lo = 0, hi = sp.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (sp[mid].start <= ms) lo = mid + 1; else hi = mid; }
    return lo - 1;
  }
  function xSpeakerAt(ms) {
    const sp = P.spans;
    // turns rarely overlap, and never by more than a few; look back from the last one that had started
    for (let i = xSpanBefore(ms), n = 0; i >= 0 && n < 6; i--, n++) if (ms < sp[i].end) return sp[i].speaker;
    return null;
  }
  function xLastTurnStart(t) {
    const i = xSpanBefore(t);
    return i < 0 ? -Infinity : P.spans[i].start;
  }
  /** When the first speech began, as the log says (speech_start, else the first turn): the leveler card waits for
   *  it rather than lighting on the leveler's own flag, which flickers while its room-floor estimate warms up. */
  function xFirstSpeech() {
    if (P._firstSpeech === undefined) {
      const ev = P.evs.find((e) => e.type === 'speech_start');
      P._firstSpeech = ev ? ev.t_ms : P.spans.length ? P.spans[0].start : null;
    }
    return P._firstSpeech;
  }

  function xCard(beat, idx) {
    let card = xCards.get(beat.id);
    if (card) return card;
    const el = document.createElement('article');
    el.className = 'xcard off';
    el.innerHTML = `<p class="xtitle"><span class="n">${String(idx + 1).padStart(2, '0')}</span>${esc(beat.title)}</p><div class="xbody"></div><div class="xfoot"><span class="xchips"></span><span class="xreceipt"></span></div>`;
    card = { el, body: el.querySelector('.xbody'), chips: el.querySelector('.xchips'), receipt: el.querySelector('.xreceipt'), canv: {}, sig: '' };
    xCards.set(beat.id, card);
    els['x-cols'].querySelectorAll('.xstack')[beat.col].appendChild(el);
    return card;
  }
  function xTitle(card, text) {
    const el = card.el.querySelector('.xtitle');
    if (el._text !== text) { el._text = text; el.lastChild.nodeValue = text; }
  }
  function xSet(card, html, chips, receipt) {
    const sig = `${html}|${chips}|${receipt}`;
    if (card.sig === sig) return;
    card.sig = sig;
    card.body.innerHTML = html;
    card.chips.innerHTML = chips;
    card.receipt.innerHTML = receipt;
  }
  /** A canvas in the card's .xcanv holder, sized to the card and the device pixel ratio, cleared for drawing. */
  function xCanvas(card, key, h) {
    let c = card.canv[key];
    if (!c) { c = document.createElement('canvas'); c.setAttribute('aria-hidden', 'true'); card.canv[key] = c; }
    const holder = card.body.querySelector(`.xcanv[data-k="${key}"]`) || card.body.querySelector('.xcanv');
    if (holder && c.parentNode !== holder) holder.appendChild(c);
    const w = Math.max(160, Math.round((holder || card.body).clientWidth || card.body.clientWidth || 300));
    const dpr = Math.min(2, window.devicePixelRatio || 1) * (card.el.classList.contains('focus') ? 2 : 1);  // crisp at 2×
    if (c._w !== w || c._h !== h || c._dpr !== dpr) {
      c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
      c.style.width = `${w}px`; c.style.height = `${h}px`;
      c._w = w; c._h = h; c._dpr = dpr;
    }
    const ctx = c.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx, w, h };
  }
  function softWedge(ctx, cx, cy, r0, r1, a0, a1, hex, alpha) {
    const steps = 6;
    for (let i = 0; i < steps; i++) {
      const k = i / steps, pad = (a1 - a0) * 0.35 * k;
      const mid = (r0 + r1) / 2;
      const rr0 = r0 + (mid - r0) * k * 0.6, rr1 = r1 + (mid - r1) * k * 0.6;
      ctx.beginPath();
      ctx.arc(cx, cy, rr1, a0 + pad, a1 - pad);
      ctx.arc(cx, cy, rr0, a1 - pad, a0 + pad, true);
      ctx.closePath();
      ctx.fillStyle = hexA(hex, alpha / steps);
      ctx.fill();
    }
  }
  function xWindow(t) { return { t0: t - XRAY_WINDOW + XRAY_LEAD, t1: t + XRAY_LEAD }; }
  function xPlayhead(ctx, x, h) { ctx.fillStyle = XRAY_LIVE; ctx.fillRect(Math.round(x) - 0.5, 0, 1.5, h); }

  function noSidecar() {
    if (P.xrayState === 'loading' || P.xrayState === 'idle') return '<p class="xempty">Reading the sound analysis…</p>';
    return `<p class="xempty">No sound analysis for this recording yet. In <code>server/</code>: <code>uv run python scripts/export_xray.py ${esc(P.id)}</code>, then reload.</p>`;
  }

  // ---- the beats, in the film's order: each draws its card from (st, t) and says whether it is up, when it last
  // changed and, when the moment deserves its own line, the caption (one sentence, at most 60 characters)
  const XRAY_CAP_MAX = 60;
  const capFit = (s) => (String(s).length > XRAY_CAP_MAX ? String(s).slice(0, XRAY_CAP_MAX - 1).trimEnd() + '…' : String(s));
  /** "Oct 29": the evening's date, from the recording's own start, for a note that says when something was logged. */
  const logDate = () => { const w = P.started ? wallDate(P.started, P.tzOffset) : null; return w ? `${MONTHS[w.mo]} ${w.d}` : P.id.slice(0, 8); };
  /** The sidecar's replay of extract.kept_edges for one logged edge, if export_xray.py carried it. */
  function xVerdict(e) {
    const C = P.xray && P.xray.checks;
    if (!C || !C.edges) return null;
    const turns = (e.turns || []).join(',');
    return C.edges.find((r) => r.t_ms === e.t_ms && r.person === e.person && (r.turns || []).join(',') === turns) || null;
  }

  const XBEATS = [
    { id: 'channels', col: 0, title: 'Four channels in', cap: 'Four channels in. The original is kept.',
      draw(card, st, t) {
        const X = P.xray;
        if (P.xrayState !== 'ok') { xSet(card, noSidecar(), xchips([['code', 'code · recording.py']]), xrec(['audio.wav'])); return { show: true, moment: 0, dim: true }; }
        const names = X.channel_names, rows = X.blocks.rms_db, n = names.length;
        const mono = n === 1;
        xTitle(card, mono ? 'One channel in' : 'Four channels in');
        const rh = n > 1 ? 24 : 44, h = rh * n + 4;
        xSet(card, '<div class="xcanv" data-k="ch"></div>',
          xchips([['code', 'code · recording.py'], ['p', `${X.channels} ch kept · ${mono ? 'mono' : 'W'} → transcriber`, XRAY_ACCENT]]),
          xrec(['audio.wav', `${X.channels} ch ${X.layout}`, `${X.rate / 1000} kHz`, `${X.block_ms} ms blocks`, 'rms_db']));
        const { ctx, w, h: H } = xCanvas(card, 'ch', h);
        const { t0, t1 } = xWindow(t);
        const L = 26, R = n > 1 ? 44 : 10, W = w - L - R;
        for (let c = 0; c < n; c++) {
          const y = c * rh + rh / 2 + 2;
          ctx.fillStyle = c === 0 ? XRAY_ACCENT : XRAY_SOFT;
          ctx.font = XRAY_MONO; ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
          ctx.fillText(names[c], 0, y);
          ctx.fillStyle = hexA(XRAY_RULE, 0.9); ctx.fillRect(L, y, W, 1);
          const dbs = rows[c];
          let lastHex = null;
          for (let px = 0; px < W; px++) {
            const ms = t0 + (px / W) * (t1 - t0);
            if (ms < 0) continue;
            const i = Math.floor(ms / X.block_ms);
            if (i >= dbs.length) break;
            const k = clamp((dbs[i] + 62) / 48, 0, 1);
            if (k <= 0.02) continue;
            const spk = xSpeakerAt(ms);
            const hex = spk ? xColourOf(spk) : (c === 0 ? XRAY_ACCENT : XRAY_SOFT);
            const a = (ms <= t ? 0.85 : 0.22) * (spk ? 1 : 0.55);
            if (hex !== lastHex || px % 8 === 0) { ctx.fillStyle = hexA(hex, a); lastHex = hex; }
            const hh = Math.max(1, k * (rh - 6));
            ctx.fillRect(L + px, y - hh / 2, 1, hh);
          }
        }
        if (n > 1) {  // the W channel peels off toward the transcriber; the four stay on disk
          const y0 = rh / 2 + 2, x0 = L + W + 4;
          ctx.strokeStyle = hexA(XRAY_ACCENT, 0.9); ctx.lineWidth = 1.4; ctx.beginPath();
          ctx.moveTo(x0, y0); ctx.bezierCurveTo(x0 + 16, y0, x0 + 16, H - 10, x0 + 30, H - 10); ctx.stroke();
          ctx.fillStyle = XRAY_ACCENT; ctx.beginPath(); ctx.arc(x0 + 32, H - 10, 2.6, 0, Math.PI * 2); ctx.fill();
        }
        xPlayhead(ctx, L + ((t - t0) / (t1 - t0)) * W, H);
        return { show: true, moment: 0, lit: t - xLastTurnStart(t) < 900, cap: mono ? 'One channel in. The original is kept.' : null };
      } },
    { id: 'leveler', col: 0, title: 'Levelled for the transcriber', cap: 'Levelled for the transcriber: you down, far guests up.',
      draw(card, st, t) {
        const X = P.xray;
        if (P.xrayState !== 'ok') return { show: false };
        const first = xFirstSpeech();
        if (first == null || t < first) return { show: false };
        const { t0, t1 } = xWindow(t);
        const inWin = X.turns.filter((tr) => tr.gain_db != null && tr.end_ms > t0 && tr.start_ms < Math.min(t1, t));
        const you = inWin.filter((tr) => P.final.owner.has(tr.speaker)).map((tr) => tr.gain_db);
        const guests = inWin.filter((tr) => !P.final.owner.has(tr.speaker)).map((tr) => tr.gain_db);
        const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
        const chips = [['code', 'code · leveler.py']];
        if (you.length) chips.push(['p', `you ${sdb(mean(you))}`, XRAY_INK]);
        if (guests.length) chips.push(['p', guests.length > 1 && Math.min(...guests) !== Math.max(...guests) ? `guests ${sdb(Math.min(...guests))} … ${sdb(Math.max(...guests))}` : `guests ${sdb(mean(guests))}`, XRAY_ACCENT]);
        chips.push(['stamp', 're-run offline on audio.wav']);
        const p = X.lev.params;
        xSet(card, '<div class="xcanv" data-k="g"></div>', xchips(chips),
          xrec([`target ${p.target_db} dBFS`, `${p.ratio}:1`, `cap +${p.max_boost_db} / −${p.max_cut_db} dB`, `${p.block_ms} ms steps`]));
        const H = 56, { ctx, w } = xCanvas(card, 'g', H);
        const L = 26, W = w - L - 6, y0 = H / 2, sc = (H / 2 - 4) / 12;
        ctx.font = XRAY_MONO; ctx.textBaseline = 'middle'; ctx.fillStyle = XRAY_SOFT;
        ctx.fillText('+12', 0, 6); ctx.fillText('0 dB', 0, y0); ctx.fillText('−12', 0, H - 6);
        ctx.strokeStyle = hexA(XRAY_SOFT, 0.5); ctx.setLineDash([2, 4]); ctx.beginPath(); ctx.moveTo(L, y0 + 0.5); ctx.lineTo(L + W, y0 + 0.5); ctx.stroke(); ctx.setLineDash([]);
        const g = X.lev.gain_db, sp = X.lev.speech;
        let lastFill = null;
        for (let px = 0; px < W; px++) {
          const ms = t0 + (px / W) * (t1 - t0);
          if (ms < 0) continue;
          const i = Math.floor(ms / X.lev.step_ms);
          if (i >= g.length) break;
          const v = g[i]; if (v == null) continue;
          const spk = xSpeakerAt(ms);
          const hex = spk ? xColourOf(spk) : XRAY_SOFT;
          const a = (ms <= t ? 0.9 : 0.25) * (sp[i] === '1' ? 1 : 0.3);
          const fill = hexA(hex, a);
          if (fill !== lastFill) { ctx.fillStyle = fill; lastFill = fill; }
          const y = y0 - clamp(v, -12, 12) * sc;
          ctx.fillRect(L + px, Math.min(y, y0), 1, Math.max(1, Math.abs(y - y0)));
        }
        xPlayhead(ctx, L + ((t - t0) / (t1 - t0)) * W, H);
        return { show: true, moment: first, lit: t - xLastTurnStart(t) < 900 };
      } },
    { id: 'hints', col: 1, title: 'Names expected before anyone speaks', cap: 'Names expected before anyone speaks.',
      draw(card, st, t) {
        const idx = (P.rec.people_index && P.rec.people_index.people) || [];
        const known = idx.filter((p) => (p.encounters || []).some((e) => e.recording !== P.id && (e.started || 0) < P.started - 1));
        const names = known.map((p) => p.name).filter(Boolean).slice(0, 40);
        const companies = [...new Set(known.map((p) => p.company).filter(Boolean))].slice(0, 20);
        const own = (P.meta.keywords || []).filter(Boolean);
        // two groups, as recording.recognition_hints builds the list: the badge's own words, then the people index
        let html = '<div class="xpills">';
        if (own.length) html += `<span class="xk">badge</span>${own.map((k) => `<span class="xpill badge">${esc(k)}</span>`).join('')}`;
        const shown = names.slice(0, 10), more = names.length - shown.length + companies.length;
        html += `<span class="xk">index</span>${shown.map((n) => `<span class="xpill">${esc(n)}</span>`).join('')}${more > 0 ? `<span class="xpill co">+${more} more · ${companies.length} ${plural(companies.length, 'company', 'companies')}</span>` : ''}</div>`;
        const A = P.xray && P.xray.accents;
        if (A) {
          const strip = (key) => `<span class="xstrip">${A.rows.map((r) => `<i class="${r[key] && r[key].name === 'yes' ? 'on' : ''}" title="${esc(`${r.accent} · ${r.gender}`)}"></i>`).join('')}</span>`;
          html += `<div class="xstat-row"><span class="xstat">${A.name_right.nohints} → ${A.name_right.hints}</span><span>of ${A.voices} names right · ${A.accents.length} accents · ${esc(A.note)}</span></div>`;
          html += `<div class="xstrips"><span class="xk">no hints</span>${strip('nohints')}<span class="xk">hints</span>${strip('hints')}</div>`;
          const fr = A.rows.find((r) => r.id === 'fr_f');
          const trim = (s) => String(s || '').replace(/^Hi[,.]? I'm /, '').replace(/\. We build.*$/, '');
          if (fr && fr.nohints && fr.hints) html += `<div class="xpair"><span><span class="xk">no hints</span>${esc(trim(fr.nohints.text))}</span><span class="on"><span class="xk">hints</span>${esc(trim(fr.hints.text))}</span></div>`;
        }
        html += `<p class="xnote">${own.length ? 'the badge\'s own words, then ' : ''}the people-index names the hint list is built from; the list itself is not logged</p>`;
        xSet(card, html, xchips([['model', 'Muse Voice Transcribe'], ['code', 'code · recording.py · recognition_hints']]),
          xrec(['people index', `${names.length} ${plural(names.length, 'name')}`, `${companies.length} ${plural(companies.length, 'company', 'companies')}`, A ? A.source : null]));
        return { show: true, moment: 0 };
      } },
    { id: 'regions', col: 0, title: 'Voices placed as soft regions', cap: 'Voices placed as soft regions, never degrees.',
      draw(card, st, t) {
        const X = P.xray;
        if (P.xrayState !== 'ok' || !X.win400 || st.x.firstPos == null) return { show: false };
        const personOf = personBySpeaker(st);
        const talking = talkingSpeakers(st, t);
        const groups = new Map();
        for (const [spk, pos] of st.positions) {
          if (st.owner.has(spk)) continue;
          const p = personOf.get(spk);
          const id = p ? `p:${p.key}` : `v:${spk}`;
          if (!groups.has(id)) groups.set(id, { id, person: p, spks: [], pos: [] });
          groups.get(id).spks.push(spk); groups.get(id).pos.push(pos);
        }
        const gs = [...groups.values()].map((g) => {
          const az = wrap180(circMean(g.pos.map((x) => x.az)) - st.yaw);
          const spread = Math.max(...g.pos.map((x) => Number(x.spread) || 0));
          const low = g.pos.every((x) => x.low === true);
          const lv = g.pos.map((x) => x.level).filter(Number.isFinite);
          return { ...g, az, spread, low, level: lv.length ? Math.max(...lv) : null, live: g.spks.some((s) => talking.has(s)),
            hex: g.person ? colourHex(g.person.key) : XRAY_SOFT, name: g.person ? shortName(g.person.name) : 'a voice' };
        });
        const named = gs.filter((g) => g.person).length;
        xSet(card, '<div class="xcanv" data-k="dome"></div><div class="xcanv" data-k="lanes"></div><p class="xnote">left / right, roughly · front / back not told apart · a region, never a number · the lanes are the badge\'s own frame, 100 ms at a time</p>',
          xchips([['code', 'code · direction.py'], PENDING_CHIP]),
          xrec(['speaker_position', `${gs.length} ${plural(gs.length, 'voice')} placed`, `${named} named`, 'win400 · az_device', 'conf ≥ 0.3']));
        // the half dome: wedges in the person's colour, wider when the direction is less sure
        const H = 118, { ctx, w } = xCanvas(card, 'dome', H);
        const CX = w / 2, CY = H - 8, RIM = Math.min(w / 2 - 78, 96);
        ctx.lineWidth = 1;
        for (const r of [RIM * 0.45, RIM * 0.72, RIM]) { ctx.strokeStyle = hexA(XRAY_SOFT, r === RIM ? 0.45 : 0.25); ctx.beginPath(); ctx.arc(CX, CY, r, rad(-178), rad(-2)); ctx.stroke(); }
        ctx.strokeStyle = hexA(XRAY_SOFT, 0.35); ctx.setLineDash([2, 5]);
        for (const az of [12, -12]) { const th = rad(-90 - az); ctx.beginPath(); ctx.moveTo(CX + Math.cos(th) * 18, CY + Math.sin(th) * 18); ctx.lineTo(CX + Math.cos(th) * RIM, CY + Math.sin(th) * RIM); ctx.stroke(); }
        ctx.setLineDash([]);
        ctx.font = XRAY_MONO; ctx.fillStyle = XRAY_SOFT; ctx.textBaseline = 'middle';
        ctx.textAlign = 'right'; ctx.fillText('left', CX - RIM - 4, CY - 4);
        ctx.textAlign = 'left'; ctx.fillText('right', CX + RIM + 4, CY - 4);
        const loud = Math.max(-99, ...gs.map((g) => g.level).filter(Number.isFinite));
        const labels = gs.map((g) => ({ g, az: g.az })).sort((a, b) => a.az - b.az);
        for (let pass = 0; pass < 8; pass++) for (let i = 1; i < labels.length; i++) { const gap = labels[i].az - labels[i - 1].az; if (gap < 36) { labels[i].az += (36 - gap) / 2; labels[i - 1].az -= (36 - gap) / 2; } }
        for (const { g, az: labAz } of labels) {
          const d = Number.isFinite(g.level) ? clamp((loud - g.level) / 18, 0, 1) : 0.5;
          const r = RIM * (0.42 + 0.4 * d);
          const half = rad(clamp(Math.max(g.spread, 10) + (g.low ? 28 : 12), 16, 60));
          const th = rad(-90 - clamp(g.az, -88, 88));
          softWedge(ctx, CX, CY, Math.max(14, r - 22), r + 22, th - half, th + half, g.hex, g.live ? 0.62 : 0.34);
          if (g.live) softWedge(ctx, CX, CY, Math.max(10, r - 34), r + 34, th - half * 1.5, th + half * 1.5, g.hex, 0.14);
          const lt = rad(-90 - clamp(labAz, -84, 84));
          const lx = CX + Math.cos(lt) * (RIM + 8), ly = CY + Math.sin(lt) * (RIM + 8) + 6;
          ctx.strokeStyle = hexA(g.hex, 0.55); ctx.beginPath(); ctx.moveTo(CX + Math.cos(th) * (r + 20), CY + Math.sin(th) * (r + 20)); ctx.lineTo(CX + Math.cos(lt) * (RIM - 2), CY + Math.sin(lt) * (RIM - 2)); ctx.stroke();
          ctx.textAlign = Math.cos(lt) < 0 ? 'right' : 'left';
          ctx.fillStyle = g.hex; ctx.font = XRAY_SERIF; ctx.textBaseline = 'alphabetic';
          ctx.fillText(g.name + (g.low ? ' ?' : ''), lx, ly - 2);
          ctx.fillStyle = XRAY_SOFT; ctx.font = XRAY_SANS; ctx.fillText(sideWord(g.az), lx, ly + 9);
        }
        ctx.textAlign = 'left';
        ctx.fillStyle = XRAY_INK; ctx.beginPath(); ctx.arc(CX, CY - 1, 5, 0, Math.PI * 2); ctx.fill();
        ctx.font = XRAY_MONO; ctx.textBaseline = 'middle'; ctx.fillText('you', CX + 9, CY - 2);
        // where the sound came from, 100 ms at a time: three lanes in the badge's own frame (az_device, so a turn of
        // the wearer's body later on never flips an earlier sample), the dot in the colour of who was talking
        const LH = 54, L = 36, lanes = xCanvas(card, 'lanes', LH);
        const W2 = lanes.w - L - 6;
        const { t0, t1 } = xWindow(t);
        const Wn = X.win400, ys = [10, 27, 44];
        const azAt = (i) => (Wn.az_device ? Wn.az_device[i]
          : Wn.az_room[i] == null ? null : wrap180(Wn.az_room[i] - (Wn.yaw && Wn.yaw[i] != null ? Wn.yaw[i] : st.yaw)));
        lanes.ctx.font = XRAY_MONO; lanes.ctx.textBaseline = 'middle'; lanes.ctx.fillStyle = XRAY_SOFT;
        ['left', 'ahead', 'right'].forEach((s, k) => { lanes.ctx.fillText(s, 0, ys[k]); lanes.ctx.fillStyle = hexA(XRAY_RULE, 0.9); lanes.ctx.fillRect(L, ys[k], W2, 1); lanes.ctx.fillStyle = XRAY_SOFT; });
        for (let i = Math.max(0, Math.floor(t0 / Wn.step_ms)); i < Math.min(Wn.az_room.length, Math.ceil(t1 / Wn.step_ms)); i++) {
          const ms = i * Wn.step_ms;
          const az = azAt(i), conf = Wn.conf[i], lv = Wn.level_db[i];
          if (az == null || conf == null || conf < 0.3 || lv == null || lv <= -45) continue;
          const spk = xSpeakerAt(ms);
          if (spk && st.owner.has(spk)) continue;  // the wearer's own voice is the next card's business
          const hex = spk ? xColourOf(spk) : XRAY_SOFT;
          const x = L + ((ms - t0) / (t1 - t0)) * W2;
          lanes.ctx.fillStyle = hexA(hex, ms <= t ? 0.4 + 0.55 * conf : 0.15);
          lanes.ctx.beginPath(); lanes.ctx.arc(x, ys[laneOf(az)] + Math.sin(i * 1.7) * 2.5, 2, 0, Math.PI * 2); lanes.ctx.fill();
        }
        xPlayhead(lanes.ctx, L + ((t - t0) / (t1 - t0)) * W2, LH);
        return { show: true, moment: st.x.firstPos, lit: t - xLastTurnStart(t) < 900 || t - st.x.firstPos < XRAY_LIT };
      } },
    { id: 'above', col: 0, title: 'Your voice, from above', cap: 'Your own voice, found because it comes from above.',
      draw(card, st, t) {
        const X = P.xray;
        if (P.xrayState !== 'ok' || !X.wearer || st.ownerT == null) return { show: false };
        const ownerEv = X.owner_events.find((e) => e.t_ms === st.ownerT) || X.owner_events[0] || {};
        const byElevation = ownerEv.source === 'elevation';
        const found = X.wearer.found ? X.wearer.found[0] : null;
        const agree = found && st.owner.has(found);
        const c = X.wearer.constants;
        // who found the wearer: the code, from the elevation, or Muse Spark from the transcript (then the code's
        // Wearer is re-run here on audio.wav, and the card shows both)
        const chips = byElevation
          ? [['code', 'code · direction.py · Wearer'], PENDING_CHIP]
          : [['model', 'Muse Spark'], ['code', 'code · direction.py · Wearer · re-run offline'], PENDING_CHIP];
        const notes = [];
        notes.push(byElevation ? `owner event from the elevation at ${secs(st.ownerT)}` : `owner event at ${secs(st.ownerT)} from the transcript`);
        notes.push(found ? `offline re-run: ${found} is the voice from above${agree ? ' · the same voice' : ''}` : 'offline re-run: no label clearly above yet');
        if (P.meta.device === 'simulator') notes.push('rehearsal mix: the wearer\'s height is in the render');
        xSet(card, `<div class="xcanv" data-k="side"></div><p class="xnote">${esc(notes.join(' · '))}</p>`, xchips(chips),
          xrec(['rule', `median ≥ ${c.min_elevation}° up`, `${c.margin}° above every other voice`, `≥ ${c.min_turns} turns`, `conf ≥ ${c.min_confidence}`]));
        const H = 104, { ctx, w } = xCanvas(card, 'side', H);
        const bx = 54, by = H - 14, span = w - bx - 70;
        ctx.strokeStyle = hexA(XRAY_RULE, 1); ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(bx, by + 0.5); ctx.lineTo(w - 12, by + 0.5); ctx.stroke();
        const ray = (deg, len) => [bx + Math.cos(rad(deg)) * len, by - Math.sin(rad(deg)) * len];
        const [tx, ty] = ray(c.min_elevation, Math.min(span, H - 18) / Math.sin(rad(c.min_elevation)) * 0.95);
        ctx.strokeStyle = hexA(XRAY_SOFT, 0.8); ctx.setLineDash([4, 5]); ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(tx, ty); ctx.stroke(); ctx.setLineDash([]);
        ctx.font = XRAY_MONO; ctx.fillStyle = XRAY_SOFT; ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
        ctx.fillText('wearer threshold · code constant', Math.min(tx + 6, w - 150), Math.max(ty, 12));
        ctx.textAlign = 'center'; ctx.fillText('UP', bx, 10); ctx.fillText('guests · near level', bx + span * 0.62, by - 16);
        ctx.strokeStyle = hexA(XRAY_SOFT, 0.5); ctx.beginPath(); ctx.moveTo(bx, by - 2); ctx.lineTo(bx, 14); ctx.stroke();
        const talking = talkingSpeakers(st, t);
        for (const [spk, med] of Object.entries(X.wearer.medians)) {
          const own = spk === found;
          const [x, y] = ray(clamp(med, -10, 85), own ? Math.min(span * 0.78, H - 30) : span * 0.6);
          ctx.save(); ctx.translate(x, y); ctx.rotate(-rad(clamp(med, -10, 85)));
          const g = ctx.createRadialGradient(0, 0, 0, 0, 0, own ? 26 : 34);
          const hex = xColourOf(spk);
          g.addColorStop(0, hexA(hex, talking.has(spk) ? 0.7 : 0.5)); g.addColorStop(1, hexA(hex, 0));
          ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(0, 0, own ? 26 : 34, own ? 12 : 9, 0, 0, Math.PI * 2); ctx.fill();
          ctx.restore();
          if (own) { ctx.font = XRAY_SERIF; ctx.fillStyle = XRAY_INK; ctx.textAlign = 'left'; ctx.fillText('you ← wearer', x + 30, y + 4); }
        }
        ctx.fillStyle = '#F4F0E7'; ctx.strokeStyle = XRAY_INK; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.roundRect(bx - 6, by - 11, 12, 17, 2); ctx.fill(); ctx.stroke();
        ctx.textAlign = 'left';
        return { show: true, moment: st.ownerT };
      } },
    { id: 'recall', col: 1, title: 'A known name, instantly', cap: 'A known name, instantly, with no model.',
      draw(card, st, t) {
        const items = [...st.x.recall.values()].sort((a, b) => a.first.t_ms - b.first.t_ms);
        if (!items.length) return { show: false };
        // recall.py matches the name the moment it is heard (provisional, no model call); people.py only looks a
        // name up after Muse Spark has named the person, so the two paths wear different chips
        const isLocal = (r) => !!(r.first.matched || r.first.provisional != null);
        const local = items.filter(isLocal).length, lookedUp = items.length - local;
        xTitle(card, local ? 'A known name, instantly' : 'A known name, looked up');
        const personT = (key) => { const p = st.people.get(key) || P.final.people.get(key); return p ? p.firstT ?? p.t_ms : null; };
        const html = `<div class="xrows">${items.map((r) => {
          const { first, last } = r;
          const where = (last.encounters || []).map((e) => e.event).filter(Boolean).join(', ');
          const how = first.matched ? ` · matched: ${esc(first.matched)}` : '';
          const state = first.provisional ? (last.provisional ? ' · <span class="xk">provisional</span>' : ` · provisional → confirmed ${esc(secs(last.t_ms))}`) : '';
          const pt = isLocal(r) ? null : personT(first.key);
          return row('◎', `<b style="color:${colourHex(first.key)}">${esc(first.name)}</b> · met before${where ? ` · ${esc(where)}` : ''}${how}${state}${pt != null ? ` · <span class="xk">looked up</span>after Muse Spark named them at ${esc(secs(pt))}` : ''}`,
            isLocal(r) ? `recall.py · ${secs(first.t_ms)}` : `people.py · ${secs(first.t_ms)}`);
        }).join('')}</div>`;
        const chips = [];
        if (local) chips.push(['code', 'code · recall.py'], NO_MODEL_CHIP);
        if (lookedUp) chips.push(['model', 'Muse Spark'], ['code', 'after Muse Spark named them · code · people.py']);
        const receipt = items.map((r) => { const pt = isLocal(r) ? null : personT(r.first.key); return `${pt != null ? `person ${secs(pt)} → ` : ''}person_history ${secs(r.first.t_ms)}`; });
        xSet(card, html, xchips(chips), xrec(receipt));
        return { show: true, moment: Math.max(...items.map((r) => r.last.t_ms)), cap: local ? null : 'A known name, looked up after Muse Spark named it.' };
      } },
    { id: 'hooks', col: 1, title: 'From the log, not a model', cap: 'A reason to write, from the log, not a model.',
      draw(card, st, t) {
        const hooks = [...st.x.hooks.values()].sort((a, b) => a.t_ms - b.t_ms);
        if (!hooks.length) return { show: false };
        const html = `<div class="xrows">${hooks.map((h) => {
          const ev = (h.evidence || [])[0] || {};
          const who = xName(st, h.person_key);
          return row('→', `<b style="color:${colourHex(h.person_key)}">${esc(shortName(who))}</b> · <b>${esc(h.title)}</b>${ev.quote ? ` · <i>“${esc(truncate(ev.quote, 110))}”</i>` : ''}${h.provisional ? ' · <span class="xk">provisional</span>' : ''}`,
            ev.recording ? `evidence ${ev.recording.slice(-4)} · turn ${ev.turn}` : secs(h.t_ms));
        }).join('')}</div>`;
        xSet(card, html, xchips([['code', 'code · hooks.py'], NO_MODEL_CHIP]), xrec(['hook', `${hooks.length} ${plural(hooks.length, 'reason')}`, 'quotes from earlier evenings\' logs']));
        return { show: true, moment: Math.max(...hooks.map((h) => h.t_ms)) };
      } },
    { id: 'models', col: 1, title: 'Each model’s output, labelled', cap: 'Each model’s output, labelled.',
      draw(card, st, t) {
        let lastTurn = null;
        for (const tr of st.turns.values()) if (tr.done && (!lastTurn || tr.end > lastTurn.end)) lastTurn = tr;
        if (!lastTurn) return { show: false };
        const lang = P.turnLang.get(lastTurn.turn) || 'English';
        const parts = [];
        parts.push(xchip('model', 'Muse Voice Transcribe') + `<div class="v"><span class="xk">turn ${lastTurn.turn} · ${esc(lastTurn.speaker)} · ${esc(lang)}</span><i>${esc(truncate(lastTurn.text, 90))}</i></div>`);
        // the newest run's output, the most telling kinds first: a promise, a translation, a name, a misheard word
        const rank = (k) => (k === 'promise corrected' ? 6 : k === 'promise' ? 5 : k.startsWith('translation') ? 4 : k === 'person' ? 3 : k === 'misheard?' ? 2 : k === 'details' ? 1.5 : k === 'set aside' ? 1 : 0);
        const newest = st.x.spark.length ? Math.max(...st.x.spark.map((s) => s.t)) : null;
        const latest = newest == null ? [] : st.x.spark.filter((s) => s.t === newest).sort((a, b) => rank(b.kind) - rank(a.kind));
        const spark = latest.slice(0, 2);
        parts.push(xchip('model', 'Muse Spark') + `<div class="v${spark.length ? '' : ' soft'}">${spark.length ? spark.map((s) => `<span class="xk">${esc(s.kind)}</span>${esc(truncate(s.text, 70))}`).join('<br>') : 'nothing yet'}</div>`);
        // a promise whose date a later run replaced: the model's own correction (promise.replaces is a field Muse
        // Spark fills in); extract.diff only logs that it changed
        const corrected = [...st.promises.values()].filter((q) => (q.struck || []).length).sort((a, b) => (a.correctedT ?? a.t_ms) - (b.correctedT ?? b.t_ms));
        for (const q of corrected) {
          parts.push(xchip('model', 'Muse Spark') + `<div class="v"><span class="xk">corrected its own promise</span>${esc(q.what)} · <span class="xstrike">${esc(q.struck.join(', '))}</span> ${esc(q.due || 'no date')}<span class="xk" style="margin-left:6px">${esc(secs(q.correctedT ?? q.t_ms))}</span></div>`);
        }
        const edges = [...st.x.edges.values()].sort((a, b) => b.t_ms - a.t_ms);
        const run = st.x.runs[st.x.runs.length - 1];
        if (edges.length || run) {
          const e = edges[0];
          const tokens = run && run.usage && Number.isFinite(Number(run.usage.total_tokens)) ? ` · ${Number(run.usage.total_tokens).toLocaleString('en-US')} tokens` : '';
          const runLine = run ? `<span class="xk">call ${esc(run.call)}</span>${Number(run.seconds).toFixed(2)} s${tokens} · up to turn ${esc(run.upto_turn)}` : '';
          parts.push(xchip('model', 'Muse Spark Open on Baseten') + `<div class="v">${e ? `<span class="xk">edge</span><i>“${esc(truncate(e.said, 60))}”</i> → ${esc(e.act)}` : ''}${run ? `${e ? '<br>' : ''}${runLine}` : ''}</div>`);
        } else {
          parts.push(xchip('model', 'Muse Spark Open on Baseten') + '<div class="v soft">no second model in this log</div>');
        }
        parts.push(xchip('model', 'SAM 3.1') + `<div class="v soft">${st.photos.length ? `${st.photos.length} ${plural(st.photos.length, 'photo')} · ${st.photos.reduce((a, p) => a + (p.faces || []).length, 0)} faces` : 'no photo this evening'}</div>`);
        const chips = corrected.length ? [['code', 'code · extract.py · diff']] : [];
        xSet(card, `<div class="xledger">${parts.join('')}</div><p class="xnote">no token count is logged for Muse Spark runs${corrected.length ? ' · a corrected date is the model\'s own later word; the diff only logs the change' : ''}</p>`, xchips(chips),
          xrec(['events.jsonl', 'turn', 'person', 'promise', corrected.length ? 'promise.replaces' : null, 'translation', edges.length || run ? 'edge · second_run' : null]));
        // the caption follows the newest thing a model said, the most telling kind first; fixed lines, so it never wraps
        const top = latest[0] || null;
        const cap = !top ? null
          : top.kind === 'promise corrected' ? 'A later word replaces the earlier one.'
          : top.kind === 'promise' ? (top.text.includes(' · ') ? 'A promise caught, with its due date.' : 'A promise caught, no date yet.')
          : top.kind.startsWith('translation') ? `Translated from ${top.kind.replace('translation · ', '') || 'another language'}, kept as spoken.`
          : top.kind === 'person' ? 'A name from the introduction.'
          : top.kind === 'details' ? 'A person’s details filled in.'
          : top.kind === 'misheard?' ? 'A misheard word flagged.'
          : top.kind === 'set aside' ? 'Small talk set aside, not deleted.'
          : 'Overheard nearby, kept apart.';
        return { show: true, moment: newest ?? lastTurn.end, lit: st.x.lastWordsT != null && t - st.x.lastWordsT < XRAY_LIT, cap };
      } },
    { id: 'checks', col: 2, title: 'The code strikes what isn’t backed', cap: 'The code strikes what the transcript doesn’t back.',
      draw(card, st, t) {
        const rows = [];
        const verbatim = [];
        let sidecar = false, replayed = false;
        // every edge on the picture now, with kept_edges' verdict: from the sidecar (the shipping function, re-run by
        // export_xray.py on the logged events) when it has one, else the page's own port of it
        for (const e of st.x.edges.values()) {
          const p = st.people.get(e.person);
          const who = p ? shortName(p.name) : e.person;
          const v = xVerdict(e);
          let kept, where = null, reason = null;
          if (v) { sidecar = true; kept = v.kept; where = v.in_turn; reason = v.reason; }
          else {
            replayed = true;
            const sps = new Set((p && p.speakers) || []);
            const said = foldWords(e.said);
            for (const n of e.turns || []) { const tr = st.turns.get(n); if (tr && tr.done && sps.has(tr.speaker) && ` ${foldWords(tr.text)} `.includes(` ${said} `)) { where = n; break; } }
            kept = where != null;
            if (!kept) reason = !p ? 'no such person yet' : 'no turn of theirs with these words yet';
          }
          rows.push({ t: e.t_ms, html: kept
            ? row('✓', `edge <i class="xkept">“${esc(truncate(e.said, 70))}”</i> · ${esc(who)}'s words, in turn ${where} in ${esc(who)}'s own voice · <b>kept</b>`, 'kept_edges')
            : row('✕', `edge <i class="xstrike">“${esc(truncate(e.said, 70))}”</i> · ${esc(who)} · ${esc(reason || 'not backed')} · <b>dropped</b>`, 'kept_edges') });
          verbatim.push(`edge · ${secs(e.t_ms, 3)} · ${e.person} · turns [${(e.turns || []).join(', ')}] · act "${e.act}"`);
        }
        // the retired two-model comparison (edge_finder.py): its confirmed / disagreement events stay in a log that has
        // them, and a withdrawn confirmation is the one logged strike there is
        const retired = st.x.disagreements.length || st.x.confirmed.size;
        for (const d of st.x.disagreements) {
          const gone = st.x.unconfirmed.some((u) => u.kind === d.kind && u.key === d.key);
          const who = xName(st, d.key);
          rows.push({ t: d.t_ms, html: row('✕', `<span class="xstrike">${esc(who)} · ${esc(d.a.text)} · confirmed</span> · ${esc(d.a.by)} says “${esc(d.a.text)}”, ${esc(d.b.by)} “${esc(d.b.text)}”${gone ? ' · confirmation withdrawn' : ''} · <span class="xk">retired comparison</span>`, `disagreement ${secs(d.t_ms)}`) });
          verbatim.push(`disagreement · ${secs(d.t_ms, 3)} · ${d.id} · ${d.a.by} "${d.a.text}" · ${d.b.by} "${d.b.text}"`);
          if (gone) verbatim.push(`confirmed_removed · ${secs(d.t_ms, 3)} · ${d.kind} · ${d.key}`);
        }
        const agreed = [...st.x.confirmed.values()];
        if (agreed.length) {
          const last = agreed[agreed.length - 1];
          const claim = (a) => (a.kind === 'promise' ? `promise · ${(st.promises.get(a.key) || P.final.promises.get(a.key) || {}).what || a.key}` : `${a.kind} · ${shortName(xName(st, a.key))}`);
          rows.push({ t: last.t_ms, html: row('✓', `${agreed.length} ${plural(agreed.length, 'claim')} where two models agreed · ${esc([...new Set(agreed.flatMap((a) => a.by || []))].join(' + '))} · ${esc(agreed.slice(-3).map(claim).join(' · '))} · <span class="xk">retired comparison</span>`, `confirmed ${secs(last.t_ms)}`) });
          verbatim.push(`confirmed · ${secs(last.t_ms, 3)} · ${last.kind} · ${last.key} · by ${(last.by || []).join(', ')}`);
        }
        if (!rows.length) return { show: false };
        rows.sort((a, b) => a.t - b.t);
        let html = `<div class="xrows">${rows.map((r) => r.html).join('')}</div>`;
        if (st.x.edgesRemoved) html += `<p class="xnote">${st.x.edgesRemoved} ${plural(st.x.edgesRemoved, 'edge')} re-cited by a later run (edge_removed is a diff, not a rejection)</p>`;
        if (retired) html += `<p class="xnote">the two-model comparison has since been retired (edge_finder.py); its events stay in this log, from ${esc(logDate())}</p>`;
        html += `<p class="xnote">${esc(verbatim.slice(-2).join('\n')).replace(/\n/g, '<br>')}</p>`;
        const chips = [];
        if (sidecar || replayed) chips.push(['code', 'code · extract.py · kept_edges'], ['stamp', sidecar ? 'verdicts re-run offline by export_xray.py · check events not logged yet' : 'verdicts re-run in the page · check events not logged yet']);
        if (retired) chips.push(['stamp', `retired two-model comparison · logged ${logDate()}`]);
        xSet(card, html, xchips(chips), xrec(['events.jsonl', sidecar || replayed ? 'edge' : null, sidecar ? 'xray.json · checks' : null, st.x.disagreements.length ? 'disagreement → confirmed_removed' : null]));
        return { show: true, moment: st.x.lastCheckT ?? rows[rows.length - 1].t };
      } },
    { id: 'research', col: 2, title: 'Research: no source, no line', cap: 'Research: no source, no line.',
      draw(card, st, t) {
        const report = P.rec.report;
        if (!st.ended || !report || !(report.checked || []).length) return { show: false };
        // the telling case first (a company found but nobody tied to it, or nothing public), its findings in full;
        // the others as one line each, so the card stays the height of a beat
        const weak = (c) => (c.status === 'no_public_record' ? 0 : c.status === 'partial' ? 1 : 2);
        const checked = report.checked.slice().sort((a, b) => weak(a) - weak(b) || (a.name || '').localeCompare(b.name || ''));
        const host = (u) => { try { const x = new URL(u); return x.host.replace(/^www\./, '') + (x.pathname === '/' ? '' : x.pathname); } catch (_) { return String(u); } };
        const html = `<div class="xrows">${checked.slice(0, 5).map((c, i) => {
          const [tag, said] = CHECK[c.status] || [String(c.status || '').replace(/_/g, ' '), ''];
          const n = (c.findings || []).length;
          const head = row('◎', `<b style="color:${colourHex(c.record_key || c.key)}">${esc(c.name)}</b>${c.company ? ` · ${esc(c.company)}` : ''} · <span class="xk">${esc(tag)}</span>${i ? ` · ${n ? `${n} ${plural(n, 'finding')} kept` : 'nothing public found'}` : ''}`, c.searched === false ? 'no search ran' : i ? '' : `${n} kept`);
          if (i) return head;
          const lines = (c.findings || []).slice(0, 3).map((f) => row('✓', `<span class="xk">${esc(f.kind || 'found')}</span>${esc(truncate(f.text, 96))}`, f.source ? host(f.source) : '')).join('');
          const none = n ? '' : row('—', `nothing public found · ${esc(said)}`, 'status');
          const gap = c.status === 'partial' || c.status === 'no_public_record' ? row('—', `<span class="xk">profile</span>nothing public ties ${esc(firstName(c.name))} to ${esc(c.company || 'the company')} · ${esc(said)}`, 'status') : '';
          return head + lines + none + gap;
        }).join('')}</div><p class="xnote">a finding whose page was not in the search results is dropped; the status is the weaker of the model's claim and what the kept findings show</p>`;
        const cost = report.cost || {};
        const searched = report.checked.filter((c) => c.searched !== false).length;
        xSet(card, html, xchips([['model', 'Muse Spark with web search'], ['code', 'code · research.py · ground']]),
          xrec(['report.checked', `${report.checked.length} checked`, `${searched} searched`, Number.isFinite(Number(cost.searches)) ? `${cost.searches} web ${plural(Number(cost.searches), 'search', 'searches')}` : null, Number(cost.research_tokens) ? `${Number(cost.research_tokens).toLocaleString('en-US')} tokens` : null]));
        return { show: true, moment: st.endT ?? t };
      } },
    { id: 'deck', col: 2, title: 'The deck, rebuilt', cap: 'The deck, rebuilt. Every number held to the slides.',
      draw(card, st, t) {
        const r = st.x.rebuilt[st.x.rebuilt.length - 1];
        const moves = [...st.moves.values()];
        const movesNote = moves.length ? `<p class="xnote">${moves.length} ${plural(moves.length, 'follow-up')} drafted, one per promise · next_move · a draft that quotes the person's own words is written again (overheard); redrafts are not logged</p>` : '';
        if (!r) {
          if (!st.ended) return { show: false };
          xSet(card, `<p class="xempty">No <code>rebuilt</code> event in this log. The notification's data is <code>onepager.rebuilt_event</code>; the page is cued on request.</p>${movesNote}`,
            xchips([['code', 'code · onepager.py']]), xrec(['rebuilt', 'none logged', moves.length ? 'next_move' : null]));
          return { show: true, dim: true };
        }
        const slides = (r.slides || []).length;
        const dropped = Array.isArray(r.dropped) ? r.dropped.length : null;
        const bits = [];
        if (slides) bits.push(`${slides} slides → 1 page`);
        if (r.shape) bits.push(r.shape);
        if (dropped != null) bits.push(`${dropped} ${plural(dropped, 'line')} dropped`);
        if (r.retried != null) bits.push(`retried: ${r.retried}`);
        if (Number.isFinite(Number(r.seconds))) bits.push(`${Number(r.seconds).toFixed(2)} s`);
        if (r.usage && Number.isFinite(Number(r.usage.total_tokens))) bits.push(`${Number(r.usage.total_tokens).toLocaleString('en-US')} tokens`);
        if (r.model) bits.push(r.model);
        const html = `<div class="xrows">${row('✓', `<b>${esc(r.name || xName(st, r.person_key))}</b> · ${esc(bits.join(' · ') || r.format || 'html')} · every number on the page must appear in the slides (onepager.numbers)`, r.cued ? 'cued' : 'rebuilt')}${(r.acts || []).slice(0, 2).map((a) => row('→', `<span class="xk">act</span>${esc(a)}`, '')).join('')}</div>${movesNote}`;
        xSet(card, html, xchips([['model', 'Muse Spark'], ['code', 'code · onepager.py · numbers']]), xrec(['rebuilt', secs(r.t_ms), r.person_key, moves.length ? 'next_move' : null]));
        return { show: true, moment: r.t_ms };
      } },
    { id: 'buzz', col: 2, title: 'The buzz', cap: 'The buzz: what the owner saw; everything above is why.',
      draw(card, st, t) {
        const r = st.x.rebuilt[st.x.rebuilt.length - 1];
        // the app's own banner, as RebuiltNotice.swift words it: "<first name> · your deck, rebuilt" / "<Shape>. Ready."
        const first = r ? firstName(r.name || '') : '';
        const what = r ? r.shape || (r.acts || [])[0] || '' : '';
        const headline = first ? `${first} · your deck, rebuilt` : 'Your deck, rebuilt';
        const subline = what ? `${what.charAt(0).toUpperCase()}${what.slice(1)}. Ready.` : 'Ready.';
        const notif = `<div class="xnotif${r ? '' : ' ghost'}"><span class="app">Hallwise · on the badge${r ? ' · now' : ''}</span><span class="h">${esc(headline)}</span><span class="s">${esc(subline)}</span></div>`;
        if (!r) {
          if (!st.ended) return { show: false };
          xSet(card, `${notif}<p class="xnote">no rebuilt event this evening: the banner above is the app's own fallback wording, with nothing filled in</p>`,
            xchips([['code', 'code · RebuiltNotice.swift'], ['none', 'none logged']]), xrec(['RebuiltNotice.swift', 'headline · subline', 'rebuilt · none']));
          return { show: true, dim: true };
        }
        xSet(card, `${notif}<p class="xnote">${(r.slides || []).length ? `${(r.slides || []).length} slides → 1 page · ` : ''}${esc(r.format || 'html')}${r.cued ? ' · cued' : ''} · one system haptic, the banner, nothing else</p>`,
          xchips([['code', 'code · RebuiltNotice.swift'], ['code', 'code · onepager.py']]), xrec(['rebuilt', secs(r.t_ms), r.person_key, 'RebuiltNotice.swift']));
        return { show: true, moment: r.t_ms };
      } },
  ];

  function renderXray(st, t) {
    // everything below is a function of (t, the fold, the sidecar, the frame); while none of them change, so does nothing here
    const sig = `${t}|${S.rev}|${P.xrayState}|${els.xray.clientWidth}x${window.innerHeight}|${xFocus}|${xFit}|${player.playing ? 1 : 0}|${els.app._barH}`;
    if (sig === xLast) return;
    xLast = sig;
    const results = [];
    XBEATS.forEach((b, i) => {
      const card = xCard(b, i);
      let r;
      try { r = b.draw(card, st, t) || { show: false }; } catch (err) { r = { show: false }; if (!card._warned) { card._warned = true; console.warn(`xray ${b.id}:`, err); } }
      const show = !!r.show;
      const lit = show && !r.dim && (r.lit != null ? r.lit : r.moment != null && t >= r.moment && t - r.moment < XRAY_LIT);
      const focus = xFocus === i + 1 && show;
      const cls = `xcard${show ? '' : ' off'}${lit ? ' lit' : show ? ' done' : ''}${r.dim ? ' dim' : ''}${focus ? ' focus' : ''}`;
      if (card.el.className !== cls) card.el.className = cls;
      results.push({ b, r, lit, show, focus });
    });
    // the caption belongs to the beat whose moment is latest; on a tie the earlier beat (the sound) keeps it
    let best = null;
    for (const x of results) if (x.show && !x.r.dim && x.r.moment != null && x.r.moment <= t && (!best || x.r.moment > best.r.moment)) best = x;
    const focused = results.find((x) => x.focus);
    const pick = focused || best;
    const n = results.filter((x) => x.show && !x.r.dim).length;
    const caption = pick
      ? `<span class="n">${String(XBEATS.indexOf(pick.b) + 1).padStart(2, '0')} / ${XBEATS.length}</span>${esc(capFit(pick.r.cap || pick.b.cap))}`
      : '<span class="n">X-ray</span>What the badge did while they talked.';
    if (els['x-caption']._html !== caption) { els['x-caption']._html = caption; els['x-caption'].innerHTML = caption; }
    const stamp = xrec([P.id, `${mmss(t)}.${Math.floor((t % 1000) / 100)}`, player.playing ? 'live' : 'frozen', P.meta.event || '']);
    if (els['x-stamp']._html !== stamp) { els['x-stamp']._html = stamp; els['x-stamp'].innerHTML = stamp; }
    const legend = xchips([['model', 'a Meta model'], ['code', 'Hallwise code'], PENDING_CHIP]);
    if (els['x-legend']._html !== legend) { els['x-legend']._html = legend; els['x-legend'].innerHTML = legend; }
    const tape = results.map((x) => `<span class="tick${x.show && !x.r.dim ? ' on' : ''}${x.lit ? ' now' : ''}"></span>`).join('') +
      `<span class="xreceipt">${xrec([`${n} of ${XBEATS.length} up`, 'every value from events.jsonl, the xray sidecar or the saved report'])}</span>`;
    if (els['x-tape']._html !== tape) { els['x-tape']._html = tape; els['x-tape'].innerHTML = tape; }
    xLayout(focused ? focused.b : null);
  }

  /** Fit the X-ray to the frame: on a wide screen the columns are scaled down until every card is in view (a
   *  headless still then shows the beat that just lit, whatever the column heights); with &focus=NN one card is
   *  held large in the centre instead, as big as the frame allows up to 2×, for a phone or a film still. */
  let xScale = 1, xCompact = false;  // the fit's state: it tightens at once and loosens only with clear room, so nothing jitters
  function xLayoutReset() { xScale = 1; xCompact = false; xLast = ''; }
  window.addEventListener('resize', xLayoutReset);
  function xLayout(focusBeat) {
    const inner = els.xray.querySelector('.xray-in');
    const barH = els.app._barH || 0;
    const avail = window.innerHeight - barH;
    els.app.classList.toggle('is-focus', !!focusBeat);
    for (const c of xCards.values()) if (c.el.classList.contains('focus') && (!focusBeat || c !== xCards.get(focusBeat.id))) c.el.classList.remove('focus');
    if (focusBeat) {
      // the card keeps its column's width (a fixed box would otherwise size itself to its widest chip), then scales
      // to the room between the caption and the bar, up to 2×, and sits in the middle of that room
      const card = xCards.get(focusBeat.id);
      inner.style.transform = ''; inner.style.marginBottom = '';
      els.app.classList.remove('is-compact');
      const w = card.el.parentNode.clientWidth || card.el.offsetWidth;
      card.el.style.width = `${w}px`;
      const h = card.el.offsetHeight;
      const top = els['x-caption'].getBoundingClientRect().bottom + 12;
      const room = Math.max(120, avail - top - 14);
      const s = Math.max(0.5, Math.min(2, (window.innerWidth - 32) / w, room / h));
      card.el.style.setProperty('--fs', s.toFixed(3));
      card.el.style.setProperty('--fy', `${Math.round(top + room / 2)}px`);
      return;
    }
    for (const c of xCards.values()) if (c.el.style.width) c.el.style.width = '';
    const wide = window.innerWidth >= 920;
    const want = xFit === 'on' || (xFit === 'auto' && wide);
    if (!want) { inner.style.transform = ''; inner.style.marginBottom = ''; els.app.classList.remove('is-compact'); return; }
    inner.style.transform = ''; inner.style.marginBottom = '';
    els.app.classList.toggle('is-compact', xCompact);
    let need = inner.scrollHeight;
    if (!xCompact && need > avail * 1.12) { xCompact = true; els.app.classList.add('is-compact'); need = inner.scrollHeight; }  // notes go before type shrinks
    const fit = need <= avail ? 1 : Math.max(0.6, avail / need);
    if (fit < xScale - 0.005 || fit > xScale + 0.08) xScale = fit;
    if (xScale >= 1) return;
    inner.style.transform = `scale(${xScale.toFixed(4)})`;
    inner.style.marginBottom = `${-Math.round(need * (1 - xScale))}px`;
  }

  // ---------------------------------------------------------------- render loop
  function stateAt(t) {
    if (t < S.t) S = freshState();
    while (S.i < P.evs.length && P.evs[S.i].t_ms <= t) { apply(S, P.evs[S.i]); S.i++; S.rev++; }
    S.t = t;
    return S;
  }

  function render(t) {
    const st = stateAt(t);
    if (!xrayOn) renderRadar(st, t);
    renderTransport(t);
    if (mode !== 'live') return;
    if (xrayOn) { renderXray(st, t); return; }  // the panels under the overlay catch up when it closes
    renderCaptions(t);
    renderPeople(st, t);
    renderTranscript(st, t);
    renderPromises(st, t);
    renderRadarNote(st);
    renderAfter(st);
  }

  function frame() {
    if (P) {
      let t = player.now();
      if (player.playing && t >= P.total) {
        player.pause(P.total);
        t = P.total;
        if (!endScrolled) {
          endScrolled = true;
          setTimeout(() => els.after.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' }), 300);
        }
      }
      render(t);
    }
    requestAnimationFrame(frame);
  }

  function jumpTo(t, turn) {
    stickTranscript = true;
    player.seek(t);
    if (turn != null) {
      flashTurn = turn;
      setTimeout(() => { if (flashTurn === turn) flashTurn = null; }, 4500);
      setTimeout(() => {
        const el = lineEls.get(turn);
        if (el) el.scrollIntoView({ block: 'nearest', behavior: reduceMotion() ? 'auto' : 'smooth' });
      }, 60);
    }
  }

  function enterLive() {
    if (mode === 'live') return;
    mode = 'live';
    els.app.classList.remove('is-intro');
    els.app.classList.add('is-live');
    document.body.classList.remove('is-intro');
    els.radar.classList.remove('ghost');
    stickTranscript = true;
  }

  function enterIntro() {
    player.pause(0);
    if (xrayOn) setXray(false);
    mode = 'intro';
    els.app.classList.add('is-intro');
    els.app.classList.remove('is-live');
    document.body.classList.add('is-intro');
    els.radar.classList.add('ghost');
    player.seek(P ? P.total : 0);  // the ghost of the finished room behind the hero
    window.scrollTo({ top: 0, behavior: reduceMotion() ? 'auto' : 'smooth' });
  }

  function togglePlay() {
    if (!P) return;
    enterLive();
    if (player.playing) player.pause();
    else { if (player.paused >= P.total - 50) endScrolled = false; player.play(); }
  }

  // ---------------------------------------------------------------- intro text
  function fillIntro() {
    const F = P.final, meta = P.meta;
    els['evening-name'].textContent = meta.event || 'An evening with the badge';
    const w = P.started ? wallDate(P.started, P.tzOffset) : null;
    const bits = [meta.venue, w ? `${dayLabel(w)} · ${hhmm(w)}` : '', durationWords(P.endT),
      P.hasDirection ? 'four microphones' : 'one microphone'].filter(Boolean);
    els['evening-meta'].textContent = bits.join(' · ');
    const voices = F.speakers.size;
    const langs = new Set([...F.translations.values()].map((x) => x.language).filter(Boolean));
    const stats = [
      [voices, plural(voices, 'voice')],
      [F.people.size, plural(F.people.size, 'person named', 'people named')],
      [F.promises.size, plural(F.promises.size, 'promise')],
    ];
    if (F.moves.size) stats.push([F.moves.size, plural(F.moves.size, 'follow-up')]);
    if (langs.size) stats.push([langs.size, `${plural(langs.size, 'language')} besides English`]);
    els['evening-stats'].innerHTML = stats.map(([n, l]) => `<span><b>${n}</b>${esc(l)}</span>`).join('');
    els['play-len'].textContent = ` · ${mmss(P.endT)}`;
    els['play-big'].disabled = false;
    els['wearer-mark'].textContent = (P.ownerName || 'Y').slice(0, 1).toUpperCase();
    const ex = P.rec.exported ? wallDate(P.rec.exported, P.tzOffset) : null;
    els['foot-id'].textContent = `Recording ${P.id}${ex ? ` · exported ${dayLabel(ex)} ${ex.y}` : ''}`;
  }

  // ---------------------------------------------------------------- loading
  async function loadJSON(url) {
    const r = await fetch(url, { cache: 'no-cache' });
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return r.json();
  }

  function resetDom() {
    for (const m of [blipEls, lineEls, promiseEls, personEls, captionEls]) { for (const el of m.values()) el.remove(); m.clear(); }
    els.transcript.innerHTML = '';
    els.promises.innerHTML = '';
    els.suspects.innerHTML = '';
    els.suspects._html = '';
    els.moves.innerHTML = '';
    els.people.innerHTML = '';
    els.captions.innerHTML = '';
    movesSig = '';
    morningDrawn = false;
    redraftEls.clear();
    for (const id of ['m-hooks', 'm-redrafts', 'm-checks', 'm-due', 'morning-count', 'morning-cost']) els[id].innerHTML = '';
    els.morning.hidden = true;
    weekDrawn = false;
    weekFilter = null;
    endScrolled = false;
    flashTurn = null;
    S = freshState();
    resetXray();
  }

  function start(rec) {
    if (player.playing) player.pause();
    resetDom();
    P = prepare(rec);
    P.xray = null;            // the sidecar data/<id>.xray.json, fetched when the X-ray opens
    P.xrayState = 'idle';     // idle | loading | ok | none
    if (xrayOn) ensureSidecar();
    setupAudio(rec);
    fillIntro();
    buildTransport();
    player.rate = 1;
    document.querySelectorAll('.speed button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.rate === '1')));
    if (mode === 'intro') { els.radar.classList.add('ghost'); player.seek(P.total); }
    else player.seek(0);
    syncPlayButton();
  }

  async function boot() {
    drawRadarStatic();
    applyTheme(lsGet('hallwise-replay-theme'));
    let index;
    try {
      index = await loadJSON('data/index.json');
    } catch (err) {
      els['evening-name'].textContent = 'No recording exported yet';
      els['evening-meta'].innerHTML = 'Run <code>uv run python scripts/export_replay.py &lt;recording id&gt;</code> in <code>server/</code>, then reload.';
      return;
    }
    const rows = index.recordings || [];
    if (!rows.length) { els['evening-name'].textContent = 'No recording exported yet'; return; }
    const want = parseHash(location.hash);
    if (new URLSearchParams(location.search).has('xray')) want.xray = true;
    const pick = rows.find((r) => r.id === want.id) || rows.find((r) => r.id === index.default) || rows[0];
    if (rows.length > 1) {
      els.pick.hidden = false;
      els.pick.innerHTML = rows.map((r) => {
        const w = r.started ? wallDate(r.started, 480) : null;
        return `<option value="${esc(r.id)}">${esc(r.event || r.id)}${w ? ` · ${DAYS[w.wd]} ${w.d} ${MONTHS[w.mo]}` : ''}</option>`;
      }).join('');
      els.pick.value = pick.id;
      els.pick.addEventListener('change', async () => {
        const row = rows.find((r) => r.id === els.pick.value);
        if (!row) return;
        try {
          const rec = await loadJSON(`data/${row.file}`);
          start(rec);
          enterIntro();
        } catch (err) { toast(`That evening could not load (${err.message}).`); }
      });
    }
    window.addEventListener('hashchange', async () => {
      const w = parseHash(location.hash);
      const row = rows.find((r) => r.id === w.id);
      if (!row) return;
      if (P && row.id === P.id) { applyHashState(w); return; }
      try {
        const rec = await loadJSON(`data/${row.file}`);
        start(rec);
        enterIntro();
        if (!els.pick.hidden) els.pick.value = row.id;
        applyHashState(w);
      } catch (err) { toast(`That evening could not load (${err.message}).`); }
    });
    try {
      const rec = await loadJSON(`data/${pick.file}`);
      start(rec);
      applyHashState(want);
    } catch (err) {
      els['evening-name'].textContent = 'This evening could not load';
      els['evening-meta'].textContent = String(err.message || err);
    }
  }

  // ---------------------------------------------------------------- theme
  const THEMES = ['auto', 'light', 'dark'];
  function applyTheme(value) {
    const v = THEMES.includes(value) ? value : null;
    if (v === 'light' || v === 'dark') document.documentElement.setAttribute('data-theme', v);
    else if (v === 'auto') document.documentElement.removeAttribute('data-theme');
    const cur = document.documentElement.getAttribute('data-theme') || 'auto';
    els['theme-label'].textContent = cur === 'auto' ? 'Auto' : cur === 'light' ? 'Light' : 'Dark';
    els.theme.setAttribute('aria-label', `Colour theme: ${cur === 'auto' ? 'automatic' : cur}. Change`);
  }
  els.theme.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme') || 'auto';
    const next = THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length];
    applyTheme(next);
    lsSet('hallwise-replay-theme', next === 'auto' ? null : next);
  });

  // ---------------------------------------------------------------- input
  els['play-big'].addEventListener('click', () => {
    if (!P) return;
    enterLive();
    endScrolled = false;
    player.seek(0);
    player.play();
  });
  const skip = () => {
    if (!P) return;
    enterLive();
    player.pause(P.total);
    stickTranscript = true;
    render(P.total);
    setTimeout(() => els.after.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' }), 80);
  };
  els['skip-end'].addEventListener('click', skip);
  els['skip-end-2'].addEventListener('click', skip);
  els.pp.addEventListener('click', togglePlay);
  function setMuted(m) {
    player.muted = m;
    if (player.audio) player.audio.muted = m;
    els.mute.setAttribute('aria-pressed', String(m));
    els.mute.setAttribute('aria-label', m ? 'Turn the sound on' : 'Mute the sound');
    els['mute-waves'].toggleAttribute('hidden', m);
    els['mute-cross'].toggleAttribute('hidden', !m);
    lsSet('hallwise-replay-muted', m ? '1' : null);
  }
  els.mute.addEventListener('click', () => setMuted(!player.muted));
  setMuted(lsGet('hallwise-replay-muted') === '1');
  els.brand.addEventListener('click', (e) => { e.preventDefault(); if (P) enterIntro(); });
  els['xray-btn'].addEventListener('click', () => { if (P) setXray(!xrayOn); });
  els['x-close'].addEventListener('click', () => setXray(false));
  document.querySelectorAll('.speed button').forEach((b) => b.addEventListener('click', () => {
    const r = Number(b.dataset.rate) || 1;
    player.setRate(r);
    document.querySelectorAll('.speed button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  }));
  els.suspects.addEventListener('click', (e) => {
    const row = e.target.closest('.suspect-row');
    if (!row) return;
    const turn = Number(row.dataset.turn);
    const t = P.turnStart.get(turn);
    if (t != null) jumpTo(t - 150, turn);
  });

  // scrubbing
  let dragging = false;
  const seekFromEvent = (e) => {
    const r = els.track.getBoundingClientRect();
    const frac = clamp((e.clientX - r.left) / r.width, 0, 1);
    stickTranscript = true;
    player.seek(frac * P.total);
  };
  els.track.addEventListener('pointerdown', (e) => {
    if (!P) return;
    dragging = true;
    enterLive();
    try { els.track.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    seekFromEvent(e);
  });
  els.track.addEventListener('pointermove', (e) => { if (dragging) seekFromEvent(e); });
  const endDrag = () => { dragging = false; };
  els.track.addEventListener('pointerup', endDrag);
  els.track.addEventListener('pointercancel', endDrag);

  const typing = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable);
  document.addEventListener('keydown', (e) => {
    if (!P || typing(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.code === 'Space' || e.key === ' ') {
      e.preventDefault();
      if (!e.repeat) togglePlay();
    } else if ((e.key === 'm' || e.key === 'M') && player.audio) {
      setMuted(!player.muted);
    } else if (e.key === 'x' || e.key === 'X') {
      setXray(!xrayOn);
    } else if (e.key === 'Escape' && xrayOn) {
      setXray(false);
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      if (mode !== 'live') return;
      e.preventDefault();
      const step = (e.shiftKey ? 15000 : 5000) * (e.key === 'ArrowLeft' ? -1 : 1);
      stickTranscript = true;
      player.seek(player.now() + step);
    }
  });
  document.addEventListener('keyup', (e) => {
    if ((e.code === 'Space' || e.key === ' ') && !typing(e.target)) e.preventDefault();  // no second toggle via button activation
  });

  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (weekDrawn && !els.week.hidden) drawWeek(); }, 200);
  });

  document.body.classList.add('is-intro');
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => { for (const el of blipEls.values()) el._lw = 0; }).catch(() => {});
  }
  boot();
  requestAnimationFrame(frame);

  // exposed for checking the replay from a console; not used by the page
  window.__hallwiseReplay = { get P() { return P; }, get S() { return S; }, player, prepare, buildCaptions, setXray, get xrayOn() { return xrayOn; } };
})();
