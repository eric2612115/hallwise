import SwiftUI

/// The pages after the badge, one screen each, reached by swiping or by the strip at the top:
/// Room (the radar and the subtitle), People, Owe, Words, Transcript.
enum Page: Int, CaseIterable, Identifiable {
    case badge, room, people, owe, words, transcript
    var id: Int { rawValue }
    var title: String {
        switch self {
        case .badge: return "Badge"
        case .room: return "Room"
        case .people: return "People"
        case .owe: return "Owe"
        case .words: return "Words"
        case .transcript: return "Talk"
        }
    }
    static let live: [Page] = [.room, .people, .owe, .words, .transcript]
}

// MARK: - Room

struct RoomPage: View {
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings

    var body: some View {
        VStack(spacing: 12) {
            RadarView(live: live, offset: settings.yawOffset)
                .padding(.horizontal, 8)
            subtitle
            Spacer(minLength: 0)
        }
        .padding(.top, 8)
    }

    /// The last thing said, big enough to read on video, with its translation when there is one.
    @ViewBuilder
    private var subtitle: some View {
        if let line = live.subtitle {
            VStack(alignment: .leading, spacing: 6) {
                Text(live.speakerName(line.speaker).uppercased())
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(live.ownerSpeakers.contains(line.speaker) ? Theme.inkSoft : Theme.accent)
                Text(line.text)
                    .font(.system(size: 20, weight: .medium, design: .serif))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(3)
                if let tr = live.translations[line.id] {
                    (Text(tr.english).italic() + Text("  translated from \(tr.language)").font(.caption))
                        .font(.system(size: 15, design: .serif))
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(2)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12).fill(Theme.paperDeep))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.rule, lineWidth: 0.5))
            .padding(.horizontal, 16)
        } else {
            Text(live.lines.isEmpty ? "Start, then walk up to someone." : "")
                .font(.system(size: 15, design: .serif))
                .foregroundStyle(Theme.inkSoft)
        }
    }
}

// MARK: - People

struct PeoplePage: View {
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    @State private var selected: LiveModel.Person?

    var body: some View {
        List {
            if live.peopleOrder.isEmpty {
                Text("Nobody yet").foregroundStyle(Theme.inkSoft).listRowBackground(Color.clear)
            }
            ForEach(live.peopleOrder, id: \.self) { key in
                if let p = live.people[key] {
                    Button { selected = p } label: { PersonRow(person: p, live: live, offset: settings.yawOffset) }
                        .listRowBackground(Theme.paperDeep)
                }
            }
        }
        .scrollContentBackground(.hidden)
        .sheet(item: $selected) { p in PersonDetail(person: p, live: live).presentationDetents([.medium, .large]) }
    }
}

struct PersonRow: View {
    let person: LiveModel.Person
    @ObservedObject var live: LiveModel
    let offset: Double

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            if let bearing = live.relativeBearing(of: person, offset: offset) {
                Image(systemName: "location.north.fill")
                    .rotationEffect(.degrees(-bearing))
                    .foregroundStyle(Theme.accent)
                    .frame(width: 24)
            } else {
                Image(systemName: "person.fill").foregroundStyle(Theme.inkSoft).frame(width: 24)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(person.name).font(.system(.headline, design: .serif)).foregroundStyle(Theme.ink)
                Text([person.company, person.role].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.subheadline).foregroundStyle(Theme.inkSoft)
                HStack(spacing: 6) {
                    if !person.language.isEmpty { Tag(text: person.language) }
                    if !person.introducedBy.isEmpty { Tag(text: "via \(live.name(for: person.introducedBy))") }
                }
            }
            Spacer()
            Image(systemName: "chevron.right").font(.caption).foregroundStyle(Theme.inkSoft)
        }
        .padding(.vertical, 2)
    }
}

/// One person: what you know, what you owe each other, what they said.
struct PersonDetail: View {
    let person: LiveModel.Person
    @ObservedObject var live: LiveModel

    var body: some View {
        ZStack {
            PaperBackground()
            List {
                Section {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(person.name).font(.system(size: 26, weight: .bold, design: .serif)).foregroundStyle(Theme.ink)
                        Text([person.company, person.role].filter { !$0.isEmpty }.joined(separator: " · "))
                            .foregroundStyle(Theme.inkSoft)
                        HStack(spacing: 6) {
                            if !person.language.isEmpty { Tag(text: "speaks \(person.language)") }
                            if !person.introducedBy.isEmpty { Tag(text: "via \(live.name(for: person.introducedBy))") }
                        }
                    }
                    .padding(.vertical, 4)
                }
                .listRowBackground(Color.clear)
                let promises = live.promiseOrder.compactMap { live.promises[$0] }
                    .filter { $0.owedTo == person.id || $0.owedBy == person.id }
                if !promises.isEmpty {
                    Section("Between you") {
                        ForEach(promises) { p in PromiseRow(promise: p, live: live) }
                    }
                    .listRowBackground(Theme.paperDeep)
                }
                let said = live.lines.filter { person.speakers.contains($0.speaker) }
                if !said.isEmpty {
                    Section("They said") {
                        ForEach(said) { line in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(line.text).font(.footnote).foregroundStyle(Theme.ink)
                                if let tr = live.translations[line.id] {
                                    Text(tr.english).font(.footnote).italic().foregroundStyle(Theme.inkSoft)
                                }
                            }
                        }
                    }
                    .listRowBackground(Theme.paperDeep)
                }
            }
            .scrollContentBackground(.hidden)
        }
    }
}

// MARK: - Owe

struct OwePage: View {
    @ObservedObject var live: LiveModel

    var body: some View {
        let all = live.promiseOrder.compactMap { live.promises[$0] }
        let mine = all.filter { $0.owedBy == "owner" }
        let theirs = all.filter { $0.owedBy != "owner" }
        List {
            if all.isEmpty {
                Text("No promises yet").foregroundStyle(Theme.inkSoft).listRowBackground(Color.clear)
            }
            if !mine.isEmpty {
                Section("You owe") { ForEach(mine) { p in PromiseRow(promise: p, live: live) } }
                    .listRowBackground(Theme.paperDeep)
            }
            if !theirs.isEmpty {
                Section("They owe you") { ForEach(theirs) { p in PromiseRow(promise: p, live: live) } }
                    .listRowBackground(Theme.paperDeep)
            }
        }
        .scrollContentBackground(.hidden)
    }
}

struct PromiseRow: View {
    let promise: LiveModel.Promise
    @ObservedObject var live: LiveModel

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(promise.what).font(.body).foregroundStyle(Theme.ink)
            HStack(spacing: 6) {
                Text(promise.owedBy == "owner" ? "→ \(live.name(for: promise.owedTo))" : "\(live.name(for: promise.owedBy)) → you")
                    .font(.subheadline).foregroundStyle(Theme.inkSoft)
                if !promise.replaces.isEmpty {
                    Text(promise.replaces).strikethrough().font(.subheadline).foregroundStyle(Theme.inkSoft)
                }
                if !promise.due.isEmpty { Text(promise.due).font(.subheadline).bold().foregroundStyle(Theme.accent) }
            }
        }
        .padding(.vertical, 2)
    }
}

// MARK: - Words

/// Words the transcriber may have got wrong. One tap keeps the suggestion and remembers it; the memory is the
/// list of words sent as recognition hints on the next recording.
struct WordsPage: View {
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    @State private var editing: LiveModel.Suspect?
    @State private var draft = ""

    var body: some View {
        List {
            Section("Check these words") {
                if live.suspects.isEmpty {
                    Text("Nothing to check").foregroundStyle(Theme.inkSoft)
                }
                ForEach(live.suspects) { s in
                    HStack(spacing: 10) {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text(s.heard).strikethrough().foregroundStyle(Theme.inkSoft)
                                Image(systemName: "arrow.right").font(.caption2).foregroundStyle(Theme.inkSoft)
                                Text(s.likely).bold().foregroundStyle(Theme.ink)
                            }
                            Text("turn \(s.turn)").font(.caption).foregroundStyle(Theme.inkSoft)
                        }
                        Spacer()
                        Button {
                            settings.remember(s.likely)
                            live.resolve(s)
                        } label: { Image(systemName: "checkmark").font(.body.weight(.semibold)) }
                            .buttonStyle(.borderedProminent).tint(Theme.accent).controlSize(.small)
                        Button {
                            draft = s.likely
                            editing = s
                        } label: { Image(systemName: "pencil") }
                            .buttonStyle(.bordered).tint(Theme.inkSoft).controlSize(.small)
                        Button { live.resolve(s) } label: { Image(systemName: "xmark") }
                            .buttonStyle(.bordered).tint(Theme.inkSoft).controlSize(.small)
                    }
                }
            }
            .listRowBackground(Theme.paperDeep)

            Section("Memory — hints for next time") {
                if settings.keywordList.isEmpty {
                    Text("Empty").foregroundStyle(Theme.inkSoft)
                }
                ForEach(settings.keywordList, id: \.self) { word in
                    HStack {
                        Text(word).foregroundStyle(Theme.ink)
                        Spacer()
                        Button { settings.forget(word) } label: { Image(systemName: "minus.circle").foregroundStyle(Theme.inkSoft) }
                    }
                }
            }
            .listRowBackground(Theme.paperDeep)
        }
        .scrollContentBackground(.hidden)
        .alert("Correct this word", isPresented: Binding(get: { editing != nil }, set: { if !$0 { editing = nil } })) {
            TextField("Word", text: $draft)
            Button("Remember") {
                if let s = editing {
                    settings.remember(draft)
                    live.resolve(s)
                }
                editing = nil
            }
            Button("Cancel", role: .cancel) { editing = nil }
        } message: {
            Text("Heard “\(editing?.heard ?? "")”. Type what it should be.")
        }
    }
}

// MARK: - Transcript

struct TranscriptPage: View {
    @ObservedObject var live: LiveModel

    var body: some View {
        ScrollViewReader { proxy in
            List {
                if live.lines.isEmpty {
                    Text("Waiting for the first words…").foregroundStyle(Theme.inkSoft).listRowBackground(Color.clear)
                }
                ForEach(live.lines) { line in
                    let kind = live.turnKind[line.id] ?? "conversation"
                    let filtered = kind != "conversation"
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(live.speakerName(line.speaker))
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(filtered ? Theme.inkSoft.opacity(0.6) : (live.ownerSpeakers.contains(line.speaker) ? Theme.inkSoft : Theme.accent))
                                .frame(width: 64, alignment: .leading)
                            Text(line.text)
                                .font(.footnote)
                                .foregroundStyle(filtered ? Theme.inkSoft.opacity(0.6) : Theme.ink)
                                .italic(kind == "ambient" || kind == "stage")
                        }
                        if let tr = live.translations[line.id] {
                            Text(tr.english).font(.footnote).italic().foregroundStyle(Theme.inkSoft).padding(.leading, 72)
                        }
                        if kind == "incidental" {
                            Text("filtered").font(.caption2).foregroundStyle(Theme.inkSoft.opacity(0.6)).padding(.leading, 72)
                        }
                    }
                    .id(line.id)
                    .listRowBackground(Theme.paperDeep)
                }
            }
            .scrollContentBackground(.hidden)
            .onChange(of: live.lines.count) { _, _ in
                if let last = live.lines.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
            }
        }
    }
}
