"""A small week on disk for the report tests: an earlier evening and tonight, in the shape the server logs."""

import json


def evening(root, rid, event, started, turns, people=(), promises=(), mentions=(), moves=(), owner="1:B", tz="Asia/Taipei",
            edges=()):
    d = root / "recordings" / rid
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({
        "id": rid, "event": event, "venue": "Taipei", "started": started, "owner_name": "Eric",
        "owner_company": "Hallwise", "tz": tz,
    }))
    lines = [{"type": "recording_start", "t_ms": 0}, {"type": "owner", "t_ms": 0, "speakers": [owner]}]
    for i, (speaker, text) in enumerate(turns, start=1):
        s, label = speaker.split(":")
        lines.append({"type": "turn", "t_ms": i * 1000, "turn": i, "speaker": label, "session": int(s), "text": text,
                      "start_ms": i * 1000 - 900, "end_ms": i * 1000})
        lines.append({"type": "turn_kind", "t_ms": i * 1000, "turn": i, "kind": "conversation"})
    for p in people:
        lines.append({"type": "person", "t_ms": 9000, "evidence_turns": [1], "introduced_by": "", "role": "",
                      "preferred_language": "", **p})
    for q in promises:
        lines.append({"type": "promise", "t_ms": 9000, "replaces": "", "due": "", **q})
    for m in mentions:
        lines.append({"type": "mention", "t_ms": 9000, "new": True, **m})
    for e in edges:
        lines.append({"type": "edge", "t_ms": 9000, "new": True, **e})
    for m in moves:
        lines.append({"type": "next_move", "t_ms": 9500, "kind": "email", "language": "English", "subject": "",
                      "body_english": "", "when": "", "duration_minutes": 30, "attach": "", "why": "", "nudge": "", **m})
    lines.append({"type": "recording_end", "t_ms": 10000})
    (d / "events.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n")


def week(root, now):
    """Oct 20: Eric promises Lena an introduction to Kenji. Oct 23: Chloé says her colleague Margaux would want to
    see this. Tonight: Margot Lefèvre (no company), who said "avec des chiffres" to herself, and Kenji again."""
    evening(
        root, "a-afterparty", "ETH Taipei afterparty", now - 7 * 86400,
        [("1:C", "Hi, I'm Lena Novak, Brightline Grid."), ("1:B", "You should meet Kenji."), ("1:C", "Please do."),
         ("1:B", "I'll introduce you two on Monday."), ("1:D", "Kenji Watanabe, Hoshizora Robotics.")],
        people=[{"key": "lena-novak-brightline-grid", "name": "Lena Novak", "company": "Brightline Grid", "speakers": ["1:C"]},
                {"key": "kenji-watanabe-hoshizora-robotics", "name": "Kenji Watanabe", "company": "Hoshizora Robotics", "speakers": ["1:D"],
                 "preferred_language": "Japanese"}],  # from a murmur, before asides stopped setting it
        promises=[{"key": "introduce-lena", "owed_by": "owner", "owed_to": "lena-novak-brightline-grid",
                   "what": "introduce you to Kenji", "due": "Monday", "evidence_turns": [4]}],
        mentions=[{"by": "owner", "name": "Kenji", "turn": 2}],
    )
    evening(
        root, "b-blockchain", "Blockchain Week side event", now - 4 * 86400,
        [("1:D", "Chloé Martin, Corvane Capital. My colleague Margaux is in Paris this week, but she'd want to see this."),
         ("1:B", "I'll send you both the one-pager.")],
        people=[{"key": "chloe-martin-corvane-capital", "name": "Chloé Martin", "company": "Corvane Capital", "speakers": ["1:D"]}],
        promises=[{"key": "one-pager-to-chloe", "owed_by": "owner", "owed_to": "chloe-martin-corvane-capital",
                   "what": "one-pager", "evidence_turns": [2]}],
        mentions=[{"by": "chloe-martin-corvane-capital", "name": "Margaux", "turn": 1}],
    )
    evening(
        root, "c-tonight", "Living-room rehearsal", now - 3600,
        [("1:C", "Margot Lefèvre."), ("1:B", "One page with numbers, tomorrow."), ("1:G", "Kenji Watanabe, we keep running into each other."),
         ("1:B", "Kenji, the coffee. Friday?"), ("1:C", "Avec des chiffres...")],
        people=[{"key": "margot-lefevre", "name": "Margot Lefèvre", "company": "", "speakers": ["1:C"]},
                {"key": "kenji-watanabe-hoshizora-robotics", "name": "Kenji Watanabe", "company": "Hoshizora Robotics", "speakers": ["1:G"]}],
        promises=[{"key": "one-pager-to-margot-lefevre", "owed_by": "owner", "owed_to": "margot-lefevre", "what": "one page with numbers",
                   "due": "tomorrow", "evidence_turns": [2]},
                  {"key": "coffee-to-kenji", "owed_by": "owner", "owed_to": "kenji-watanabe-hoshizora-robotics", "what": "coffee",
                   "due": "Friday", "evidence_turns": [4]}],
        edges=[{"person": "margot-lefevre", "turns": [5], "language": "French", "said": "Avec des chiffres", "english": "With numbers",
                "text": "Said to herself, in French: 'with numbers'.", "act": "one page, numbers first"}],
        moves=[{"promise_key": "one-pager-to-margot-lefevre", "person_key": "margot-lefevre",
                "body": "Hi Margot, one page with numbers, as promised. Eric", "remind_at": "2000-01-01T10:00:00+08:00"},
               {"promise_key": "coffee-to-kenji", "person_key": "kenji-watanabe-hoshizora-robotics", "kind": "calendar",
                "body": "Coffee Friday? Eric", "remind_at": "2999-01-01T09:00:00+08:00"}],
    )
