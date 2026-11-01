# Hallwise demo — networking fails the next morning, about 3:00

The story in one line: **networking doesn't fail in the room, it fails the next morning.** You promise a deck,
a coffee, an introduction; the next day you are busy, nothing goes out, and the relationship fades. Hallwise is
a name badge that listens, so by morning every follow-up is already written, in the other person's language,
with a reason to write that you had forgotten you had.

The video answers four questions, in PITCH.md's order: what the market is missing, what we built, why now, why
us. It is told as a drama, not a pitch: a debt set up in the first seven seconds, a man who can't place a face,
a badge that can, and the same eight o'clock buzz at both ends of the film.

It runs in story order:
- Cold open: 8:00, a text from Lena asking about an introduction to someone named Kenji. Eric has no idea who
  Kenji is.
- Eric in his glasses in a silent room, then the room's real sound.
- The wall of "Speaker 2": what today's tools give you at a mixer.
- The glasses put away and the badge clipped on.
- One evening, where Kenji walks up and Eric still can't place him. The badge can.
- Stop, then the next morning: the same buzz, and this time the introduction is already written.
- The week's map under why now; why me, and the close.

Rules for every shot:
- The hero is people and follow-ups, never text. Never say notes, transcript, summary or meeting; say people,
  promises, follow-ups, the room, this week. The exceptions are in What's missing: "note-takers", said once,
  and the vendors' own quotes on the wall.
- Never mention microphones or direction, on camera, in a caption or on a card.
- What's missing gets at most 16 seconds; brands appear only on the cards.
- Why now and why us are spoken mostly over product shots (the map, the repo); a talking head alone holds a few
  seconds at most.
- A feature gets screen time only if it proves "you don't have to remember, it does, and it acts". Everything
  else is one or two seconds of texture.

The room is real: computers and phones play the other guests' voices from where they would stand, Eric and his
friend talk live, and Hallwise gets one device, the badge on Eric's chest. Everything on the panels is written
by the models from what the badge heard; nothing is typed. The four other evenings in the week were rehearsals
run through the same pipeline, dated on the days they stand for.

The guests' exact lines, cues and durations are in `rig/v4/LINES.md` and `rig/v4/CUES.md`. This file is the
shape, the frame, and what each beat has to prove.

## Shape

| Time | Part | Beat | Where | What it proves |
|---|---|---|---|---|
| 0:00–0:07 | Pain | Cold open: 8:00 | Eric's room, the morning of the take | Lena's text: the intro to Kenji, still unsent. "...Kenji?" The stakes, before a word of pitch. |
| 0:07–0:22 | Pain | The glasses | Friend's room, at its door | A mixer is loud and sideways, full of accents, asides and asks, and half the faces you have met before. The glasses come off and go in a pocket. |
| 0:22–0:36 | What's missing | The wall of "Speaker 2" | Same, the wall over the shot | At most 14 s. 183 note-takers; at a mixer, everyone is "Speaker 2". "I don't need another one. I need to remember who Kenji is." Dated facts, on the wall only. |
| 0:36–0:42 | What we built | The badge | Same | Start; the phone clipped to his chest; its lock screen is the name card. "I don't type a thing." Title. |
| 0:42–1:00 | What we built | The door | Outside the friend's door (A) | Leo gives his name and company; Eric promises the deck tonight. |
| 1:00–1:40 | What we built | The sofa | West end of sofa 1 (B) | **The proof.** Two investors talk among themselves; Margaux says "une page, avec des chiffres" to herself; only then is Eric introduced, and the grey dots get names. The panel links Margaux to Chloé, her colleague Eric met at Blockchain Week. |
| — | | Past the table | Walking | The waiter still plays in the take, so Siddharth's label stays clean; the edit cuts it. |
| 1:40–2:05 | What we built | The table | West end of the table (C) | Siddharth and Kenji ringed: met before. Eric can't place Kenji, and Kenji has to give his own name. The panel knows what Eric has forgotten: he has owed Lena an introduction to Kenji since Oct 20. Thursday, no, Friday. |
| 2:05–2:07 | What we built | Stop | Eric's door | "That's it. I go home." |
| 2:07–2:31 | What we built | The next morning | Eric's room, morning light | The report: Margaux's follow-up in French, quoting her aside; the introduction Eric forgot, written to Kenji and Lena; Julien's time checked against the calendar; a check on who each person is. "I typed nothing." |
| 2:31–2:43 | Why now | The map | Same | The week on the map while Eric says why now: the big companies bought memory of your own day; 410 people asked for memory of people, and the company was sold first. |
| 2:43–3:00 | Why us | Why me, the close, end card | Same, then the doorway | "I'm the engineer, the salesman, and the guy who forgot Kenji's name." Two seconds of the repo and the tests. "A one-person company's CEO can't also be the one who remembers. Hallwise can." Models, open source. |

The evening's timings are edit targets: the guests' lines don't change, the edit trims pauses and the walks.

## The payoff, written down first

The morning report must say this, because the night has to earn exactly these lines:
- **Margaux (French, one-pager):** "Bonjour Margaux, Chloé m'a dit que vous voudriez voir ça… une page, avec des
  chiffres, comme promis." Hook: her colleague Chloé (Corvane Capital) said so at Blockchain Week on Oct 23.
  "Une page, avec des chiffres" is what Margaux said to herself in French before anyone knew her name. She spoke
  English to Eric all evening; the draft is in French because of that aside.
- **Kenji and Lena (the introduction):** one letter to both. Eric promised Lena (Brightline Grid) an
  introduction to Kenji at the ETH Taipei afterparty on Oct 20 and never sent it. This is the letter that
  rescues the evening Eric fumbled. The coffee with Kenji sits on the free Friday slot.
- **Julien (demo, Wednesday):** 16:00, "avoids your 14:00 board call". Check: no public profile found at
  Corvane, confirm before sending the deck.
- **Leo (deck, last night):** promised "tonight", still unsent: overdue.
- **Introductions to make:** Lena and Kenji, from the open promise; nothing invented.

## Frame

- Left 60%: the camera.
- Right 40% in the opening: nothing from the app yet, then the title.
- Right 40% during the night: the app's **Room page** from the iOS Simulator on Mac-0, following the live
  recording (follow mode) and recorded with `demo/rig/record-follow-view.sh`. It shows a dot per person, lit
  while they talk, with a ring when the badge has met them before; the strip of who Eric has met; and the hook
  lines ("met before", "Chloé's colleague", "you owe Lena an intro"). Nothing in the edit or the captions
  points at where a dot sits.
- Right 40% in the morning: the iPhone 17 Pro's own screen recording. The phone is in Eric's hand, not on his
  chest.
- Insert, timed from the event log by the editor: Margaux's aside, with its English marked *translated*.
- Small model captions, lower left, two seconds each, at the moment the model acted:
  - The night: "Muse Voice Transcribe · two voices, apart before anyone has a name", "Muse Spark · translated",
    "Muse Spark · names from the introduction", "Muse Spark · links Margaux to Chloé (Oct 23)",
    "Muse Spark · met before", "Muse Spark · promise corrected".
  - The morning: "Muse Spark · drafted in her language", "Muse Spark · checks who they are",
    "Muse Spark Open · a second listener checks the names".
- If the live capture of the right panel fails, replay the recording at its original pace in follow mode and
  record it again; the content is the same event log.

## On-screen text

- Under the first shot at the door: "AI guests: voices by ElevenLabs, faces by Muse Image, their web pages
  invented. Lena's text is staged. My friend and I are real. The other evenings this week were rehearsals through the same pipeline."
- The wall of "Speaker 2", each label with its source (see What's missing).
- The why-now card, small, over the map: "Meta bought Limitless (Dec 2025) · Amazon bought Bee (Jul 2025) · 410
  Limitless users asked for a personal CRM; still unbuilt (2025-12-08)".
- End card: "Built with Muse Voice Transcribe · Muse Spark · SAM 3.1 · Muse Spark Open on Baseten. Open source,
  AGPL-3.0."

Personas and companies are fictional. [FRIEND] is a real friend.

## Cast

| Person | Where | Device | Voice |
|---|---|---|---|
| Eric | the badge wearer | live | his own |
| [FRIEND], the introducer | Door (A), then the sofa, from Eric's right | live | their own |
| Leo Wong, Bright Path, wallet infrastructure | Door (A), chest height | Phone-L | Roger, Hong Kong accent |
| Margaux Lefèvre, Corvane Capital, pre-seed | Sofa 1, near cushion (B1) | Mac-1 | Lily, French accent |
| Julien Caron, Corvane Capital, diligence | Sofa 1, far cushion (B2) | Mac-2 | Callum, French accent |
| Waiter, then Siddharth Raghunathan, Quill Mesh (met Oct 20 and Oct 23) | Dining table, east end (C) | Mac-3, two files | waiter: Jessica; Siddharth: Chris, Indian accent |
| Kenji Watanabe, Hoshizora Robotics (met Oct 20 and Oct 22) | Sofa 2, south armrest, head height (D) | iPhone 16 (iPhone-K) | Liam, Japanese accent |
| Hall bed | TV | Mac-0 over HDMI | voices the cast doesn't use |

Every guest speaks English to Eric, in their own accent. The only other language in the evening is Margaux's
aside to herself, in French. The voices are ElevenLabs Eleven v4 built-in voices with an accent tag on every
line; the heavier-accent library voices need a paid plan (LINES.md, Cast).

Mac-3 plays the waiter, then three seconds of nothing, then Siddharth, so the two never share a speaker label.

The week already on the server before the take (rehearsed recordings, dated): ETH Taipei afterparty (Oct 20:
Siddharth, Lena, Kenji, Tomás), Hardware meetup (Oct 22: Kenji, Hana, Priya, Daniel), Blockchain Week side event
(Oct 23: Siddharth, Tomás, Chloé, Yuki, Ahmed), Founder dinner (Oct 24: Lena, Sofia, Daniel, Ben). Kenji is the
one the badge will recognise tonight. At the afterparty he and Eric agreed to "the coffee we never did", and
Eric promised Lena an introduction to him.

## Room

| Spot | What is there |
|---|---|
| Friend's room (upper left) | The opening is shot at its door, looking out at the living room. Eric then steps out into the living room. |
| Friend's door (A) | Phone-L (Leo) at chest height just outside it; [FRIEND] stands beside it. Eric faces south-east; the TV is behind his left shoulder. |
| Sofa 1 (B), under the TV | Mac-1 (Margaux) on the near cushion, Mac-2 (Julien) on the far cushion, about a metre apart. Eric's mark: the west end of the sofa, facing east along it, so the TV is on his left, not behind the guests. |
| Dining table (C), below sofa 1 | Mac-3 at the east end: the waiter's line as Eric passes the west end, then Siddharth. Eric's mark for the table scene: the west end, facing east. |
| Sofa 2 (D), right wall | iPhone-K on the south armrest at head height (Kenji), within a metre or two of Eric's table mark. |
| TV, top wall | Mac-0 over HDMI: the hall bed, muted until the first click. Mac-0 also runs the Hallwise server, the dashboard (screen-recorded) and the rig controller; the presenter is paired to it. |
| Eric's room (lower left) | Stop is at its door; the morning is shot inside, on the edge of the bed. |
| Eric | His own glasses on for the opening, then in his jacket pocket. The iPhone 17 Pro worn as a badge on a magnetic lanyard mount (portrait, screen out, nothing covering the bottom edge); its lock screen is the name card "Eric · Hallwise". Presenter in hand. |
| Follow view | The Hallwise app in the iOS Simulator on Mac-0, in follow mode, recorded with `xcrun simctl io booted recordVideo`: the exact app screen, no second phone. |
| Camera | A friend's iPhone 18 Pro on a gimbal. The operator walks backwards ahead of Eric from the friend's room to Eric's door, pausing at the three corners (the door, the sofa's west end, the table's west end). Walk it once empty-handed first; the turns are tight. Its audio is the opening's sound and the sync reference. |

## Sound

- The opening is the camera's audio: the silence, then the hall bed coming in on the click. The badge is not
  recording yet.
- From Start to Stop the soundtrack is the badge's own recording (iPhone 17 Pro): exactly what Hallwise heard,
  Eric's voice included, mixed down plainly. The app keeps the full file on the phone while it streams.
- In post, the camera's scratch audio and the clap line the badge recording up with the picture.
- Background: the hall bed on the TV (`rig/tv-hall-bed.wav`, looped) from the first click to Stop. At the sofa
  the TV is on Eric's left, never behind the two guests.
- `[click]` is where Eric presses the presenter to cue the next guest lines (CUES.md). The first click unmutes
  the TV.

---

## Cold open (0:00–0:07), Eric's room, the morning of the take

Black. A phone buzzes on the nightstand: 7:59 becomes 8:00. Eric, half awake, picks it up. A text, on screen
in full:

> **Lena:** Morning! Did you ever send that intro to Kenji? 🙂

Eric stares at it. Beat.

ERIC (to himself): ...Kenji?

Smash cut to black, then white text: **Networking doesn't fail in the room. It fails the next morning.**

The text is a staged prop from a second phone saved as "Lena" (Lena is from the rehearsal week, Oct 20). Use
the same buzz sound here and at the 8:00 notification in The next morning; the film opens and closes on it.

## The glasses (0:07–0:22), the friend's room, at its door

Silence. Eric wears his own glasses. To camera:

ERIC: Networking events never sound like this. [click] They sound like this.

The hall bed comes in on the TV, hard. Two seconds of it.

ERIC: My glasses hear whoever I'm facing. But at a mixer, the person talking to me is usually beside me. And I
can't point a camera at everyone.

He takes the glasses off, folds them and puts them in his jacket pocket. They are put away, never dropped or
thrown.

Quick cuts, about one second each, from later in the take (the editor picks them from the badge recording):
Leo's accent, Margaux's aside, "send me your one-pager", "Thursday is... no, Friday".

ERIC (over the cuts): Accents. Asides. Asks. Promises.

Cut to Kenji's "Eric! We keep running into each other." and Eric's blank face.

ERIC: And half of them, I've met before. I just can't remember where.

Eric says all of these lines live, standing at the door; the cuts are laid over them in the edit, which keeps
this beat to 15 seconds.

## What's missing (0:22–0:36), at most 14 seconds

The wall of "Speaker 2". Labels stack up over the frozen face of the stranger from the quick cuts: "Speaker 1",
"Speaker 2", "Speaker A", "Speaker", each one a real label from a dated vendor page (below), each with its
source in small type. They come faster and faster with a ticking sound until they cover the frame. Hard stop.
Silence.

ERIC: There are 183 AI note-takers. I don't need another one.

Beat.

ERIC: I need to remember who Kenji is.

The sources on the wall, brands only here (all in `competitors/landscape.md`):
- 183 AI note-takers. (Product Hunt category, 2026-10-28)
- "Speaker 1, 2" until you name them, and only for that one recording. (Plaud help center, Oct 2026)
- "Speaker A, Speaker B" on iPhone. (Granola help center, iOS transcription, read 2026-10-28)
- "Speaker name detection only works when Fireflies joins a video meeting, or you're using the Chrome
  extension." (Fireflies help center, read 2026-10-28)
- People in the room must be "enrolled with their voice profile and be invited to the scheduled meeting";
  everyone else is "Speaker". (Microsoft Teams Rooms docs, 2026-08-27)

Eric never says that they can't do something; the wall shows only what the vendors write themselves. PITCH.md,
part 1, has the full gap and what must never be said. Re-check every source the week of the submission.

## The badge (0:36–0:42)

Eric taps Start and clips the phone to the mount on his chest, screen out. Insert, one second: the side button,
the lock screen, the name card "Eric · Hallwise".

ERIC: So I wear this. I don't type a thing.

Title over the shot: **Hallwise.** A name badge that remembers the room.

He steps out of the friend's room into the living room.

## The door (0:42–1:00), just outside the friend's door (A)

[click]
LEO (Phone-L): Eric! Hey, hey, you made it! Okay, okay. For your badge, yeah? Leo Wong. Bright Path. We do,
uh... wallet infrastructure. For apps.

ERIC: Leo! Good to see you. I'm Eric, from Hallwise. This badge. I'll send you our deck tonight.

[click]
LEO: Tonight? Okay, okay. I'm holding you to that, ah.

[FRIEND]: Eric, come. You should meet Margaux and Julien.

Panels: Leo's dot gets his name and company; the deck, due tonight. The edit trims the walk to the sofa.

## The sofa (1:00–1:40), the west end of sofa 1 (B), facing east

Eric stops at the sofa's west end; the TV is on his left.

[click] Margaux and Julien talk between themselves in English about yesterday's pitch: she did not understand
their model; he counted twenty slides and zero numbers. Then Margaux, to herself, in French:

MARGAUX: Une page, avec des chiffres...

The aside is played slower than her other lines and just as loud, with a pause on each side. It is not
whispered: the morning hangs on it (see Risks).

Panels: two grey dots; the lines arrive with nobody's name on them; the aside with "One page, with numbers..."
under it, marked *translated*. Caption: "Muse Voice Transcribe · two voices, apart before anyone has a name".

[FRIEND] (from Eric's right, a step back from the Macs): Margaux, Julien, this is Eric. He makes the badge.

ERIC: Hi. Eric, from Hallwise. May I join you?

[click]
MARGAUX: Oh, of course! Margaux. Margaux Lefèvre, Corvane Capital.
JULIEN: And I am Julien. Julien Caron, also Corvane. I do the, euh... the diligence.

Panels: the two grey dots become Margaux and Julien, the same two voices as before. Under Margaux: "Chloé's
colleague · Blockchain Week, Oct 23". Captions: "Muse Spark · names from the introduction", then "Muse Spark ·
links Margaux to Chloé (Oct 23)".

ERIC: Margaux, are you investing this quarter?

[click]
MARGAUX: Pre-seed, yes. This quarter. Euh... send me your one-pager? One page, with numbers. Please.

ERIC: One page, with numbers. Tomorrow.

[click]
JULIEN: And, euh... come by our office? Show us the demo. Wednesday afternoon?

ERIC: Wednesday works.

## Past the table (cut in the edit)

Mac-3 as a waiter: "Hi! Something to drink?" ERIC (walking): "I'm good, thanks." It stays in the take so the
waiter never shares a label with Siddharth; the edit cuts it. Mac-3 then stays silent for at least three seconds.

## The table (1:40–2:05), the west end of the dining table (C), facing east

[click]
SIDDHARTH (Mac-3): Eric! Hey! Siddharth. Siddharth Raghunathan, Quill Mesh? We met at Blockchain Week. You know
Kenji, no?
KENJI (iPhone-K): Eric! We keep running into each other.

ERIC: Hey! It's, uh... sorry, it's been a long week...

Eric plainly can't place him. Let the moment be awkward; everyone has been there.

[click]
KENJI: Kenji. Kenji Watanabe, Hoshizora Robotics? The hardware meetup?

Panels: both dots ringed, "met before · Blockchain Week" and "met before · Hardware meetup, ETH Taipei
afterparty". Under Kenji, the open thread: "You owe Lena (Brightline) an intro · Oct 20". Caption: "Muse Spark ·
met before". The badge faces out and Eric never looks at it: the viewer knows what he has forgotten, and he
doesn't.

ERIC: Kenji! Of course, the hardware meetup. We still owe each other a coffee. Thursday?

[click]
KENJI: Thursday is... hmm. No... Friday. Friday is better.

Panels: coffee with Kenji, **Friday**, "Thursday" struck through. Caption: "Muse Spark · promise corrected".

Eric walks to his own door.

## Stop (2:05–2:07), Eric's door

Eric lifts the badge and taps Stop. The TV mutes on the same click.

ERIC: That's it. I go home.

Cut before the follow-ups land on the panel; they belong to the morning.

## The next morning (2:07–2:31), Eric's room, morning light

Shot the morning after the take. Eric sits on the edge of the bed, phone in hand; the 17 Pro records its own
screen. The camera holds on his face, then the phone.

The same frame as the cold open: the nightstand, 7:59 becomes 8:00, the same buzz. Eric flinches, expecting
Lena. It is Hallwise.

The eight o'clock notification opens the morning report: five people last night; Leo's deck, overdue; the
follow-ups ready, Margaux's in French; the introduction he owes; "Julien: no public profile found at Corvane,
check first".

ERIC: Five people. I typed nothing.

Margaux's draft: French, "Chloé m'a dit…", "une page, avec des chiffres", the one-pager attached. Insert: her
aside from last night. Caption: "Muse Spark · drafted in her language".

ERIC: She said that to herself, in French, before I even knew her name.

The introduction: one letter to Kenji and Lena, from the promise of Oct 20.

ERIC: I couldn't remember his name. I'd forgotten I owed him an introduction. It hadn't.

He taps Send on the introduction.

Then one second each:
- Julien's invite, "Wednesday 16:00 · avoids your 14:00 board call", with the check under it: Corvane is real,
  but no page ties him to it. Caption: "Muse Spark · checks who they are".
- Words: a name the two listeners heard differently, fixed with one tap (in rehearsal, Margaux kept coming out
  as "Margot"). Caption: "Muse Spark Open · a second listener checks the names".

## The map, and why now (2:31–2:43)

Map, Tonight: the room from above, the dotted path from the door to the table, the times. Two seconds.
Map, All: the week, Kenji's ring in the middle, the five evenings as chips, one line from Chloé to Margaux.
The camera pushes in on the map slowly while Eric talks.

ERIC (over the map): Last year, the biggest companies bought wearables that remember your day. Four hundred and
ten people asked one of them to remember people. Then it was sold. Still unbuilt.

The why-now card, small, lower right, with its dates (On-screen text). Never say "never built": the board's
last snapshot is 2025-12-08.

## Why me, and the close (2:43–3:00)

Eric's room, morning light, to camera, phone in hand.

ERIC: Why me? I'm a one-person company. I'm the engineer, the salesman, and the guy who forgot Kenji's name.

Two seconds, fast: the repo scrolling, the test run going green, the four model names. The rules ask the video
to show the code too.

ERIC: One person. Nine days. Four Meta models.

He stands, clips the phone back on his chest, walks to the lit doorway.

ERIC: A one-person company's CEO can't also be the one who remembers.

Beat. He turns at the door.

ERIC: Hallwise can.

The badge, the name. Cut to black on the 8:00 buzz. End card.

[ERIC: confirm "one-person company" and the rest of this beat are true for you before the shoot; PITCH.md, part
4.]

---

## To do before the shoot

- Rig audio (`rig/v4/`):
  - Margaux's aside slower and as loud as her other lines, in `mac1-margaux-01.wav` (Julien's pair file keeps
    the same length).
  - Kenji's Japanese murmur cut from the end of `iphoneK-kenji-03.wav`.
  - LINES.md and CUES.md updated to match: the glasses lines added; Kenji's murmur and "It remembered him before
    I did" removed (that beat is now the morning's "It hadn't").
  - If the guests are re-rendered with library voices on a paid plan, the aside is re-rendered slower at the
    same time.
- New props and lines:
  - A second phone saved as "Lena" on the 17 Pro, to send the cold open's text; the 17 Pro's clock set so
    7:59 turns to 8:00 on camera, in the cold open and again the next morning.
  - Eric's new lines (the cold open, What's missing, why now, why me) added to LINES.md; none of them is cued.
  - A two-second screen capture of the repo, the test run going green, and the four model names.
  - Eric confirms the why-me lines are true for him (PITCH.md, part 4).
- Real-device checks: two real evenings in a row for "met before"; a photo with the real camera (below); the
  name card as the badge phone's lock-screen wallpaper.
- Reinstall the app on the badge phone within seven days of the shoot (the free signing expires).
- A Wednesday 14:00–15:30 "Board call" on the 17 Pro's calendar; deck and one-pager links set in the menu.
- The photo is optional. Keep it only if the real-camera test passes: one selfie with [FRIEND] at the sofa,
  after the introductions. SAM 3.1 finds the faces and Muse Spark says who is who, in about seven seconds.
  [FRIEND] has no face match unless they have said their own name in the take. Without the photo, Siddharth's
  and Kenji's faces come from earlier evenings (Muse Image portraits attached to those recordings), and
  Margaux and Julien stay dots. That is the point: people you know have faces; people you just met do not yet.

## Before the take

- Move every rehearsal recording of tonight's scene out of server/data/recordings into the scratchpad first, or
  tonight's guests come back as "met before". Keep the four dated evenings: they are the week.
- Badge phone: event "Living-room rehearsal" and venue cleared so the app fills them itself; words memory reset
  to "Hallwise" only; links set; Do Not Disturb; the badge on its mount so it can't spin; forward offset
  calibrated facing the camera.
- Server: the four rehearsed evenings present and dated; `/api/people` lists sixteen people; Kenji's history
  shows two encounters; started with HALLWISE_RESEARCH_CORPUS pointing at `rig/fictional-web.json`.
- Follow view: the Simulator on Mac-0 switched to follow mode on the new recording id as soon as Start is
  tapped (the dashboard shows it); screen recording running.
- Phone-L: Leo's two files loaded, at chest height outside the friend's door.
- Mac-3: the waiter file and Siddharth's file on separate presenter keys, in that order.
- Mac-0: output device set to HDMI, muted until the first click; presenter keys captured globally; Do Not
  Disturb; dashboard screen recording running.
- iPhone-K and Phone-L: auto-lock never, one tap to arm audio; every player shows a green heartbeat on the
  controller.
- Sync: Eric claps before the take starts; Mac-0 logs the clap.
- [FRIEND]: speaks English; keeps to their two lines.
- Rehearse the LIVE lines against `rig/v4/rehearsal-mix.mp3`, then once end to end in the room, and read the
  morning report before the final take.
- After the take, before the morning shot: in People, check that Margaux and Julien carry Corvane Capital (the
  check skips anyone without a company); accept the Margaux fix in Words; then tap "Write it now" on the
  morning report so the drafts and the checks use the corrected names.

## Risks

From the v4 pipeline check (CUES.md, 2026-10-27) and the rehearsals:
- "Une page" was lost in every run; only "avec des chiffres" came through, and only with the known names
  hinted. Hence the slower, louder aside. If "une page" is still lost, the morning draft quotes "avec des
  chiffres" only, and the payoff line changes to match.
- Margaux came out as "Margot" in every run. The one-tap fix in the morning turns it into a beat; if it is not
  fixed before the morning shot, her draft greets "Margot".
- Diarization sometimes merges two introductions that follow each other closely (Margaux into Julien,
  Siddharth into Kenji). Keep the gaps the v4 files carry; never cue over a guest's line.
- Diarization merged Leo and Kenji when both had young American base voices; Leo is now Roger, and the two stay
  apart.
- Mac-3 plays the waiter and then Siddharth: keep the three-second gap, or the waiter's line lands on
  Siddharth's label.
- The friend introduces from Eric's right, a step back from the Macs: two voices from one spot would merge.
- "Met before" now rings about a second after the introduction. Still let Kenji's ring come up before Eric's
  "Kenji! Of course".
- Every guest is fictional, so the live web has nothing on any of them. For the shoot the check reads a small
  invented web instead (`rig/fictional-web.json`, switched on with HALLWISE_RESEARCH_CORPUS): Muse Spark does
  the same check over those pages, and the on-screen note says they are invented. Corvane's team page lists
  Margaux and Chloé but not Julien, so he is the one flagged.
- On the chest, a dot's left or right is only rough, and front or back not at all. Never point at a dot's
  position in the edit or a caption.
- Live diarization must keep up in a noisy room; if not, use the replay fallback.
