import SwiftUI
import UIKit

/// The pages after the badge, one screen each: Room (the radar and the subtitle), People, Owe (promises),
/// Words (misheard words to settle), Talk (the transcript).
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
}

func mmss(_ ms: Int) -> String {
    let s = max(0, ms / 1000)
    return "\(s / 60):\(String(format: "%02d", s % 60))"
}

/// A section header in the paper voice instead of the system's.
struct PaperHeader: View {
    let text: String
    var body: some View {
        Text(text)
            .font(.system(size: 17, weight: .semibold, design: .serif))
            .foregroundStyle(Theme.ink)
            .textCase(nil)
    }
}

// MARK: - Room

struct RoomPage: View {
    @ObservedObject var app: AppModel
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    @Binding var showBadge: Bool
    @State private var selected: LiveModel.Person?
    @State private var confirmStop = false

    var body: some View {
        VStack(spacing: 14) {
            RadarView(live: live, offset: settings.yawOffset, ownerInitial: ownerInitial, listening: app.listening && !app.paused) { person in
                selected = person
            }
            .padding(.horizontal, 8)
            controls
            subtitle
            Spacer(minLength: 0)
        }
        .padding(.top, 4)
        .sheet(item: $selected) { p in PersonDetail(person: p, live: live).presentationDetents([.medium, .large]) }
        .confirmationDialog("Stop listening?", isPresented: $confirmStop, titleVisibility: .visible) {
            Button("Stop", role: .destructive) { app.stop() }
            Button("Keep going", role: .cancel) {}
        } message: {
            Text("The recording ends and the people, promises and words so far are kept.")
        }
    }

    private var ownerInitial: String {
        settings.ownerName.first.map { String($0).uppercased() } ?? "•"
    }

    /// The one control that matters, in the middle where a thumb lands. Start flips back to the badge:
    /// the phone goes on the chest, name out, and Hallwise listens from there.
    @ViewBuilder
    private var controls: some View {
        if app.listening {
            HStack(spacing: 14) {
                bigButton(app.paused ? "Resume" : "Pause", icon: app.paused ? "play.fill" : "pause.fill",
                          fill: Theme.paperDeep, text: Theme.ink) {
                    app.paused ? app.resume() : app.pause()
                }
                bigButton("Stop", icon: "stop.fill", fill: Theme.live, text: Theme.paper) { confirmStop = true }
            }
            .padding(.horizontal, 24)
        } else {
            VStack(spacing: 8) {
                bigButton("Start", icon: "mic.fill", fill: Theme.accent, text: Theme.paper) {
                    app.start()
                    withAnimation(.easeInOut(duration: 0.35)) { showBadge = true }
                }
                .padding(.horizontal, 60)
                Text("Your badge comes back up. Hallwise listens from your chest.")
                    .font(.system(size: 13, design: .serif))
                    .foregroundStyle(Theme.inkSoft)
            }
        }
    }

    private func bigButton(_ title: String, icon: String, fill: Color, text: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon).font(.system(size: 18, weight: .semibold))
                Text(title).font(.system(size: 20, weight: .semibold))
            }
            .foregroundStyle(text)
            .frame(maxWidth: .infinity)
            .frame(height: 64)
            .background(Capsule().fill(fill))
            .overlay(Capsule().stroke(Theme.rule, lineWidth: fill == Theme.paperDeep ? 1 : 0))
        }
        .buttonStyle(.plain)
    }

    /// The last thing said, big enough to read on video, with its translation when there is one.
    @ViewBuilder
    private var subtitle: some View {
        if let line = live.subtitle {
            let isOwner = live.ownerSpeakers.contains(line.speaker)
            let name = live.speakerName(line.speaker)
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    Text(name.prefix(1).uppercased())
                        .font(.system(size: 12, weight: .semibold, design: .serif))
                        .foregroundStyle(Theme.paper)
                        .frame(width: 24, height: 24)
                        .background(Circle().fill(isOwner ? Theme.inkSoft : Theme.accent))
                    Text(name.uppercased())
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(isOwner ? Theme.inkSoft : Theme.accent)
                }
                Text(line.text)
                    .font(.system(size: 20, weight: .medium, design: .serif))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(3)
                    .contentTransition(.opacity)
                if let tr = live.translations[line.id] {
                    Text(tr.english)
                        .font(.system(size: 15, design: .serif))
                        .italic()
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(2)
                    Text("\(tr.language) → English")
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.inkSoft)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 14).fill(Theme.paperDeep))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.rule, lineWidth: 0.5))
            .padding(.horizontal, 16)
            .animation(.easeInOut(duration: 0.25), value: line.id)
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
        let talking = person.speakers.contains(live.activeSpeaker ?? "")
        HStack(alignment: .top, spacing: 12) {
            ZStack(alignment: .topTrailing) {
                if let bearing = live.relativeBearing(of: person, offset: offset) {
                    Image(systemName: "location.north.fill")
                        .rotationEffect(.degrees(-bearing))
                        .foregroundStyle(Theme.accent)
                        .frame(width: 24, height: 24)
                } else {
                    Image(systemName: "person.fill").foregroundStyle(Theme.inkSoft).frame(width: 24, height: 24)
                }
                if talking {
                    Circle().fill(Theme.accent).frame(width: 8, height: 8)
                        .shadow(color: Theme.accent.opacity(0.6), radius: 4)
                        .offset(x: 4, y: -4)
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(person.name).font(.system(.headline, design: .serif)).foregroundStyle(Theme.ink)
                Text([person.company, person.role].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.subheadline).foregroundStyle(Theme.inkSoft)
                HStack(spacing: 6) {
                    if !person.language.isEmpty { Tag(text: person.language) }
                    if !person.introducedBy.isEmpty { Tag(text: "via \(live.name(for: person.introducedBy))") }
                    if let last = live.lines.last(where: { person.speakers.contains($0.speaker) }), !talking {
                        Text("spoke \(mmss(live.tMs - lastEnd(last))) ago")
                            .font(.system(size: 13)).foregroundStyle(Theme.inkSoft)
                    }
                }
            }
            Spacer()
            Image(systemName: "chevron.right").font(.system(size: 17)).foregroundStyle(Theme.inkSoft)
        }
        .padding(.vertical, 2)
    }

    private func lastEnd(_ line: LiveModel.Line) -> Int { live.turnEnd[line.id] ?? live.tMs }
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
                    Section(header: PaperHeader(text: "Between you")) {
                        ForEach(promises) { p in PromiseRow(promise: p, live: live) }
                    }
                    .listRowBackground(Theme.paperDeep)
                }
                let said = live.lines.filter { person.speakers.contains($0.speaker) }
                if !said.isEmpty {
                    Section(header: PaperHeader(text: "They said")) {
                        ForEach(said) { line in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(line.text).font(.system(size: 16)).foregroundStyle(Theme.ink)
                                if let tr = live.translations[line.id] {
                                    Text(tr.english).font(.system(size: 15)).italic().foregroundStyle(Theme.inkSoft)
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
        let open = all.filter { !live.donePromises.contains($0.id) }
        let mine = open.filter { $0.owedBy == "owner" }
        let theirs = open.filter { $0.owedBy != "owner" }
        let done = all.filter { live.donePromises.contains($0.id) }
        List {
            if all.isEmpty {
                Text("No promises yet").foregroundStyle(Theme.inkSoft).listRowBackground(Color.clear)
            }
            if !mine.isEmpty {
                Section(header: PaperHeader(text: "You owe")) { ForEach(mine) { p in PromiseRow(promise: p, live: live) } }
                    .listRowBackground(Theme.paperDeep)
            }
            if !theirs.isEmpty {
                Section(header: PaperHeader(text: "They owe you")) { ForEach(theirs) { p in PromiseRow(promise: p, live: live) } }
                    .listRowBackground(Theme.paperDeep)
            }
            if !done.isEmpty {
                Section(header: PaperHeader(text: "Done")) { ForEach(done) { p in PromiseRow(promise: p, live: live) } }
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
        let done = live.donePromises.contains(promise.id)
        HStack(alignment: .top, spacing: 12) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    if done { live.donePromises.remove(promise.id) } else { live.donePromises.insert(promise.id) }
                }
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
            } label: {
                ZStack {
                    Circle().stroke(Theme.accent, lineWidth: 1.5).frame(width: 28, height: 28)
                    if done {
                        Circle().fill(Theme.accent).frame(width: 28, height: 28)
                        Image(systemName: "checkmark").font(.system(size: 14, weight: .bold)).foregroundStyle(Theme.paper)
                    }
                }
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            VStack(alignment: .leading, spacing: 3) {
                Text(promise.what)
                    .font(.system(size: 17))
                    .strikethrough(done)
                    .foregroundStyle(done ? Theme.inkSoft : Theme.ink)
                HStack(spacing: 6) {
                    Text(promise.owedBy == "owner" ? "to \(live.name(for: promise.owedTo))" : "from \(live.name(for: promise.owedBy))")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft)
                    if !promise.replaces.isEmpty {
                        Text(promise.replaces).strikethrough().font(.subheadline).foregroundStyle(Theme.inkSoft)
                    }
                    if !promise.due.isEmpty {
                        Text("· \(promise.due)").font(.subheadline).bold().foregroundStyle(done ? Theme.inkSoft : Theme.accent)
                    }
                }
            }
            .padding(.top, 10)
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
            Section(header: PaperHeader(text: "Check these words")) {
                if live.suspects.isEmpty {
                    Text("Nothing to check").foregroundStyle(Theme.inkSoft)
                }
                ForEach(live.suspects) { s in suspectRow(s) }
            }
            .listRowBackground(Theme.paperDeep)

            Section(header: PaperHeader(text: "Remembered words")) {
                if settings.keywordList.isEmpty {
                    Text("Nothing saved yet — kept words are sent as hints next time.")
                        .font(.subheadline).foregroundStyle(Theme.inkSoft)
                }
                ForEach(settings.keywordList, id: \.self) { word in
                    HStack {
                        Text(word).font(.system(size: 17)).foregroundStyle(Theme.ink)
                        Spacer()
                        Button { settings.forget(word) } label: {
                            Image(systemName: "minus.circle").font(.system(size: 20)).foregroundStyle(Theme.inkSoft)
                                .frame(width: 44, height: 44)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .listRowBackground(Theme.paperDeep)
        }
        .scrollContentBackground(.hidden)
        .alert("Correct this word", isPresented: Binding(get: { editing != nil }, set: { if !$0 { editing = nil } })) {
            TextField("Word", text: $draft)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.words)
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

    private func suspectRow(_ s: LiveModel.Suspect) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(s.heard).strikethrough().font(.system(size: 15)).foregroundStyle(Theme.inkSoft)
                Image(systemName: "arrow.right").font(.caption).foregroundStyle(Theme.inkSoft)
                Text(s.likely).font(.system(size: 20, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
            }
            if let line = live.line(forTurn: s.turn) {
                Text("\(live.speakerName(line.speaker)) · \(mmss(live.turnStart[line.id] ?? 0)) — “\(snippet(line.text, around: s.heard))”")
                    .font(.system(size: 13)).foregroundStyle(Theme.inkSoft).lineLimit(2)
            }
            HStack(spacing: 8) {
                Spacer()
                Button {
                    settings.remember(s.likely)
                    UINotificationFeedbackGenerator().notificationOccurred(.success)
                    withAnimation { live.resolve(s) }
                } label: {
                    Label("Keep", systemImage: "checkmark").font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(Theme.paper).frame(width: 96, height: 44)
                        .background(Capsule().fill(Theme.accent))
                }
                .buttonStyle(.plain)
                Button {
                    draft = s.likely
                    editing = s
                } label: {
                    Text("Edit").font(.system(size: 16, weight: .medium)).foregroundStyle(Theme.ink)
                        .frame(width: 72, height: 44)
                        .overlay(Capsule().stroke(Theme.rule, lineWidth: 1))
                }
                .buttonStyle(.plain)
                Button { withAnimation { live.resolve(s) } } label: {
                    Image(systemName: "xmark").font(.system(size: 16, weight: .medium)).foregroundStyle(Theme.inkSoft)
                        .frame(width: 44, height: 44)
                        .overlay(Circle().stroke(Theme.rule, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Dismiss")
            }
        }
        .padding(.vertical, 4)
    }

    private func snippet(_ text: String, around word: String) -> String {
        guard let range = text.range(of: word, options: .caseInsensitive) else { return String(text.prefix(60)) }
        let start = text.index(range.lowerBound, offsetBy: -24, limitedBy: text.startIndex) ?? text.startIndex
        let end = text.index(range.upperBound, offsetBy: 24, limitedBy: text.endIndex) ?? text.endIndex
        return (start > text.startIndex ? "…" : "") + text[start..<end] + (end < text.endIndex ? "…" : "")
    }
}

// MARK: - Talk

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
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(filtered ? Theme.inkSoft.opacity(0.6) : (live.ownerSpeakers.contains(line.speaker) ? Theme.inkSoft : Theme.accent))
                                .frame(width: 72, alignment: .leading)
                            Text(line.text)
                                .font(.system(size: 16))
                                .foregroundStyle(filtered ? Theme.inkSoft.opacity(0.6) : Theme.ink)
                                .italic(kind == "ambient" || kind == "stage")
                        }
                        if let tr = live.translations[line.id] {
                            Text(tr.english).font(.system(size: 15)).italic().foregroundStyle(Theme.inkSoft).padding(.leading, 80)
                        }
                        if kind == "incidental" {
                            Text("filtered").font(.caption2).foregroundStyle(Theme.inkSoft.opacity(0.6)).padding(.leading, 80)
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
