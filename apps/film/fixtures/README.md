# Fixtures

The small inputs `tools/extract_data.py` reads besides the repo's own recordings, copied here so the film's data
can be regenerated after the session that produced them is gone. Nothing in this folder is edited by hand; every
file is a verbatim copy, read-only, and the film cites each one by name.

| File | What it is | Produced by |
|---|---|---|
| `asr_cast.json` | The transcriber test: 25 synthetic library voices under 13 accent labels, each run without and with hints (name, company, exact transcript per run) | the accent test (`scratchpad/accent-test`, Oct 29) |
| `onepager/margaux-lefevre-corvane-capital.json` | The saved one-pager: the deck rebuilt as "one page, numbers first" (figures, sections, `dropped[]`, `retried`, usage, seconds, model). Its `person_key` is the demo rig's; the film cues it into run 51b4 the way `onepager.cue` would, so the name on the notice is that run's person | `onepager.rebuild` on `demo/deck/hallwise-deck.md` (demo-margaux rig) |
| `aside/raw-c.txt` | Muse Spark's raw `hallwise_record` answer (translations + edges) on the aside take, before the checks, from one run of the script | `scratchpad/rehearsal/tools/aside_check.py` |
| `aside/result-c-final.txt` | A later run of the same script after `asides_kept_aside`: people with speaker keys, the translation's aside flag, the kept edges, the drafts, and the calls' token counts (its edges differ from raw-c.txt's: a different call) | `aside_check.py` |
| `aside/finder-check-c.txt`, `aside/finder-check-c-final.txt` | Muse Spark Open on Baseten as the edge finder on the same take: each `hallwise_edges` call with seconds and tokens, its raw edge count, the edges `take_edges -> kept_edges` kept, and the ones the check dropped (`(dropped by the check)` lines) | `scratchpad/rehearsal-v5/tools/finder_check.py` |
| `recordings/20261029-015514-51b4/events.jsonl`, `meta.json` | The mono rehearsal run with hooks, recall, second runs, the retired two-model comparison (`confirmed`, `disagreement`) and a corrected promise. Simulator run, synthetic voices, fictional names | the server, Oct 29 |

The aside take's own `events.jsonl` was not kept, so `kept_edges` cannot be re-run on it here; the film shows the
verdicts the finder check printed from the server's own `take_edges -> kept_edges`, and says so.

The 4-channel rehearsal (`server/data/recordings/20261027-064036-3f3e`), its xray sidecar
(`apps/replay/data/20261027-064036-3f3e.xray.json`, from `server/scripts/export_xray.py`), the four earlier
evenings the hooks cite, the research cache and `demo/rig/fictional-web.json` are read from the repo directly.
