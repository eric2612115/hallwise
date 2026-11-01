# Hallwise

The owner's pitch, one `##` per slide, in the order it is told. Every number has its source in a comment under it.
Hallwise rebuilds this deck for the person who will read it (server/hallwise/onepager.py, HALLWISE_DECK): only the
facts and numbers written here can reach that page.

## Hallwise

A name badge that remembers the room.

An iPhone worn on the chest, and Meta's models: everyone you met, what you promised them, and a follow-up in their
language, written by 8:00 the next morning.
<!-- The morning report is read at eight: demo/PITCH.md, "The next morning (08:00)"; server/hallwise/report.py builds it after the recording. -->

## Great conversation. Gone by morning.

- Names? Forgotten.
- Promises? Unsent.
- Half the faces, you have met before. You just can't remember where.

Networking doesn't fail in the room. It fails the next morning.

## What is missing

Today's tools learn who you are talking to from a calendar invite, a swapped card, or a voice you label by hand.
A mixer gives you none of those.

- Fireflies: speaker name detection "only works when Fireflies joins a video meeting, or you're using the Chrome
  extension."
- Granola on iPhone: "Speaker A, Speaker B".
- Plaud: "Speaker 1, 2" until you name them, for that one recording.
<!-- Plaud help center, Oct 2026 (demo/PITCH.md, part 1; demo/competitors/landscape.md). Fireflies and Granola help centers, read 2026-10-28. -->
- Microsoft Teams Rooms: people in the room must be "enrolled with their voice profile and be invited to the
  scheduled meeting".
<!-- Microsoft Teams Rooms docs, 2026-08-27 (demo/PITCH.md, part 1). -->

## The insight

The room already says who everyone is. People introduce themselves, say their company, and say what they will
send and when. The badge is already facing them. There is nothing to type, only something to listen for.

## The evening

- Names from the introduction: no invite, no card, no name tag.
- Promises as they are made, and as they change: "Thursday, no, Friday" keeps Friday.
- Met before: when someone from an earlier evening says their name, their card rings with where you met and what
  you owe each other.
- Several languages in one room: an aside in French, translated for you.

## The next morning

- A follow-up for every promise, ready to send, in the language each person spoke with you.
- The reason to write you had forgotten: an introduction still owed, a colleague who mentioned them.
- A check on who each new person is, against public sources; only real sources are kept.
- What is due today, and what is overdue.

## Built with Meta

| Model | Job in Hallwise |
| --- | --- |
| Muse Voice Transcribe | separates the voices, live, with known names and companies as hints |
| Muse Spark | people, promises, translations, follow-ups, reasons to write, the morning report; with web search, the check on each new person |
| Muse Spark Open on Baseten | reads the evening as it grows for what people want, so each follow-up can act on it |
| SAM 3.1 | finds the faces in one photo; Muse Spark says who is who |
<!-- The four models in the code: server/hallwise/asr.py (Muse Voice Transcribe), extract.py and research.py (Muse Spark), edge_finder.py (Muse Spark Open on Baseten), sam.py (SAM 3.1). -->

## Why now

- The biggest companies are buying memory you wear. Meta bought Limitless; its sales ended 2025-12-05. Amazon
  bought Bee in Jul 2025 and shipped two new devices in Oct 2026. Both remember the wearer's own day; everyone
  else stays in the background.
<!-- demo/PITCH.md, part 3; demo/competitors/landscape.md, "Meta" (Limitless: no new sales since 2025-12-05). -->
- The demand is on record: 410 Limitless users voted for a personal CRM. Still unbuilt when Meta bought the
  company.
<!-- Limitless feature board, last snapshot 2025-12-08 (demo/PITCH.md, part 3). -->
- Meta's models carry the hard part. Muse Voice Transcribe streams with speaker attribution for 20+ speakers and
  keyword biasing. Muse Spark has a 1M-token context, so it re-reads the whole evening on every turn.
<!-- Meta's model pages, read 2026-10-28 (demo/PITCH.md, part 3). -->

## The field

- 183 AI note-takers, in one category of one site. They learn who you are talking to from an invite, a card, or
  a voice you label.
<!-- Product Hunt category "AI meeting notetakers", accessed 2026-10-28 (demo/competitors/landscape.md). -->
- About 5-8 commercial products record a live room and keep a profile per person.
<!-- demo/competitors/landscape.md, "Are there 500 companies doing this?", 2026-10-28. -->
- The whole chain, from a name said in the room to a follow-up in that person's language, joined across
  evenings: no product we checked documents it, as of 2026-10-28.
<!-- demo/competitors/landscape.md, "What this changes in PITCH.md", point 2, 2026-10-28. -->
- The idea appeared at 6 or more hackathons in 2026, mostly on glasses and faces.
<!-- Devpost projects, 2026 (demo/competitors/landscape.md, "Hackathon prototypes"; demo/PITCH.md, Risks). -->

## What sets it apart, and what does not

- No glasses, and no face for naming.
- Names from the introduction. Others do this too: Limitless shipped it inside one conversation in Feb 2025, and
  Omi's open-source code does it on a paid plan. The difference is the chain, not a moat.
<!-- demo/competitors/landscape.md, "What this changes in PITCH.md", point 1; demo/PITCH.md, "Never say". -->
- Promises and follow-ups per person, in their own language.
- Memory across evenings. "Met before" is name-based, not a voiceprint: someone who never says their name is
  recognised only through the photo.

## The build, in numbers

- 4 Meta models in one live pipeline.
<!-- See "Built with Meta": asr.py, extract.py and research.py, edge_finder.py, sam.py. -->
- "Met before" rings about 1 s after the introduction in rehearsal, down from 17-24 s when it waited for Muse
  Spark.
<!-- Oct 27 rehearsals: demo/SCRIPT.md ("about a second after the introduction") and server/hallwise/recall.py ("17-24 s after he introduced himself, in rehearsal"). -->
- Names heard right: 24 of 25 synthetic voices across 13 accents, with name hints; 13 of 25 without.
<!-- Accent test, 2026-10-29: 25 synthetic voices through Muse Voice Transcribe as the server runs it, once without and once with name and company hints (scratchpad accent-test/out/asr_cast.json; with hints the one miss is Ruaridh MacGillivray, Scottish, heard as "Rudy McGillivray"). -->
- 240 server tests, all passing. 68 commits.
<!-- pytest -q in server/ (240 passed) and git log in the repo (68 commits), 2026-10-29; update both before sending. -->
- One person, nine days: Oct 26 to Nov 4, 2026.
<!-- README.md ("Oct 26 – Nov 4, 2026"); demo/PITCH.md, part 4. -->

## Why us, and where it stands

- I'm the user: the person at the mixer who forgot a name by morning.
- One person built the whole chain: the badge app, the server, the Meta models, and a replay page for judges
  with only a laptop.
- 0 users. A working prototype, rehearsed with synthetic guests.
<!-- demo/PITCH.md, part 4: "No users yet. ... The rehearsal guests are synthetic." -->
