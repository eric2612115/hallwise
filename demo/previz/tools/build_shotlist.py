#!/usr/bin/env python3
"""Builds demo/previz/shotlist.json and SHOTLIST.md.

The shot list is the single source for the previz animatic (src/ reads shotlist.json).
Every guest file length is probed from the real audio in public/audio, so a beat can
never be shorter than the file it plays. Times are seconds from the film's first frame.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "public" / "audio"
FFPROBE = "/opt/homebrew/bin/ffprobe"
FPS = 30
TOTAL = 180.0


def probe(name: str) -> float:
    out = subprocess.check_output(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(AUDIO / name)]
    )
    return round(float(out.decode().strip()), 2)


# ---------------------------------------------------------------------------
# The apartment. Metres; x runs east, y runs south (north is up on the plan).
# From SCRIPT.md "Room" and the floor plan in script-draft-v1.md, section 3.
# ---------------------------------------------------------------------------
PLAN = {
    "units": "metres; x east, y south; z up",
    "bounds": {"x0": 0, "y0": 0, "x1": 11, "y1": 8},
    "rooms": [
        {"id": "friend", "label": "FRIEND'S ROOM", "x0": 0, "y0": 0, "x1": 4, "y1": 4,
         "door": {"wall": "east", "from": 2.9, "to": 3.7, "label": "friend's door (A)"}},
        {"id": "eric", "label": "ERIC'S ROOM", "x0": 0, "y0": 4, "x1": 4, "y1": 8,
         "door": {"wall": "east", "from": 6.0, "to": 6.8, "label": "Eric's door"}},
        {"id": "living", "label": "LIVING ROOM", "x0": 4, "y0": 0, "x1": 11, "y1": 8, "door": None},
    ],
    "objects": [
        {"id": "bed", "label": "Bed", "x0": 0.5, "y0": 0.5, "x1": 2.5, "y1": 2.0, "h": 0.5},
        {"id": "ericSofa", "label": "Eric's sofa", "x0": 0.6, "y0": 5.0, "x1": 2.6, "y1": 5.9, "h": 0.45},
        {"id": "sofa1", "label": "Sofa 1 (B)", "x0": 5.6, "y0": 0.9, "x1": 9.0, "y1": 1.8, "h": 0.45},
        {"id": "table", "label": "Dining table (C)", "x0": 6.0, "y0": 4.3, "x1": 8.6, "y1": 5.3, "h": 0.75},
        {"id": "sofa2", "label": "Sofa 2 (D)", "x0": 10.1, "y0": 1.6, "x1": 10.9, "y1": 4.4, "h": 0.45},
    ],
    "devices": [
        {"id": "TV", "label": "TV · hall bed (Mac-0, HDMI)", "kind": "tv", "x": 7.1, "y": 0.12, "z": 1.25, "w": 3.0,
         "plays": "the hall bed, looped, from [click 1] to Stop"},
        {"id": "Mac-0", "label": "Mac-0 · server · follow view", "kind": "laptop", "x": 9.4, "y": 0.5, "z": 0.5,
         "plays": "nothing audible; runs the server, the dashboard and the rig controller"},
        {"id": "Phone-L", "label": "Phone-L · Leo", "kind": "phone", "x": 5.3, "y": 3.8, "z": 1.2,
         "plays": "Leo Wong (Bright Path), chest height just outside the friend's door"},
        {"id": "Mac-1", "label": "Mac-1 · Margaux", "kind": "laptop", "x": 6.4, "y": 1.3, "z": 0.5,
         "plays": "Margaux Lefèvre (Corvane Capital), sofa 1 near cushion"},
        {"id": "Mac-2", "label": "Mac-2 · Julien", "kind": "laptop", "x": 8.2, "y": 1.3, "z": 0.5,
         "plays": "Julien Caron (Corvane Capital), sofa 1 far cushion"},
        {"id": "Mac-3", "label": "Mac-3 · waiter → Siddharth", "kind": "laptop", "x": 8.8, "y": 4.8, "z": 0.8,
         "plays": "the waiter, then Siddharth Raghunathan (Quill Mesh), table east end"},
        {"id": "iPhone-K", "label": "iPhone-K · Kenji", "kind": "phone", "x": 10.5, "y": 4.55, "z": 1.2,
         "plays": "Kenji Watanabe (Hoshizora Robotics), sofa 2 south armrest, head height"},
    ],
    "marks": [  # Eric's marks, numbered in story order
        {"n": 1, "id": "bed", "label": "bed", "x": 1.5, "y": 1.25, "pose": "lie", "face": 0},
        {"n": 2, "id": "bedEdge", "label": "bed's edge", "x": 1.5, "y": 2.35, "pose": "sit", "face": 90},
        {"n": 3, "id": "doorInside", "label": "inside the door", "x": 3.4, "y": 3.3, "pose": "stand", "face": 0},
        {"n": 4, "id": "A", "label": "the door (A)", "x": 4.7, "y": 3.1, "pose": "stand", "face": 45},
        {"n": 5, "id": "B", "label": "sofa 1, west end (B)", "x": 5.0, "y": 1.5, "pose": "stand", "face": 0},
        {"n": 6, "id": "C", "label": "table, west end (C)", "x": 5.5, "y": 4.8, "pose": "stand", "face": 0},
        {"n": 7, "id": "ericDoor", "label": "his door", "x": 4.3, "y": 6.4, "pose": "stand", "face": 180},
        {"n": 8, "id": "ericSofa", "label": "his sofa", "x": 1.6, "y": 5.45, "pose": "lie", "face": 0},
    ],
    "friendSpots": [
        {"id": "knock", "label": "outside the friend's door", "x": 4.5, "y": 3.7, "face": 180},
        {"id": "byDoor", "label": "beside the door, north of Eric", "x": 4.6, "y": 2.3, "face": 135},
        {"id": "sofaRight", "label": "to Eric's right at the sofa, a step back", "x": 5.3, "y": 2.6, "face": 315},
    ],
    "cameraSpots": [
        {"id": "K1", "label": "K1 · top-down over the bed", "x": 2.9, "y": 1.25, "look": {"x": 1.5, "y": 1.25}, "topDown": True},
        {"id": "K2", "label": "K2 · eye level, at the bed's edge", "x": 1.5, "y": 3.6, "look": {"x": 1.5, "y": 2.35}},
        {"id": "K2b", "label": "K2 · over his shoulder at the door", "x": 2.6, "y": 3.0, "look": {"x": 4.4, "y": 3.3}},
        {"id": "K3", "label": "K3 · 2 m south-east of the door (A)", "x": 6.3, "y": 3.7, "look": {"x": 4.7, "y": 3.1}},
        {"id": "K4", "label": "K4 · a step south of sofa 1's east end", "x": 9.3, "y": 2.5, "look": {"x": 5.0, "y": 1.5}},
        {"id": "K5", "label": "K5 · beside Mac-3, the table's east end", "x": 9.4, "y": 4.2, "look": {"x": 5.5, "y": 4.8}},
        {"id": "K6", "label": "K6 · inside Eric's room, facing his door", "x": 3.0, "y": 6.4, "look": {"x": 4.3, "y": 6.4}},
        {"id": "K7", "label": "K7 · top-down over Eric's sofa (K1's framing)", "x": 1.6, "y": 6.6, "look": {"x": 1.6, "y": 5.45}, "topDown": True},
    ],
}

MARK = {m["id"]: m for m in PLAN["marks"]}
FSPOT = {s["id"]: s for s in PLAN["friendSpots"]}
CAM = {c["id"]: c for c in PLAN["cameraSpots"]}
# Angles: degrees, 0 = east, 90 = south, 180 = west, 270 = north (y runs south).
FACE_NAME = {0: "E", 45: "SE", 90: "S", 135: "SW", 180: "W", 225: "NW", 270: "N", 315: "NE"}

# File lengths, probed.
L = {n: probe(n) for n in [
    "phoneL-leo-01.wav", "phoneL-leo-02.wav", "mac1-margaux-01.wav", "mac2-julien-01.wav",
    "mac1-margaux-02.wav", "mac2-julien-02.wav", "mac1-margaux-03.wav", "mac2-julien-03.wav",
    "mac3-01-waiter.wav", "mac3-02-siddharth.wav", "iphoneK-kenji-00.wav", "iphoneK-kenji-01.wav",
    "iphoneK-kenji-02.wav", "iphoneK-kenji-03.wav", "tv-hall-bed.wav",
    "mac1-margaux-02a.wav", "mac1-margaux-02b.wav",
    "standin-eric-chloe-1.wav", "standin-eric-chloe-2.wav", "standin-eric-chloe-3.wav",
    "eric-03.wav", "eric-04.wav", "eric-05.wav", "eric-06.wav", "eric-08.wav", "eric-09.wav", "eric-11.wav",
    "say/eric-bed-1.wav", "say/eric-bed-2.wav", "say/friend-knock.wav", "say/eric-wear.wav", "say/friend-come.wav",
    "say/eric-whisper.wav", "say/friend-intro.wav", "say/eric-chloe.wav", "say/eric-itdoes.wav",
    "say/eric-japanese.wav", "say/eric-progress.wav", "buzz.wav",
]}

SOURCES = {
    "phoneL-leo-01.wav": "rehearsal-v5/cues/leo-01@alan", "phoneL-leo-02.wav": "rehearsal-v5/cues/leo-02@alan",
    "mac1-margaux-01.wav": "rehearsal-v5/cues/sofa-chat@fr1 (pair)", "mac2-julien-01.wav": "rehearsal-v5/cues/sofa-chat@fr1 (pair)",
    "mac1-margaux-02.wav": "rehearsal-v5/cues/sofa-intros@lison (pair)", "mac2-julien-02.wav": "rehearsal-v5/cues/sofa-intros@lison (pair)",
    "mac1-margaux-03.wav": "rehearsal-v5/cues/margaux-03@lison", "mac2-julien-03.wav": "rehearsal-v5/cues/julien-03@marcel",
    "mac3-01-waiter.wav": "rig/v4", "mac3-02-siddharth.wav": "rehearsal-v5/cues/table-intros@ruhaan (pair)",
    "iphoneK-kenji-00.wav": "rehearsal-v5/cues/kenji-call@taro", "iphoneK-kenji-01.wav": "rehearsal-v5/cues/table-intros@ruhaan (pair)",
    "iphoneK-kenji-02.wav": "rehearsal-v5/cues/kenji-02@taro",
    "iphoneK-kenji-03.wav": "rehearsal-v5/cues/kenji-03@taro, cut at 6.5 s (the murmur removed)",
    "tv-hall-bed.wav": "rig/tv-hall-bed.wav",
    "mac1-margaux-02a.wav": "rehearsal-v5/rig-v5 (CUES-additions, cue 5b)",
    "mac1-margaux-02b.wav": "rehearsal-v5/rig-v5 (CUES-additions, cue 5c)",
}


def line(at, who, text, dur, *, device="live", lang="en", english=None, audio=None, note=None, choice=False):
    d = {"at": round(at, 2), "end": round(at + dur, 2), "who": who, "device": device, "text": text, "lang": lang}
    if english:
        d["english"] = english
    if audio:
        d["audio"] = audio
    if note:
        d["note"] = note
    if choice:
        d["choice"] = True
    return d


def play(device, file, at, *, length=None, note=None):
    d = {"device": device, "file": file, "at": round(at, 2), "length": length if length is not None else L[file]}
    d["end"] = round(d["at"] + d["length"], 2)
    if file in SOURCES:
        d["source"] = SOURCES[file]
    if note:
        d["note"] = note
    return d


def ev(at, kind, label, device="badge"):
    return {"at": round(at, 2), "kind": kind, "label": label, "device": device}


# Helpers for stage directions.
def eric_at(mark, face=None, pose=None, action=""):
    m = MARK[mark]
    return {"mark": f"{m['n']} · {m['label']}", "markId": mark,
            "face": FACE_NAME.get(face if face is not None else m["face"], str(face)),
            "pose": pose or m["pose"], "action": action}


def eric_walk(a, b, t0, t1, face=None, pose=None, action=""):
    ma, mb = MARK[a], MARK[b]
    return {"mark": f"{ma['n']} → {mb['n']} · {ma['label']} → {mb['label']}", "markId": a, "toMarkId": b,
            "t0": t0, "t1": t1, "face": FACE_NAME.get(face if face is not None else mb["face"], str(face)),
            "pose": pose or mb["pose"], "action": action}


def friend_at(spot, action="", face=None):
    s = FSPOT[spot]
    return {"spot": s["label"], "spotId": spot, "face": FACE_NAME.get(face if face is not None else s["face"]), "action": action}


def friend_walk(a, b, t0, t1, action=""):
    return {"spot": f"{FSPOT[a]['label']} → {FSPOT[b]['label']}", "spotId": a, "toSpotId": b, "t0": t0, "t1": t1,
            "face": FACE_NAME.get(FSPOT[b]["face"]), "action": action}


def cam_at(spot, framing, look_at):
    return {"spot": CAM[spot]["label"], "spotId": spot, "framing": framing, "lookAt": look_at}


def cam_walk(a, b, t0, t1, framing, look_at):
    return {"spot": f"{CAM[a]['id']} → {CAM[b]['id']}: {CAM[b]['label']}", "spotId": a, "toSpotId": b,
            "t0": t0, "t1": t1, "framing": framing, "lookAt": look_at}


# ---------------------------------------------------------------------------
# The beats. Durations are chosen so that every kept file plays whole.
# ---------------------------------------------------------------------------
B = []

B.append(dict(
    id=1, key="bed", name="After every mixer", part="setup", temp="cold", duration=6.5,
    eric=eric_at("bed", action="On his back on the friend's bed, dressed for the party, the empty badge mount on his lanyard; both hands hold the phone over his face. He types into the blank reply, the grip slackens, the phone drops on the pillow beside his cheek."),
    friend=friend_at("knock", action="Off camera, outside the friend's door; knocks at +4.9 s."),
    camera=cam_at("K1", "Locked top-down over the bed (gimbal held overhead, or on an arm). Pillow to waist, the phone at centre; its glow the only light.", "Eric's face and the phone"),
    lines=[
        line(1.6, "Eric", "Great to meet you at... at...", L["say/eric-bed-1.wav"], audio="say/eric-bed-1.wav", note="muttered while typing"),
        line(3.6, "Eric", "...Yeah.", L["say/eric-bed-2.wav"], audio="say/eric-bed-2.wav", note="muffled, the phone on his face"),
        line(4.9, "Friend", "Eric! People are here.", L["say/friend-knock.wav"], audio="say/friend-knock.wav", note="through the door"),
    ],
    plays=[], bed=False,
    post=["Insert (the 17 Pro's screen): the blank reply 'Hi ___, great to meet you at ___! As promised, here's the ___'; he types K and deletes it",
          "Card: After every mixer.",
          "Sound: keyboard taps, the thud, then the party faint through the door"],
    proves="The failure is after the room: who, where, what you promised.",
))

B.append(dict(
    id=2, key="out", name="Out of the room", part="setup", temp="cold", hot_at=4.8, duration=6.0,
    extra_kf=[{"at": 0.3, "mark": "bed", "move": False}, {"at": 1.3, "mark": "bedEdge", "move": True}],
    eric=eric_walk("bedEdge", "doorInside", 2.2, 4.6, action="Sits up on the bed's edge, opens Hallwise and taps Start, clips the phone on his chest (screen out), walks to the door and opens it. The presenter in the same hand gives [click 1]; the hall bed hits. He holds at the threshold while the operator slips past (the edit cuts the wait)."),
    friend=friend_walk("knock", "byDoor", 0.0, 2.0, action="Steps back from the door to his spot beside it."),
    camera=cam_walk("K2", "K2b", 2.2, 4.6, "Eye level on Eric at the bed's edge, then over his shoulder as the door opens on the living room: the TV, the two Macs on the sofa, the table.", "Eric, then the open door"),
    lines=[line(0.5, "Eric", "So tonight, I wear this. I don't type a thing.", L["say/eric-wear.wav"], audio="say/eric-wear.wav", note="to camera, clipping the phone on")],
    plays=[play("TV", "tv-hall-bed.wav", 4.8, length=0.0, note="[click 1]: the TV unmutes as the door opens; the hall bed loops until Stop")],
    events=[ev(4.8, "click", "[click 1] · TV hall bed on", "TV")],
    bed=False,
    post=["Insert, 1 s: the side button, the lock screen, the name card 'Eric · Hallwise'",
          "Title over the open door: Hallwise · a name badge that remembers the room",
          "Sound: the room hits as the door swings"],
    proves="One phone, worn, nothing typed. Cold to hot in one cut.",
))

leo1, leo2 = L["phoneL-leo-01.wav"], L["phoneL-leo-02.wav"]
e03 = L["eric-03.wav"]
t_e = leo1 + 0.4
t_leo2 = t_e + e03 + 0.35
B.append(dict(
    id=3, key="door", name="The door: Leo", part="development", temp="hot", duration=23.3,
    eric=eric_at("A", action="Just outside the friend's door, facing south-east toward Phone-L at chest height (Leo's portrait on its screen); the TV behind his left shoulder. Presenter in hand."),
    friend=friend_at("byDoor", action="Beside the door, a step north of Eric, out of Phone-L's line; says nothing yet."),
    camera=cam_at("K3", "Medium on Eric, Phone-L in the foreground.", "Eric and Phone-L"),
    lines=[
        line(0.15, "Leo", "Eric! Hey, hey, you made it! Okay, okay. For your badge, yeah? Leo Wong. Bright Path. We do, uh... wallet infrastructure. For apps.", leo1 - 0.5, device="Phone-L"),
        line(t_e, "Eric", "Leo! Good to see you. I'm Eric, from Hallwise. This badge. I'll send you our deck tonight.", e03, audio="eric-03.wav"),
        line(t_leo2 + 0.15, "Leo", "Tonight? Okay, okay. I'm holding you to that, ah.", leo2 - 0.5, device="Phone-L"),
    ],
    plays=[play("Phone-L", "phoneL-leo-01.wav", 0.0, note="[click 2]"), play("Phone-L", "phoneL-leo-02.wav", t_leo2, note="[click 3]")],
    events=[ev(0.0, "click", "[click 2]", "Phone-L"), ev(t_leo2, "click", "[click 3]", "Phone-L")],
    bed=True,
    post=["Disclosure card, first 5 s: AI guests: voices by ElevenLabs, faces by Muse Image, their web pages invented. My friend and I are real.",
          "Panel: a grey dot → Leo Wong · Bright Path; promise: deck · tonight",
          "Caption: Muse Voice Transcribe · Muse Spark · a name and company from his own introduction"],
    proves="A person from what he said; a promise with a deadline (the deck he will owe).",
))

B.append(dict(
    id=4, key="walk-sofa", name="To the sofa", part="development", temp="hot", duration=3.3,
    eric=eric_walk("A", "B", 0.3, 3.1, action="Follows the friend north-east to the west end of sofa 1; turns to face east along it."),
    friend=friend_walk("byDoor", "sofaRight", 0.0, 3.0, action="Leads, saying the line; stops to Eric's right, a step back from the Macs. The line ends before [click 4]."),
    camera=cam_walk("K3", "K4", 0.0, 3.3, "Walks backwards along sofa 1's south side, keeping Eric in a medium shot.", "Eric"),
    lines=[line(0.0, "Friend", "Eric, come. You should meet Margaux and Julien.", L["say/friend-come.wav"], audio="say/friend-come.wav")],
    plays=[], bed=True,
    post=["The edit keeps only the tail of the friend's line under the cut to the sofa"],
    proves="",
))

fr = L["mac1-margaux-01.wav"]
B.append(dict(
    id=5, key="french", name="The French complaint", part="development", temp="hot", duration=16.0,
    eric=eric_at("B", action="West end of sofa 1, facing east along it: Mac-1 is the near cushion, the TV on his left. Not yet introduced: polite, glancing round; at the French, a lost half-smile toward the lens. He says nothing."),
    friend=friend_at("sofaRight", action="To Eric's right, a step back from the Macs."),
    camera=cam_at("K4", "Medium on Eric, both Macs' faces in the foreground; a slow push in during the French.", "Eric, Mac-1 and Mac-2"),
    lines=[
        line(0.22, "Margaux", "Franchement, le pitch d'hier... j'ai rien compris à leur modèle.", 5.08 - 0.22, device="Mac-1", lang="fr", english="Honestly, yesterday's pitch... I understood nothing of their model."),
        line(5.45, "Julien", "Vingt slides. Et pas un seul chiffre.", 8.39 - 5.45, device="Mac-2", lang="fr", english="Twenty slides. And not a single number."),
        line(8.39, "Margaux", "Vingt slides ! Moi, je veux une page. Une page, avec des chiffres. C'est tout.", 13.46 - 8.39, device="Mac-1", lang="fr", english="Twenty slides! Me, I want one page. One page, with numbers. That's all."),
        line(13.75, "Julien", "Mm. Exactement.", 15.43 - 13.75, device="Mac-2", lang="fr", english="Mm. Exactly."),
    ],
    plays=[play("Mac-1", "mac1-margaux-01.wav", 0.0, note="[click 4], pair: one click starts both files"),
           play("Mac-2", "mac2-julien-01.wav", 0.0, note="[click 4], pair")],
    events=[ev(0.0, "click", "[click 4] · pair", "Mac-1")],
    bed=True,
    post=["Panel: two grey dots light in turn; the lines carry nobody's name",
          "Subtitles: the French, with the English under it, tagged translated",
          "Caption: Muse Voice Transcribe · two voices, apart before anyone has a name"],
    proves="It catches what he can't: a complaint in French, before anyone has a name.",
))

B.append(dict(
    id=6, key="whisper", name="Silence. The whisper.", part="development", temp="cold", silence=True, duration=3.0,
    eric=eric_at("B", face=45, action="Turns to the lens (K4, east-south-east of him), a whisper gesture. Delivered in the gap after the exchange ends and before the friend introduces him; the edit makes it a stop in the middle of the conversation."),
    friend=friend_at("sofaRight", action="Freezes like a statue, for the laugh."),
    camera=cam_at("K4", "Holds the push-in: Eric fills the frame, the frozen friend behind him.", "Eric, to the lens"),
    lines=[line(0.3, "Eric", "I don't speak any French. At all.", L["say/eric-whisper.wav"], audio="say/eric-whisper.wav", note="whispered, to camera")],
    plays=[], bed=True,
    post=["Hard cut to near silence: only the whisper stays (the badge's recording through the voice isolator, or a clean pickup). No rig change: the hall bed keeps playing in the room",
          "The last French subtitle and its English stay on screen",
          "Backup: shoot a pickup of the aside on the same mark right after the take"],
    proves="The gag: he heard none of it. The badge did.",
))

B.append(dict(
    id=7, key="introduced", name="Introduced", part="development", temp="hot", duration=3.9,
    eric=eric_at("B", action="Turns back to the sofa. His 'Hi. Eric, from Hallwise. May I join you?' is still said in the take; the film cuts it."),
    friend=friend_at("sofaRight", action="Unfreezes and introduces him, from Eric's right, a step back from the Macs (two voices from one spot would merge)."),
    camera=cam_at("K4", "Widens a touch to take in the friend.", "Eric and the friend"),
    lines=[line(0.1, "Friend", "Margaux, Julien, this is Eric. He makes the badge.", L["say/friend-intro.wav"], audio="say/friend-intro.wav")],
    plays=[], bed=True,
    post=["Sound: the party crashes back in on the cut",
          "CUT from the film, kept in the take: ERIC 'Hi. Eric, from Hallwise. May I join you?' (3.1 s)"],
    proves="",
))

si = L["mac1-margaux-02.wav"]
B.append(dict(
    id=8, key="names", name="Names, and the Chloé link", part="development", temp="hot", duration=13.7,
    eric=eric_at("B", action="Listens. About a second after Margaux says her name the badge buzzes on his chest (live); he glances down, holds while Julien speaks."),
    friend=friend_at("sofaRight", action="Stays."),
    camera=cam_at("K4", "Medium; a tilt down to the badge on the buzz and back up.", "Eric, the badge on the buzz"),
    lines=[
        line(0.22, "Margaux", "Oh, of course! Margaux. Margaux Lefèvre, Corvane Capital.", 5.24 - 0.22, device="Mac-1"),
        line(6.84, "Julien", "And I am Julien. Julien Caron, also Corvane. I do the, euh... the diligence.", 13.12 - 6.84, device="Mac-2"),
    ],
    plays=[play("Mac-1", "mac1-margaux-02.wav", 0.0, note="[click 5], pair"), play("Mac-2", "mac2-julien-02.wav", 0.0, note="[click 5], pair")],
    events=[ev(0.0, "click", "[click 5] · pair", "Mac-1"),
            ev(6.3, "buzz", "LIVE · She may be Chloé's colleague · Blockchain Week, Oct 23")],
    bed=True,
    post=["Notification pop, from the live event log: She may be Chloé's colleague · Blockchain Week, Oct 23",
          "Panel: the two grey dots become Margaux and Julien, the same two voices as before",
          "Captions: Muse Spark · names from the introduction; Muse Spark · links Margaux to Chloé (Oct 23)"],
    proves="Names from the introduction, joined to another evening, about a second after she says her name. Eric called this one very important.",
))

c1, c2, c3 = L["standin-eric-chloe-1.wav"], L["standin-eric-chloe-2.wav"], L["standin-eric-chloe-3.wav"]
m2a, m2b = L["mac1-margaux-02a.wav"], L["mac1-margaux-02b.wav"]
t_2a = c1 + 0.3
t_c2 = t_2a + m2a + 0.3
t_2b = t_c2 + c2 + 0.3
t_c3 = t_2b + m2b + 0.3
B.append(dict(
    id=9, key="chloe", name="Do you know Chloé? The call.", part="development", temp="hot", duration=26.0,
    eric=eric_at("B", action="Asks straight away, to Margaux (Mac-1). Four exchanges, then a 1.5 s pause before 'Margaux, are you investing this quarter?' (cut from the film). In the take the exchange runs about 81.8 to 108.0 s."),
    friend=friend_at("sofaRight", action="Stays."),
    camera=cam_at("K4", "Medium on Eric and Mac-1; a touch closer on 'Small world'.", "Eric and Mac-1"),
    lines=[
        line(0.0, "Eric", "Margaux... do you know Chloé? Chloé Martin?", c1, audio="standin-eric-chloe-1.wav"),
        line(t_2a + 0.21, "Margaux", "Chloé? Of course! She's my colleague. How do you two know each other?", 5.39 - 0.21, device="Mac-1"),
        line(t_c2, "Eric", "We met at Blockchain Week, last Friday. She said you'd want to see what I'm building.", c2, audio="standin-eric-chloe-2.wav"),
        line(t_2b + 0.17, "Margaux", "Small world. Then let's do a call next week, the three of us. With Chloé.", 5.31 - 0.17, device="Mac-1"),
        line(t_c3, "Eric", "Perfect. I'll send an invite.", c3, audio="standin-eric-chloe-3.wav", note="then a 1.5 s pause"),
    ],
    plays=[play("Mac-1", "mac1-margaux-02a.wav", t_2a, note="[click 5b]"), play("Mac-1", "mac1-margaux-02b.wav", t_2b, note="[click 5c]")],
    events=[ev(t_2a, "click", "[click 5b]", "Mac-1"), ev(t_2b, "click", "[click 5c]", "Mac-1")],
    bed=True,
    post=["Panel: Margaux's row: Chloé's colleague · Corvane Capital; promise: a call next week, the three of us",
          "Caption: Muse Spark · a promise with a person attached (Chloé Martin)",
          "CUT from the film, kept in the take as a safety after the pause: ERIC 'Margaux, are you investing this quarter?' + Mac-1 mac1-margaux-03.wav (the English one-pager ask, 10.95 s) + ERIC 'One page, with numbers. Tomorrow.' (16.6 s)"],
    proves="He acts on the link in the room, not the next morning: a call with Chloé, promised live. Paid off by the calendar invite on his sofa.",
    choices=["The English one-pager ask (margaux-03) is cut from the film to pay for this exchange; it stays in the take after the pause so the morning draft keeps the explicit ask. Alternative: keep it and cut Leo's second line plus Eric's greeting to Leo."],
))

B.append(dict(
    id=10, key="waiter", name="Past the waiter: the buzz", part="turn", temp="hot", duration=4.3,
    eric=eric_walk("B", "C", 0.2, 4.0, action="Walks south past the table's west end; the waiter's line comes from Mac-3. At +3.0 the phone buzzes on his chest; he unclips it and looks while he walks: his deck is already one page, numbers first."),
    friend=friend_at("sofaRight", action="Stays at the sofa."),
    camera=cam_walk("K4", "K5", 0.0, 4.3, "Backs south to K5 beside Mac-3, holding Eric and the phone in his hand.", "Eric and the phone"),
    lines=[
        line(0.45, "Waiter", "Hi! Something to drink?", 1.9, device="Mac-3"),
        line(2.7, "Eric", "I'm good, thanks.", L["eric-08.wav"], audio="eric-08.wav", note="walking"),
    ],
    plays=[play("Mac-3", "mac3-01-waiter.wav", 0.3, note="Mac-3 waiter key; Mac-3 then stays silent at least 3 s")],
    events=[ev(3.0, "buzz", "the one-pager, made beforehand from the rehearsal recording, shown on cue")],
    bed=True,
    post=["Deck morph while he walks: the real 7 slides (demo/deck/render/slide-1..7.png) pressed into the real one-pager (onepager.png)",
          "Under it [CHOICE: placement]: Julien Caron · unverified: no public page ties him to Corvane · confirm before you send the deck",
          "The waiter's line stays in the take so Siddharth's label stays clean; the film keeps it as texture"],
    proves="The complaint he could not understand has already rebuilt his deck. The buzz lands about 50 s after the French ends.",
    choices=["Where the Julien-unverified flag appears: under the one-pager here (default), or in the connector card on his sofa."],
))

B.append(dict(
    id=11, key="itdoes", name="...It does.", part="turn", temp="hot", duration=2.0,
    eric=eric_at("C", face=0, action="At the table's west end; looks up from the one-pager to the lens."),
    friend=friend_at("sofaRight", action="Stays."),
    camera=cam_at("K5", "Close on Eric, the phone's screen in the bottom of frame.", "Eric, to the lens"),
    lines=[line(0.3, "Eric", "...It does.", L["say/eric-itdoes.wav"], audio="say/eric-itdoes.wav", note="to camera")],
    plays=[], bed=True,
    post=["Insert: the one-pager holds on screen"],
    proves="The turn: the film is about everything after the conversation.",
))

B.append(dict(
    id=12, key="xray", name="X-ray", part="turn", temp="cold", silence=True, xray=True, duration=8.0,
    eric=eric_at("C", action="Frozen (post). Nothing happens on set; the take runs on."),
    friend=friend_at("sofaRight", action="Frozen (post)."),
    camera=cam_at("K5", "Freeze-frame of the last shot.", "the frozen frame"),
    lines=[],
    plays=[], bed=True,
    xraySteps=["the four channels", "the voices around him", "Voice Transcribe hears French", "the edge finder catches it",
               "the check passes", "Spark rebuilds the deck", "the number check", "the buzz"],
    post=["Freeze-frame added in post (apps/replay X-ray mode): the film rewinds into the French complaint going through the machinery, 1 s a step",
          "Sound: the room drops out; a quiet machine pulse; then the room comes back"],
    proves="How: the French went through the machinery.",
))

kc = L["iphoneK-kenji-00.wav"]
B.append(dict(
    id=13, key="call", name="Kenji's call", part="after-the-turn", temp="hot", duration=8.6,
    eric=eric_at("C", action="At the table's west end, facing east toward Mac-3. A phone call in Japanese from sofa 2, behind his right shoulder; he half turns."),
    friend=friend_at("sofaRight", action="Stays."),
    camera=cam_at("K5", "Medium on Eric; iPhone-K at the right edge of frame.", "Eric and iPhone-K"),
    lines=[line(0.19, "Kenji", "あ、エリックさんが来た。前に話した、名札の人。…うん、うちのロボットの現場ログに使えるかもしれない。", 7.87 - 0.19, device="iPhone-K", lang="ja",
                english="Oh, Eric's here. The one I told you about, the name-badge guy. ...Yeah, it might work for our robots' field logs.")],
    plays=[play("iPhone-K", "iphoneK-kenji-00.wav", 0.0, note="[click 7], new in v5: Kenji on the phone, before Siddharth")],
    events=[ev(0.0, "click", "[click 7]", "iPhone-K")],
    bed=True,
    post=["Subtitles: the Japanese, with the English under it, tagged translated",
          "Panel: a grey dot, no name yet; the topic kept: field logs for robots",
          "Caption: Muse Voice Transcribe · a phone call, in Japanese"],
    proves="The seed of the connector: his topic, in a language Eric doesn't speak.",
))

B.append(dict(
    id=14, key="japanese", name="...Or Japanese.", part="after-the-turn", temp="cold", silence=True, duration=1.2,
    eric=eric_at("C", face=0, action="A glance at the lens (K5, east of him)."),
    friend=friend_at("sofaRight", action="Stays."),
    camera=cam_at("K5", "Holds.", "Eric, to the lens"),
    lines=[line(0.0, "Eric", "...Or Japanese.", L["say/eric-japanese.wav"], audio="say/eric-japanese.wav", note="to camera")],
    plays=[], bed=True,
    post=["One-second callback: silence, the glance"],
    proves="",
))

ti = L["mac3-02-siddharth.wav"]
B.append(dict(
    id=15, key="table", name="The table: Siddharth and Kenji", part="after-the-turn", temp="hot", duration=13.1,
    eric=eric_at("C", action="Facing east toward Mac-3; Kenji greets from the right."),
    friend=friend_at("sofaRight", action="Stays."),
    camera=cam_at("K5", "Medium on Eric, Mac-3 in the foreground.", "Eric and Mac-3"),
    lines=[
        line(0.18, "Siddharth", "Eric! Hey! Siddharth. Siddharth Raghunathan, Quill Mesh? We met at Blockchain Week. You know Kenji, no?", 8.0 - 0.18, device="Mac-3"),
        line(9.6, "Kenji", "Eric! We keep running into each other.", 12.49 - 9.6, device="iPhone-K"),
    ],
    plays=[play("Mac-3", "mac3-02-siddharth.wav", 0.0, note="[click 8], pair; at least 3 s after the waiter"),
           play("iPhone-K", "iphoneK-kenji-01.wav", 0.0, note="[click 8], pair")],
    events=[ev(0.0, "click", "[click 8] · pair", "Mac-3"), ev(9.0, "ring", "met before · Siddharth · Blockchain Week, Oct 23 · ETH Taipei afterparty, Oct 20")],
    bed=True,
    post=["Panel: Siddharth's dot ringed, met before, about a second after his introduction",
          "Caption: Muse Spark · met before"],
    proves="Memory across evenings, from the name he said.",
))

B.append(dict(
    id=16, key="fumble", name="The fumble", part="after-the-turn", temp="hot", duration=4.2,
    eric=eric_at("C", action="Plainly can't place Kenji. Let it be awkward; everyone has been there."),
    friend=friend_at("sofaRight", action="Stays."),
    camera=cam_at("K5", "Pushes in on his face.", "Eric's frozen smile"),
    lines=[line(0.1, "Eric", "Hey! It's, uh... sorry, it's been a long week...", L["eric-09.wav"], audio="eric-09.wav")],
    plays=[], bed=True,
    post=["Hold the awkward smile"],
    proves="He can't place him. The viewer will soon know what he has forgotten.",
))

B.append(dict(
    id=17, key="kenji", name="Kenji", part="after-the-turn", temp="hot", duration=6.4,
    eric=eric_at("C", action="Listens; the badge faces out and he never looks at it."),
    friend=friend_at("sofaRight", action="Stays."),
    camera=cam_at("K5", "Medium; iPhone-K in frame right.", "Eric and iPhone-K"),
    lines=[line(0.23, "Kenji", "Kenji. Kenji Watanabe, Hoshizora Robotics? The hardware meetup?", 5.7, device="iPhone-K")],
    plays=[play("iPhone-K", "iphoneK-kenji-02.wav", 0.0, note="[click 9]")],
    events=[ev(0.0, "click", "[click 9]", "iPhone-K"), ev(3.6, "ring", "met before · Kenji · Hardware meetup, Oct 22 · ETH Taipei afterparty, Oct 20")],
    bed=True,
    post=["Panel: Kenji ringed, met before · Hardware meetup, Oct 22 · ETH Taipei afterparty, Oct 20",
          "Caption: Muse Spark · met before, from the name he just said"],
    proves="It remembered him before Eric did.",
))

k3 = L["iphoneK-kenji-03.wav"]
t_k3 = 12.2 - k3
B.append(dict(
    id=18, key="coffee", name="Coffee: Thursday, no, Friday", part="after-the-turn", temp="hot", duration=12.2,
    eric=eric_at("C", action="Recovers; proposes Thursday."),
    friend=friend_at("sofaRight", action="Stays."),
    camera=cam_at("K5", "Medium on Eric and iPhone-K.", "Eric and iPhone-K"),
    lines=[
        line(0.0, "Eric", "Kenji! Of course, the hardware meetup. We still owe each other a coffee. Thursday?", L["eric-11.wav"], audio="eric-11.wav"),
        line(t_k3 + 0.23, "Kenji", "Thursday is... hmm. No... Friday. Friday is better.", 5.91 - 0.23, device="iPhone-K"),
    ],
    plays=[play("iPhone-K", "iphoneK-kenji-03.wav", t_k3, note="[click 10]; the file is cut at 6.5 s, the Japanese murmur removed")],
    events=[ev(t_k3, "click", "[click 10]", "iPhone-K"), ev(t_k3 + 5.9, "ring", "coffee · Thursday → Friday")],
    bed=True,
    post=["Panel: coffee with Kenji · Thursday struck through → Friday",
          "Caption: Muse Spark · promise corrected"],
    proves="The promise corrects itself.",
))

B.append(dict(
    id=19, key="stop", name="Stop", part="resolution", temp="cold", duration=2.8,
    eric=eric_walk("C", "ericDoor", 0.0, 2.2, action="Walks west along the table's south side to his own door; lifts the badge and taps Stop. The TV mutes on the same click. No line [CHOICE]."),
    friend=friend_at("sofaRight", action="Relaxes; stays out of the shot."),
    camera=cam_walk("K5", "K6", 0.0, 2.2, "Backs ahead of him along the table's south side, through Eric's door, turns to face it.", "Eric at his door"),
    lines=[],
    plays=[play("TV", "tv-hall-bed.wav", 2.2, length=0.0, note="[click 11]: Stop; the TV mutes")],
    events=[ev(2.2, "click", "[click 11] · Stop · TV off", "TV")],
    bed=True, bed_off_at=2.2,
    post=["The split frame ends on Stop; nothing from the morning yet",
          "Sound: the TV mutes on the click; room tone"],
    proves="The evening is over. Nothing has been typed.",
    choices=["Stop is silent (SCRIPT.md's 'That's it. I go home.' is dropped). Alternative: keep the line."],
))

B.append(dict(
    id=20, key="invite", name="The invite, on his sofa", part="resolution", temp="cold", duration=5.0,
    eric=eric_walk("ericDoor", "ericSofa", 0.0, 2.0, pose="lie", action="Drops onto his sofa on his back and holds the phone over his face: the hook's pose. The first thing on screen is the call he promised, already in his calendar."),
    friend=friend_at("sofaRight", action="Off camera."),
    camera=cam_walk("K6", "K7", 0.0, 2.0, "Then locked top-down over the sofa, the same height and framing as K1.", "Eric's face and the phone"),
    lines=[],
    plays=[],
    events=[ev(2.3, "buzz", "the invite: Call with Margaux and Chloé · Tue Nov 3, 11:00–11:30 · avoids your board call, Wed Nov 4 14:00–15:30")],
    bed=False,
    post=["Insert (the real rehearsal draft, shown on cue): a 30-minute call · Margaux Lefèvre and Chloé Martin (Corvane) · Tue Nov 3, 11:00–11:30 · reason: avoids Wed busy window and is in free time · avoids your board call, Wed Nov 4 14:00–15:30",
          "Draft: 'Margaux, lovely to join you tonight. As Chloé told me you'd want to see this, I'll send an invite for a call next week with you and Chloé. Would Tuesday at 11:00 work? / Eric'",
          "He taps Send [CHOICE]"],
    proves="'I'll send an invite' is already drafted, on a Tuesday slot that dodges the board call he forgot he had.",
    choices=["Whether Eric taps Send on camera. The slot and the text are the real rehearsal draft (Tue Nov 3, 11:00–11:30).",
             "The invite comes before the connector so the connector stays the ending."],
))

B.append(dict(
    id=21, key="connector", name="The connector", part="resolution", temp="cold", duration=8.5,
    eric=eric_at("ericSofa", action="Still on his back, the phone over his face. The connector's proposal, made beforehand from the rehearsal recording, is shown on cue. He taps Introduce; the grip slackens; he catches the phone an inch from his face."),
    friend=friend_at("sofaRight", action="Off camera."),
    camera=cam_at("K7", "Locked top-down over the sofa.", "Eric's face and the phone"),
    lines=[line(7.2, "Eric", "Progress.", L["say/eric-progress.wav"], audio="say/eric-progress.wav", note="deadpan [CHOICE: closing line]", choice=True)],
    plays=[],
    events=[ev(0.4, "buzz", "the connector: Kenji ↔ Ben Walker, made beforehand, shown on cue")],
    bed=False,
    post=["Insert: Introduce Kenji to Ben? · Ben Walker (Stride Mobility · Founder dinner, Oct 24) wants a small robot arm to pilot on his Taoyuan frame line · Kenji Watanabe (Hoshizora Robotics) builds them · Both at the Nangang hardware meetup, Thu Nov 5",
          "He taps Introduce. Callback: the blank reply's three blanks, now filled",
          "The near-drop and the catch"],
    proves="Everything after the conversation: an introduction toward a concrete collaboration, and next week's event, where the right person will be.",
    choices=["Closing line: 'Progress.' (hook #1's callback), or no line.",
             "The connector card's wording is a placeholder; the film shows the real proposal from the run (Ben's robot-arm line is in rig-v5/ben-walker-01.wav)."],
))

B.append(dict(
    id=22, key="end", name="End card", part="resolution", temp="cold", duration=2.0,
    eric=eric_at("ericSofa", action="Holds."),
    friend=friend_at("sofaRight", action="Off camera."),
    camera=cam_at("K7", "Cut to black on the buzz.", "the end card"),
    lines=[], plays=[], bed=False,
    post=["Hallwise · A name badge that remembers the room",
          "Built with Muse Voice Transcribe · Muse Spark · SAM 3.1 · Muse Spark Open on Baseten. Open source, AGPL-3.0"],
    proves="",
))

# ---------------------------------------------------------------------------
# Resolve times, check the arithmetic.
# ---------------------------------------------------------------------------
t = 0.0
for b in B:
    b["start"] = round(t, 2)
    t = round(t + b["duration"], 2)
    b["end"] = t
    for key in ("lines", "plays", "events"):
        for item in b.get(key, []):
            item["t"] = round(b["start"] + item["at"], 2)
            if "end" in item:
                item["tEnd"] = round(b["start"] + item["end"], 2)
    for p in b["plays"]:
        if p.get("placeholder") or p["length"] == 0.0:
            continue
        assert p["end"] <= b["duration"] + 1e-6, f"beat {b['id']}: {p['file']} ends at {p['end']} > beat {b['duration']}"
    for ln in b["lines"]:
        assert ln["end"] <= b["duration"] + 0.05, f"beat {b['id']}: line '{ln['text'][:30]}' ends at {ln['end']} > {b['duration']}"
assert abs(t - TOTAL) < 1e-6, f"total is {t}, not {TOTAL}"

# Keyframes for the three figures, from the stage directions.
# A keyframe with move=False is a step: the figure holds its previous position until then.
# A keyframe with move=True is reached by walking from the previous keyframe.
def emit(lst, t, x, y, move, **extra):
    k = {"t": round(t, 2), "x": x, "y": y, "move": bool(move), **extra}
    if lst and abs(lst[-1]["t"] - k["t"]) < 1e-6:
        k["move"] = k["move"] or lst[-1]["move"]  # an arrival keeps its walk
        lst[-1] = k
    else:
        lst.append(k)


def hold(lst, t):
    """Holds the figure where it is until t (so a later walk starts from here, not from the last keyframe)."""
    if lst and lst[-1]["t"] < t - 1e-6:
        last = dict(lst[-1])
        last["t"] = round(t, 2)
        last["move"] = False
        lst.append(last)


def differs(lst, x, y):
    return bool(lst) and (abs(lst[-1]["x"] - x) > 1e-6 or abs(lst[-1]["y"] - y) > 1e-6)


FACE_DEG = {v: k for k, v in FACE_NAME.items()}
eric_kf, friend_kf, cam_kf = [], [], []
for b in B:
    s = b["start"]
    for x in b.get("extra_kf", []):  # explicit sub-moves (Eric sits up before he walks)
        m = MARK[x["mark"]]
        emit(eric_kf, s + x["at"], m["x"], m["y"], x["move"], face=m["face"], pose=m["pose"])
    e = b["eric"]
    if "toMarkId" in e:
        a, c = MARK[e["markId"]], MARK[e["toMarkId"]]
        if e["t0"] > 0:
            hold(eric_kf, s)
        emit(eric_kf, s + e["t0"], a["x"], a["y"], differs(eric_kf, a["x"], a["y"]), face=a["face"], pose=a["pose"])
        emit(eric_kf, s + e["t1"], c["x"], c["y"], True, face=FACE_DEG.get(e["face"], c["face"]), pose=e["pose"])
    else:
        m = MARK[e["markId"]]
        emit(eric_kf, s, m["x"], m["y"], differs(eric_kf, m["x"], m["y"]), face=FACE_DEG.get(e["face"], m["face"]), pose=e["pose"])
    f = b["friend"]
    if "toSpotId" in f:
        a, c = FSPOT[f["spotId"]], FSPOT[f["toSpotId"]]
        if f["t0"] > 0:
            hold(friend_kf, s)
        emit(friend_kf, s + f["t0"], a["x"], a["y"], differs(friend_kf, a["x"], a["y"]), face=a["face"])
        emit(friend_kf, s + f["t1"], c["x"], c["y"], True, face=c["face"])
    else:
        sp = FSPOT[f["spotId"]]
        emit(friend_kf, s, sp["x"], sp["y"], differs(friend_kf, sp["x"], sp["y"]), face=FACE_DEG.get(f["face"], sp["face"]))
    c = b["camera"]
    if "toSpotId" in c:
        a, d = CAM[c["spotId"]], CAM[c["toSpotId"]]
        if c["t0"] > 0:
            hold(cam_kf, s)
        emit(cam_kf, s + c["t0"], a["x"], a["y"], differs(cam_kf, a["x"], a["y"]), look=a["look"], topDown=bool(a.get("topDown")), spot=a["id"])
        emit(cam_kf, s + c["t1"], d["x"], d["y"], True, look=d["look"], topDown=bool(d.get("topDown")), spot=d["id"])
    else:
        sp = CAM[c["spotId"]]
        emit(cam_kf, s, sp["x"], sp["y"], differs(cam_kf, sp["x"], sp["y"]), look=sp["look"], topDown=bool(sp.get("topDown")), spot=sp["id"])


def dedupe(kfs):
    return kfs

eric_kf, friend_kf, cam_kf = dedupe(eric_kf), dedupe(friend_kf), dedupe(cam_kf)

# The soundtrack for the previz: real guest files, the hall bed, stand-ins for the live lines, buzzes.
audio = []
for b in B:
    for p in b["plays"]:
        if p.get("placeholder") or p["length"] == 0.0:
            continue
        audio.append({"src": p["file"], "at": p["t"], "duration": p["length"], "volume": 1.0, "kind": "guest", "device": p["device"]})
    for ln in b["lines"]:
        if ln.get("audio"):
            audio.append({"src": ln["audio"], "at": ln["t"], "duration": round(ln["end"] - ln["at"], 2), "volume": 0.75,
                          "kind": "standin", "device": "live"})
    for evn in b.get("events", []):
        if evn["kind"] == "buzz":
            audio.append({"src": "buzz.wav", "at": evn["t"], "duration": L["buzz.wav"], "volume": 0.6, "kind": "sfx", "device": "badge"})

bed_on = next(b for b in B if b.get("hot_at") is not None)
bed_on_t = round(bed_on["start"] + bed_on["hot_at"], 2)
bed_off = next(b for b in B if b.get("bed_off_at") is not None)
bed_off_t = round(bed_off["start"] + bed_off["bed_off_at"], 2)
silences = [{"start": b["start"], "end": b["end"]} for b in B if b.get("silence")]

cut = [
    {"what": "The English one-pager ask: ERIC 'Margaux, are you investing this quarter?' + Mac-1 mac1-margaux-03.wav 'Pre-seed, yes... send me your one-pager? One page, with numbers. Please.' + ERIC 'One page, with numbers. Tomorrow.'",
     "seconds": 16.6,
     "why": "Pays for the Chloé exchange (+22.0 s). Not one of DIRECTION.md's surprises: the French complaint already carries 'une page, avec des chiffres', and the deck buzz works off it. Kept in the take as a safety, after the exchange's pause, so the morning draft keeps the explicit ask [CHOICE]."},
    {"what": "ERIC 'Hi. Eric, from Hallwise. May I join you?' (after the friend's introduction)", "seconds": 3.1,
     "why": "Texture; the friend's 'this is Eric. He makes the badge.' leads straight into 'Oh, of course! Margaux...'. Still said in the take."},
    {"what": "Trims: the bed −1.0, out of the room −0.5, the walk to the sofa −0.2, the whisper −0.5, past the waiter −0.7, Stop −0.2, end card −0.5, the aftermath re-cut (invite 5.0 + connector 8.5 for the old 12.3)",
     "seconds": 3.6, "why": "Gaps and walks, no line lost."},
    {"what": "Julien's demo invite: mac2-julien-03.wav 'And, euh... come by our office? Show us the demo. Wednesday afternoon?' + Eric's 'Wednesday works.'",
     "seconds": round(L["mac2-julien-03.wav"] + 1.2, 1),
     "why": "Already out in the first cut: its payoff (Wednesday 16:00) is not a DIRECTION.md surprise; the Julien-unverified flag rides the one-pager. Keep it in the take as a safety."},
    {"what": "Eric's 'It remembered him before I did.' (LINES.md #27)", "seconds": 2.3, "why": "Dropped by DIRECTION.md; the connector carries it."},
    {"what": "Kenji's Japanese murmur at the end of iphoneK-kenji-03.wav", "seconds": 3.5, "why": "Cut by DIRECTION.md; the file is trimmed at 6.5 s."},
    {"what": "SCRIPT.md's glasses opening, the wall of 'Speaker 2', Lena's text, the morning report, the map, the why-me talking head",
     "seconds": 0, "why": "Replaced by hook #1 (the blank reply), the live surprises, the invite and the connector; the four parts land by showing, not saying (DIRECTION.md)."},
]

choices = [
    "DECIDED: a third person operates the gimbal; [FRIEND] stays on camera and freezes for the whisper gag.",
    "DECIDED: the Chloé link is a full exchange (beat 9, 26.0 s): Eric asks, Margaux answers (mac1-margaux-02a.wav), Eric says where they met, Margaux proposes the call (mac1-margaux-02b.wav), Eric: 'Perfect. I'll send an invite.', 1.5 s pause.",
    "[CHOICE] To pay for it, the English one-pager ask (margaux-03 + Eric's two lines, 16.6 s) is cut from the film and kept in the take after the pause. Alternative: keep it and instead cut Leo's 'I'm holding you to that' (5.5 s), trim Eric's reply to Leo (−2.6 s) and shave the aftermath, which loses a laugh and cramps every beat.",
    "DECIDED: the invite is the real rehearsal draft: a 30-minute call, Tue Nov 3, 11:00–11:30 (reason: avoids Wed busy window and is in free time; the board call is Wed Nov 4 14:00–15:30). [CHOICE] whether Eric taps Send on camera.",
    "[CHOICE] The invite (beat 20, 5.0 s) comes before the connector (beat 21, 8.5 s), so the connector stays the ending. Alternative: connector first, invite as the last card.",
    "[CHOICE] The deck buzz now lands 49.6 s after the French ends (65.6 s after it starts) because the exchange sits between; DIRECTION.md asks for 40 to 60 s after the French.",
    "[CHOICE] The connector card's wording now uses Ben's dinner line (a small robot arm for the Taoyuan frame line, rig-v5/ben-walker-01.wav); the real proposal from the run replaces it. The meetup is Thu Nov 5 (Nov 5, 2026 is a Thursday).",
    "[CHOICE] Julien-unverified appears under the one-pager as the buzz lands (beat 10), not on the sofa at the end.",
    "[CHOICE] The waiter's line stays in the film as texture under the walk (SCRIPT.md cut it in the edit).",
    "[CHOICE] Stop is silent; 'That's it. I go home.' is dropped (beat 19).",
    "[CHOICE] Closing line 'Progress.' (hook #1's callback) on the catch (beat 21).",
    "[CHOICE] Kenji's ring comes 3.6 s into kenji-02, about a second after his name; the 'met before' for Siddharth 9 s into the table pair.",
    "[CHOICE] Cue numbers: [click 5b] and [click 5c] for the exchange (CUES-additions.md); [click 7]..[click 11] renumbered for v5 (Kenji's call added, Julien's invite out); the old cue 5 (margaux-03) becomes the safety cue after the pause. CUES.md still carries v4's numbers.",
    "[CHOICE] Previz soundtrack: real v5 guest files; Eric's unchanged lines use the rehearsal stand-in voice, the Chloé lines use rig-v5's stand-ins; new lines (bed, whisper, 'It does', 'Or Japanese', 'Progress.', the friend) use a macOS voice for timing only.",
    "[CHOICE] The friend stays at his sofa spot from beat 4 to the end; he has no further lines.",
]

shotlist = {
    "title": "Hallwise demo shoot · previz shot list",
    "date": "2026-10-29",
    "follows": ["demo/DIRECTION.md (wins)", "demo/SCRIPT.md: Cast, Room, Sound, Before the take", "demo/rig/v4/CUES.md, LINES.md", "scratchpad/script-draft-v1.md (hook #1, floor plan)"],
    "fps": FPS,
    "duration": TOTAL,
    "durationInFrames": int(round(TOTAL * FPS)),
    "parts": [
        {"id": "setup", "label": "Setup"}, {"id": "development", "label": "Development"}, {"id": "turn", "label": "Turn"},
        {"id": "after-the-turn", "label": "After the turn"}, {"id": "resolution", "label": "Resolution"},
    ],
    "plan": PLAN,
    "beats": B,
    "keyframes": {"eric": eric_kf, "friend": friend_kf, "camera": cam_kf},
    "audio": audio,
    "hallBed": {"src": "tv-hall-bed.wav", "on": bed_on_t, "off": bed_off_t, "volume": 0.16, "silences": silences},
    "fileLengths": {k: v for k, v in L.items() if not k.startswith("say/") and not k.startswith("eric-") and not k.startswith("standin-") and k != "buzz.wav"},
    "cut": cut,
    "choices": choices,
}

(ROOT / "shotlist.json").write_text(json.dumps(shotlist, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# SHOTLIST.md
# ---------------------------------------------------------------------------
def mmss(x):
    m = int(x // 60)
    s = x - 60 * m
    return f"{m}:{s:04.1f}"


PART_LABEL = {p["id"]: p["label"] for p in shotlist["parts"]}
md = []
md.append("# Hallwise demo shoot: previz shot list (3:00)\n")
md.append("Generated by `tools/build_shotlist.py` from `shotlist.json`, 2026-10-29. Follows `demo/DIRECTION.md` first, then `SCRIPT.md` (Cast, Room, Sound, Before the take), `rig/v4/CUES.md` and `LINES.md`, and the hook #1 draft. Every guest file length is probed from the real v5 audio, so no beat is shorter than the file it plays. Times are film time; the take runs longer (the edit trims the walks and the live gaps).\n")
md.append("Open items are marked **[CHOICE]**. Compass bearings are crew notes: nothing on screen says where anyone or anything is.\n")
md.append("## The arc\n")
md.append("| Part | Time | Beats | What it does |\n|---|---|---|---|")
arc_rows = {}
for b in B:
    arc_rows.setdefault(b["part"], []).append(b)
arc_text = {
    "setup": "The blank reply on the friend's bed; the badge goes on; the room hits.",
    "development": "The door (Leo), the sofa (Margaux, Julien): the French complaint, the whisper, the Chloé link live, the call with Chloé promised.",
    "turn": "Past the waiter the deck is already one page. '...It does.' The X-ray.",
    "after-the-turn": "The table: Kenji's Japanese call and '...Or Japanese.'; Siddharth and Kenji ringed; the fumble; Friday.",
    "resolution": "Stop. On his sofa: the invite (the call with Chloé, dodging the board call), then the connector: introduce Kenji to Ben, the Thu Nov 5 Nangang meetup. End card.",
}
for pid, rows in arc_rows.items():
    md.append(f"| {PART_LABEL[pid]} | {mmss(rows[0]['start'])}–{mmss(rows[-1]['end'])} | {rows[0]['id']}–{rows[-1]['id']} | {arc_text[pid]} |")
md.append("")
md.append("Cold and hot: " + ", ".join(f"{b['id']} {'cold' if b['temp']=='cold' else 'hot'}{' (→ hot at +%.1f s)' % b['hot_at'] if b.get('hot_at') else ''}" for b in B) + ".\n")

md.append("## The beats\n")
md.append("| Time | # | Beat | Part · temp | Eric (mark · facing) | Friend | Camera (spot · looks at) | Plays (device · file · s) | Post |")
md.append("|---|---|---|---|---|---|---|---|---|")
for b in B:
    temp = b["temp"] + (f" → hot at +{b['hot_at']}s" if b.get("hot_at") else "") + (" (silence in post)" if b.get("silence") else "")
    plays = "<br>".join(
        f"{p['device']} · {p['file']}" + (f" · {p['length']} s" if p.get("length") else "") + (f" · {p['note']}" if p.get("note") else "")
        for p in b["plays"]) or ("TV · hall bed (loop)" if b.get("bed") else "—")
    if b["plays"] and b.get("bed"):
        plays += "<br>TV · hall bed (loop)"
    post = "<br>".join(b["post"]) if b["post"] else "—"
    eric = f"**{b['eric']['mark']}** · faces {b['eric']['face']} · {b['eric']['pose']}<br>{b['eric']['action']}"
    friend = f"{b['friend']['spot']}<br>{b['friend']['action']}"
    cam = f"**{b['camera']['spot']}**<br>{b['camera']['framing']}<br>Looks at: {b['camera']['lookAt']}"
    md.append(f"| {mmss(b['start'])}–{mmss(b['end'])} ({b['duration']} s) | {b['id']} | **{b['name']}** | {PART_LABEL[b['part']]} · {temp} | {eric} | {friend} | {cam} | {plays} | {post} |")
md.append("")

md.append("## The lines, beat by beat\n")
md.append("Guest lines play from their device; LIVE lines are spoken in the room. Times are film time (beat start + offset).\n")
for b in B:
    md.append(f"### {b['id']} · {b['name']} · {mmss(b['start'])}–{mmss(b['end'])}")
    if b.get("proves"):
        md.append(f"*Proves:* {b['proves']}\n")
    if not b["lines"]:
        md.append("No lines." + (" X-ray steps, 1 s each: " + "; ".join(f"{i+1} {s}" for i, s in enumerate(b["xraySteps"])) + "." if b.get("xraySteps") else ""))
    for ln in b["lines"]:
        who = f"**{ln['who'].upper()}**" + (" (LIVE)" if ln["device"] == "live" else f" ({ln['device']})")
        tag = " **[CHOICE]**" if ln.get("choice") else ""
        text = ln["text"] if ln["lang"] == "en" else f"*{ln['text']}* — {ln['english']}"
        note = f" *({ln['note']})*" if ln.get("note") else ""
        md.append(f"- {mmss(ln['t'])} {who}: {text}{note}{tag}")
    for evn in b.get("events", []):
        if evn["kind"] != "click":
            md.append(f"- {mmss(evn['t'])} ⚡ {evn['kind'].upper()}: {evn['label']}")
    if b.get("choices"):
        for c in b["choices"]:
            md.append(f"- **[CHOICE]** {c}")
    md.append("")

md.append("## Does not fit in 3:00\n")
md.append("| What | Seconds | Why |\n|---|---|---|")
for c in cut:
    md.append(f"| {c['what']} | {c['seconds']} | {c['why']} |")
md.append("")

md.append("## Choices\n")
for c in choices:
    md.append(f"- {c}")
md.append("")

md.append("## File lengths used (probed)\n")
md.append("| File | Seconds | Source |\n|---|---|---|")
for k, v in shotlist["fileLengths"].items():
    md.append(f"| `{k}` | {v} | {SOURCES.get(k, '')} |")
md.append("")
guest_total = sum(v for k, v in shotlist["fileLengths"].items() if k not in ("tv-hall-bed.wav", "mac2-julien-03.wav", "mac1-margaux-03.wav"))
md.append(f"Guest audio kept in the film: {guest_total:.1f} s of {TOTAL:.0f}. The hall bed loops from {mmss(bed_on_t)} ([click 1]) to {mmss(bed_off_t)} (Stop); in post it drops to silence at " + ", ".join(f"{mmss(s['start'])}–{mmss(s['end'])}" for s in silences) + ".\n")

md.append("## Floor plan key\n")
md.append("Metres; x east, y south; north is up. Approximate: walk the path once empty-handed, the turns are tight.\n")
md.append("| Eric's marks | x, y | Facing |\n|---|---|---|")
for m in PLAN["marks"]:
    md.append(f"| {m['n']} · {m['label']} | {m['x']}, {m['y']} | {FACE_NAME.get(m['face'])} ({m['pose']}) |")
md.append("")
md.append("| Device | Spot | x, y, z |\n|---|---|---|")
for d in PLAN["devices"]:
    md.append(f"| {d['label']} | {d['plays']} | {d['x']}, {d['y']}, {d['z']} |")
md.append("")
md.append("| Camera | x, y | Looks at |\n|---|---|---|")
for c in PLAN["cameraSpots"]:
    md.append(f"| {c['label']} | {c['x']}, {c['y']} | {'straight down' if c.get('topDown') else str(c['look']['x']) + ', ' + str(c['look']['y'])} |")
md.append("")
md.append("| Friend | x, y |\n|---|---|")
for s in PLAN["friendSpots"]:
    md.append(f"| {s['label']} | {s['x']}, {s['y']} |")
md.append("")

(ROOT / "SHOTLIST.md").write_text("\n".join(md) + "\n", encoding="utf-8")

print(f"beats: {len(B)}  total: {t} s  frames: {shotlist['durationInFrames']}")
for b in B:
    print(f"  {b['id']:2d} {mmss(b['start'])}–{mmss(b['end'])} {b['duration']:5.1f}s  {b['part']:15s} {b['temp']:4s}  {b['name']}")
print(f"hall bed on {bed_on_t} off {bed_off_t}; audio clips: {len(audio)}")
