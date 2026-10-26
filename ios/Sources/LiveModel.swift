import Foundation
import SwiftUI

/// The live record, rebuilt from the server's event stream.
final class LiveModel: ObservableObject {
    struct Person: Identifiable, Equatable {
        let id: String  // person key
        var name: String
        var company: String
        var role: String
        var language: String
        var introducedBy: String
        var speakers: [String]
    }

    struct Promise: Identifiable {
        let id: String
        var what: String
        var due: String
        var replaces: String
        var owedTo: String
        var owedBy: String
    }

    struct Line: Identifiable {
        let id: Int  // turn
        let speaker: String
        let text: String
    }

    /// Where the owner met this person before, and what passed between them: from earlier recordings.
    struct History {
        struct Encounter: Identifiable {
            var id: String { recording }
            let recording: String
            let event: String
            let venue: String
            let started: Double
            let introducedBy: String
        }
        struct PastPromise: Identifiable {
            var id: String { recording + what }
            let recording: String
            let event: String
            let what: String
            let due: String
            let direction: String  // owner_owes, they_owe, between_others
        }
        let encounters: [Encounter]
        let promises: [PastPromise]
    }

    @Published var photos: [String: UIImage] = [:]        // a face per person key, from the owner's photos
    var recordingID = ""                                   // where faces are kept on disk
    var serverBase = ""                                    // ws:// address, for faces kept on the server

    /// A reason to reach out, found across evenings: an open introduction, a colleague who mentioned them,
    /// a question left hanging. From the recording's `hook` events or from the morning report.
    struct Hook: Identifiable, Equatable {
        struct Evidence: Equatable {
            let event: String
            let day: String
            let speaker: String
            let quote: String
            let source: String  // research only: the page it came from
        }
        var id: String { type + "|" + title }
        let type: String     // introduction, mutual_connection, open_thread, timely
        let title: String
        let tag: String      // the short form, under the name in the room
        let reason: String
        let names: [String]
        let evidence: [Evidence]
        let draft: String
        let draftEnglish: String
        let language: String
        let promiseKey: String

        init(_ d: [String: Any]) {
            type = (d["kind"] as? String) ?? (d["type"] as? String) ?? "open_thread"
            title = d["title"] as? String ?? ""
            let t = d["tag"] as? String ?? ""
            tag = t.isEmpty ? title : t
            reason = d["reason"] as? String ?? ""
            names = d["names"] as? [String] ?? []
            evidence = (d["evidence"] as? [[String: Any]] ?? []).map {
                Evidence(event: $0["event"] as? String ?? "", day: $0["day"] as? String ?? "",
                         speaker: $0["speaker"] as? String ?? "", quote: $0["quote"] as? String ?? "",
                         source: $0["source"] as? String ?? "")
            }
            draft = d["draft"] as? String ?? ""
            draftEnglish = d["draft_english"] as? String ?? ""
            language = d["language"] as? String ?? ""
            promiseKey = d["promise_key"] as? String ?? ""
        }
    }

    @Published var liveHooks: [String: [Hook]] = [:]    // by person key, from `hook` events
    @Published var reportHooks: [String: [Hook]] = [:]  // by person key, from the morning report
    var indexKeys: [String: String] = [:]               // person key -> people-index key, from person_history

    /// Hooks for someone met tonight: the report's (reasoned across the week) first, then the room's own.
    func hooks(for key: String) -> [Hook] {
        let report = reportHooks[key] ?? []
        let room = (liveHooks[key] ?? []).filter { h in !report.contains { $0.tag == h.tag || $0.title == h.title } }
        return report + room
    }

    /// The morning report's hooks, attached to tonight's people by their key in this recording.
    func applyReport(_ report: [String: Any]) {
        var out: [String: [Hook]] = [:]
        for h in report["hooks"] as? [[String: Any]] ?? [] {
            let hook = Hook(h)
            for key in (h["record_keys"] as? [String: String] ?? [:]).values { out[key, default: []].append(hook) }
        }
        reportHooks = out
    }

    /// Where the server keeps this person's face: the people index key (name and company, slugged as the server
    /// does), or the one person_history named.
    func indexKey(for key: String) -> String {
        if let k = indexKeys[key] { return k }
        guard let p = people[key] else { return key }
        let company = Self.slug(p.company)
        return Self.slug(p.name) + (company.isEmpty ? "" : "-" + company)
    }

    /// The server's slug: lowercase ASCII letters and digits, runs joined by "-" ("Lefèvre" → "lef-vre").
    static func slug(_ text: String) -> String {
        var runs: [String] = []
        var cur = ""
        for ch in text.lowercased().unicodeScalars {
            if ("a"..."z").contains(ch) || ("0"..."9").contains(ch) { cur.unicodeScalars.append(ch) }
            else if !cur.isEmpty { runs.append(cur); cur = "" }
        }
        if !cur.isEmpty { runs.append(cur) }
        return runs.joined(separator: "-")
    }

    /// Someone met before turns up with no face here: bring the one kept on the server from an earlier evening.
    private func fetchFace(for key: String) {
        guard photos[key] == nil, !serverBase.isEmpty, let p = people[key] else { return }
        let base = serverBase, ik = indexKey(for: key)
        Task { [weak self] in
            guard let image = await Faces.fetch(base: base, key: ik, name: p.name, company: p.company) else { return }
            await MainActor.run {
                guard let self, self.photos[key] == nil else { return }
                self.photos[key] = image
            }
        }
    }

    /// Keep a face for a person, on screen and on disk under the recording.
    func setPhoto(_ image: UIImage?, for key: String) {
        photos[key] = image
        let dir = Self.photoDir(recordingID)
        let file = dir.appendingPathComponent(key + ".jpg")
        if let image, let data = image.jpegData(compressionQuality: 0.85) {
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            try? data.write(to: file)
        } else {
            try? FileManager.default.removeItem(at: file)
        }
    }

    /// Faces saved earlier for this recording, when a person turns up again (a relaunch, a replay).
    func loadPhoto(for key: String) {
        guard photos[key] == nil, !recordingID.isEmpty else { return }
        let file = Self.photoDir(recordingID).appendingPathComponent(key + ".jpg")
        if let data = try? Data(contentsOf: file), let image = UIImage(data: data) { photos[key] = image }
    }

    static func photoDir(_ rid: String) -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("photos").appendingPathComponent(rid)
    }

    @Published var history: [String: History] = [:]       // by person key
    @Published var speakerFirstMs: [String: Int] = [:]     // when each voice was first heard

    /// When the owner first heard this person tonight, on the recording clock.
    func firstHeardMs(of person: Person) -> Int? {
        person.speakers.compactMap { speakerFirstMs[$0] }.min()
    }

    /// A ready-to-send follow-up for one promise, drafted by the server when the recording ends.
    struct Move: Identifiable {
        var id: String { promiseKey }
        let promiseKey: String
        let personKey: String
        let kind: String        // message, email, calendar, nudge
        let language: String
        let subject: String
        let body: String
        let bodyEnglish: String
        let when: String        // ISO 8601, calendar kinds only
        let durationMinutes: Int
        let attach: String      // deck, one_pager, blurb or ""
        let why: String
        let remindAt: String    // ISO 8601: when to tap the owner if this is still not sent
        let nudge: String       // the reminder line
    }

    /// What Hallwise would tap you on the shoulder about: drafts waiting to go, a time not yet on the
    /// calendar, words to settle.
    struct Notice: Identifiable {
        enum Kind { case send, calendar, word }
        let id: String
        let title: String
        let detail: String
        let kind: Kind
        let promiseKey: String?
    }

    @Published var dismissedNotices: Set<String> = []
    @Published var calendarAdded: Set<String> = []

    var notices: [Notice] {
        var out: [Notice] = []
        for key in promiseOrder where !donePromises.contains(key) {
            guard let p = promises[key], let m = moves[key] else { continue }
            let who = p.owedBy == "owner" ? name(for: p.owedTo) : name(for: p.owedBy)
            let due = p.due.isEmpty ? "" : " · \(p.due)"
            if m.kind == "calendar" {
                guard !calendarAdded.contains(key) else { continue }
                out.append(Notice(id: "cal:" + key, title: m.nudge.isEmpty ? "Put \(who) on the calendar" : m.nudge,
                                  detail: p.what + due, kind: .calendar, promiseKey: key))
            } else if m.kind == "nudge" {
                out.append(Notice(id: "nudge:" + key, title: m.nudge.isEmpty ? "Nudge \(who) in a few days" : m.nudge,
                                  detail: p.what + due, kind: .send, promiseKey: key))
            } else {
                out.append(Notice(id: "send:" + key, title: m.nudge.isEmpty ? "Send to \(who)" : m.nudge,
                                  detail: p.what + due, kind: .send, promiseKey: key))
            }
        }
        if !suspects.isEmpty {
            out.append(Notice(id: "words", title: suspects.count == 1 ? "One word to confirm" : "\(suspects.count) words to confirm",
                              detail: suspects.prefix(3).map(\.likely).joined(separator: ", "), kind: .word, promiseKey: nil))
        }
        return out.filter { !dismissedNotices.contains($0.id) }
    }

    func markDone(_ key: String) {
        donePromises.insert(key)
        Reminders.cancel(key)
    }

    func markUndone(_ key: String) {
        donePromises.remove(key)
        if let m = moves[key] { Reminders.schedule(m, promise: promises[key]) }
    }

    struct Suspect: Identifiable {
        var id: String { "\(turn)-\(heard)" }
        let heard: String
        let likely: String
        let turn: Int
    }

    @Published var people: [String: Person] = [:]
    @Published var peopleOrder: [String] = []
    @Published var promises: [String: Promise] = [:]
    @Published var promiseOrder: [String] = []
    @Published var speakerAzimuth: [String: Double] = [:]  // room bearing per speaker key
    @Published var speakerLevel: [String: Double] = [:]    // mean loudness per speaker key, dBFS
    @Published var ownerSpeakers: Set<String> = []
    @Published var lines: [Line] = []
    @Published var turnKind: [Int: String] = [:]
    @Published var turnStart: [Int: Int] = [:]
    @Published var turnEnd: [Int: Int] = [:]
    @Published var suspects: [Suspect] = []
    @Published var moves: [String: Move] = [:]  // by promise key
    @Published var topics: [String] = []
    @Published var translations: [Int: (language: String, english: String)] = [:]
    @Published var yaw: Double = 0  // the badge's current yaw
    @Published var tMs = 0          // the recording clock, from the latest event
    private var lastSpeaker: (speaker: String, untilMs: Int)?

    /// Whoever spoke within the last moment, by speaker key.
    var activeSpeaker: String? {
        guard let last = lastSpeaker, last.untilMs >= tMs else { return nil }
        return last.speaker
    }

    /// Whoever spoke in the last twenty seconds or so: the "who just spoke" cue after the glow fades.
    var recentSpeaker: String? {
        guard let last = lastSpeaker, last.untilMs + 18_500 >= tMs else { return nil }
        return last.speaker
    }

    /// Promises the owner ticked off on the phone.
    @Published var donePromises: Set<String> = []

    /// The line a suspect word was heard in, for context.
    func line(forTurn turn: Int) -> Line? {
        lines.first { $0.id == turn }
    }

    /// The latest conversation line, for the subtitle.
    var subtitle: Line? {
        lines.last { (turnKind[$0.id] ?? "conversation") == "conversation" } ?? lines.last
    }

    /// How far a voice is, 0 = as close as anyone gets, 1 = far: its loudness against the loudest voice that
    /// is not the wearer's own, over roughly an 18 dB range (a person at 1 m vs across the room).
    func distance(ofSpeakers speakers: [String]) -> Double {
        let others = speakerLevel.filter { !ownerSpeakers.contains($0.key) }.map(\.value)
        guard let reference = others.max(), let level = speakers.compactMap({ speakerLevel[$0] }).max() else { return 0.5 }
        return min(1, max(0, (reference - level) / 18))
    }

    func reset() {
        people = [:]; peopleOrder = []; promises = [:]; promiseOrder = []; speakerAzimuth = [:]; speakerLevel = [:]
        ownerSpeakers = []; lines = []; turnKind = [:]; turnStart = [:]; turnEnd = [:]
        suspects = []; moves = [:]; topics = []; translations = [:]; history = [:]; speakerFirstMs = [:]; photos = [:]
        liveHooks = [:]; reportHooks = [:]; indexKeys = [:]
        tMs = 0; lastSpeaker = nil; donePromises = []; dismissedNotices = []; calendarAdded = []
    }

    /// A room bearing as seen from the badge now (degrees, 0 = ahead, positive = left).
    func relative(_ roomAzimuth: Double, offset: Double) -> Double {
        let a = roomAzimuth - yaw - offset
        return (a + 540).truncatingRemainder(dividingBy: 360) - 180
    }

    /// Where a person stands relative to where the badge faces now.
    func relativeBearing(of person: Person, offset: Double) -> Double? {
        let bearings = person.speakers.compactMap { speakerAzimuth[$0] }
        guard !bearings.isEmpty else { return nil }
        let x = bearings.map { cos($0 * .pi / 180) }.reduce(0, +)
        let y = bearings.map { sin($0 * .pi / 180) }.reduce(0, +)
        return relative(atan2(y, x) * 180 / .pi, offset: offset)
    }

    /// The person's colour: the same dot on the radar, in the list and in the transcript.
    func color(for key: String) -> Color {
        guard let i = peopleOrder.firstIndex(of: key) else { return Theme.inkSoft }
        return Theme.people[i % Theme.people.count]
    }

    func color(forSpeaker speaker: String) -> Color {
        if ownerSpeakers.contains(speaker) { return Theme.inkSoft }
        if let p = people.values.first(where: { $0.speakers.contains(speaker) }) { return color(for: p.id) }
        return Theme.inkSoft
    }

    func name(for key: String) -> String {
        key == "owner" ? "you" : (people[key]?.name ?? key)
    }

    /// First name of whoever speaks under a label; "You" for the owner; "Someone" before they introduce themselves.
    func speakerName(_ speaker: String) -> String {
        if ownerSpeakers.contains(speaker) { return "You" }
        if let p = people.values.first(where: { $0.speakers.contains(speaker) }) {
            return p.name.split(separator: " ").first.map(String.init) ?? p.name
        }
        return "Someone"
    }

    /// The owner dealt with a suspect word (kept, corrected or dismissed); it leaves the list, and so does
    /// its mirror image ("Margo → Margaux" settles "Margaux → Margo" too).
    func resolve(_ suspect: Suspect) {
        suspects.removeAll {
            $0.id == suspect.id
                || ($0.heard.caseInsensitiveCompare(suspect.likely) == .orderedSame
                    && $0.likely.caseInsensitiveCompare(suspect.heard) == .orderedSame)
        }
    }

    func apply(_ e: [String: Any]) {
        if let t = e["t_ms"] as? Int { tMs = max(tMs, t) }
        switch e["type"] as? String {
        case "turn":
            guard let turn = e["turn"] as? Int, let text = e["text"] as? String, !text.isEmpty else { return }
            let speaker = "\(e["session"] as? Int ?? 1):\(e["speaker"] as? String ?? "?")"
            lines.append(Line(id: turn, speaker: speaker, text: text))
            if lines.count > 60 { lines.removeFirst(lines.count - 60) }
            turnStart[turn] = e["start_ms"] as? Int ?? tMs
            turnEnd[turn] = e["end_ms"] as? Int ?? tMs
            if speakerFirstMs[speaker] == nil { speakerFirstMs[speaker] = e["start_ms"] as? Int ?? tMs }
            lastSpeaker = (speaker, (e["end_ms"] as? Int ?? tMs) + 1500)
        case "translation":
            if let turn = e["turn"] as? Int {
                translations[turn] = (e["language"] as? String ?? "", e["english"] as? String ?? "")
            }
        case "translation_removed":
            if let turn = e["turn"] as? Int { translations[turn] = nil }
        case "turn_kind":
            if let turn = e["turn"] as? Int, let kind = e["kind"] as? String { turnKind[turn] = kind }
        case "owner":
            ownerSpeakers = Set(e["speakers"] as? [String] ?? [])
        case "speaker_position":
            if let s = e["speaker"] as? String, let az = e["azimuth"] as? Double {
                speakerAzimuth[s] = az
                if let level = e["level_db"] as? Double { speakerLevel[s] = level }
            }
        case "person":
            guard let key = e["key"] as? String else { return }
            if people[key] == nil { peopleOrder.append(key); loadPhoto(for: key) }
            people[key] = Person(
                id: key,
                name: e["name"] as? String ?? key,
                company: e["company"] as? String ?? "",
                role: e["role"] as? String ?? "",
                language: e["preferred_language"] as? String ?? "",
                introducedBy: e["introduced_by"] as? String ?? "",
                speakers: e["speakers"] as? [String] ?? []
            )
        case "promise":
            guard let key = e["key"] as? String else { return }
            if promises[key] == nil { promiseOrder.append(key) }
            promises[key] = Promise(
                id: key,
                what: e["what"] as? String ?? "",
                due: e["due"] as? String ?? "",
                replaces: e["replaces"] as? String ?? "",
                owedTo: e["owed_to"] as? String ?? "",
                owedBy: e["owed_by"] as? String ?? ""
            )
        case "suspect_word":
            guard let heard = e["heard"] as? String, let turn = e["turn"] as? Int else { return }
            suspects.removeAll { $0.heard == heard && $0.turn == turn }
            suspects.append(Suspect(heard: heard, likely: e["likely"] as? String ?? "", turn: turn))
        case "person_removed":
            if let key = e["key"] as? String {
                people[key] = nil
                peopleOrder.removeAll { $0 == key }
            }
        case "promise_removed":
            if let key = e["key"] as? String {
                promises[key] = nil
                promiseOrder.removeAll { $0 == key }
            }
        case "suspect_word_removed":
            if let heard = e["heard"] as? String, let turn = e["turn"] as? Int {
                suspects.removeAll { $0.heard == heard && $0.turn == turn }
            }
        case "person_history":
            guard let key = e["key"] as? String else { return }
            let encounters = (e["encounters"] as? [[String: Any]] ?? []).map {
                History.Encounter(recording: $0["recording"] as? String ?? "", event: $0["event"] as? String ?? "",
                                  venue: $0["venue"] as? String ?? "", started: $0["started"] as? Double ?? 0,
                                  introducedBy: $0["introduced_by"] as? String ?? "")
            }
            let promises = (e["promises"] as? [[String: Any]] ?? []).map {
                History.PastPromise(recording: $0["recording"] as? String ?? "", event: $0["event"] as? String ?? "",
                                    what: $0["what"] as? String ?? "", due: $0["due"] as? String ?? "",
                                    direction: $0["direction"] as? String ?? "")
            }
            history[key] = History(encounters: encounters, promises: promises)
            if let ik = e["index_key"] as? String, !ik.isEmpty { indexKeys[key] = ik }
            fetchFace(for: key)
        case "hook":
            guard let key = e["person_key"] as? String, !key.isEmpty else { return }
            let hook = Hook(e)
            liveHooks[key] = (liveHooks[key] ?? []).filter { $0.title != hook.title } + [hook]
        case "next_move":
            guard let m = Move(e) else { return }
            let key = m.promiseKey
            moves[key] = m
            if !donePromises.contains(key) { Reminders.schedule(m, promise: promises[key]) }
        case "room_topics":
            topics = e["topics"] as? [String] ?? []
        case "replay_clock":
            break  // a replay's clock through a silence: it only moves tMs (above), so the glow fades as it did live
        default:
            break
        }
    }
}

extension LiveModel.Move {
    /// A follow-up as the server sends it: a `next_move` event, or a row of the morning report.
    init?(_ e: [String: Any]) {
        guard let key = e["promise_key"] as? String, !key.isEmpty else { return nil }
        self.init(
            promiseKey: key,
            personKey: e["person_key"] as? String ?? "",
            kind: e["kind"] as? String ?? "message",
            language: e["language"] as? String ?? "",
            subject: e["subject"] as? String ?? "",
            body: e["body"] as? String ?? "",
            bodyEnglish: e["body_english"] as? String ?? "",
            when: e["when"] as? String ?? "",
            durationMinutes: e["duration_minutes"] as? Int ?? 30,
            attach: e["attach"] as? String ?? "",
            why: e["why"] as? String ?? "",
            remindAt: e["remind_at"] as? String ?? "",
            nudge: e["nudge"] as? String ?? ""
        )
    }
}
