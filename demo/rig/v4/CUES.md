# Rig cues, v4

Each device plays only its own files when the controller cues it. Eric and [FRIEND] speak live; their lines are
listed only as the prompt for the next cue. The TV (Mac-0 over HDMI) loops the old rig's `../tv-hall-bed.wav`
from click 1 ("They sound like this.") until Stop; it is not re-rendered.

Files: dry, mono, 48 kHz, 16-bit WAV (mp3 copies beside them for listening), levelled to -20 dBFS active speech,
0.15 s lead-in, 0.4 s tail. Set each device's volume in the room at Eric's marks, as for the old rig: Margaux a
little louder than Julien; Mac-3 and iPhone-K about 6 dB louder at the source than Mac-1/Mac-2.

**New device: Phone-L.** Leo Wong has no device in SCRIPT.md. Phone-L is any spare phone or laptop running the
rig player, at chest height by the friend's door (A), where [FRIEND] used to stand alone. It plays cues 1 and 2.

**Pairs (two devices, one click).** Cues 3, 4, 8 are each one exchange between two guests on two devices: one click starts both files
together. The two files of a pair have the same length; each carries silence where the other guest speaks, so
the rhythm of the rendered dialogue survives (start them within about 50 ms of each other). This replaces the old
rig's chained cues for these exchanges.

Rendered with ElevenLabs Eleven v4 (text-to-dialogue), built-in voices with an accent tag on every line (the
free plan refuses library voices through the API; see LINES.md): Leo Roger (built-in) `[strong Hong Kong Cantonese accent]`; Margaux Lily (built-in) `[strong French accent]`; Julien Callum (built-in) `[strong French accent]`; Waiter Jessica (built-in); Siddharth Chris (built-in) `[strong Indian accent]`; Kenji Liam (built-in) `[strong Japanese accent]`. Optional: [FRIEND]'s two lines in `optional/` (Will (built-in)), only if he cannot be there.

| Cue | Click | Device | File | Line | Eric says just before | Length |
|---|---|---|---|---|---|---|
| 0 | 1 | TV (Mac-0, HDMI) | `../tv-hall-bed.wav` | hall babble, loops until Stop | ERIC: "They sound like this." | loop |
| 1 | 2 | Phone-L (NEW: a spare phone at the friend's door, chest height) | `phoneL-leo-01.wav` | Eric! Hey, hey, you made it! Okay, okay. For your badge, yeah? Leo Wong. Bright Path. We do, uh... wallet infrastructure. For apps. | ERIC: "They sound like this." | 11.8 s |
| 2 | 3 | Phone-L (NEW: a spare phone at the friend's door, chest height) | `phoneL-leo-02.wav` | Tonight? Okay, okay. I'm holding you to that, ah. | ERIC: "Leo! Good to see you. I'm Eric, from Hallwise. This badge. I'll send you our deck tonight." | 5.3 s |
| 3 | 4 · **pair**: also starts `mac2-julien-01.wav` | Mac-1 (sofa 1, near cushion) | `mac1-margaux-01.wav` | Honestly... the deck yesterday? I did not understand their model. At all. Twenty slides! Une page, avec des chiffres... | [FRIEND]: "Eric, come. You should meet Margaux and Julien." | 21.2 s |
| 3 | 4 · **pair**: also starts `mac1-margaux-01.wav` | Mac-2 (sofa 1, far cushion) | `mac2-julien-01.wav` | Same. Twenty slides and, euh... zero numbers. Zero. Mm. Exactly. | [FRIEND]: "Eric, come. You should meet Margaux and Julien." | 21.2 s |
| 4 | 5 · **pair**: also starts `mac2-julien-02.wav` | Mac-1 (sofa 1, near cushion) | `mac1-margaux-02.wav` | Oh, of course! Margaux. Margaux Lefèvre, Corvane Capital. | ERIC: "Hi. Eric, from Hallwise. May I join you?" | 14.3 s |
| 4 | 5 · **pair**: also starts `mac1-margaux-02.wav` | Mac-2 (sofa 1, far cushion) | `mac2-julien-02.wav` | And I am Julien. Julien Caron, also Corvane. I do the, euh... the diligence. | ERIC: "Hi. Eric, from Hallwise. May I join you?" | 14.3 s |
| 5 | 6 | Mac-1 (sofa 1, near cushion) | `mac1-margaux-03.wav` | Pre-seed, yes. This quarter. Euh... send me your one-pager? One page, with numbers. Please. | ERIC: "Margaux, are you investing this quarter?" | 10.7 s |
| 6 | 7 | Mac-2 (sofa 1, far cushion) | `mac2-julien-03.wav` | And, euh... come by our office? Show us the demo. Wednesday afternoon? | ERIC: "One page, with numbers. Tomorrow." | 5.5 s |
| 7 | Mac-3 waiter key | Mac-3 (dining table, east end) | `mac3-01-waiter.wav` | Hi! Something to drink? | ERIC: "Wednesday works." (walking on) | 2.3 s |
| 8 | 8 · **pair**: also starts `iphoneK-kenji-01.wav` | Mac-3 (dining table, east end) | `mac3-02-siddharth.wav` | Eric! Hey! Siddharth. Siddharth Raghunathan, Quill Mesh? We met at Blockchain Week. You know Kenji, no? | at least 3 s after cue 7 ends; Eric at the table's west end, after ERIC: "I'm good, thanks." | 12.8 s |
| 8 | 8 · **pair**: also starts `mac3-02-siddharth.wav` | iPhone-K (sofa 2, south armrest, head height) | `iphoneK-kenji-01.wav` | Eric! We keep running into each other. | at least 3 s after cue 7 ends; Eric at the table's west end, after ERIC: "I'm good, thanks." | 12.8 s |
| 9 | 9 | iPhone-K (sofa 2, south armrest, head height) | `iphoneK-kenji-02.wav` | Kenji. Kenji Watanabe, Hoshizora Robotics? The hardware meetup? | ERIC: "Hey! It's, uh... sorry, it's been a long week..." | 6.5 s |
| 10 | 10 | iPhone-K (sofa 2, south armrest, head height) | `iphoneK-kenji-03.wav` | Thursday is... hmm. No... Friday. Friday is better. 金曜日ね、メモしておこう。 | ERIC: "Kenji! Of course, the hardware meetup. We still owe each other a coffee. Thursday?" | 10.0 s |

`rehearsal-mix.mp3` (166 s): every guest cue in story order, with silence where Eric or
[FRIEND] speaks (words / 2.6 per second + 0.8 s) and a few seconds where Eric walks. Say the LIVE lines from
LINES.md into the gaps.

From the pipeline check (these files with Eric's lines in a stand-in voice and the hall bed 22 dB under, streamed
mono through Muse Voice Transcribe and Muse Spark, 2026-10-27):

- With the known names hinted, as the app runs: all five people named (Margaux always spelled "Margot
  Lefevre"), all four promises, Friday replacing Thursday, both "met before" rings (Siddharth and Kenji, each
  within about a second of the end of their introduction) and the Chloé hook. The waiter was set aside.
- Kenji's murmur was lost in all five runs, although this file alone transcribes it exactly. Test cue 10 alone
  in the room, with iPhone-K close to Eric's mark (SCRIPT.md, Risks).
- Margaux's aside, with these pauses around it, came through as "Avec des chiffres" in both hinted runs (her
  draft was then written in French) and not at all with the hints off; "une page" was lost every time, and so
  was the whole aside when it sat tight between the lines at a whisper's level. Keep Mac-1 loud enough that her
  whisper carries.
- Diarization put Leo and Kenji on one speaker label when both were young American base voices; Leo is now
  Roger, and the two stay apart.
