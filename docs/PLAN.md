# Hallwise — plan and architecture

Working name. Meta Global AI Developer Hackathon, Indie Developer track, theme "Build for Your World".
Submission: Wed 2026-11-04 9:00 PM ET (Thu 2026-11-05 10:00 Taipei) on the Cerebral Valley platform: public repo,
three-minute demo video, live product.

Judging (Stage Two, 0–10 each): Impact 30%, Use of Meta AI Tooling 25%, Technical Depth & Execution 20%,
Demo 25%. Top five per track go to a live final.

## What it is

You meet twenty or thirty people at an event and lose half of them by morning: who they were, what they do, what
you promised. Hallwise runs on one device, the phone you wear as your badge: its microphones hear where each
voice comes from, and its gyroscope keeps those positions fixed in the room while you turn or lean in to listen.
The models write and judge in real time: the people you met, where each one stood, what you owe each of them,
a follow-up for each person in the language they asked for, and a radar of what the room was talking about.

Lead with these three, in this order:
1. **Identity without biometrics.** People are named from what they say ("Hi, I'm Sarah from Acme") and your
   one-tap confirmation; no voiceprints, no faces.
2. **A promise ledger that understands corrections.** "Coffee on Thursday — no, Friday" becomes one promise, on
   Friday, with the quote it came from.
3. **It learns your world's words.** Words that look misheard are surfaced; your corrections become recognition
   hints for the next recording. The harness measures the before and after on accented English.

Positioning to avoid: "never forget a face", "always-on memory of everything around you".

## Pitch (first lines of the video, the submission text, the README and the X post)

Screeners, human or AI, read the top and watch the first seconds. These go first, in this order:

- **One line:** Hallwise turns a loud networking event into everyone you met, what you promised them, and a
  follow-up in their language — live, from your phone and AirPods, with no voiceprints or faces.
- **Problem:** You meet thirty people at an event and forget half of them by morning.
- **Why it's better:** Note-takers give you "Speaker 1, Speaker 2" and fall apart in a loud room. Hallwise names
  people from how they introduce themselves, hears where each voice comes from, and a second Meta model
  double-checks every name.
- **Result:** "One take, five people, four accents, crowd noise: N/5 people named, N/N promises caught, names
  A% → B% after one correction." Every number comes from the harness run on the final take.

## Hosting

Users don't run anything. One Docker image holds the server, the web UI and SQLite.

- Demo: the image runs on Mac-0 in the living room.
- Live product for judges: the same image on an ordinary cloud host, with sample recordings preloaded and
  record-in-browser.
- Bystanders get topics only (room radar), never a person card.
- Roadmap: the same image in a GPU TEE (Phala Cloud: Intel TDX + H100 confidential computing) with public
  attestation and a "verified enclave" badge in the app.

## Meta models

| Model | Role |
|---|---|
| Muse Voice Transcribe (`muse-voice-transcribe-1.0`) | Realtime transcription with DIARIZATION (session-scoped labels, turn-level timestamps), `languageBias`, `keywords` from memory. Code-switching for French and Japanese turns. |
| Muse Spark 1.3 (`muse-spark-1.3`, Standard mode) | Rolling structured extraction: room radar topics from ambient speech, introductions, label → person bindings with evidence quotes, promises with corrections, preferred language, misheard-looking words. Tool use for follow-through: email drafts, `.ics` invites, introductions. Approve before anything is sent. |
| Muse Spark Open (Baseten) | **Second listener.** Voice Transcribe returns no confidence. For each turn that contains a name or a suspect word, Spark Open hears that turn's audio with the candidate names and gives its own reading. Where the two Meta models disagree, the word is flagged. The harness reports name accuracy with one listener and with two. Eligible for the open-weight bonus. |

## Architecture

```
iPhone Safari /record ──audio WebSocket──▶ server ──▶ Voice Transcribe realtime ──▶ turns
badge gyroscope ──orientation (same app)──▶     │                                          │
                                                ├──▶ split: conversation vs ambient ◀──────┘
                                                │        │                    └──▶ Muse Spark ──▶ room_topic
                                                │        └──▶ Muse Spark (rolling extraction) ──▶ events
                                                │                     └──▶ Spark Open second listener
events ──▶ SQLite ──▶ web UI (live dashboard, recap; replay of any recording)
```

### The contract: one event log per recording

Typed events on the recording's clock: `turn`, `speaker`, `device_pose`, `position`, `person_bound`,
`person_updated`, `suspect_term`, `listener_disagreement`, `promise`, `followup`, `room_topic`. The UI renders only
events, so the same components serve live (WebSocket) and replay. The demo player reads only this log, never the
rig's scene files. The harness scores the log against the scene's ground truth.

### Pipeline (Python)

1. Capture: multichannel audio and the phone's own orientation from the iOS capture app, which also saves the full multichannel recording on the phone (the demo
   soundtrack and a replay source). First choice: iOS 26
   spatial audio (first-order ambisonics, four channels, full 360°) if it can be captured audio-only in real time —
   to be confirmed on the device; otherwise built-in stereo. AirPods are optional, one ear for whisper prompts only.
   Recorded on one clock (iPhone 17 Pro worn as a
   badge: portrait, on a short lanyard or clipped to the shirt, screen out and always on, showing the owner's
   name, company and logo in a paper-like design the user customises; built-in stereo; the phone's gyroscope
   corrects for swing; a landscape chest clip stays an option if the harness shows it is clearly better). The app pins the input to the built-in mics and never enables Bluetooth (HFP) input,
   so connected AirPods can't take over the recording. Fallback without Xcode: Safari `/record` (mono, no
   direction).
2. Transcribe: realtime, DIARIZATION, keyword hints from memory, on a mono mix.
3. Positions: for each turn, the direction the voice came from relative to the badge (level and time
   differences between channels), rotated by the badge's orientation into room coordinates. Each speaker label
   gets a stable position in the room that does not move when Eric turns, leans in sideways to hear, or the badge
   swings. Facing direction is never used as "who I'm talking to".
4. Classify every turn (`turn_class`), so only real conversation reaches people and promises:
   - `conversation`: back-and-forth with Eric → kept.
   - `incidental`: "thank you" to a waiter, "excuse me", "sorry", "cheers" — short phatic lines, often while
     walking or to someone who never speaks again → dropped, shown only as a grey "filtered" chip.
   - `ambient`: other people's conversations → `room_topic` only.
   - `stage`: an MC or speaker on a PA → event notes, not a person.
   - `noise`: music, video, glasses → dropped.
   Signals: turn-taking with Eric (answers him, is answered by him, says his name); closeness (louder, less
   reverb — leaning in to listen makes this stronger); a stable position near Eric; length and wording; badge
   motion (walking). Muse Spark makes the final call with structured output.
5. Extract: people, bindings, promises, preferred language, suspect words.
6. Second listener: Spark Open on flagged turns; disagreements become `listener_disagreement`.
7. Resolve: exact then fuzzy match to known people; ambiguous matches ask the owner, never merge silently.
8. Follow-through: drafts and invites for approval.

Raw API responses for rig recordings are cached by (input hash, parameters) for free, reproducible reruns and
golden tests.

### Storage

SQLite is the source of truth (people, aliases, bindings, bearings, promises, vocabulary, corrections,
follow-ups; FTS5 over turns). JSONL is the event log. JSON holds API caches and scene ground truth. YAML holds
scene scripts. Markdown is an exported recap. No RAG and no vector store: one person's history fits in Muse
Spark's context.

### Languages

Python 3.13 (uv, FastAPI) for server, pipeline, rig and harness. TypeScript, React and Vite for the web UI
(live dashboard, recap, `/record`, `/player` for rig devices). Swift: the iOS capture app (badge screen, spatial or
stereo audio, phone orientation; installed from Xcode, not the App Store). No Rust.

### Rig (demo and test bench)

- Scene YAML: personas, lines (fillers, pauses, restarts, a correction, code-switched lines), cue points for the
  owner, background groups, hall bed, incidental lines (a waiter, "excuse me"), an MC announcement.
- Kokoro voices plus L2 phoneme shaping (th-stopping, r variants, vowel length), tuned by ear until each accent
  sounds like a real speaker. Background groups use voices the foreground personas do not use. The hall bed is
  Kokoro babble.
- Controller on Mac-0: hall bed to the TV over HDMI (output device set explicitly), cues to browser players over
  WebSocket, presenter clicks captured globally, a logged sync mark.
- Memory is reset before every scored run and before the final take; the UI shows "memory: empty".

### Harness

Per-accent word error rate, names counted separately; speaker attribution with and without voice direction;
position error per person while Eric turns, leans in and walks; stereo vs spatial audio; lanyard vs clip; turn classification (no incidental line may reach a person card or a promise); promise recall including corrections; suspect-word precision; name accuracy with one
listener vs two, and before vs after memory. One scoreboard.

## Cut first if time runs out

1. Agentic follow-through beyond drafts (`.ics`, introductions).
2. Second listener (falls back to name-not-in-memory heuristics).

The core: live audio + head direction → people from introductions, with bearings → promise ledger with
corrections → misheard words with correction → follow-ups, on a noisy multi-accent recording, scored.

## Open items for the owner

- Meta Model API card, spend notification, API key. Credits form: submitted.
- Baseten form (Muse Spark Open, the only open-weight model we use).
- [FRIEND] for scene 1.
- Screen layout mock-up and a room photo.
