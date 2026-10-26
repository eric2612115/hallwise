# Rig cues

Each device plays only its own files, in its own order, when the controller cues it. Eric and [FRIEND] speak
live; their lines are listed only as the prompt for the next cue. The TV (Mac-0 over HDMI) loops
`tv-hall-bed.wav` from the first click (“They sound like this.”) until Stop.

Files are dry (no room added), mono, 48 kHz, 16-bit, levelled to -20 dBFS active speech with 0.15 s of lead-in.
Set each device's volume in the room, measured at Eric's marks: Margaux (near cushion) a little louder than
Julien (far cushion); Mac-3 (Siddharth) and iPhone-K (Kenji) about 6 dB louder at the source than Mac-1/Mac-2.
In rehearsal, at equal source level, the transcriber dropped their turns next to Eric's own voice at the badge.
Mac-3 plays the waiter, then waits at least three seconds before Siddharth (separate presenter keys).

Rendered by `server/scripts/make_party_audio.py` with Kokoro: Margaux `ff_siwis`; Julien `am_michael` for French and English; waiter `bf_emma`; Siddharth `hm_omega`; Kenji `jm_kumo`; hall bed eleven other voices (English and Mandarin).

Clicks follow SCRIPT.md's `[click]` marks; click 1 unmutes the TV. A chained cue fires by itself once the
previous file ends, so one click plays both halves of an exchange.

| Cue | Click | Device | File | Line | After | Length |
|---|---|---|---|---|---|---|
| 0 | 1 | TV (Mac-0, HDMI) | `tv-hall-bed.wav` | hall babble, 3:05, loops seamlessly until Stop | ERIC: “They sound like this.” | loop |
| 1 | 2 | Mac-1 (sofa 1, near cushion) | `mac1-margaux-01.wav` | Franchement, le deck d'hier, j'ai rien compris à leur modèle. | Eric stops at the sofa's west end; [FRIEND]: “Come, you should meet Margaux and Julien.” (live) | 3.6 s |
| 2 | auto, 1.0 s after the previous cue ends | Mac-2 (sofa 1, far cushion) | `mac2-julien-01.wav` | Pareil. Vingt slides, zéro chiffre. | cue 1 ends (Margaux) | 2.6 s |
| 3 | 3 | Mac-1 (sofa 1, near cushion) | `mac1-margaux-02.wav` | Margaux Lefèvre, Corvane Capital. | ERIC: “Hi. Eric, from Hallwise. May I join your conversation?” | 2.7 s |
| 4 | auto, 1.8 s after the previous cue ends | Mac-2 (sofa 1, far cushion) | `mac2-julien-02.wav` | Julien Caron. I'm with Margaux; I do the diligence. | cue 3 ends (Margaux) | 3.7 s |
| 5 | 4 | Mac-1 (sofa 1, near cushion) | `mac1-margaux-03.wav` | Pre-seed, yes. Send me your one-pager. Bon, une page, avec des chiffres. | ERIC: “Margaux, are you investing this quarter?” | 5.5 s |
| 6 | 5 | Mac-2 (sofa 1, far cushion) | `mac2-julien-03.wav` | Come by our office next week and show us the demo? Wednesday afternoon? | ERIC: “One page, with numbers. Tomorrow.” | 5.4 s |
| 7 | Mac-3 waiter key | Mac-3 (dining table, east end) | `mac3-01-waiter.wav` | Something to drink? | as Eric walks past the table's west end, after ERIC: “Wednesday works.” | 1.9 s |
| 8 | 6 | Mac-3 (dining table, east end) | `mac3-02-siddharth.wav` | Eric! Siddharth Raghunathan, Quill Mesh, we met at Blockchain Week. You know Kenji. | Eric at the table's west end, at least 3 s after cue 7; after ERIC: “I'm good, thanks.” | 5.7 s |
| 9 | auto, 1.5 s after the previous cue ends | iPhone-K (sofa 2, south armrest, head height) | `iphoneK-kenji-01.wav` | Kenji Watanabe, Hoshizora Robotics. We keep running into each other. | cue 8 ends (Siddharth) | 5.7 s |
| 10 | 7 | iPhone-K (sofa 2, south armrest, head height) | `iphoneK-kenji-02.wav` | Thursday is... no, Friday. Friday is better. 金曜日ね、メモしておこう。 | ERIC: “Kenji! The coffee. Thursday?” | 7.2 s |
