# Submission draft

The Cerebral Valley submission form (seen 2026-10-27). Required fields marked *. Fill the bracketed parts from
the final take and the harness; keep every number real.

Deadline: Wed 2026-11-04 9:00 PM ET (Thu 2026-11-05 10:00 Taipei). Before submitting: make the GitHub repo
public, check the video link opens in a private window, check the live URL works without a login.

| Field | Answer |
|---|---|
| Team Name* | Hallwise |
| Team Members | Eric Fang and PeakSan958457 — both are the owner's own accounts; solo entry |
| Track* | Indie Developer |
| Problem statement* | Build for Your World |
| Most Viral Track (X post link) | optional; only if we post the demo on X |
| Project Description* | see below |
| Public GitHub Repository* | https://github.com/eric2612115/hallwise |
| 3-Minute Demo Video* | [YouTube link, public, under 3:00] |
| Use of Meta products* | see below |
| Why Meta's models matter* | see below |
| Feedback on Meta products | see below |
| Feedback on partner technologies | Baseten, if credits arrive |
| Consent | Meta and Cerebral Valley may use, publish and promote the submitted materials |

## Project Description

Hallwise turns a loud networking event into everyone you met, what you promised them, and a follow-up in their
language — live, from the phone you wear as your badge, with no voiceprints or faces.

You meet thirty people at an event and forget half of them by morning. Note-takers give you "Speaker 1,
Speaker 2" and fall apart in a loud room. Hallwise names people from how they introduce themselves ("I'm Sarah
from Acme"), hears where each voice comes from with the phone's spatial-audio microphones, keeps every person's
position fixed in the room while you turn or lean in to listen, tracks promises including corrections
("Thursday — no, Friday"), filters "thanks" and "excuse me", and drafts a follow-up for each person in the
language they asked for. Words that look misheard are surfaced for one-tap correction, and corrections become
recognition hints next time.

One take in a living room standing in for a conference hall — five people, four accents, crowd noise:
[N/5 people named, N/N promises caught, names A% → B% after one correction]. Numbers from the harness run on the
final take.

Live product: [URL] (sample recordings preloaded; record in the browser).

## Use of Meta products

- **Muse Voice Transcribe** (realtime WebSocket, DIARIZATION): live turns with speaker labels in a noisy room,
  25-language code-switching (French and Japanese lines in the demo), and keyword biasing fed from the user's own
  corrections — the memory loop.
- **Muse Spark 1.3** (structured output, JSON schema): runs on every new turn over the transcript so far and
  returns the whole picture — who is who from introductions, label → person bindings with evidence, promises with
  corrections, each person's preferred language, which turns are conversation / incidental / ambient / stage,
  misheard-looking words, room topics. The app shows only what changed between runs.
- **Muse Spark Open** (open weights, on Baseten): a second listener. For every turn with a name or a suspect
  word it re-hears the audio with the candidate names; where the two Meta models disagree the word is flagged.
  [Only if credits arrive; otherwise say so and describe the fallback.]

## Why Meta's models are important

Diarization that survives a cocktail party, code-switching inside one sentence, keyword biasing without
fine-tuning, and a reasoning model with schema-constrained output that can be asked the same question every ten
seconds cheaply. Three models, one API, one bill. [Add the measured numbers: per-accent WER with and without
hints, name accuracy with one vs two listeners.]

## Feedback on Meta products

[Honest notes from the build: what was easy, what we worked around. Candidates: no confidence scores on
transcription; session-scoped speaker labels; FOA capture needs iOS 26 hardware; what we wished for.]

## Notes from the kickoff (Oct 26)

- The demo video is what judges watch first; the repo must be public.
- The Most Viral prize counts X engagement through Nov 8; we don't buy engagement — post once, honestly, or skip.
