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
    @Published var ownerSpeakers: Set<String> = []
    @Published var lines: [Line] = []
    @Published var turnKind: [Int: String] = [:]
    @Published var suspects: [Suspect] = []
    @Published var topics: [String] = []
    @Published var yaw: Double = 0  // the badge's current yaw

    func reset() {
        people = [:]; peopleOrder = []; promises = [:]; promiseOrder = []; speakerAzimuth = [:]
        ownerSpeakers = []; lines = []; turnKind = [:]; suspects = []; topics = []
    }

    /// Where a person stands relative to where the badge faces now (degrees, counter-clockwise = left).
    func relativeBearing(of person: Person, offset: Double) -> Double? {
        let bearings = person.speakers.compactMap { speakerAzimuth[$0] }
        guard !bearings.isEmpty else { return nil }
        let x = bearings.map { cos($0 * .pi / 180) }.reduce(0, +)
        let y = bearings.map { sin($0 * .pi / 180) }.reduce(0, +)
        var a = atan2(y, x) * 180 / .pi - yaw - offset
        a = (a + 540).truncatingRemainder(dividingBy: 360) - 180
        return a
    }

    func name(for key: String) -> String {
        key == "owner" ? "you" : (people[key]?.name ?? key)
    }

    func apply(_ e: [String: Any]) {
        switch e["type"] as? String {
        case "turn":
            guard let turn = e["turn"] as? Int, let text = e["text"] as? String, !text.isEmpty else { return }
            let speaker = "\(e["session"] as? Int ?? 1):\(e["speaker"] as? String ?? "?")"
            lines.append(Line(id: turn, speaker: speaker, text: text))
            if lines.count > 40 { lines.removeFirst(lines.count - 40) }
        case "turn_kind":
            if let turn = e["turn"] as? Int, let kind = e["kind"] as? String { turnKind[turn] = kind }
        case "owner":
            ownerSpeakers = Set(e["speakers"] as? [String] ?? [])
        case "speaker_position":
            if let s = e["speaker"] as? String, let az = e["azimuth"] as? Double { speakerAzimuth[s] = az }
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
        case "room_topic":
            if let topic = e["topic"] as? String, !topics.contains(topic) { topics.append(topic) }
        default:
            break
        }
    }
}
