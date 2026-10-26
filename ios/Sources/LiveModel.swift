import Foundation

/// The live record, rebuilt from the server's event stream.
final class LiveModel: ObservableObject {
    struct Person: Identifiable {
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
    @Published var suspects: [Suspect] = []
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
        ownerSpeakers = []; lines = []; turnKind = [:]; suspects = []; topics = []; translations = [:]
        tMs = 0; lastSpeaker = nil
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

    func name(for key: String) -> String {
        key == "owner" ? "you" : (people[key]?.name ?? key)
    }

    func apply(_ e: [String: Any]) {
        if let t = e["t_ms"] as? Int { tMs = max(tMs, t) }
        switch e["type"] as? String {
        case "turn":
            guard let turn = e["turn"] as? Int, let text = e["text"] as? String, !text.isEmpty else { return }
            let speaker = "\(e["session"] as? Int ?? 1):\(e["speaker"] as? String ?? "?")"
            lines.append(Line(id: turn, speaker: speaker, text: text))
            if lines.count > 40 { lines.removeFirst(lines.count - 40) }
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
            if people[key] == nil { peopleOrder.append(key) }
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
        case "room_topics":
            topics = e["topics"] as? [String] ?? []
        default:
            break
        }
    }
}
