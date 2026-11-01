# Director's notes for the next script

These are Eric's decisions, collected while the features are being built (2026-10-29). The next rewrite of SCRIPT.md follows this file; where they disagree, this file wins.

## The film

- **Length and arc.** Three minutes with a full arc: setup, development, turn, resolution. It has a real opening and a real ending.
- **Pacing.** Alternate cold and hot: quiet rooms against the loud party, and silences inside the noise. A hook or a laugh lands at least every 15 to 20 seconds. Anyone who watches should want it at their next event.
- **Subject.** The film is about everything after the conversation, not about how well it listens. The listening gets only the time the payoffs need.
- **Visuals.** They must be the best we can make. Post-production is done in code, from the real event log and audio (`apps/film`). The X-ray mode lives in the replay page (`apps/replay`).
- **Blocking.** Eric moves in this order:
  1. He wakes on the bed in his friend's room and says something.
  2. He walks out of the room and says something.
  3. Group 1, the sofa: Margaux and Julien.
  4. Group 2, the table: Siddharth and Kenji.
  5. Back to his own room, ending on the sofa there.
- **The four parts.** What the market is missing, what we built, why now and why us still land, but lightly and mostly by showing them.

## The surprises, live wherever possible

1. **The French complaint, and the deck rebuilt mid-evening.**
   - Margaux and Julien complain to each other in French: twenty slides, not one number; she wants one page, with numbers.
   - As Eric passes the waiter, the phone on his chest buzzes. He opens it, and his deck is already one page with the numbers first.
2. **The Chloé link, live.**
   - The moment Margaux says her name, the phone buzzes: "She may be Chloé's colleague, from Blockchain Week, Oct 23."
   - Eric asks straight away: "Do you know Chloé?"
   - Eric called this one very important.
   - The exchange runs to the end, so the link leads somewhere. It sits after Julien's introduction; the take is dated Wed Oct 28, so Oct 23 is last Friday:
     - ERIC: "Margaux... do you know Chloé? Chloé Martin?"
     - MARGAUX: "Chloé? Of course! She's my colleague. How do you two know each other?"
     - ERIC: "We met at Blockchain Week, last Friday. She said you'd want to see what I'm building."
     - MARGAUX: "Small world. Then let's do a call next week, the three of us. With Chloé."
     - ERIC: "Perfect. I'll send an invite."
   - Payoff: the call becomes a promise, and the invite is drafted around his board call.
3. **Julien, unverified.** No public page ties him to Corvane: "confirm before you send the deck." Eric likes this one.
4. **Kenji's Japanese call, and the connector.**
   - Kenji's topic links to someone from an earlier week.
   - Hallwise proposes introducing them toward a concrete collaboration.
   - Back on his sofa, Eric sees the proposals and next week's event, where the right person will be.
5. **The old "introduction owed to Lena" beat is out** as a surprise. The connector replaces it.

## The aside: "I don't speak French"

Eric's idea, from 2026-10-29:
- During the French, the sound cuts to sudden silence.
- He turns to the camera, makes a whisper gesture and says: "I don't speak any French. Or Japanese. At all."
- Then the room's sound comes back.

Proposed refinements, pending Eric's choice. French and Japanese are two separate moments with separate payoffs; the order follows the walk:

1. **The sofa, the French (surprise 1).**
   - Silence, the whisper gesture: "I don't speak any French. At all."
   - Walking past the waiter, the phone buzzes: the deck is already one page.
   - To the camera: "...It does." Then the X-ray.
2. **The table, Kenji's Japanese call (surprise 4).**
   - A one-second callback: silence, a glance at the camera: "...Or Japanese."
   - Its payoff waits for the end: on his own sofa, the connector proposes the introduction and next week's event, both drawn from that call.
- **Put the X-ray right after the deck reveal.** Eric looks at the one-pager and wonders: how? The film rewinds into the X-ray (8 to 10 s) and shows the French complaint going through the machinery:
  1. the four channels;
  2. the voices around him;
  3. Voice Transcribe hearing French;
  4. the edge finder catching it;
  5. the check passing;
  6. Spark rebuilding the deck;
  7. the number check;
  8. the buzz.

  Then the room comes back.

How it is shot (Eric's call, 2026-10-29):
- **The footage.** Eric and [FRIEND] are filmed for real in the apartment, with the guests' voices played from the devices. Everything else is post-production in `apps/film`.
- **The silence is done in post.** The soundtrack drops to silence and only the whisper stays. Use the badge's recording run through the voice isolator, or a clean pickup of the line. No rig change.
- **During the silence.** [FRIEND] freezes, and Eric turns to the lens and whispers.
- **Crew.** A third person operates the gimbal, so [FRIEND] stays on camera. Eric confirmed one is available on 2026-10-29.
- **Slow outputs are made beforehand.** Nothing slow has to run live in the take. The real code makes them before the shoot from the rehearsal recording, and they are shown on cue: the rebuilt one-pager, the connector's proposals and next week's event. Only the instant things fire live: "met before" and the Chloé link, about a second after an introduction.
- **The X-ray.** It is a freeze-frame added in post.
- **The deck morph.** Done in post while Eric walks past the waiter. The real 7 slides (`demo/deck/render/slide-1.png` to `slide-7.png`) are pressed into the real one-pager (`demo/deck/render/onepager.png`). Both come from `demo/deck/hallwise-deck.html` and `hallwise-onepager.html`, in the Vexi deck's style.

Production notes for the aside:

- **Timing.** Eric never speaks over the French: the edge depends on the badge hearing it clearly. He delivers the aside in the gap after the exchange ends and before [FRIEND] introduces him. The edit makes it play as a stop in the middle of the conversation.
- **Sound.** In post, all sound drops to near silence on a hard cut and the whisper is the only sound. Then the party crashes back in.
- **On screen.** During the silence, the last French subtitle and its English stay on screen.
- **[FRIEND].** Freezes like a statue during the silence, for the laugh.
- **Backup.** Shoot a pickup of the aside on the same mark right after the take.
- **The badge hears the whisper.** It becomes Eric's own turn. That is harmless, but check that the morning drafts don't take anything from it.

## Open, being measured

- **Mono vs 4-channel runs.** Is the owner found from elevation? Do promises come out owed by or to the right person? Does direction separate Siddharth from Leo?
- **The radar and "your voice from above".** These visuals stay marked pending until the runs above settle them.
- **Transcription of the new lines.** Do the French exchange and Kenji's Japanese call come through in the room mix?
- **The rebuild's latency.** The buzz has to land 40 to 60 s after the French.
- **Why us.** "One-person company, engineer and salesman" is still [ERIC: confirm].
