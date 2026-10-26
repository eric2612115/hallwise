# Hallwise demo — networking fails the next morning, about 2:55

The story in one line: **networking doesn't fail in the room, it fails the next morning.** You promise a deck,
a coffee, an introduction; the next day you are busy, nothing goes out, and the relationship fades. Hallwise is
a name badge that listens, so by morning every follow-up is already written, in the other person's language,
with a reason to write that you had forgotten you had.

Rules for every shot: the hero is people and follow-ups, never text. Never say notes, transcript, summary or
meeting; say people, promises, follow-ups, the room, this week. A feature gets screen time only if it proves
"you don't have to remember, it does, and it acts". Everything else is one or two seconds of texture.

The room is real: computers play the other guests' voices from where they would stand, Eric and his friend talk
live, and Hallwise gets one device, the badge on Eric's chest. Everything on the panels is written by the models
from what the badge heard; nothing is typed. The four other evenings in the week were rehearsals run through the
same pipeline, dated on the days they stand for.

## Shape

| Time | Beat | Where | What it proves |
|---|---|---|---|
| 0:00–0:15 | The morning after | Eric's room, morning light, phone in hand | The payoff first: the morning report. Follow-ups written in French and English, two introductions he owed, one contact that could not be verified. "I typed nothing." |
| 0:15–0:25 | Last night | Friend's room, then its door | "Networking events never sound like this. They sound like this." The crowd comes in. |
| 0:25–0:45 | The door | Outside the friend's door | Start; the card stays a card. The friend, a promise, one selfie: SAM finds the faces, Spark says who is who. |
| 0:45–1:40 | The sofa | West end of sofa 1 | **The proof.** Two French investors talk among themselves; Margaux murmurs "une page, avec des chiffres"; only then is Eric introduced and the grey dots get names. The panel links Margaux to Chloé, her colleague Eric met at Blockchain Week. |
| 1:40–1:47 | Past the table | Walking | The waiter, filtered. One second. |
| 1:47–2:15 | The table | West end of the table | Siddharth and Kenji ringed the moment they speak: met before. An open thread surfaces: Eric promised Lena an introduction to Kenji on Oct 20. Thursday, no, Friday. |
| 2:15–2:40 | That night | Eric's room, lamp | Stop. The follow-ups land, each with its hook. "Who do I still owe an introduction?", asked out loud. |
| 2:40–2:55 | One night, one week | Same | Tonight's path, then the week's map. "When you're the whole company, you can't also be the one who remembers. Hallwise is." |
| 2:55–3:00 | End card | | Models, open source. |

## The payoff, written down first

The opening and the drafts must say this, because the night has to earn exactly these lines:
- **Margaux (French, one-pager):** "Bonjour Margaux, Chloé m'a dit que vous voudriez voir ça… une page, avec des
  chiffres, comme promis." Hook: her colleague Chloé (Corvane Capital) said so at Blockchain Week on Oct 23; the
  "one page, with numbers" is what Margaux muttered in French before anyone knew her name.
- **Kenji (coffee, Friday):** an invite at a free Friday slot. Hook: Eric promised Lena (Brightline Grid) an
  introduction to Kenji at the ETH Taipei afterparty on Oct 20 and never sent it; the draft offers it.
- **Julien (demo, Wednesday):** 16:00, "avoids your 14:00 board call". Morning check: no public profile found at
  Corvane, confirm before sending the deck.
- **[FRIEND] (deck, tonight):** sent with the deck link; the morning check matches their public company page.
- **Introductions to make:** Lena and Kenji, from the open promise; nothing invented.

## Frame

- Left 60%: the camera.
- Right 40% during the night: the app's **Room page** from the iOS Simulator on Mac-0 following the live
  recording (follow mode), recorded with `demo/rig/record-follow-view.sh`: the radar (ahead = up, a coloured dot
  per person where their voice comes from, lit while they talk, a ring when the badge has met them before), the
  strip of who Eric has met, and the hook lines ("met before", "Chloé's colleague", "you owe Lena an intro").
- Right 40% in the morning and in Eric's room: the iPhone 17 Pro's own screen recording; after Stop it is in
  Eric's hand, not a badge.
- Inserts, timed from the event log by the editor: the French lines with their English marked *translated*,
  Margaux's aside, Kenji's murmur.
- Small model captions, lower left, two seconds each, at the moment the model acted:
  "Muse Voice Transcribe · two voices, still apart after the switch to English", "Muse Spark · translated",
  "SAM 3.1 finds the faces · Muse Spark says who is who", "Muse Spark · links Margaux to Chloé (Oct 23)",
  "Muse Spark · promise corrected", "Muse Spark Open · a second listener checks the names", "Muse Spark · search
  grounding checks who they are".
- If the live capture of the right panel fails, replay the recording at its original pace in follow mode and
  record it again; the content is the same event log.

## On-screen text

- 0:00: "🎧 Headphones on."
- Under the first night shot: "AI guests: voices by Kokoro, faces by Muse Image. My friend and I are real. The
  other evenings this week were rehearsals through the same pipeline."
- End card: "Built with Muse Voice Transcribe · Muse Spark · SAM 3.1 · Muse Spark Open on Baseten. Open source,
  AGPL-3.0."

Personas and companies are fictional. [FRIEND] and [FRIEND_CO] are a real friend's name and company.

## Cast

| Person | Where | Device | Voice |
|---|---|---|---|
| [FRIEND], [FRIEND_CO], wallets | Door (A) | live | their own |
| Margaux Lefèvre, Corvane Capital, pre-seed | Sofa 1, near end (B1) | Mac-1 | `ff_siwis` (French and English) |
| Julien Caron, Corvane Capital, diligence | Sofa 1, far end (B2) | Mac-2 | `ff_siwis` pitched down 4 semitones for French; `am_michael` with French shaping for English |
| Waiter, then Siddharth Raghunathan, Quillmesh (met Oct 20 and Oct 23) | Dining table, east end (C) | Mac-3, two files | waiter: a voice the cast doesn't use; Siddharth: `hm_omega`, Indian English shaping |
| Kenji Watanabe, Hoshizora Robotics (met Oct 20 and Oct 22) | Sofa 2, south armrest, head height (D) | iPhone 16 (iPhone-K) | `jm_kumo` |
| MC, hall bed | TV | Mac-0 over HDMI | voices the cast doesn't use |

Margaux and Julien share a base voice and sit a metre apart on one sofa; diarization tells them apart by
voice, the radar by direction. Rehearse this pair first (see Risks). Mac-3 plays the waiter, then three seconds
of nothing, then Siddharth, so the two never share a speaker label.

The week already on the server before the take (rehearsed recordings, dated): ETH Taipei afterparty (Oct 20:
Siddharth, Lena, Kenji, Tomás), Hardware meetup (Oct 22: Kenji, Hana, Priya, Daniel), Blockchain Week side event
(Oct 23: Siddharth, Tomás, Chloé, Yuki, Ahmed), Founder dinner (Oct 24: Lena, Sofia, Daniel, Ben). Kenji is the
one the badge will recognise tonight; at the afterparty he and Eric agreed to "the coffee we never did".

## Room

| Spot | What is there |
|---|---|
| Friend's room (upper left) | Where the take starts: Eric sits, then walks out of its door into the living room. |
| Friend's door (A) | [FRIEND] waits just outside it, in the living room. Eric faces them, south-east; the TV is behind Eric's left shoulder. |
| Sofa 1 (B), under the TV | Mac-1 (Margaux) on the near cushion, Mac-2 (Julien) on the far cushion, about a metre apart. Eric's mark: the west end of the sofa, facing east along it, so the TV is on his left, not behind the guests. |
| Dining table (C), below sofa 1 | Mac-3 at the east end: the waiter's line as Eric passes the west end, then Siddharth. Eric's mark for the table scene: the west end, facing east. |
| Sofa 2 (D), right wall | iPhone-K on the south armrest at head height: Kenji, ahead-left of Eric's table mark by about 35°. |
| TV, top wall | Mac-0 over HDMI: the hall bed, muted until the first click; also the Hallwise server, the dashboard (screen-recorded), the rig controller; the presenter is paired to it. |
| Eric's room (lower left) | Where the closing is shot: in through its door, lamp on, the sofa in the room's top-right corner. |
| Eric | iPhone 17 Pro worn as a badge on a magnetic lanyard mount (portrait, screen out, nothing covering the microphones), showing "Eric · Hallwise" on the paper card. Presenter in hand. |
| Follow view | The Hallwise app in the iOS Simulator on Mac-0, in follow mode, recorded with `xcrun simctl io booted recordVideo`: the exact app screen, no second phone. The iPhone 16 is free to play Kenji. |
| Camera | A friend's iPhone 18 Pro on a gimbal. The operator walks backwards ahead of Eric from the friend's room to Eric's door, pausing at the three corners (the door, the sofa's west end, the table's west end). Walk it once empty-handed first; the turns are tight. Its audio is only a sync reference. |

## Sound

- The soundtrack is the badge's own recording (iPhone 17 Pro): exactly what Hallwise heard, Eric's voice
  included. The app keeps the full multichannel file on the phone while it streams. The opening silence and
  the bedroom are the camera's audio, so the cut from silence to crowd is clean.
- In post, the camera's scratch audio and the clap line the badge recording up with the picture. The four
  channels are decoded to headphone stereo; no on-camera mention of it.
- Background, all Kokoro: the hall bed on the TV from the cue to Stop; group X (Mac-1/2) during the door
  scene; group Y (iPhone-K) during the door and sofa scenes; group Z (Mac-1/2) during the table scene. The
  background groups feed the room topics. An optional MC announcement also comes from the TV. At the sofa the
  bed is on Eric's left, so the crowd never sits behind the two guests on the radar.
- `[click]` is where Eric presses the presenter to cue the next synthetic lines. The first click unmutes the TV.

---

## The morning after (0:00–0:15), Eric's room, morning light

Shot last, the morning after the take. Eric sits on the edge of the bed, phone in hand; the 17 Pro records its
own screen. The camera holds on his face, then the phone.

ERIC: Networking doesn't fail in the room. It fails the next morning.

He opens the morning report: four people last night; three follow-ups ready, Margaux's in French; "You owe Lena
an introduction to Kenji, from Oct 20"; "Julien: no public profile found at Corvane, check first".

ERIC: This is my morning after last night. Every follow-up is written, in their language, with a reason to
write. I typed nothing. Here's last night.

## Last night (0:15–0:25), the friend's room, then its door

Silence. Eric at the door of the friend's room, to camera.

ERIC: Networking events never sound like this. [click] They sound like this.

He steps through; the hall bed comes in on the TV, hard. Two seconds of it.

## The door (0:25–0:45), just outside the friend's door (A)

Eric taps Start; the card comes back up; the phone goes onto the mount on his chest. Insert, one second: the
side button, the lock screen, the same name card.

The friend's lines are their own words; keep to these beats.
1. [FRIEND] greets Eric, gives name, company and one sentence on what they do.
2. ERIC: I'm Eric, from Hallwise. This badge. I'll send you our deck tonight.
3. ERIC: Selfie? (front camera, one shot, the phone back on the mount) Now you have a face.
4. [FRIEND]: Come, you should meet Margaux and Julien.

Panels: [FRIEND]'s dot toward the door; about seven seconds after the selfie, their face on the dot and the card.
Caption: "SAM 3.1 finds the faces · Muse Spark says who is who". Keep talking through the wait.

## The sofa (0:45–1:40), the west end of sofa 1 (B), facing east

Margaux and Julien talk to each other in French. Eric stops at the sofa's west end; the TV is on his left.

[click]
MARGAUX (to Julien): Franchement, le deck d'hier, j'ai rien compris à leur modèle.
JULIEN: Pareil. Vingt slides, zéro chiffre.

Panels: two grey dots ahead; the lines arrive as *ambient* with their English marked *translated*. Nobody has a
name yet.

[FRIEND] (from Eric's right, a step back from the Macs): Margaux, Julien, this is Eric. He makes the badge.

ERIC: Hi. Eric, from Hallwise. May I join your conversation?

[click]
MARGAUX: Margaux Lefèvre, Corvane Capital.
JULIEN: Julien Caron. I'm with Margaux; I do the diligence.

Panels: the two grey dots become Margaux and Julien, the same two voices as the French. Under Margaux: "Chloé's
colleague · Blockchain Week, Oct 23". Caption: "Muse Voice Transcribe · two voices, still apart after the
switch to English".

ERIC: Margaux, are you investing this quarter?

[click]
MARGAUX: Pre-seed, yes. Send me your one-pager. (half to herself) Bon, une page, avec des chiffres.

Insert: the aside, French, with "Right. One page, with numbers." under it, marked *translated*.

ERIC: One page, with numbers. Tomorrow.

[click]
JULIEN: Come by our office next week and show us the demo? Wednesday afternoon?

ERIC: Wednesday works.

## Past the table (1:40–1:47)

Mac-3 as a waiter: "Something to drink?" ERIC (walking): "I'm good, thanks." One second of the line marked
*filtered*. Mac-3 then stays silent for three seconds.

## The table (1:47–2:15), the west end of the dining table (C), facing east

[click]
SIDDHARTH (Mac-3, ahead): Eric! Siddharth, from Blockchain Week. You know Kenji.
KENJI (iPhone-K, ahead-left): Kenji Watanabe, Hoshizora Robotics. We keep running into each other.

Panels: both dots ringed the moment they are named: "met before · Blockchain Week", "met before · Hardware
meetup, ETH Taipei afterparty". Under Kenji, the open thread: "You promised Lena (Brightline) an intro · Oct 20".

ERIC (to camera, one beat): It remembered both of them before I did. (to Kenji) Kenji! The coffee. Thursday?

[click]
KENJI: Thursday is... no, Friday. Friday is better. (murmurs) 金曜日ね、メモしておこう。

Panels: coffee with Kenji, **Friday**, "Thursday" struck through. Insert: the murmur with "Friday, then. I'll
make a note." under it, marked *translated*. Caption: "Muse Spark · promise corrected".

Eric walks to his own door.

## That night (2:15–2:40), Eric's room, lamp on, the sofa in the top-right corner

Lamp on, Eric sits, lifts the badge, taps Stop. The TV mutes on the same click. From here the right panel is the
17 Pro's own screen.

ERIC (while the follow-ups land): It wrote these just now.

Each given a moment: Margaux's, French, "Chloé m'a dit…", "une page, avec des chiffres", the one-pager attached;
Julien's invite, "Wednesday 16:00 · avoids your 14:00 board call"; Kenji's, Friday, offering the introduction to
Lena. One second of Words: "two Meta models heard this differently: Ragoo Nathan / Raghunathan" (Muse Spark Open
as the second listener).

Eric opens Ask and holds the mic.

ERIC: Who do I still owe an introduction?

The answer: Lena and Kenji, from Oct 20; the draft is ready. The bell shows the count; a reminder for eight
o'clock is set.

## One night, one week (2:40–2:55)

Map, Tonight: the room from above, the dotted path 1 → 5, the times. Two seconds. Map, All: the week, Kenji's
ring in the middle, the five evenings as chips, one line from Chloé to Margaux. Two seconds.

ERIC: One night. One week. When you're the whole company, you can't also be the one who remembers. Hallwise is.

End card (2:55–3:00).

---

## To build before the shoot

- The morning report and the hooks (queued): research of new people with Muse Spark search grounding, rate
  limited; hooks from the people index, promises and mentions across evenings (Chloé said "my colleague Margaux";
  Eric promised Lena an intro to Kenji on Oct 20); a report screen in the app and an eight o'clock notification.
- The hook lines on the Room strip and the person card ("Chloé's colleague", "you owe Lena an intro").
- The second listener on Baseten (queued) for the Words moment.
- Timed replay in follow mode (in progress) as the fallback for the right panel.
- Julien's voice distinct from Margaux's; check diarization keeps them apart.
- A Wednesday 14:00–15:30 "Board call" on the 17 Pro's calendar; deck and one-pager links set in the menu.
- Selfies at the sofa and the table are not needed: the guests are laptops. Their faces on the radar come from
  earlier evenings (Muse Image portraits attached to those recordings); Margaux and Julien stay dots, which is
  the point: people you know have faces, people you just met do not yet.

## Before the take

- Badge phone: event "Living-room rehearsal" and venue cleared so the app fills them itself; words memory reset
  to "Hallwise" only; links set; Do Not Disturb; the badge on its mount so it can't spin; forward offset
  calibrated facing the camera.
- Server: the four rehearsed evenings present and dated; `/api/people` lists sixteen people; Kenji's history
  shows two encounters.
- Follow view: the Simulator on Mac-0 switched to follow mode on the new recording id as soon as Start is tapped (the dashboard shows it);
  screen recording running.
- Mac-3: the waiter file and Siddharth's file on separate presenter keys, in that order.
- Mac-0: output device set to HDMI, muted until the first click; presenter keys captured globally; Do Not
  Disturb; dashboard screen recording running.
- iPhone-K: auto-lock never, one tap to arm audio; every player shows a green heartbeat on the controller.
- Sync: Eric claps before the take starts; Mac-0 logs the clap. The badge recording is the video's soundtrack.
- [FRIEND]: speaks English or Mandarin, not Taiwanese Hokkien; keeps to the five beats.
- Rehearse once end to end and read the Owe page before the final take.

## Risks

- Margaux and Julien share a base voice. If diarization merges them, render Julien with `am_michael` for the
  French lines too (French shaping) and accept the accent.
- Mac-3 plays the waiter and then Siddharth: keep the three-second gap, or the waiter's line lands on
  Siddharth's label.
- The friend introduces from Eric's right, a step back from the Macs: two voices from one spot would merge.
- Margaux's line must not start over Siddharth's introduction, or both may land on one speaker label.
- Recognition is live but arrives with the first extraction run after the introduction, a few seconds later.
  Hold on Kenji until the ring appears before the "It remembered" line.
- The drafts take five to ten seconds after Stop; hold the shot on Eric until the first chip lands.
- The calendar editor must be prefilled in the follow view, not on the badge phone: for the take, click Add to
  calendar in the Simulator (same server, same drafts).
- The selfie at the door: two faces, the wearer excluded, about seven seconds; the first SAM call of the day
  can take nine. Take one warm-up photo before the take.
- On the real iPhone, check once that a talker on the left lights the left dot with the badge hanging upside
  down: if iOS already corrects the microphones for orientation, the server's mirroring would flip it twice.
- Live diarization must keep up in a noisy room; if not, use the replay fallback and its caption.
