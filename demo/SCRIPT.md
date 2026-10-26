# Hallwise demo — a week on one map, then one night, about 2:50

Three minutes is the limit and the first round watches fast. The video opens on sound, then on the week's map,
then shows one night happening, then what the badge did with it. The party is one continuous camera take
through the living room; the opening and the closing are shot in the two bedrooms on either side of it.

The room is real: computers play the other guests' voices from where they would stand, Eric talks live, and
Hallwise gets one device, the badge on Eric's chest. Everything on the panels is written by the models during
the take; nothing is typed. The other four evenings on the map were rehearsed the same way earlier in the week.

## Shape

| Time | Beat | What the viewer gets |
|---|---|---|
| 0:00–0:08 | Silence, then the room | "Networking never sounds like this. It sounds like this." The crowd comes in. |
| 0:08–0:25 | The week on one map | Five evenings, sixteen people, one map. "I typed nothing." Four lines on what the badge does. |
| 0:25–0:40 | The door | Start, the badge on the chest, a side-button press: still a name card. A friend, the first promise. |
| 0:40–1:35 | The sofa | Two French investors talking among themselves; an introduction; English; two grey dots become two names. A one-pager and a Wednesday demo. |
| 1:35–2:00 | The window | Kenji introduces himself and the badge remembers him first: "met before · ETH Taipei afterparty · the coffee you never did". Thursday → Friday, a Japanese murmur. |
| 2:00–2:15 | Stop | The drafts land: Margaux's in French; Julien's invite dodges Wednesday's 2 pm; Kenji's mentions the coffee from last week. |
| 2:15–2:35 | The bedroom | "What did I promise tonight?", spoken. The answer. The bell: "Deck for Kevin due tonight." One word fixed. |
| 2:35–2:50 | One night, one week | Tonight's path on the map, then the week. "When you're the whole company, you can't also be the one who remembers. Hallwise is." |
| 2:50–2:56 | End card | Models used, open source. |

## Frame

- Left 60%: the camera.
- Right 40%: the app's **Room page**, screen-recorded from the iPhone 16 following the live recording (follow
  mode): the radar (ahead = up, each person a coloured dot where their voice comes from, lit while they talk, a
  ring when the badge has met them before) and the strip of who Eric has met. For Stop, the bedroom and the
  map, the second phone switches to Ask, the bell and Map.
- Inserts from the dashboard on Mac-0 (screen-recorded) for lines that need reading: the French chat with its
  English under it marked *translated*, Margaux's aside, Kenji's murmur, the Words list.
- The panels read only the server's event stream, never the rig's scene files.
- Fallback if live capture fails during the take: process the badge recording afterwards and caption the
  panels "Hallwise's output for this recording, replayed at the moment each thing was said".

## On-screen text

- 0:00: "🎧 Headphones on."
- Under the map: "Everyone except my friend and me is AI-generated. Voices: Kokoro. The other evenings were
  rehearsals run through the same pipeline."
- End card: "Built with Muse Voice Transcribe · Muse Spark · Muse Spark Open. Open source, AGPL-3.0."

Personas and companies are fictional. [FRIEND] and [FRIEND_CO] are a real friend's name and company.

## Cast

| Person | Where | Device | Voice |
|---|---|---|---|
| [FRIEND], [FRIEND_CO], wallets | Door (A) | live | their own |
| Siddharth Raghunathan, Quillmesh, warehouse robots | Sofa, left (B1) | Mac-1 | `hm_omega`, Indian English shaping |
| Margaux Lefèvre, Corvane Capital, pre-seed | Sofa, middle (B2) | Mac-2 | `ff_siwis` (French and English) |
| Julien Caron, Corvane Capital, diligence | Sofa, middle-right (B2′) | Mac-2 second output, or Mac-3 | `ff_siwis` pitched down 4 semitones for French; `am_michael` with French shaping for English |
| Wei Ling, Pandan Pay, hawker-stall payments | Sofa, right (B3) | Mac-3 | `zf_xiaoyi` |
| Kenji Watanabe, Hoshizora Robotics (met Oct 20 and Oct 22) | Window (C) | iPhone 16 (iPhone-K) | `jm_kumo` |
| Waiter, MC, hall bed | TV | Mac-0 over HDMI | voices the cast doesn't use |

Julien and Margaux sit together, so their two voices come from nearly the same spot; the radar spreads them
apart, diarization tells them apart by voice. Rehearse this pair first (see Risks).

The week already on the server before the take (rehearsed recordings, dated): ETH Taipei afterparty (Oct 20:
Siddharth, Lena, Kenji, Tomás), Hardware meetup (Oct 22: Kenji, Hana, Priya, Daniel), Blockchain Week side event
(Oct 23: Siddharth, Tomás, Chloé, Yuki, Ahmed), Founder dinner (Oct 24: Lena, Sofia, Daniel, Ben). Kenji is the
one the badge will recognise tonight; at the afterparty he and Eric agreed to "the coffee we never did".

## Room

| Spot | What is there |
|---|---|
| Friend's room | Where the take starts: Eric steps out of it into the living room. |
| Door (A) | [FRIEND]. |
| Sofa (B) | Mac-1, Mac-2, Mac-3 in a half circle about 1 m from Eric's mark. |
| Window (C) | iPhone-K at head height. |
| TV | Mac-0: hall bed over HDMI, muted until the cue; also the Hallwise server, the dashboard (screen-recorded), the rig controller; the presenter is paired to it. |
| Eric's room | Where the closing is shot: desk lamp, the phone in hand. |
| Eric | iPhone 17 Pro worn as a badge on a magnetic lanyard mount (portrait, screen out, nothing covering the microphones), showing "Eric · Hallwise" on the paper card. Presenter in hand. |
| Follow phone | iPhone 16 in follow mode on a small stand by the TV, screen-recorded for the right panel. |
| Camera | A friend's iPhone 18 Pro on a gimbal, following Eric from the first door to the last. The operator stays silent. Its audio is only a sync reference. |

## Sound

- The soundtrack is the badge's own recording (iPhone 17 Pro): exactly what Hallwise heard, Eric's voice
  included. The app keeps the full multichannel file on the phone while it streams. The opening silence and
  the bedroom are the camera's audio, so the cut from silence to crowd is clean.
- In post, the camera's scratch audio and the clap line the badge recording up with the picture. The four
  channels are decoded to headphone stereo; no on-camera mention of it.
- Background, all Kokoro: the hall bed on the TV from the cue to Stop; group X (Mac-1/2/3) during the door
  scene; group Y (iPhone-K) during the door and sofa scenes; group Z (Mac-1/2/3) during the window scene. The
  background groups feed the room topics. A waiter's line and an optional MC announcement also come from the TV.
- `[click]` is where Eric presses the presenter to cue the next synthetic lines. The first click unmutes the TV.

---

## Opening (0:00–0:25), the friend's room door, then the hallway

Silence. Eric in the doorway of the friend's room, to camera. Caption: 🎧 Headphones on.

ERIC: Networking events never sound like this. [click] They sound like this.

The hall bed comes in on the TV, hard. Eric lets it run for two seconds.

ERIC: Twenty people a night, half of them you've met before, and by morning you can't remember who promised
what.

He lifts the phone into frame: the Map tab, All. Five event chips, sixteen dots, Kenji ringed in the middle.

ERIC: This is my week. Five evenings, sixteen people, one map. I typed nothing.

ERIC (walking toward the living room): Hallwise is a name badge that listens. It hears who's talking from
where their voice comes from. It names them from how they introduce themselves. It catches what you promised.
And it writes the follow-up in their language before you've left the room. Put your headphones on and come
with me.

## The door (0:25–0:40), door (A)

Eric taps Start; the card comes back up; the phone goes onto the mount on his chest. Insert, two seconds: his
thumb presses the side button, the screen locks, the lock screen shows the same name card. Nothing else on it.

The friend's lines are their own words, about 30 words in all; keep the scene to these five beats.

1. [FRIEND] greets Eric.
2. [FRIEND] gives name, company and one sentence on what they do.
3. ERIC: I'm Eric, from Hallwise. This badge.
4. ERIC: I'll send you our deck tonight.
5. [FRIEND] says Eric should meet Siddharth, by the sofa.

Panels: [FRIEND] appears as a dot toward the door, lit while they talk. Owe: deck → [FRIEND], tonight.
Mentioned, not met yet: Siddharth. Words: "Hallwise" (expected back as "Hall Wise" or "hallways").

Walk to the sofa (0:38–0:43). A waiter's voice from the TV side: "Something to drink?" ERIC (still walking):
"I'm good, thanks." Insert: the line in the transcript marked *filtered*. Nothing reaches the roster.

## The sofa (0:43–1:35), sofa (B)

Eric arrives mid-conversation. Margaux and Julien are talking to each other, in French, about yesterday's pitch.
Siddharth and Wei Ling listen.

[click]
MARGAUX (to Julien): Franchement, le deck d'hier, j'ai rien compris à leur modèle.
JULIEN: Pareil. Vingt slides, zéro chiffre.

Panels: two unnamed grey dots on the sofa side; the lines in the transcript as *ambient*, English under them
marked *translated*: "Honestly, yesterday's deck, I didn't get their model at all." / "Same. Twenty slides,
zero numbers." Nobody is a person yet; the room topics pick up "pitch decks".

ERIC: Hi, I'm Eric, from Hallwise. May I join your conversation?

[click]
SIDDHARTH: Oh, you must be Eric! Margaux, Julien, this is the badge guy. I'm Siddharth, Siddharth Raghunathan.
I run Quillmesh; we, um, schedule warehouse robots.
MARGAUX: Margaux Lefèvre, Corvane Capital.
JULIEN: Julien Caron. I'm with Margaux; I do the diligence.
WEI LING: Wei Ling, from Pandan Pay. Payments for, uh, hawker stalls. In Singapore.

(Eric leans in sideways, ear toward Mac-3, to hear her over the room. Her dot does not move.)

Panels: the two grey dots become Margaux and Julien in their colours, the same two voices; Siddharth and Wei
Ling appear as they speak. Margaux's card gets *French*. Words: "Raghunathan".

ERIC: Margaux, are you investing this quarter?

[click]
MARGAUX: Pre-seed, yes. Send me your one-pager. (half to herself) Bon, une page, avec des chiffres.

Insert: the aside, French, with "Right. One page, with numbers." under it, marked *translated*.

ERIC: One page, with numbers. Tomorrow. Wei Ling, [FRIEND] builds wallets. I'll introduce you two.

[click]
JULIEN: Come by our office next week and show us the demo? Wednesday afternoon?

ERIC: Wednesday works.

[click]
SIDDHARTH: And Eric, we launch in, sorry, we pilot next week. Launch is March.

Panels: Owe: one-pager → Margaux, tomorrow; introduce Wei Ling ↔ [FRIEND]; demo at Corvane with Julien,
Wednesday afternoon. Quillmesh: pilot next week, launch in March (the restart resolved). Four dots stay put
where each voice came from while Eric turns and leans in.

Walk to the window (1:35–1:40). ERIC (squeezing past the end of the sofa): "Sorry, excuse me." Filtered the
same way. Optional: the MC on the TV, "The panel starts in five minutes in the main hall" → a *stage* line, not
a person.

## The window (1:40–2:00), window (C)

[click]
KENJI: Ah, excuse me. Eric? Kenji Watanabe, Hoshizora Robotics. We keep running into each other.

Panels: Kenji's dot appears with a ring; the strip reads "met before · ETH Taipei afterparty · Hardware
meetup"; his card opens on "Before tonight: the coffee we never did".

ERIC (to camera, one beat): It remembered before I did. (to Kenji) Kenji! The coffee. Thursday?

[click]
KENJI: Thursday is... no, Friday. Friday is better. (murmurs) 金曜日ね、メモしておこう。

Panels: Owe: coffee with Kenji, **Friday**, with "Thursday" struck through. Insert: the murmur in Japanese
with "Friday, then. I'll make a note." under it, marked *translated*; Kenji's card gets *Japanese*.

Eric lifts the badge, swipes, taps Stop, "Stop" again on the sheet. The TV mutes on the same click.

## Stop (2:00–2:15), by the window

The right panel switches to the bell, then Owe. The Draft chips arrive one after another.

ERIC (to camera, while they land): It wrote these just now.

Right panel, each given a moment: Margaux's draft, French with English under it, "one page, with numbers",
the one-pager link attached. Julien's invite: "Wednesday 16:00 · 30 min · avoids your 14:00 board call".
Kenji's: Friday, and it mentions the coffee from last week's afterparty.

## The bedroom (2:15–2:35), Eric's room, lamp on

Eric sits, phone in hand, Ask page. He holds the mic.

ERIC: What did I promise tonight?

The panel shows the question as heard, then the answer: four lines, one per promise. Eric reads the last one
out.

ERIC: ...and [FRIEND] gets the deck tonight. (the bell shows 4; he taps it) And if I forget, it doesn't. Eight
o'clock, it taps me.

Insert: the notification "Deck for [FRIEND] due tonight". Then Words: "Hall Wise → Hallwise", Eric taps Keep.

ERIC: I fix a word once. Next time it's a hint.

## One night, one week (2:35–2:50)

Map, Tonight: the room from above, the dotted path 1 → 5, the timeline underneath. Two seconds. Map, All: the
week, Kenji's ring in the middle, five event chips. Two seconds.

ERIC: One night. One week. One map. When you're the whole company, you can't also be the one who remembers.
Hallwise is.

End card (2:50–2:56).

---

## To build before the shoot

- Julien's voice: render the French lines with `ff_siwis` pitched down, the English with `am_michael` and French
  shaping; check in rehearsal that diarization keeps him and Margaux apart.
- A Wednesday 14:00–15:30 "Board call" on the badge phone's calendar, so the invite has something to dodge.
- Deck and one-pager links set in the menu, so the drafts attach them.
- Nobody has to pronounce a surname right. Names from earlier evenings go to the transcriber as hints, and the
  badge matches a person by first name and company, so "Ragoo Nathan, Quill Mesh" is still Siddharth.

## Before the take

- Badge phone: event "Living-room rehearsal" and venue cleared so the app fills them itself; words memory reset
  to "Hallwise" only; links set; Do Not Disturb; the badge on its mount so it can't spin; forward offset
  calibrated facing the camera.
- Server: the four rehearsed evenings present and dated; `/api/people` lists sixteen people; Kenji's history
  shows two encounters.
- Follow phone: follow mode on the new recording id as soon as Start is tapped (the dashboard shows it);
  screen recording running.
- Mac-0: output device set to HDMI, muted until the first click; presenter keys captured globally; Do Not
  Disturb; dashboard screen recording running.
- iPhone-K: auto-lock never, one tap to arm audio; every player shows a green heartbeat on the controller.
- Sync: Eric claps before the take starts; Mac-0 logs the clap. The badge recording is the video's soundtrack.
- [FRIEND]: speaks English or Mandarin, not Taiwanese Hokkien; keeps to the five beats.
- Rehearse once end to end and read the Owe page before the final take.

## Risks

- Margaux and Julien share a spot and a base voice. If diarization merges them, move Julien to Mac-3 and Wei
  Ling to iPhone-K beside Kenji, and re-time the window scene.
- Margaux's line must not start over Siddharth's introduction, or both may land on one speaker label.
- Recognition is live but arrives with the first extraction run after the introduction, a few seconds later.
  Hold on Kenji until the ring appears before the "It remembered" line.
- The drafts take five to ten seconds after Stop; hold the shot on Eric until the first chip lands.
- The calendar editor must be prefilled on the follow phone, not the badge phone: for the take, tap Add to
  calendar on the follow phone (same server, same drafts).
- Live diarization must keep up in a noisy room; if not, use the replay fallback and its caption.
