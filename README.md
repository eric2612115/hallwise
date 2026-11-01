# Hallwise

**Hallwise turns a loud networking event into everyone you met, what you promised them, and a follow-up in their
language — live, from the phone you wear as your badge, with no voiceprints or faces.**

You meet thirty people at an event and forget half of them by morning. Note-takers give you "Speaker 1,
Speaker 2" and fall apart in a loud room. Hallwise names people from how they introduce themselves, hears where
each voice comes from, and a second Meta model double-checks every name.

Built for the Meta Global AI Developer Hackathon (Indie Developer track, "Build for Your World").

## How it works

- **One device.** An iPhone worn as your badge: its microphones capture spatial audio (where each voice comes
  from), its gyroscope keeps every person's position fixed in the room while you turn or lean in to listen.
- **Meta Voice Transcribe** transcribes live and separates speakers, primed with names and words from your
  memory.
- **Muse Spark** works out who is who from introductions, tracks promises (including "Thursday — no, Friday"),
  flags words that look misheard for one-tap correction (corrections become recognition hints for next time),
  filters "thanks" and "excuse me", and drafts follow-ups in the language each person spoke with you.
- **Muse Spark Open** is the edge finder: it reads the conversation as it grows for what people say not to you (an
  aside to themselves, a word to a colleague, in any language) that shows what they want, and the follow-up acts on
  it without ever quoting it.

## Repository

```
apps/web/        web UI: live dashboard, recap, judge demo
server/          FastAPI: audio ingest, event log, SQLite
pipeline/        transcribe, positions, classify, extract, edge finder, follow-ups
ios/             badge capture app (Swift)
rig/             living-room test bench: scenes, voices, players
harness/         scoring against scene ground truth
tools/probe-ios/ microphone capability probe
docs/            plan and architecture
demo/            demo script
```

Work in progress during the hackathon (Oct 26 – Nov 4, 2026).

## License

AGPL-3.0. See [LICENSE](LICENSE).
