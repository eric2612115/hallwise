import SwiftUI

/// Everyone met, across recordings, as the server lists them.
struct DirectoryPerson: Identifiable {
    struct Encounter: Identifiable {
        var id: String { recording }
        let recording: String
        let event: String
        let venue: String
        let started: Double
        let introducedBy: String
    }
    struct Promise: Identifiable {
        var id: String { recording + what }
        let recording: String
        let event: String
        let what: String
        let due: String
        let direction: String
    }
    let id: String
    let name: String
    let company: String
    let role: String
    let language: String
    let encounters: [Encounter]
    let promises: [Promise]

    var firstName: String { name.split(separator: " ").first.map(String.init) ?? name }
    var line: String { [company, role].filter { !$0.isEmpty }.joined(separator: " · ") }

    init?(_ d: [String: Any]) {
        guard let key = d["key"] as? String, let name = d["name"] as? String else { return nil }
        id = key
        self.name = name
        company = d["company"] as? String ?? ""
        role = d["role"] as? String ?? ""
        language = d["language"] as? String ?? ""
        encounters = (d["encounters"] as? [[String: Any]] ?? []).map {
            Encounter(recording: $0["recording"] as? String ?? "", event: $0["event"] as? String ?? "",
                      venue: $0["venue"] as? String ?? "", started: $0["started"] as? Double ?? 0,
                      introducedBy: $0["introduced_by"] as? String ?? "")
        }
        promises = (d["promises"] as? [[String: Any]] ?? []).map {
            Promise(recording: $0["recording"] as? String ?? "", event: $0["event"] as? String ?? "",
                    what: $0["what"] as? String ?? "", due: $0["due"] as? String ?? "", direction: $0["direction"] as? String ?? "")
        }
    }
}

/// The directory, fetched once per appearance and whenever the record changes.
@MainActor
final class Directory: ObservableObject {
    @Published var people: [DirectoryPerson] = []
    @Published var loaded = false

    func load(base: String) async {
        let list = await ServerLink().fetchPeople(base: base)
        people = list.compactMap(DirectoryPerson.init)
        loaded = true
    }

    /// Events, newest first, with how many people were met at each.
    var events: [(name: String, started: Double, count: Int)] {
        var seen: [String: (Double, Int)] = [:]
        for p in people {
            for e in p.encounters {
                let name = e.event.isEmpty ? "untitled" : e.event
                let cur = seen[name] ?? (e.started, 0)
                seen[name] = (max(cur.0, e.started), cur.1 + 1)
            }
        }
        return seen.map { (name: $0.key, started: $0.value.0, count: $0.value.1) }.sorted { $0.started > $1.started }
    }
}

func dayString(_ started: Double) -> String {
    guard started > 0 else { return "" }
    let f = DateFormatter()
    f.dateFormat = "MMM d"
    return f.string(from: Date(timeIntervalSince1970: started))
}

// MARK: - Map

/// Tonight from above, or everyone you know as a network. Owe lives in the bell now.
struct MapPage: View {
    @ObservedObject var app: AppModel
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    @StateObject private var directory = Directory()
    @State private var scope = 0
    @State private var selected: LiveModel.Person?
    @State private var selectedKnown: DirectoryPerson?

    var body: some View {
        VStack(spacing: 10) {
            Picker("", selection: $scope) {
                Text("Tonight").tag(0)
                Text("All").tag(1)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.top, 8)
            if scope == 0 {
                TonightMap(live: live, settings: settings) { selected = $0 }
            } else {
                NetworkView(directory: directory) { selectedKnown = $0 }
                    .task { await directory.load(base: settings.serverURL) }
            }
        }
        .sheet(item: $selected) { p in PersonDetail(person: p, live: live, settings: settings).presentationDetents([.medium, .large]) }
        .sheet(item: $selectedKnown) { p in KnownPersonSheet(person: p, settings: settings).presentationDetents([.medium, .large]) }
    }
}

/// The room from above in room coordinates (it does not turn with the badge): where everyone stood at the
/// end, the order you met them as a faint path, and when, underneath.
struct TonightMap: View {
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    let onTap: (LiveModel.Person) -> Void

    private struct Spot: Identifiable {
        let id: String
        let person: LiveModel.Person
        let point: CGPoint
        let index: Int
    }

    var body: some View {
        let people = live.peopleOrder.compactMap { live.people[$0] }
        VStack(spacing: 0) {
            GeometryReader { geo in
                let size = min(geo.size.width, geo.size.height)
                let c = CGPoint(x: geo.size.width / 2, y: geo.size.height / 2)
                let r = size * 0.42
                let spots = laidOut(people, c: c, r: r)
                ZStack {
                    Canvas { ctx, _ in
                        for k in [1.0, 0.55] {
                            let ring = Path(ellipseIn: CGRect(x: c.x - r * k, y: c.y - r * k, width: 2 * r * k, height: 2 * r * k))
                            ctx.stroke(ring, with: .color(Theme.inkSoft.opacity(k == 1 ? 0.45 : 0.3)),
                                       style: StrokeStyle(lineWidth: k == 1 ? 1.5 : 1, dash: k == 1 ? [] : [3, 5]))
                        }
                        // the order you met people, as a path
                        if spots.count > 1 {
                            var path = Path()
                            path.move(to: spots[0].point)
                            for s in spots.dropFirst() { path.addLine(to: s.point) }
                            ctx.stroke(path, with: .color(Theme.inkSoft.opacity(0.5)), style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round, dash: [4, 6]))
                        }
                        for s in spots {
                            let colour = live.color(for: s.person.id)
                            let dot = Path(ellipseIn: CGRect(x: s.point.x - 9, y: s.point.y - 9, width: 18, height: 18))
                            ctx.fill(dot, with: .color(colour))
                            ctx.stroke(dot, with: .color(Theme.paper), lineWidth: 2)
                            if live.history[s.person.id] != nil {
                                let ring = Path(ellipseIn: CGRect(x: s.point.x - 14, y: s.point.y - 14, width: 28, height: 28))
                                ctx.stroke(ring, with: .color(colour), lineWidth: 1.5)
                            }
                        }
                    }
                    // the wearer
                    VStack(spacing: 2) {
                        Text(settings.ownerName.prefix(1).uppercased())
                            .font(.system(size: 11, weight: .semibold, design: .serif))
                            .foregroundStyle(Theme.paper)
                            .frame(width: 22, height: 22)
                            .background(Circle().fill(Theme.ink))
                        Text("you").font(.system(size: 11)).foregroundStyle(Theme.inkSoft)
                    }
                    .position(x: c.x, y: c.y + 6)
                    ForEach(spots) { s in
                        // the label sits on the outward side, its near edge clear of the dot
                        let dx = s.point.x - c.x, dy = s.point.y - c.y
                        let sideways = abs(dx) >= abs(dy)
                        let label = HStack(spacing: 4) {
                            Text("\(s.index + 1)")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(Theme.paper)
                                .frame(width: 16, height: 16)
                                .background(Circle().fill(Theme.ink))
                            Text(s.person.name.split(separator: " ").first.map(String.init) ?? s.person.name)
                                .font(.system(size: 14, weight: .semibold, design: .serif))
                                .foregroundStyle(Theme.ink)
                                .shadow(color: Theme.paper, radius: 2)
                                .lineLimit(1)
                        }
                        .onTapGesture { onTap(s.person) }
                        if sideways {
                            label
                                .frame(width: 110, alignment: dx < 0 ? .trailing : .leading)
                                .position(x: s.point.x + (dx < 0 ? -1 : 1) * (18 + 55), y: s.point.y)
                        } else {
                            label.position(x: s.point.x, y: s.point.y + (dy < 0 ? -26 : 26))
                        }
                    }
                    if people.isEmpty {
                        Text("Nobody placed yet")
                            .font(.system(size: 14, design: .serif))
                            .foregroundStyle(Theme.inkSoft)
                            .position(x: c.x, y: c.y - r * 0.6)
                    }
                }
            }
            .aspectRatio(1, contentMode: .fit)
            .padding(.horizontal, 8)
            // when you met each of them
            List {
                ForEach(Array(people.enumerated()), id: \.element.id) { i, p in
                    Button { onTap(p) } label: {
                        HStack(spacing: 12) {
                            Text(live.firstHeardMs(of: p).map(mmss) ?? "–")
                                .font(.system(size: 15, weight: .medium).monospacedDigit())
                                .foregroundStyle(Theme.inkSoft)
                                .frame(width: 44, alignment: .leading)
                            Circle().fill(live.color(for: p.id)).frame(width: 10, height: 10)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(p.name).font(.system(size: 16, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                                let placeLine = live.history[p.id].map { h in
                                    h.encounters.first.map { "met before · \($0.event) · \(dayString($0.started))" } ?? ""
                                } ?? [p.company, p.role].filter { !$0.isEmpty }.joined(separator: " · ")
                                if !placeLine.isEmpty {
                                    Text(placeLine).font(.system(size: 13)).foregroundStyle(live.history[p.id] != nil ? Theme.accent : Theme.inkSoft).lineLimit(1)
                                }
                            }
                            Spacer()
                        }
                    }
                    .buttonStyle(.plain)
                    .listRowBackground(Theme.paperDeep)
                }
            }
            .scrollContentBackground(.hidden)
        }
    }

    /// Room bearings, calibrated by the forward offset only; close voices inside, far ones out.
    private func laidOut(_ people: [LiveModel.Person], c: CGPoint, r: CGFloat) -> [Spot] {
        var out: [Spot] = []
        for (i, p) in people.enumerated() {
            let bearings = p.speakers.compactMap { live.speakerAzimuth[$0] }
            guard !bearings.isEmpty else { continue }
            let x = bearings.map { cos($0 * .pi / 180) }.reduce(0, +)
            let y = bearings.map { sin($0 * .pi / 180) }.reduce(0, +)
            let a = (atan2(y, x) * 180 / .pi - settings.yawOffset) * .pi / 180
            let d = live.distance(ofSpeakers: p.speakers)
            let radius = r * (0.6 + 0.4 * d)
            out.append(Spot(id: p.id, person: p, point: CGPoint(x: c.x - radius * sin(a), y: c.y - radius * cos(a)), index: i))
        }
        return out
    }
}

/// Everyone you know, as a network: a dot per person, bigger the more you have talked, coloured by the event
/// you first met at, ringed when you have met more than once. Lines: who introduced whom, and who was at the
/// same event. Tap a dot for the person; tap an event below to see only that evening's people.
struct NetworkView: View {
    @ObservedObject var directory: Directory
    let onTap: (DirectoryPerson) -> Void
    @State private var filter: String?
    @State private var positions: [CGPoint] = []
    @State private var laidOutFor = 0

    var body: some View {
        let people = directory.people
        let events = directory.events
        let eventIndex = Dictionary(uniqueKeysWithValues: events.enumerated().map { ($0.element.name, $0.offset) })
        VStack(spacing: 8) {
            GeometryReader { geo in
                let pts = positions.count == people.count ? positions : []
                ZStack {
                    Canvas { ctx, _ in
                        guard pts.count == people.count else { return }
                        let edges = edges(people)
                        for (i, j, strong) in edges {
                            let dim = filter != nil && !(attends(people[i], filter) && attends(people[j], filter))
                            var path = Path()
                            path.move(to: pts[i])
                            path.addLine(to: pts[j])
                            ctx.stroke(path, with: .color(Theme.inkSoft.opacity(dim ? 0.08 : (strong ? 0.6 : 0.2))),
                                       style: StrokeStyle(lineWidth: strong ? 1.5 : 1, dash: strong ? [] : [2, 4]))
                        }
                        for (i, p) in people.enumerated() {
                            let dim = filter != nil && !attends(p, filter)
                            let first = p.encounters.last?.event ?? ""
                            let colour = Theme.people[(eventIndex[first.isEmpty ? "untitled" : first] ?? 0) % Theme.people.count]
                            let size = CGFloat(12 + 4 * min(4, p.encounters.count))
                            let dot = Path(ellipseIn: CGRect(x: pts[i].x - size / 2, y: pts[i].y - size / 2, width: size, height: size))
                            ctx.fill(dot, with: .color(colour.opacity(dim ? 0.25 : 1)))
                            ctx.stroke(dot, with: .color(Theme.paper), lineWidth: 2)
                            if p.encounters.count > 1 {
                                let ring = Path(ellipseIn: CGRect(x: pts[i].x - size / 2 - 5, y: pts[i].y - size / 2 - 5, width: size + 10, height: size + 10))
                                ctx.stroke(ring, with: .color(colour.opacity(dim ? 0.25 : 1)), lineWidth: 1.5)
                            }
                        }
                    }
                    ForEach(Array(people.enumerated()), id: \.element.id) { i, p in
                        if pts.count == people.count {
                            let dim = filter != nil && !attends(p, filter)
                            Text(p.firstName)
                                .font(.system(size: 13, weight: .semibold, design: .serif))
                                .foregroundStyle(Theme.ink.opacity(dim ? 0.3 : 1))
                                .shadow(color: Theme.paper, radius: 2)
                                .position(x: pts[i].x, y: pts[i].y + 20)
                        }
                    }
                    if !directory.loaded {
                        ProgressView().tint(Theme.inkSoft)
                    } else if people.isEmpty {
                        Text("No one yet").font(.system(size: 14, design: .serif)).foregroundStyle(Theme.inkSoft)
                    }
                }
                .contentShape(Rectangle())
                .onTapGesture { at in
                    guard pts.count == people.count else { return }
                    if let i = pts.indices.min(by: { hypot(pts[$0].x - at.x, pts[$0].y - at.y) < hypot(pts[$1].x - at.x, pts[$1].y - at.y) }),
                       hypot(pts[i].x - at.x, pts[i].y - at.y) < 28 {
                        onTap(people[i])
                    }
                }
                .onAppear { layout(people, in: geo.size) }
                .onChange(of: people.count) { _, _ in layout(people, in: geo.size) }
            }
            // events, newest first; tap to see only that evening's people
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(Array(events.enumerated()), id: \.element.name) { i, e in
                        let on = filter == e.name
                        Button { filter = on ? nil : e.name } label: {
                            HStack(spacing: 6) {
                                Circle().fill(Theme.people[i % Theme.people.count]).frame(width: 9, height: 9)
                                Text(e.name).font(.system(size: 13, weight: .medium)).lineLimit(1)
                                Text("\(e.count)").font(.system(size: 12)).foregroundStyle(on ? Theme.paper.opacity(0.8) : Theme.inkSoft)
                            }
                            .foregroundStyle(on ? Theme.paper : Theme.ink)
                            .padding(.horizontal, 12)
                            .frame(height: 36)
                            .background(Capsule().fill(on ? Theme.ink : Theme.paperDeep))
                            .overlay(Capsule().stroke(Theme.rule, lineWidth: on ? 0 : 0.5))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 16)
            }
            .frame(height: 44)
            .padding(.bottom, 6)
        }
    }

    private func attends(_ p: DirectoryPerson, _ event: String?) -> Bool {
        guard let event else { return true }
        return p.encounters.contains { ($0.event.isEmpty ? "untitled" : $0.event) == event }
    }

    /// (i, j, strong): strong when one introduced the other, weak when they were at the same event.
    private func edges(_ people: [DirectoryPerson]) -> [(Int, Int, Bool)] {
        var out: [(Int, Int, Bool)] = []
        let byName = Dictionary(people.enumerated().map { ($0.element.name.lowercased(), $0.offset) }, uniquingKeysWith: { a, _ in a })
        var seen: Set<String> = []
        for (i, p) in people.enumerated() {
            for e in p.encounters where !e.introducedBy.isEmpty {
                if let j = byName[e.introducedBy.lowercased()], j != i, seen.insert("\(min(i, j))-\(max(i, j))").inserted {
                    out.append((i, j, true))
                }
            }
        }
        var byRecording: [String: [Int]] = [:]
        for (i, p) in people.enumerated() {
            for e in p.encounters { byRecording[e.recording, default: []].append(i) }
        }
        for members in byRecording.values where members.count > 1 {
            for a in members.indices {
                for b in (a + 1)..<members.count {
                    let i = members[a], j = members[b]
                    if seen.insert("\(min(i, j))-\(max(i, j))").inserted { out.append((i, j, false)) }
                }
            }
        }
        return out
    }

    /// A small force layout: everyone repels, lines pull, the centre holds; deterministic, so the map is
    /// the same each time you open it.
    private func layout(_ people: [DirectoryPerson], in size: CGSize) {
        let n = people.count
        guard n > 0 else { positions = []; return }
        let c = CGPoint(x: size.width / 2, y: size.height / 2 - 10)
        let radius = min(size.width, size.height) * 0.36
        var pts = (0..<n).map { i -> CGPoint in
            let a = Double(i) / Double(n) * 2 * .pi - .pi / 2
            return CGPoint(x: c.x + radius * cos(a), y: c.y + radius * sin(a))
        }
        let es = edges(people)
        let rest: CGFloat = 96
        for _ in 0..<220 {
            var force = [CGVector](repeating: .zero, count: n)
            for i in 0..<n {
                for j in (i + 1)..<n {
                    let dx = pts[j].x - pts[i].x, dy = pts[j].y - pts[i].y
                    let d2 = max(1, dx * dx + dy * dy), d = sqrt(d2)
                    let push = 5200 / d2
                    force[i].dx -= dx / d * push; force[i].dy -= dy / d * push
                    force[j].dx += dx / d * push; force[j].dy += dy / d * push
                }
            }
            for (i, j, strong) in es {
                let dx = pts[j].x - pts[i].x, dy = pts[j].y - pts[i].y
                let d = max(1, hypot(dx, dy))
                let pull = (d - rest) * (strong ? 0.04 : 0.015)
                force[i].dx += dx / d * pull; force[i].dy += dy / d * pull
                force[j].dx -= dx / d * pull; force[j].dy -= dy / d * pull
            }
            for i in 0..<n {
                force[i].dx += (c.x - pts[i].x) * 0.01
                force[i].dy += (c.y - pts[i].y) * 0.01
                pts[i].x = min(size.width - 40, max(40, pts[i].x + force[i].dx * 0.6))
                pts[i].y = min(size.height - 50, max(30, pts[i].y + force[i].dy * 0.6))
            }
        }
        positions = pts
    }
}

/// Someone from the directory: every evening you met them, and what passed between you.
struct KnownPersonSheet: View {
    let person: DirectoryPerson
    @ObservedObject var settings: BadgeSettings

    var body: some View {
        ZStack {
            PaperBackground()
            List {
                Section {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(person.name).font(.system(size: 26, weight: .bold, design: .serif)).foregroundStyle(Theme.ink)
                        if !person.line.isEmpty { Text(person.line).foregroundStyle(Theme.inkSoft) }
                        if !person.language.isEmpty { Tag(text: "speaks \(person.language)") }
                    }
                    .padding(.vertical, 4)
                }
                .listRowBackground(Color.clear)
                Section(header: PaperHeader(text: person.encounters.count == 1 ? "Met once" : "Met \(person.encounters.count) times")) {
                    ForEach(person.encounters) { e in
                        VStack(alignment: .leading, spacing: 2) {
                            Text([e.event.isEmpty ? "untitled" : e.event, dayString(e.started)].filter { !$0.isEmpty }.joined(separator: " · "))
                                .font(.system(size: 16, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                            Text([e.venue, e.introducedBy.isEmpty ? "" : "via \(e.introducedBy)"].filter { !$0.isEmpty }.joined(separator: " · "))
                                .font(.system(size: 14)).foregroundStyle(Theme.inkSoft)
                        }
                    }
                }
                .listRowBackground(Theme.paperDeep)
                if !person.promises.isEmpty {
                    Section(header: PaperHeader(text: "Between you")) {
                        ForEach(person.promises) { q in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(q.what).font(.system(size: 16)).foregroundStyle(Theme.ink)
                                Text([q.direction == "owner_owes" ? "you owe" : q.direction == "they_owe" ? "they owe you" : "", q.due, q.event].filter { !$0.isEmpty }.joined(separator: " · "))
                                    .font(.system(size: 14)).foregroundStyle(Theme.inkSoft)
                            }
                        }
                    }
                    .listRowBackground(Theme.paperDeep)
                }
            }
            .scrollContentBackground(.hidden)
        }
        .preferredColorScheme(settings.colorScheme)
    }
}
