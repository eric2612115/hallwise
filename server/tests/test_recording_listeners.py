"""Inside a recording: the fast "met before", the edge finder, and the transcriber's hints from earlier evenings."""

import asyncio
import json
import time

import numpy as np

from hallwise.asr import FakeAsr
from hallwise.events import read_events
from hallwise.extract import Extractor
from hallwise.recording import Hello, Recording
from hallwise.edge_finder import OPEN, EdgeFinder
from hallwise.extract import SCHEMA_NO_EDGES, SYSTEM, SYSTEM_NO_EDGES


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


def record(tmp_path, spark, make_edge_finder=None, script=SCRIPT, seconds=3.5):
    hello = Hello(sample_rate=24_000, channels=1, layout="mono", owner_name="Eric", owner_company="Hallwise",
                  fake_script=script)

    def make_asr(sink, *, rate, hello):
        return FakeAsr(sink, rate=rate, script=hello.fake_script)

    rec = Recording(tmp_path, hello, make_asr, lambda h: Extractor(spark, h.owner_name, h.owner_company, h.keywords or []),
                    make_edge_finder=make_edge_finder)

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
    events = record(tmp_path, SlowSpark(state(), state(people=[sid()])), make_edge_finder=lambda: None)
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
    events = record(tmp_path, SlowSpark(state(), state(people=[tomas])), make_edge_finder=lambda: None)
    removed = [e for e in events if e["type"] == "person_history_removed"]
    assert [(e["key"], e["speaker"]) for e in removed] == [("siddharth-raghunathan-quill-mesh", "1:F")]
    assert removed[0]["reason"] == "Muse Spark heard Tomás Ferreira for this voice"
    assert [e for e in events if e["type"] == "person_history" and not e.get("provisional")] == []


def test_a_ring_spark_never_confirms_is_withdrawn_before_the_drafts(tmp_path):
    earlier_evening(tmp_path)
    events = record(tmp_path, SlowSpark(state()), make_edge_finder=lambda: None)
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


class Spark(SlowSpark):
    """Muse Spark that writes one draft at Stop and remembers how it was asked: with or without edges."""

    def __init__(self, *results, edges=()):
        super().__init__(*results, delay=0.01)
        self.asked: list[str] = []  # with_edges, no_edges or drafts, call by call
        self.edges = list(edges)

    async def __call__(self, system, user, **kw):
        if kw.get("name") == "hallwise_next_moves":
            self.asked.append("drafts")
            return {"moves": [{"promise_key": "deck-to-siddharth", "person_key": "siddharth-raghunathan-quill-mesh",
                               "kind": "email", "language": "English", "subject": "Deck", "body": "Here it is. Eric",
                               "body_english": "", "when": "", "duration_minutes": 0, "attach": "", "why": ""}]}
        out = dict(await super().__call__(system, user, **kw))
        if system == SYSTEM_NO_EDGES:
            assert kw.get("schema") is SCHEMA_NO_EDGES
            self.asked.append("no_edges")
        else:
            assert system == SYSTEM and "schema" not in kw
            self.asked.append("with_edges")
            out["edges"] = [dict(e) for e in self.edges]
        return out


DECK = {"key": "deck-to-siddharth", "owed_by": "owner", "owed_to": "siddharth-raghunathan-quill-mesh",
        "what": "send the deck", "due": "tonight", "replaces": "", "evidence_turns": [3]}
WEEK = {"person": "siddharth-raghunathan-quill-mesh", "turns": [2], "language": "English", "said": "we met at Blockchain Week",
        "english": "we met at Blockchain Week", "text": "Reminded you where you met.", "act": "mention Blockchain Week"}


def test_the_edge_finder_reads_spark_s_transcript_and_its_edges_reach_the_record_before_the_drafts(tmp_path):
    earlier_evening(tmp_path)
    spark = Spark(state(people=[sid()], promises=[DECK]))
    other = FakeOpen({"edges": [WEEK, {**WEEK, "said": "words nobody said"}, {**WEEK, "person": "a-stranger"}]})
    events = record(tmp_path, spark, make_edge_finder=lambda: EdgeFinder(other, every=1, min_gap_s=0, max_calls=5))
    assert set(spark.asked) == {"no_edges", "drafts"}  # Spark looked for no edges itself
    runs = [e for e in events if e["type"] == "second_run"]
    assert runs and runs[-1]["final"] is True and runs[-1]["upto_turn"] == 3 and runs[-1]["role"] == "edge_finder"
    assert runs[0]["usage"]["total_tokens"] == 1700 and runs[0]["model"] == OPEN and runs[0]["edges"] == 3
    extraction = [p for p in spark.prompts if p.startswith("Owner:") and "Vocabulary" in p]
    assert other.prompts[-1].startswith(extraction[-1] + "\n\nPeople the owner has met tonight")  # the very transcript
    # only the edge the transcript backs, once, under Spark's key; and it is in the picture the drafts were written from
    edges = [e for e in events if e["type"] == "edge"]
    assert [(e["person"], e["said"]) for e in edges] == [("siddharth-raghunathan-quill-mesh", "we met at Blockchain Week")]
    types = [e["type"] for e in events]
    assert max(i for i, t in enumerate(types) if t == "second_run") < types.index("next_move")
    assert not {"confirmed", "disagreement"} & set(types)
    assert types[-1] == "recording_end"


def test_a_broken_edge_finder_hands_the_edges_back_to_spark(tmp_path):
    class Broken(FakeOpen):
        async def __call__(self, *a, **k):
            raise RuntimeError("Baseten is down")

    spark = Spark(state(people=[sid()]), edges=[WEEK])
    events = record(tmp_path, spark, make_edge_finder=lambda: EdgeFinder(Broken({}), every=1, min_gap_s=0))
    assert [e["key"] for e in events if e["type"] == "person"] == ["siddharth-raghunathan-quill-mesh"]
    assert {e["type"] for e in events if e["type"].startswith("second")} == {"second_error"}
    assert spark.asked[0] == "no_edges" and spark.asked[-1] == "with_edges"  # after the failure, Spark finds them
    assert [e["said"] for e in events if e["type"] == "edge"] == ["we met at Blockchain Week"]
    assert events[-1]["type"] == "recording_end"


def test_without_the_edge_finder_spark_finds_the_edges(tmp_path):
    spark = Spark(state(people=[sid()]), edges=[WEEK])
    events = record(tmp_path, spark, make_edge_finder=lambda: None)
    assert set(spark.asked) == {"with_edges"}
    assert [e["said"] for e in events if e["type"] == "edge"] == ["we met at Blockchain Week"]


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


def test_names_said_at_earlier_evenings_join_the_hints_after_the_people_met(tmp_path):
    """Chloé said "my colleague Margaux" on Oct 23; Margaux came out "Margot" in every run until her name was a hint."""
    earlier_evening(tmp_path)
    d = tmp_path / "recordings" / "early" / "events.jsonl"
    d.write_text(d.read_text() + "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in [
        {"type": "turn", "t_ms": 2000, "turn": 2, "speaker": "D", "session": 1, "start_ms": 1000, "end_ms": 2000,
         "text": "Chloé Martin, Corvane Capital. My colleague Margaux would want to see this."},
        {"type": "mention", "t_ms": 2000, "name": "Margaux", "by": "chlo-martin-corvane-capital", "turn": 2},
        {"type": "mention", "t_ms": 2000, "name": "Kenji", "by": "chlo-martin-corvane-capital", "turn": 2},  # met: there
        {"type": "mention", "t_ms": 2000, "name": "Wei Ling", "by": "owner", "turn": 2},  # the owner's own: not a hint
    ]))
    got = {}

    def make_asr(sink, *, rate, hello):
        got["keywords"] = list(hello.keywords)
        return FakeAsr(sink, rate=rate)

    Recording(tmp_path, Hello(sample_rate=24_000, channels=1, layout="mono", keywords=["Hallwise"]), make_asr)
    words = got["keywords"]
    assert words.index("Margaux") > max(words.index(n) for n in ("Siddharth Raghunathan", "Chloé Martin", "Kenji Watanabe"))
    assert words.index("Margaux") < min(words.index(c) for c in ("Quill Mesh", "Corvane Capital"))
    assert "Kenji" not in words and "Wei Ling" not in words


def test_the_mentioned_names_are_bounded_and_newest_first():
    from hallwise.recording import MAX_HINT_MENTIONS, recognition_hints

    index = [{"name": "Chloé Martin", "company": "Corvane Capital"}]
    mentioned = [f"Name{i}" for i in range(15)] + ["Chloé", "Name0"]
    words = recognition_hints(["Hallwise"], index, [], mentioned)
    assert words == ["Hallwise", "Chloé Martin", *[f"Name{i}" for i in range(MAX_HINT_MENTIONS)], "Corvane Capital"]
