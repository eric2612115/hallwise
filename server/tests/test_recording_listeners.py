"""Inside a recording: the fast "met before", the second listener, and the transcriber's hints from earlier evenings."""

import asyncio
import json
import time

import numpy as np

from hallwise.asr import FakeAsr
from hallwise.events import read_events
from hallwise.extract import Extractor
from hallwise.recording import Hello, Recording
from hallwise.second import MAIN, OPEN, SecondListener


def earlier_evening(root, rid="early", started=None):
    """Oct 23 at Blockchain Week: Siddharth of Quill Mesh; Chloé of Corvane Capital; Kenji and Hana of Hoshizora."""
    d = root / "recordings" / rid
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"id": rid, "event": "Blockchain Week side event", "venue": "Taipei",
                                             "started": started or time.time() - 4 * 86400}))
    people = [("siddharth-raghunathan-quill-mesh", "Siddharth Raghunathan", "Quill Mesh"),
              ("chlo-martin-corvane-capital", "Chloé Martin", "Corvane Capital"),
              ("kenji-watanabe-hoshizora-robotics", "Kenji Watanabe", "Hoshizora Robotics"),
              ("hana-sato-hoshizora-robotics", "Hana Sato", "Hoshizora Robotics")]
    lines = [{"type": "recording_start", "t_ms": 0}] + [
        {"type": "person", "t_ms": 1000, "key": k, "name": n, "company": c, "role": "", "speakers": [],
         "preferred_language": "", "introduced_by": "", "evidence_turns": [1]} for k, n, c in people]
    (d / "events.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))


def state(people=(), promises=(), owner=("1:B",)):
    return {"owner_speakers": list(owner), "turns": [], "people": list(people), "mentioned": [],
            "promises": list(promises), "suspect_words": [], "translations": [], "room_topics": []}


def sid(speakers=("1:F",), key="siddharth-raghunathan-quill-mesh", name="Siddharth Raghunathan"):
    return {"key": key, "name": name, "company": "Quill Mesh", "role": "", "speakers": list(speakers),
            "preferred_language": "", "introduced_by": "", "evidence_turns": [2]}


class SlowSpark:
    """Muse Spark that takes a while, as it does: the fast path has to beat it."""

    def __init__(self, *results, delay=0.05):
        self.results, self.delay, self.prompts = list(results), delay, []

    async def __call__(self, system, user, **kw):
        self.prompts.append(user)
        await asyncio.sleep(self.delay)
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


SCRIPT = [
    {"start_ms": 200, "end_ms": 900, "speaker": "B", "text": "I'm Eric, from Hallwise."},
    {"start_ms": 1000, "end_ms": 2400, "speaker": "F", "text": "Eric! Siddharth Raghunathan, Quill Mesh, we met at Blockchain Week."},
    {"start_ms": 2600, "end_ms": 3000, "speaker": "B", "text": "Of course! Good to see you."},
]


def record(tmp_path, spark, make_second=None, script=SCRIPT, seconds=3.5):
    hello = Hello(sample_rate=24_000, channels=1, layout="mono", owner_name="Eric", owner_company="Hallwise",
                  fake_script=script)

    def make_asr(sink, *, rate, hello):
        return FakeAsr(sink, rate=rate, script=hello.fake_script)

    rec = Recording(tmp_path, hello, make_asr, lambda h: Extractor(spark, h.owner_name, h.owner_company, h.keywords or []),
                    make_second=make_second)

    async def run():
        await rec.start()
        audio = np.zeros(int(24_000 * seconds), dtype=np.int16).tobytes()
        for i in range(0, len(audio), 4800):
            await rec.on_audio(audio[i:i + 4800])
            await asyncio.sleep(0.01)
        await rec.close()

    asyncio.run(run())
    return read_events(rec.dir / "events.jsonl")


def test_a_known_guest_is_ringed_the_moment_he_says_his_name_and_spark_confirms_it(tmp_path):
    earlier_evening(tmp_path)
    events = record(tmp_path, SlowSpark(state(), state(people=[sid()])), make_second=lambda: None)
    types = [e["type"] for e in events]
    first = types.index("person_history")
    provisional = events[first]
    assert provisional["provisional"] is True and provisional["speaker"] == "1:F" and provisional["turn"] == 2
    assert provisional["key"] == "siddharth-raghunathan-quill-mesh"
    assert [x["event"] for x in provisional["encounters"]] == ["Blockchain Week side event"]
    # right behind his turn, before Muse Spark has named anyone
    assert types[first - 1] in ("turn", "position") and "person" not in types[:first]
    assert provisional["t_ms"] - next(e for e in events if e["type"] == "turn" and e["turn"] == 2)["end_ms"] < 500
    # then Spark names him for that voice, and the ring stays, confirmed
    confirmed = [e for e in events if e["type"] == "person_history" and not e.get("provisional")]
    assert [e["key"] for e in confirmed] == ["siddharth-raghunathan-quill-mesh"]
    assert types.index("person") < events.index(confirmed[0])
    assert "person_history_removed" not in types


def test_spark_naming_someone_else_for_that_voice_takes_the_ring_away(tmp_path):
    earlier_evening(tmp_path)
    tomas = {**sid(), "key": "tomas-ferreira", "name": "Tomás Ferreira", "company": "Marlin Ventures"}
    events = record(tmp_path, SlowSpark(state(), state(people=[tomas])), make_second=lambda: None)
    removed = [e for e in events if e["type"] == "person_history_removed"]
    assert [(e["key"], e["speaker"]) for e in removed] == [("siddharth-raghunathan-quill-mesh", "1:F")]
    assert removed[0]["reason"] == "Muse Spark heard Tomás Ferreira for this voice"
    assert [e for e in events if e["type"] == "person_history" and not e.get("provisional")] == []


def test_a_ring_spark_never_confirms_is_withdrawn_before_the_drafts(tmp_path):
    earlier_evening(tmp_path)
    events = record(tmp_path, SlowSpark(state()), make_second=lambda: None)
    types = [e["type"] for e in events]
    assert "person_history_removed" in types
    assert types.index("person_history_removed") < types.index("recording_end")


class FakeOpen:
    def __init__(self, result):
        self.result, self.prompts = result, []
        self.last_usage = {"prompt_tokens": 900, "completion_tokens": 800, "total_tokens": 1700,
                           "completion_tokens_details": {"reasoning_tokens": 600}}
        self.last_seconds = 3.1

    async def __call__(self, system, user, schema=None, name=""):
        self.prompts.append(user)
        await asyncio.sleep(0.01)
        return self.result


def test_the_second_listener_hears_the_same_transcript_and_its_verdicts_land_in_the_log(tmp_path):
    earlier_evening(tmp_path)
    deck = {"key": "deck-to-siddharth", "owed_by": "owner", "owed_to": "siddharth-raghunathan-quill-mesh",
            "what": "send the deck", "due": "tonight", "replaces": "", "evidence_turns": [3]}
    spark = SlowSpark(state(people=[sid()], promises=[deck]), delay=0.01)
    other = FakeOpen({
        "people": [{"name": "Siddharth Ragunathan", "company": "Quill Mesh", "speakers": ["1:F"]}],
        "promises": [{"owed_by": "owner", "owed_to": "Siddharth Ragunathan", "what": "the deck", "due": "tonight", "turn": 3}],
        "suspect_words": [],
    })
    second = SecondListener(other, every=1, min_gap_s=0, max_calls=5)
    events = record(tmp_path, spark, make_second=lambda: second)
    runs = [e for e in events if e["type"] == "second_run"]
    assert runs and runs[-1]["final"] is True and runs[-1]["upto_turn"] == 3
    assert runs[0]["usage"]["total_tokens"] == 1700 and runs[0]["model"] == OPEN
    extraction = [p for p in spark.prompts if p.startswith("Owner:") and "Vocabulary" in p]
    assert other.prompts[-1] == extraction[-1]  # the very transcript Muse Spark read
    assert [(e["kind"], e["key"], e["by"]) for e in events if e["type"] == "confirmed"] == [
        ("promise", "deck-to-siddharth", [MAIN, OPEN])]
    # The fakes answer the same at every run, so Open "heard" the deck before Spark's evidence for it was in range:
    # raised once, withdrawn when the two agreed on it. The surname stays in dispute.
    raised = {e["id"]: e for e in events if e["type"] == "disagreement"}
    gone = {e["id"] for e in events if e["type"] == "disagreement_removed"}
    assert gone == {"promise:open-the-deck-siddharth-raghunathan-quill-mesh:exists"}
    (d,) = [d for i, d in raised.items() if i not in gone]
    assert (d["id"], d["a"]["text"], d["b"]["text"]) == (
        "person:siddharth-raghunathan-quill-mesh:name", "Siddharth Raghunathan", "Siddharth Ragunathan")
    assert [e["type"] for e in events][-1] == "recording_end"


def test_a_broken_second_listener_changes_nothing_on_the_main_path(tmp_path):
    class Broken(FakeOpen):
        async def __call__(self, *a, **k):
            raise RuntimeError("Baseten is down")

    spark = SlowSpark(state(people=[sid()]), delay=0.01)
    events = record(tmp_path, spark, make_second=lambda: SecondListener(Broken({}), every=1, min_gap_s=0))
    assert [e["key"] for e in events if e["type"] == "person"] == ["siddharth-raghunathan-quill-mesh"]
    assert {e["type"] for e in events if e["type"].startswith("second")} == {"second_error"}
    assert events[-1]["type"] == "recording_end"


def test_the_transcriber_hears_earlier_names_then_their_companies(tmp_path):
    earlier_evening(tmp_path)
    got = {}

    def make_asr(sink, *, rate, hello):
        got["keywords"] = list(hello.keywords)
        return FakeAsr(sink, rate=rate)

    Recording(tmp_path, Hello(sample_rate=24_000, channels=1, layout="mono", keywords=["Hallwise"]), make_asr)
    words = got["keywords"]
    assert words[0] == "Hallwise"  # the badge's own hints first
    names = ["Siddharth Raghunathan", "Chloé Martin", "Kenji Watanabe", "Hana Sato"]
    companies = ["Quill Mesh", "Corvane Capital", "Hoshizora Robotics"]
    assert sorted(words[1:5]) == sorted(names)  # names before companies
    assert sorted(words[5:]) == sorted(companies)  # each company once
