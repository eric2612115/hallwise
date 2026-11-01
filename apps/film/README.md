# Hallwise film

The post-production pipeline for the demo film: data-driven [Remotion](https://remotion.dev) compositions that draw
the X-ray freeze, the notification pops on the badge, the subtitle cards, the deck morph, the check strike-outs, the
connector reveal and the end card over footage. Every number, name and label on screen comes from a recording's
`events.jsonl`, its xray sidecar, the accent test, a saved one-pager or the research cache, never from a component;
`tools/extract_data.py` gathers them into one JSON that the compositions take as a prop.

Visual language: the "paper" spec (paper ground for what the owner sees, dark frame for the frozen footage, Newsreader
/ Instrument Sans / IBM Plex Mono, the app's palette from `ios/Sources/Theme.swift`), with the hud grafts (envelopes
coloured by the live speaker, particles, the win400 lanes, the two-ring buzz) and the blueprint grafts (the app's own
notification strings, verbatim event rows as receipts, the ochre PENDING stamp, no degrees anywhere).

## Pinned

- remotion, @remotion/cli, @remotion/media, @remotion/captions, @remotion/google-fonts: **4.0.535**
- react / react-dom 19.1.1, typescript 5.8.3
- Node 24 (`engines`, `.nvmrc`), ffmpeg 9 (Homebrew; only for `tools/prep_audio.sh` and `tools/frames.sh`)
- Python: the server's own venv (`server/.venv`) for `tools/extract_data.py`, which imports `hallwise.onepager`,
  `hallwise.direction`, `hallwise.leveler` and `hallwise.recording` read-only.

Remotion's licence is free for an individual, personal or commercial use (remotion.dev/docs/license/faq).

## Setup

```sh
cd apps/film
npm install
```

`node_modules/`, `out/`, `public/footage/` and `public/audio/` stay out of git.

## Data in

```sh
# 1. the JSON every composition reads: the FOA rehearsal 3f3e, its xray sidecar (server/scripts/export_xray.py,
#    in apps/replay/data), run 51b4 and the small inputs in fixtures/ (every default is relative to the repo)
PYTHONDONTWRITEBYTECODE=1 ../../server/.venv/bin/python -B tools/extract_data.py

# 2. the badge audio, cut and decoded to stereo (FOA W/Y → two virtual cardioids, -18 LUFS)
SRC=../../server/data/recordings/20261027-064036-3f3e/audio.wav
tools/prep_audio.sh $SRC 52.0 10.0 public/audio/aside_52-62.wav screen
tools/prep_audio.sh $SRC 83.0  9.0 public/audio/onepage_83-92.wav screen
tools/prep_audio.sh $SRC 121.5 8.0 public/audio/kenji_121-129.wav screen
tools/prep_audio.sh $SRC 44.0 56.0 public/audio/bed_44-100.wav screen -18
```

`extract_data.py` is read-only on `server/data`, the sidecar and `fixtures/`. For another recording, export its
sidecar first (`uv run python scripts/export_xray.py <rec dir>` in `server/`), then
`tools/extract_data.py --rec <rec dir> --xray <sidecar> [--run <mono run dir>] --out <json>` and pass the JSON with
`--props`. The iPhone takes use the "camera" frame: pass `camera` as the fifth argument of `prep_audio.sh` so left and
right are not swapped (direction.py `FRAME_ROTATION`). `fixtures/README.md` says where each small input came from.

What the tool derives rather than copies: the cast (names by speaker label, colours in order of first appearance,
the owner from the owner event) for every recording it touches; the names a frame may show at a time t (person
events logged by then); the notice's name through `onepager.find_person`, the way a cued page lands on a run's
person; the app's own strings by line from `ios/Sources` and `report.py`; the meetup's date from its corpus page;
the finder check's kept and dropped edges from `finder_check.py`'s printout.

## Compositions (`src/Root.tsx`)

| id | what | source of every value |
|---|---|---|
| `Proof` | 39.5 s, 1920x1080, 30 fps: aside subtitles → hook pop → X-ray freeze → deck morph → check → connector → end card, over the rehearsal's audio | `public/data/proof.json` + `public/audio/*.wav` |
| `XRay` / `XRayOverlay` / `XRayFallback` | the 12-beat freeze (0.85 s per beat); Overlay draws on transparency; Fallback drops beats 04 and 05 while the FOA comparison is PENDING | events.jsonl, xray sidecar, asr_cast.json, the one-pager JSON, research cache |
| `BuzzBoth` / `BuzzDeck` / `BuzzHook` | the phone on the chest, LISTENING; the rebuilt notice with the two-ring buzz, or the hook as the room page shows it (tag + hook row, no buzz); the right side says what fired it | `RebuiltNotice.swift` strings composed from the cued `rebuilt` event, `LivePages.swift` layout, the 51b4 hook event |
| `SubtitlesFR` / `SubtitlesJA` | one lower-third card at a time: the words in serif italic, the English under them, the turn_kind tag | turns + translations as logged |
| `DeckMorph` | 12 slides fold into the one page; figures count up; "← slide N" per figure; REBUILT IN 3.77 s | `onepager.numbers` over `hallwise-deck.md` |
| `CheckStrike` | the edge finder's dropped and kept edges as the server's check judged them, the withdrawn confirmation of the retired comparison, the model's own promise correction; verbatim event rows | `fixtures/aside/finder-check-c*.txt`, run 51b4 events, 3f3e promise |
| `Connector` | the week line, Kenji (recall.py, no model), the owed introduction (hooks.py), the proposal, where they could meet | run 51b4 events, people index evenings, the corpus |
| `Voices` | soft wedges, particles from the live region to the badge, the win400 lanes, the side view; both PENDING | xray sidecar (`direction.py` recomputed) |
| `EndCard` | badge glyph, wordmark, the deck's first line, the pipeline row, BUILT WITH chips, AGPL-3.0 | `hallwise-deck.md` slide 1, SCRIPT.md |

Props: every composition takes `{data: ProofData}` (`src/lib/types.ts`); `Proof`'s shot list is `SHOTS` in
`src/Proof.tsx`; `XRay` takes `freezeMs`, `beatSeconds`, `transparent`, `beats`; `Subtitles` takes the turns and the
recording time at frame 0; `Room` (the stand-in footage) takes `startMs`, `frozen` and `holdFrom`.

## Render

```sh
npm run studio                                         # preview, scrub every composition
npx remotion render src/index.ts Proof out/proof.mp4   # H.264, ~50 s on an M1 for 1185 frames
npx remotion still  src/index.ts XRay out/xray.png --frame=330

# a transparent overlay for compositing over real footage in ffmpeg (ProRes 4444, keeps alpha)
npx remotion render src/index.ts XRayOverlay out/xray_overlay.mov \
  --image-format=png --codec=prores --prores-profile=4444 --pixel-format=yuva444p10le

# one PNG per "<composition> <frame> <name>" line, into out/qa, to look at a composition at a given frame
printf 'XRay 330 xray_330\nCheckStrike 149 check_149\n' | tools/stills.sh

# one frame per second, to look at a cut
tools/frames.sh out/proof.mp4 out/frames 1
ffmpeg -i out/proof.mp4 -vf "fps=1,scale=480:270,tile=4x10" -frames:v 1 out/contact.png
```

Compositing an overlay over a frozen frame of real footage, per the post-production plan:

```sh
ffmpeg -ss 91.26 -i camera.mov -frames:v 1 still.png
ffmpeg -loop 1 -t 12 -i still.png -i out/xray_overlay.mov \
  -filter_complex "[0:v]eq=saturation=0.25:brightness=-0.08,gblur=sigma=6[bg];[bg][1:v]overlay=shortest=1" \
  -c:v libx264 -pix_fmt yuv420p xray_over_footage.mp4
```

## Honesty rules the code keeps

- Every frame is a function of t: the X-ray's regions use only turns that had ended by the freeze, and a voice is
  named only once a person event had named it (else "a voice"); `extract_data.py` and `XRay.tsx` both check that no
  region's first turn is after the freeze.
- The X-ray is stamped as a composite: the 4-channel rehearsal frozen at 91.3 s, plus run 51b4 on its own clock,
  the aside take and a saved page; every card's receipt names its source, and no receipt is cut with an ellipsis.
- One name per film, from one source: the run's person event ("Margot Lefebvre" on 51b4), reached for the notice
  through `onepager.find_person` + `rebuilt_event` as a cued page would; the headline and subline are composed as
  `RebuiltNotice.swift` composes them, cited by line. On 3f3e the log says "Margot Lefèvre" and "Julian".
- A hook is drawn the way the app draws it (a tag under the name, a hook row); the app has no hook notification.
- Direction is words only (left / ahead / right), soft wedges, "?" for low confidence; the radar and the from-above
  view wear PENDING until the FOA comparison lands; `XRayFallback` is the cut without them (re-flowed, renumbered).
  On 3f3e the owner event has no `source`: Muse Spark found the owner from the transcript, and the Wearer medians
  are a re-run offline on a mix that places the owner high; the cards say both.
- A strike is drawn only where a logged verdict exists: the edge finder's edge that `take_edges -> kept_edges`
  dropped during the finder check (`fixtures/aside/finder-check-c.txt`), the retired comparison's
  `disagreement -> confirmed_removed` (labelled retired), and Muse Spark's own `promise.replaces` (labelled as the
  model's field, not a code check). `edge_removed` is never drawn as a rejection.
- The research card uses the app's partial wording ("company found, no public profile for them", report.py:98 /
  MorningReport.swift:427); SCRIPT.md's "confirm before sending the deck" is not an app string and is not shown.
- No haptic pattern, no Muse Spark token counts (not logged), no SAM photo (none this evening), no measured degrees.
- `public/data/proof.json` carries only repo-relative paths and recording ids.

## Not verified

- The stand-in footage is a generated dark room; no camera footage exists yet. `<OffthreadVideo>` is the one to use
  for real clips (`@remotion/media <Video>` letterboxed portrait clips in the proof).
- Audio: the rehearsal windows were listened to by level only (`loudnorm` to -18 LUFS); the left/right decode of an
  iPhone take ("camera" frame) needs a check by ear.
- Fonts still come from Google at render time (`@remotion/google-fonts`); vendoring the woff2 files into
  `public/fonts` and loading them with `@remotion/fonts` is a separate download step.
- The aside take's own `events.jsonl` was not kept, so `kept_edges` is not re-run here; the finder check's printed
  verdicts are shown and stamped as such.
- `Voices` and the X-ray beats 04/05 draw the regions `direction.py` recomputes today; the FOA comparison is running.
