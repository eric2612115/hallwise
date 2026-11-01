# Hallwise pitch spine

The video and the written submission answer four questions, in this order:

1. What the market is missing.
2. What we built.
3. Why now.
4. Why us.

They map onto the theme, "Build for Your World":

- **"Make something possible that wasn't before"** is the gap and why now.
- **"Free up time and mental space"** is what we built.
- **"Solve a problem you know firsthand"** is why us.

The video (SCRIPT.md) is told as a drama, not a pitch. It opens on a debt: at 8:00, Lena asks about an introduction to someone called Kenji, and Eric has no idea who Kenji is. It closes on the same 8:00 buzz, when the introduction is already written. The gap gets a face before it gets a source. Its order and timings:

| Time | Part |
|---|---|
| 0:00–0:22 | The pain: the cold open at 8:00, then the glasses |
| 0:22–0:36 | What's missing: the wall of "Speaker 2" |
| 0:36–2:31 | What we built: the badge, the evening, the morning |
| 2:31–2:43 | Why now, spoken over the week's map |
| 2:43–3:00 | Why us and the close |

The written submission and the README carry the full tables below. The video never shows a transcript page.

Every competitor line is dated and in the vendor's own words. Sources are in `competitors/landscape.md` and `competitors/landscape/`; re-check every row the week of the submission.

## 0. The pain (0:00–0:22)

Great conversation. Gone by morning.

In the video:

- The cold open: 8:00, a text from Lena, "Did you ever send that intro to Kenji?" Eric: "...Kenji?" Then the
  line on black: "Networking doesn't fail in the room. It fails the next morning."
- Eric in his glasses, a silent room, then the room's real sound.
- "My glasses hear whoever I'm facing. But at a mixer, the person talking to me is usually beside me. And I can't point a camera at everyone." The glasses go in his pocket, never thrown.
- "Accents. Asides. Asks. Promises."
- "And half of them, I've met before. I just can't remember where."

In writing, three lines in the Vexi cadence:

- Names? Forgotten.
- Promises? Unsent.
- Follow-ups? Written before you woke up.

## 1. What the market is missing (0:22–0:36)

**Not another note-taker.**

The gap in one sentence: today's tools learn who you're talking to from a calendar invite, a swapped card, or a voice you label by hand, and a mixer gives you none of those.

In the video, the wall of "Speaker 2": real labels from dated vendor pages stack up over a stranger's face until they cover the frame, then silence. Spoken, about 8 seconds:

> There are 183 AI note-takers. I don't need another one. … I need to remember who Kenji is.

Eric never says what they can't do; the wall shows only what the vendors write themselves. Its sources, brands only here:

- 183 AI note-takers. (Product Hunt category, 2026-10-28)
- "Speaker 1, 2" until you name them, for that one recording. (Plaud help center, Oct 2026)
- "Speaker A, Speaker B" on iPhone. (Granola help center, read 2026-10-28)
- "Speaker name detection only works when Fireflies joins a video meeting, or you're using the Chrome extension." (Fireflies help center, read 2026-10-28)
- People in the room must be "enrolled with their voice profile and be invited to the scheduled meeting". (Microsoft Teams Rooms docs, 2026-08-27)

In writing, the same gap in plain words: Product Hunt lists 183 AI note-takers; they learn who you're talking to from a calendar invite, a card, or a voice you label by hand; at a mixer there's no invite and no time.

The full gap, for the written submission:

| What is missing | Who documents it |
|---|---|
| Names that don't need a calendar invite | The vendors state the limit: Fireflies (above); Circleback, voice ID "only available for meetings associated with a calendar event" (2024-11-20); Granola's People directory holds only calendar attendees; Fellow never names external attendees; Teams Rooms (above) |
| Recognising someone later without labelling them by hand | Limitless: 20 seconds of voice (2025). Fieldy: tag a voice five times (beta). Plaud: "Speaker 1/2" until you name them, for that one recording (Oct 2026) |
| Several languages in one recording | Otter says no. Plaud says mixed languages are not supported (Oct 2026). Granola mobile asks for one language. Only Omi documents a mixed mode. |
| A check on who someone is, starting from their voice | Granola starts from the attendee's email; Blinq from the card swap. No product we checked documents a check on someone known only from what they said (2026-10-28). |
| Reasons to write that join several evenings, and a follow-up in each person's own language | No product we checked documents either (2026-10-28) |
| The whole chain | Only hackathon prototypes, mostly on glasses and faces, with no users |

Never say:

- **"First" or "only" at naming people from their introduction.** Others do it:
  - Limitless shipped it inside one conversation (Feb 2025).
  - Omi's open-source code does it on a paid plan.
  - Blinq and Jamie use names said in the room.
  - Compass suggests names.
- **"They don't draft follow-ups" or "they don't track promises."** Bee and Limitless do both, for the wearer.
- **"Nobody does X."** Say "no product we checked documents X, as of <date>".
- **"Plaud only transcribes."** Its October 2026 agent drafts and sends email.
- **Anything about Ambi.** The facts are too thin.

"Note-takers" is said once, here, to put the category behind us. Everywhere else the rule holds: never say notes, transcript, summary or meeting.

## 2. What we built (0:36–2:31)

**The insight.** The room already says who everyone is. People introduce themselves, say their company, and say what they will send and when. The badge is already facing them. There is nothing to type, only something to listen for. In the video this is "I don't type a thing."

**One line.** **Hallwise.** A name badge that remembers the room. An iPhone worn on the chest, and Meta's models.

**How it works** (the evening and the next morning):

| Beat | What the viewer sees | Meta model |
| --- | --- | --- |
| Leo gives his name at the door; Eric promises the deck tonight | Leo's name and company; the deck, due tonight | Voice Transcribe hears him through the accent, with known names as hints; Spark binds the name and the promise |
| Two investors talk among themselves; Margaux says "une page, avec des chiffres" to herself | Grey dots, the aside translated | Voice Transcribe separates the voices; Spark translates |
| Eric is introduced; the dots get names | "Margaux Lefèvre", "Julien Caron", "Chloé's colleague", no name tags | Spark binds names and companies from the introduction and links Margaux to Chloé |
| Eric can't place Kenji; Kenji gives his own name | His card rings: met before, Hardware meetup, "you owe Lena an intro". Eric never sees it | The people index across evenings; Spark finds the hook |
| Coffee moves from Thursday to Friday | The promise corrects itself | Spark re-reads the whole conversation every turn |
| The next morning (08:00) | The report: Margaux's follow-up in French quoting her aside; the introduction Eric forgot, to Kenji and Lena; Julien's time checked; checks run | Spark drafts in each person's language; Spark with web search checks people; Spark Open on Baseten re-hears and confirms |
| The week's map | Who I know, how we met, what's still open | The people index across evenings |

**Each gap, closed** (written):

| What is missing | What Hallwise does | Where the video proves it |
| --- | --- | --- |
| Names without an invite or a card | Names from the introduction, kept across evenings | The grey dots become Margaux and Julien |
| Recognising someone later without labelling | "Met before", and what you owe each other | Kenji's ring: "you owe Lena an intro · Oct 20" |
| Several languages in one room | An aside in French, a follow-up in French | "Une page, avec des chiffres", then her draft in French |
| A check from the voice alone | Spark with web search checks each new person and keeps only real sources | Julien flagged: no page ties him to Corvane |
| Reasons to write, across evenings | The follow-up writes itself, with the reason you'd forgotten | The introduction to Kenji and Lena, sent |

Plus one thing no product we checked documents: a second model re-hears the evening and flags names the two disagree on.

**Built with Meta** (card or README):

| Model | Job in Hallwise |
| --- | --- |
| Muse Voice Transcribe | separates the voices, live, with known names and companies as hints |
| Muse Spark | people, promises, translations, drafts, hooks, the morning report, Ask |
| Muse Spark with web search | checks each new person against public sources, keeps only real ones |
| SAM 3.1 | finds the faces in one photo; Spark says who is who |
| Muse Spark Open on Baseten | the second listener: re-hears the transcript, confirms or disagrees |
| Muse Image | the fictional guests' portraits in the rehearsal |

## 3. Why now (2:31–2:43, over the week's map)

- **The big companies are buying memory you wear.**
  - Meta bought Limitless; its sales ended 2025-12-05.
  - Amazon bought Bee (Jul 2025) and shipped two new devices (Oct 2026).
  - Both remember the wearer's own day; everyone else stays in the background.
- **The demand is on record.** 410 Limitless users voted for a personal CRM. It was still unbuilt when Meta bought the company (feature board, 2025-12-08).
- **Meta's models carry the hard part.** On Meta's own model pages (read 2026-10-28):
  - Muse Voice Transcribe streams with "speaker attribution for 20+ speakers" and keyword biasing; Hallwise feeds it the names it already knows.
  - Muse Spark has a 1M-token context, so it re-reads the whole evening on every turn.
  - Search grounding gives it the live web.
  - The pages give no release dates, so never say "just released" or "for the first time".

Spoken, about 12 seconds, over the map:

> Last year, the biggest companies bought wearables that remember your day. Four hundred and ten people asked one of them to remember people. Then it was sold. Still unbuilt.

Say "still unbuilt" (true at the board's last snapshot, 2025-12-08), never "never built". The models' part of why now lives in writing and in the model captions during the evening.

The card: "Meta bought Limitless (Dec 2025) · Amazon bought Bee (Jul 2025) · 410 Limitless users asked for a personal CRM; still unbuilt (2025-12-08)".

Written only: the idea showed up at six or more hackathons in 2026, mostly on glasses (see Risks).

## 4. Why us (2:43–3:00)

The theme asks for "a problem you know firsthand".

- **I'm the user.** [ERIC: confirm before the shoot. Proposed: a one-person company in Taipei; the evenings of the rehearsal week (ETH Taipei afterparty, Blockchain Week side event, hardware meetup, founder dinner) are the kind of room I'm in every week; English in everyone's own accent, asides in their own language.]
- **I built the whole chain.**
  - One person, nine days.
  - Four Meta models in one live pipeline, and a second model that checks the first.
  - A replay page for judges with only a laptop.
  - 68 commits and 218 server tests on Oct 28. Update the counts at submission.
- **No users yet.** Never imply traction. The rehearsal guests are synthetic, and the video says so on screen.

Spoken, about 17 seconds, then the close:

> Why me? I'm a one-person company. I'm the engineer, the salesman, and the guy who forgot Kenji's name. One person. Nine days. Four Meta models. A one-person company's CEO can't also be the one who remembers. … Hallwise can.

[ERIC: confirm "one-person company" and "salesman" are true for you.]

On "one person, nine days, four Meta models": two seconds of the repo, the test run and the model list. The rules ask the video to show "the specific features, code, and functionality you built".

Then the badge on the chest, the lit doorway, the name.

## Risks (written submission and Q&A)

- **The judges may have seen the idea.** It appeared at six or more hackathons in 2026, Rete and Cue in October. Hallwise is different on four counts:
  - No glasses, and no face for naming.
  - Names from the introduction.
  - Promises and follow-ups per person, in their own language.
  - Memory across evenings.
- **Omi has introduction naming in its open-source code.** The difference is the chain, not a moat.
- **"Met before" is name-based, not a voiceprint** (`server/hallwise/recall.py`). Someone who never says their name is recognised only through the photo.

## Rules kept

- Never say notes, transcript, summary or meeting. The exceptions are in part 1: "note-takers", said once, and the vendors' own quotes on the wall.
- Name categories out loud; brands appear only on the cards. The judges are Meta, and Limitless is theirs now.
- Never mention microphones or direction in the video or the written submission. On the chest, left and right are only rough, and front and back not at all.
- Time limits:
  - The pain and the gap together: under 40 seconds.
  - Why now and why us together: under 30 seconds, mostly over product shots; a talking head alone holds a few seconds at most.
  - The evening and the morning carry the rest.
- Leave Meta's NameTag out of the video and the writing. It is a face feature, and Hallwise names people from what they say.
