import SwiftUI

/// The connector (server/hallwise/connector.py), for the moment the owner sits down after the evening: two people
/// from his week who should meet, each with what they said, and next week's event where one of them will be. Every
/// quote on it comes from the log, the event from a page a search returned; nothing on it was promised, and
/// nothing is invented. Read from GET /api/connector/{recording} (or /latest).
struct Connections {
    /// One line a person said, as the log has it.
    struct Said {
        let quote: String       // their words, in the language they said them
        let english: String     // the line in English when it was not
        let language: String
        let event: String
        let day: String
        let tonight: Bool
        let aside: Bool         // not said to the owner: on the phone, to themselves, to someone else

        init(_ d: [String: Any]) {
            quote = d["quote"] as? String ?? ""
            english = d["english"] as? String ?? ""
            language = d["language"] as? String ?? ""
            event = d["event"] as? String ?? ""
            day = d["day"] as? String ?? ""
            tonight = d["tonight"] as? Bool ?? false
            aside = d["aside"] as? Bool ?? false
        }

        /// "Tonight · in Japanese" / "Founder dinner · Oct 24".
        var whereSaid: String {
            let lang = language.isEmpty || language == "English" ? "" : "in \(language)"
            return (tonight ? ["Tonight", lang] : [event, day, lang]).filter { !$0.isEmpty }.joined(separator: " · ")
        }
    }

    struct Person: Identifiable {
        let id: String          // people-index key
        let name: String
        let company: String
        let wants: String       // what they need, offer, build or plan, in one sentence
        let quote: String       // the words of theirs it rests on (checked against the log on the server)
        let aside: Bool
        let said: [Said]
        let sources: [String]   // the pages behind what research added to `wants`

        init(_ d: [String: Any]) {
            id = d["key"] as? String ?? UUID().uuidString
            name = d["name"] as? String ?? ""
            company = d["company"] as? String ?? ""
            wants = d["wants"] as? String ?? ""
            quote = d["quote"] as? String ?? ""
            aside = d["aside"] as? Bool ?? false
            said = (d["evidence"] as? [[String: Any]] ?? []).map(Said.init)
            var seen = Set<String>()
            sources = (d["public"] as? [[String: Any]] ?? []).compactMap { $0["source"] as? String }.filter { seen.insert($0).inserted }
        }

        var firstName: String { name.split(separator: " ").first.map(String.init) ?? name }

        /// The line the quote is from: the one to show.
        var line: Said? {
            let q = quote.lowercased()
            return said.first { $0.quote.lowercased().contains(q) || $0.english.lowercased().contains(q) } ?? said.first
        }
    }

    struct Proposal: Identifiable {
        let id: String
        let rank: Int
        let title: String
        let collaboration: String
        let why: String
        let askFirst: String
        let sameEvening: Bool
        let a: Person
        let b: Person

        init?(_ d: [String: Any]) {
            let people = (d["people"] as? [[String: Any]] ?? []).map(Person.init)
            guard people.count == 2 else { return nil }
            a = people[0]
            b = people[1]
            id = a.id + "+" + b.id
            rank = d["rank"] as? Int ?? 0
            title = d["title"] as? String ?? ""
            collaboration = d["collaboration"] as? String ?? ""
            why = d["why"] as? String ?? ""
            askFirst = d["ask_first"] as? String ?? a.id
            sameEvening = d["same_evening"] as? Bool ?? false
        }

        var asked: Person { askFirst == b.id ? b : a }
    }

    struct Event: Identifiable {
        var id: String { url + date }
        let title: String
        let date: String        // YYYY-MM-DD
        let time: String
        let place: String
        let url: String
        let site: String
        let who: String
        let whoKey: String      // the owner met them, when set
        let role: String
        let why: String
        let bring: [(key: String, name: String)]

        init(_ d: [String: Any]) {
            title = d["title"] as? String ?? ""
            date = d["date"] as? String ?? ""
            time = d["time"] as? String ?? ""
            place = d["place"] as? String ?? ""
            url = d["url"] as? String ?? ""
            site = d["site"] as? String ?? ""
            who = d["who"] as? String ?? ""
            whoKey = d["who_key"] as? String ?? ""
            role = d["role"] as? String ?? "attends"
            why = d["why"] as? String ?? ""
            bring = (d["bring"] as? [[String: Any]] ?? []).map { ($0["key"] as? String ?? "", $0["name"] as? String ?? "") }
        }

        var day: Date? { Connections.dayFormatter.date(from: date) }
    }

    let recording: String
    let evening: String
    let proposals: [Proposal]
    let events: [Event]
    let usd: Double
    let tokens: Int

    init?(_ d: [String: Any]) {
        guard let rid = d["recording"] as? String else { return nil }
        recording = rid
        evening = d["event"] as? String ?? ""
        proposals = (d["introductions"] as? [[String: Any]] ?? []).compactMap(Proposal.init)
        events = ((d["lookahead"] as? [String: Any])?["events"] as? [[String: Any]] ?? []).map(Event.init)
        let usage = d["usage"] as? [String: Any] ?? [:]
        usd = usage["usd"] as? Double ?? 0
        tokens = usage["tokens"] as? Int ?? 0
    }

    static let dayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f
    }()

    /// A person's colour here: the same one wherever they appear on the page, never the accent's teal.
    static func color(for key: String, avoiding other: String? = nil) -> Color {
        let n = Theme.people.count - 1
        var i = Int(fnv(key) % UInt64(n)) + 1
        if let other, i == Int(fnv(other) % UInt64(n)) + 1 { i = i % n + 1 }
        return Theme.people[i]
    }

    private static func fnv(_ s: String) -> UInt64 {
        var h: UInt64 = 0xcbf29ce484222325
        for b in s.utf8 { h = (h ^ UInt64(b)) &* 0x100000001b3 }
        return h
    }
}

/// Fetches what the connector found for a recording, or the newest.
@MainActor
final class ConnectorStore: ObservableObject {
    @Published var found: Connections?
    @Published var state = ""

    func load(base: String, recording: String?) async {
        state = "Loading…"
        let d = await ReportStore.get(ServerLink.httpBase(base) + "/api/connector/" + (recording ?? "latest"))
        found = d.flatMap(Connections.init)
        state = found == nil ? "Nothing yet. It is written after the morning report." : ""
    }

    func show(_ d: [String: Any]) {
        found = Connections(d)
        state = found == nil ? "This could not be read." : ""
    }
}

/// The page: who should meet, as two linked cards with what each said and the collaboration in one line under them,
/// then where to meet them next week. It comes in the way a thought does: one person, the other, the thread between
/// them, the idea, then the evening to make it happen.
struct ConnectorView: View {
    let serverURL: String
    let recording: String?
    var preloaded: [String: Any]? = nil
    /// The owner taps "Ask Ben first": the app opens a draft to them. Without it, the page only says whom to ask.
    var onAsk: ((Connections.Proposal) -> Void)? = nil
    /// A person's face (key, name, company), as the morning report finds it; their initial in their colour without.
    var face: ((String, String, String) async -> UIImage?)? = nil

    @StateObject private var store = ConnectorStore()
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var stage = 0
    @State private var started = false

    var body: some View {
        ZStack {
            PaperBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    header
                    if let c = store.found {
                        if c.proposals.isEmpty {
                            nothingYet
                        }
                        ForEach(Array(c.proposals.enumerated()), id: \.element.id) { i, p in
                            proposal(p, first: i == 0, colors: colors(c))
                        }
                        if !c.events.isEmpty {
                            lookAhead(c)
                        }
                        footer(c)
                    } else if !store.state.isEmpty {
                        Text(store.state).font(.system(size: 16, design: .serif)).foregroundStyle(Theme.inkSoft)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 20)
                .padding(.top, 12)
                .padding(.bottom, 44)
            }
            .scrollIndicators(.hidden)
        }
        .onAppear {
            // a plain Task, as the morning report does: .task is cancelled when the sheet re-lays out mid-request
            guard !started else { return }
            started = true
            Task {
                if let preloaded { store.show(preloaded) } else {
                    await store.load(base: serverURL, recording: recording?.isEmpty == false ? recording : nil)
                }
                await reveal()
            }
        }
    }

    // MARK: the reveal

    /// 1 the header, 2 the first person, 3 the second, 4 the thread between them, 5 the idea, 6 next week.
    private func reveal() async {
        guard !reduceMotion else {
            stage = 6
            return
        }
        for (next, pause) in [(1, 150), (2, 420), (3, 520), (4, 560), (5, 520), (6, 650)] {
            try? await Task.sleep(for: .milliseconds(pause))
            withAnimation(next == 4 ? .easeInOut(duration: 0.7) : .spring(duration: 0.7, bounce: 0.12)) { stage = next }
            if next == 4 { UIImpactFeedbackGenerator(style: .soft).impactOccurred(intensity: 0.7) }
        }
    }

    /// The first introduction comes in step by step; any others with its idea.
    private func shown(_ at: Int, first: Bool) -> Bool { stage >= (first ? at : 5) }

    // MARK: header

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(store.found.map { $0.evening.isEmpty ? "After tonight" : "After \($0.evening)" } ?? "After tonight",
                  systemImage: "moon.stars")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.accent)
            Text("Who should meet")
                .font(.system(size: 34, weight: .bold, design: .serif))
                .foregroundStyle(Theme.inkStrong)
            Text(subtitle)
                .font(.system(size: 17, design: .serif)).italic()
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
        }
        .opacity(stage >= 1 ? 1 : 0)
        .offset(y: stage >= 1 ? 0 : 8)
    }

    private var subtitle: String {
        guard let c = store.found else { return "" }
        switch c.proposals.count {
        case 0: return "From what everyone said this week."
        case 1: return "An introduction nobody asked for."
        default: return "\(c.proposals.count) introductions nobody asked for, in their own words."
        }
    }

    private var nothingYet: some View {
        Text("Nothing anyone said fits anyone else yet, and Hallwise will not make one up.")
            .font(.system(size: 17, design: .serif))
            .foregroundStyle(Theme.ink)
            .fixedSize(horizontal: false, vertical: true)
            .opacity(stage >= 2 ? 1 : 0)
    }

    // MARK: one introduction

    /// Each person's colour on this page: the two sides of an introduction never share one.
    private func colors(_ c: Connections) -> [String: Color] {
        var out: [String: Color] = [:]
        for p in c.proposals {
            out[p.a.id] = out[p.a.id] ?? Connections.color(for: p.a.id)
            out[p.b.id] = out[p.b.id] ?? Connections.color(for: p.b.id, avoiding: p.a.id)
        }
        return out
    }

    private func proposal(_ p: Connections.Proposal, first: Bool, colors: [String: Color]) -> some View {
        let colorA = colors[p.a.id] ?? Connections.color(for: p.a.id)
        let colorB = colors[p.b.id] ?? Connections.color(for: p.b.id, avoiding: p.a.id)
        return VStack(alignment: .leading, spacing: 0) {
            PersonCard(person: p.a, color: colorA, face: face)
                .opacity(shown(2, first: first) ? 1 : 0)
                .offset(x: shown(2, first: first) ? 0 : -24)
            LinkThread(colorA: colorA, colorB: colorB, drawn: shown(4, first: first), note: p.sameEvening ? "" : "Never in the same room")
            PersonCard(person: p.b, color: colorB, face: face)
                .opacity(shown(3, first: first) ? 1 : 0)
                .offset(x: shown(3, first: first) ? 0 : 24)
            idea(p)
                .padding(.top, 18)
                .opacity(shown(5, first: first) ? 1 : 0)
                .offset(y: shown(5, first: first) ? 0 : 10)
        }
    }

    private func idea(_ p: Connections.Proposal) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Image(systemName: "arrow.turn.down.right")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(Theme.accent)
                Text(p.collaboration.capitalisedFirst)
                    .font(.system(size: 23, weight: .semibold, design: .serif))
                    .foregroundStyle(Theme.inkStrong)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !p.why.isEmpty {
                Text(p.why)
                    .font(.system(size: 14))
                    .foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.leading, 28)
            }
            askFirst(p).padding(.leading, 28)
        }
    }

    @ViewBuilder
    private func askFirst(_ p: Connections.Proposal) -> some View {
        let who = p.asked
        let label = HStack(spacing: 7) {
            Image(systemName: "bubble.left.and.text.bubble.right").font(.system(size: 13, weight: .semibold))
            Text("Ask \(who.firstName) first").font(.system(size: 14, weight: .semibold))
        }
        if let onAsk {
            Button { onAsk(p) } label: {
                label.foregroundStyle(Theme.paper)
                    .padding(.horizontal, 14).frame(height: 38)
                    .background(Capsule().fill(Theme.accent))
            }
            .buttonStyle(.plain)
        } else {
            label.foregroundStyle(Theme.accent)
        }
    }

    // MARK: next week

    private func lookAhead(_ c: Connections) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Where to meet them next").font(.system(size: 20, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                Text("From a page the search returned").font(.system(size: 13)).foregroundStyle(Theme.inkSoft)
            }
            ForEach(c.events) { e in
                EventTicket(event: e, colors: colors(c))
            }
        }
        .opacity(stage >= 6 ? 1 : 0)
        .offset(y: stage >= 6 ? 0 : 16)
    }

    private func footer(_ c: Connections) -> some View {
        Text("Every quote is from what the badge heard; every event, from a page a search returned. Nothing here was promised, and nothing is made up."
             + (c.tokens > 0 ? " · \(c.tokens.formatted()) tokens · " + String(format: "$%.2f", c.usd) : ""))
            .font(.system(size: 12))
            .foregroundStyle(Theme.inkSoft)
            .fixedSize(horizontal: false, vertical: true)
            .opacity(stage >= 6 ? 1 : 0)
    }

}

/// One person: their face or initial in their colour, who they are, what they want in a sentence, and what they
/// said, in their words, with the part it rests on in full ink.
private struct PersonCard: View {
    let person: Connections.Person
    let color: Color
    let face: ((String, String, String) async -> UIImage?)?
    @State private var image: UIImage?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 12) {
                avatar
                VStack(alignment: .leading, spacing: 1) {
                    Text(person.name)
                        .font(.system(size: 19, weight: .semibold, design: .serif))
                        .foregroundStyle(Theme.inkStrong)
                    if !person.company.isEmpty {
                        Text(person.company).font(.system(size: 13, weight: .medium)).foregroundStyle(color)
                    }
                }
                Spacer(minLength: 0)
            }
            if !person.wants.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    Text(person.wants.asSentence)
                        .font(.system(size: 15))
                        .foregroundStyle(Theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    // what research added, with the page it came from
                    if let host = person.sources.first.flatMap({ URL(string: $0)?.host() }) {
                        Label(host, systemImage: "globe")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
            }
            if let line = person.line {
                said(line)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 18).fill(Theme.paperDeep))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Theme.rule, lineWidth: 0.5))
        .shadow(color: Theme.ink.opacity(0.06), radius: 10, y: 4)
        .task {
            guard image == nil, let face else { return }
            image = await face(person.id, person.name, person.company)
        }
    }

    private var avatar: some View {
        Group {
            if let image {
                Image(uiImage: image).resizable().scaledToFill()
            } else {
                Text(String(person.name.prefix(1)))
                    .font(.system(size: 20, weight: .semibold, design: .serif))
                    .foregroundStyle(Theme.paper)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(color)
            }
        }
        .frame(width: 46, height: 46)
        .clipShape(Circle())
        .overlay(Circle().stroke(color, lineWidth: 2).padding(-3))
    }

    /// What they said: the line in their language, its English under it when it had to be translated, and where.
    /// A line said not to the owner says so: it is for his eyes, and a follow-up never quotes it.
    private func said(_ line: Connections.Said) -> some View {
        let translated = !line.english.isEmpty && line.english != line.quote
        return HStack(alignment: .top, spacing: 12) {
            Capsule().fill(color.opacity(0.85)).frame(width: 3)
            VStack(alignment: .leading, spacing: 6) {
                Text(highlighted(line.quote, size: translated ? 16 : 17))
                    .fixedSize(horizontal: false, vertical: true)
                if translated {
                    Text(highlighted(line.english, size: 15))
                        .fixedSize(horizontal: false, vertical: true)
                }
                HStack(spacing: 8) {
                    Text(line.whereSaid)
                    if line.aside {
                        Label("not said to you", systemImage: "ear")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(color)
                            .padding(.horizontal, 7).frame(height: 20)
                            .background(Capsule().fill(color.opacity(0.12)))
                            .accessibilityHint("For your eyes only: a follow-up never quotes it.")
                    }
                }
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(Theme.inkSoft)
                .padding(.top, 2)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// The line in serif italic, the quoted words in full ink and the rest softer; all of it in ink when the quote
    /// is not found word for word (another spelling, the other language). Japanese, Chinese and Korean keep
    /// their own corner quotes and stand upright: slanted kana are a typographer's nightmare.
    private func highlighted(_ text: String, size: CGFloat) -> AttributedString {
        let cjk = text.unicodeScalars.contains { (0x3040...0x30FF).contains($0.value) || (0x3400...0x9FFF).contains($0.value) || (0xAC00...0xD7AF).contains($0.value) }
        var out = AttributedString(cjk ? "「" + text + "」" : "“" + text + "”")
        out.font = cjk ? .system(size: size, design: .serif) : .system(size: size, design: .serif).italic()
        let quote = person.quote.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !quote.isEmpty, quote.count < text.count, let r = out.range(of: quote, options: [.caseInsensitive, .diacriticInsensitive]) else {
            out.foregroundColor = Theme.ink
            return out
        }
        out.foregroundColor = Theme.inkSoft
        out[r].foregroundColor = Theme.inkStrong
        return out
    }
}

/// The thread between the two cards: a line from one colour to the other, drawn down, and the knot where it ties.
private struct LinkThread: View {
    let colorA: Color
    let colorB: Color
    let drawn: Bool
    let note: String

    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                LinearGradient(colors: [colorA, colorB], startPoint: .top, endPoint: .bottom)
                    .frame(width: 2.5)
                    .scaleEffect(x: 1, y: drawn ? 1 : 0, anchor: .top)
                Image(systemName: "link")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(Theme.paper)
                    .frame(width: 28, height: 28)
                    .background(Circle().fill(Theme.accent))
                    .overlay(Circle().stroke(Theme.paper, lineWidth: 3))
                    .scaleEffect(drawn ? 1 : 0.2)
                    .opacity(drawn ? 1 : 0)
            }
            .frame(width: 46)
            if !note.isEmpty {
                Text(note)
                    .font(.system(size: 13, design: .serif)).italic()
                    .foregroundStyle(Theme.inkSoft)
                    .opacity(drawn ? 1 : 0)
            }
            Spacer(minLength: 0)
        }
        .frame(height: 44)
        .padding(.leading, 16)
        .accessibilityHidden(true)
    }
}

/// Next week's event as a ticket: the date on the stub, then what it is, who will be there, whom to bring and the
/// page it comes from.
private struct EventTicket: View {
    let event: Connections.Event
    let colors: [String: Color]

    private func color(_ key: String) -> Color { colors[key] ?? Connections.color(for: key) }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            stub.frame(width: 76)
            VStack(alignment: .leading, spacing: 9) {
                Text(event.title)
                    .font(.system(size: 17, weight: .semibold, design: .serif))
                    .foregroundStyle(Theme.inkStrong)
                    .fixedSize(horizontal: false, vertical: true)
                Text([event.time, event.place].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.system(size: 13)).foregroundStyle(Theme.inkSoft)
                HStack(spacing: 7) {
                    Circle().fill(event.whoKey.isEmpty ? Theme.inkSoft : color(event.whoKey)).frame(width: 9, height: 9)
                    Text("\(event.who) \(event.role)")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                }
                if !event.why.isEmpty {
                    Text(event.why)
                        .font(.system(size: 14)).foregroundStyle(Theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if !event.bring.isEmpty {
                    HStack(spacing: 6) {
                        Text("Bring").font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.inkSoft)
                        ForEach(event.bring, id: \.key) { b in
                            HStack(spacing: 5) {
                                Text(String(b.name.prefix(1)))
                                    .font(.system(size: 11, weight: .bold, design: .serif))
                                    .foregroundStyle(Theme.paper)
                                    .frame(width: 20, height: 20)
                                    .background(Circle().fill(color(b.key)))
                                Text(b.name).font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.ink)
                            }
                            .padding(.leading, 3).padding(.trailing, 9).frame(height: 26)
                            .background(Capsule().fill(Theme.paper))
                            .overlay(Capsule().stroke(Theme.rule, lineWidth: 0.5))
                        }
                    }
                }
                if let url = ServerData.webURL(event.url) {
                    Link(destination: url) {
                        Label(event.site.isEmpty ? (url.host() ?? event.url) : event.site, systemImage: "link")
                            .font(.system(size: 12, weight: .medium))
                    }
                    .foregroundStyle(Theme.accent)
                }
            }
            .padding(.vertical, 16)
            .padding(.leading, 16)
            .padding(.trailing, 14)
        }
        .background(TicketShape(stub: 76).fill(Theme.paperDeep))
        .overlay(TicketShape(stub: 76).stroke(Theme.rule, lineWidth: 0.5))
        .overlay(alignment: .leading) {
            Perforation().stroke(Theme.rule, style: StrokeStyle(lineWidth: 1, dash: [3, 4]))
                .frame(width: 1).padding(.vertical, 14).offset(x: 76)
        }
        .shadow(color: Theme.ink.opacity(0.06), radius: 10, y: 4)
    }

    private var stub: some View {
        VStack(spacing: 1) {
            Text(event.day.map { $0.formatted(.dateTime.weekday(.abbreviated)) }?.uppercased() ?? "")
                .font(.system(size: 12, weight: .bold)).tracking(1.2)
                .foregroundStyle(Theme.accent)
            Text(event.day.map { $0.formatted(.dateTime.day()) } ?? "")
                .font(.system(size: 36, weight: .bold, design: .serif))
                .foregroundStyle(Theme.inkStrong)
            Text(event.day.map { $0.formatted(.dateTime.month(.abbreviated)) }?.uppercased() ?? event.date)
                .font(.system(size: 12, weight: .semibold)).tracking(1.2)
                .foregroundStyle(Theme.inkSoft)
        }
        .padding(.top, 18)
        .frame(maxWidth: .infinity)
    }
}

/// A rounded card with a notch top and bottom where the stub tears off.
private struct TicketShape: Shape {
    let stub: CGFloat
    var radius: CGFloat = 18
    var notch: CGFloat = 8

    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX + radius, y: r.minY))
        p.addLine(to: CGPoint(x: r.minX + stub - notch, y: r.minY))
        p.addArc(center: CGPoint(x: r.minX + stub, y: r.minY), radius: notch, startAngle: .degrees(180), endAngle: .degrees(0), clockwise: true)
        p.addLine(to: CGPoint(x: r.maxX - radius, y: r.minY))
        p.addArc(center: CGPoint(x: r.maxX - radius, y: r.minY + radius), radius: radius, startAngle: .degrees(-90), endAngle: .degrees(0), clockwise: false)
        p.addLine(to: CGPoint(x: r.maxX, y: r.maxY - radius))
        p.addArc(center: CGPoint(x: r.maxX - radius, y: r.maxY - radius), radius: radius, startAngle: .degrees(0), endAngle: .degrees(90), clockwise: false)
        p.addLine(to: CGPoint(x: r.minX + stub + notch, y: r.maxY))
        p.addArc(center: CGPoint(x: r.minX + stub, y: r.maxY), radius: notch, startAngle: .degrees(0), endAngle: .degrees(180), clockwise: true)
        p.addLine(to: CGPoint(x: r.minX + radius, y: r.maxY))
        p.addArc(center: CGPoint(x: r.minX + radius, y: r.maxY - radius), radius: radius, startAngle: .degrees(90), endAngle: .degrees(180), clockwise: false)
        p.addLine(to: CGPoint(x: r.minX, y: r.minY + radius))
        p.addArc(center: CGPoint(x: r.minX + radius, y: r.minY + radius), radius: radius, startAngle: .degrees(180), endAngle: .degrees(270), clockwise: false)
        p.closeSubpath()
        return p
    }
}

/// A vertical line down the middle of its frame: the perforation.
private struct Perforation: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.midX, y: r.minY))
        p.addLine(to: CGPoint(x: r.midX, y: r.maxY))
        return p
    }
}

extension Connections {
    /// The demo's fixed result (Resources/ConnectorDemo.json): made beforehand by connector.py with the real models,
    /// from the rehearsed week, so the page can be shown on cue with nothing running live. Pass it as `preloaded`.
    static var demo: [String: Any]? {
        guard let url = Bundle.main.url(forResource: "ConnectorDemo", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
}

private extension String {
    /// "a pilot of …" -> "A pilot of …": the model's line as a headline.
    var capitalisedFirst: String { first.map { $0.uppercased() + dropFirst() } ?? self }
    /// "builds compact arms" -> "Builds compact arms.": the model's sentence, as a sentence.
    var asSentence: String {
        let out = capitalisedFirst
        return out.last.map { ".!?".contains($0) } ?? true ? out : out + "."
    }
}
