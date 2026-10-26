import SwiftUI
import UIKit

/// The pages after the badge, one screen each: Room (the radar and who you met), People, Owe (promises),
/// Words (misheard words to settle), Talk (the transcript).
enum Page: Int, CaseIterable, Identifiable {
    case badge, room, people, ask, owe, words, transcript, map
    var id: Int { rawValue }
    var title: String {
        switch self {
        case .badge: return "Badge"
        case .room: return "Room"
        case .people: return "People"
        case .ask: return "Ask"
        case .map: return "Map"
        case .owe: return "Owe"
        case .words: return "Words"
        case .transcript: return "Transcript"
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
    @State private var showCamera = false
    @State private var taken: TakenPhoto?

    var body: some View {
        VStack(spacing: 14) {
            RadarView(live: live, offset: settings.yawOffset, ownerInitial: ownerInitial, listening: app.listening && !app.paused) { person in
                selected = person
            }
            .padding(.horizontal, 8)
            .overlay(alignment: .topTrailing) {
                // one photo, everyone gets a face
                if !live.peopleOrder.isEmpty {
                    Button { showCamera = true } label: {
                        Image(systemName: "camera.fill")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                            .frame(width: 48, height: 48)
                            .background(Circle().fill(Theme.paperDeep))
                            .overlay(Circle().stroke(Theme.rule, lineWidth: 0.5))
                    }
                    .buttonStyle(.plain)
                    .padding(.trailing, 16)
                    .accessibilityLabel("Photo of the people here")
                }
            }
            .fullScreenCover(isPresented: $showCamera) {
                PhotoPicker { image in
                    showCamera = false
                    // let the camera go away before the sheet comes up, or the two presentations fight
                    if let image {
                        let photo = image.normalised()
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { taken = TakenPhoto(image: photo) }
                    }
                }
                .ignoresSafeArea()
            }
            .sheet(item: $taken) { t in
                PhotoMatchSheet(photo: t.image, app: app, live: live, settings: settings)
                    .presentationDetents([.large])
                    .presentationDragIndicator(.visible)
            }
            controls
            met
            Spacer(minLength: 0)
        }
        .padding(.top, 4)
        .sheet(item: $selected) { p in PersonDetail(person: p, live: live, settings: settings).presentationDetents([.medium, .large]) }
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

    /// Who you have met tonight, newest first, with the one line that places them. Tap for the card.
    @ViewBuilder
    private var met: some View {
        let people = live.peopleOrder.compactMap { live.people[$0] }
        if !people.isEmpty {
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
                let tall = people.suffix(6).contains { !live.hooks(for: $0.id).isEmpty }
                ForEach(Array(people.suffix(6).reversed())) { p in
                    Button { selected = p } label: {
                        HStack(spacing: 8) {
                            FaceDot(live: live, key: p.id, size: 10)
                            VStack(alignment: .leading, spacing: 1) {
                                Text(p.name)
                                    .font(.system(size: 15, weight: .semibold, design: .serif))
                                    .foregroundStyle(Theme.ink).lineLimit(1)
                                if let hook = live.hooks(for: p.id).first {
                                    // the reason to write, the moment they turn up
                                    Text(hook.tag)
                                        .font(.system(size: 12, weight: .semibold)).foregroundStyle(Theme.live).lineLimit(1)
                                        .minimumScaleFactor(0.65)
                                }
                                if let h = live.history[p.id], let e = h.encounters.first {
                                    Text("met before · \(e.event.isEmpty ? dayString(e.started) : e.event)")
                                        .font(.system(size: 12, weight: .medium)).foregroundStyle(Theme.accent).lineLimit(1)
                                } else if live.hooks(for: p.id).isEmpty {
                                    Text([p.company, p.role].filter { !$0.isEmpty }.joined(separator: " · "))
                                        .font(.system(size: 12)).foregroundStyle(Theme.inkSoft).lineLimit(1)
                                }
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 10)
                        .frame(height: tall ? 58 : 46)
                        .background(RoundedRectangle(cornerRadius: 10).fill(Theme.paperDeep))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 2)
        }
    }
}

// MARK: - People

struct PeoplePage: View {
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    @StateObject private var directory = Directory()
    @State private var selected: LiveModel.Person?
    @State private var selectedKnown: DirectoryPerson?
    @State private var query = ""

    var body: some View {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        let tonight = live.peopleOrder.compactMap { live.people[$0] }
            .filter { q.isEmpty || ($0.name + " " + $0.company + " " + $0.role).lowercased().contains(q) }
        let tonightNames = Set(live.people.values.map { $0.name.lowercased() })
        let earlier = directory.people
            .filter { !tonightNames.contains($0.name.lowercased()) }
            .filter { q.isEmpty || ($0.name + " " + $0.company + " " + $0.role + " " + $0.encounters.map(\.event).joined(separator: " ")).lowercased().contains(q) }
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundStyle(Theme.inkSoft)
                TextField("Name, company, event…", text: $query)
                    .font(.system(size: 16))
                    .foregroundStyle(Theme.ink)
                    .autocorrectionDisabled()
            }
            .padding(.horizontal, 14)
            .frame(height: 44)
            .background(RoundedRectangle(cornerRadius: 12).fill(Theme.paperDeep))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.rule, lineWidth: 0.5))
            .padding(.horizontal, 16)
            .padding(.top, 8)
            List {
                Section(header: PaperHeader(text: "Tonight")) {
                    if tonight.isEmpty {
                        Text("Nobody yet").foregroundStyle(Theme.inkSoft)
                    }
                    ForEach(tonight) { p in
                        Button { selected = p } label: { PersonRow(person: p, live: live, offset: settings.yawOffset) }
                    }
                }
                .listRowBackground(Theme.paperDeep)
                if !earlier.isEmpty {
                    Section(header: PaperHeader(text: "Earlier")) {
                        ForEach(earlier) { p in
                            Button { selectedKnown = p } label: {
                                HStack(spacing: 14) {
                                    Circle().fill(Theme.inkSoft.opacity(0.5)).frame(width: 12, height: 12).frame(width: 20, height: 20)
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(p.name).font(.system(size: 17, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink).lineLimit(1)
                                        if !p.line.isEmpty { Text(p.line).font(.system(size: 15)).foregroundStyle(Theme.inkSoft).lineLimit(1) }
                                        if let e = p.encounters.first {
                                            Text([e.event.isEmpty ? "untitled" : e.event, dayString(e.started)].filter { !$0.isEmpty }.joined(separator: " · ")
                                                 + (p.encounters.count > 1 ? " · ×\(p.encounters.count)" : ""))
                                                .font(.system(size: 13)).foregroundStyle(Theme.inkSoft).lineLimit(1)
                                        }
                                    }
                                    Spacer(minLength: 8)
                                    Image(systemName: "chevron.right").font(.system(size: 17)).foregroundStyle(Theme.inkSoft)
                                }
                                .padding(.vertical, 4)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .listRowBackground(Theme.paperDeep)
                }
            }
            .scrollContentBackground(.hidden)
            .scrollDismissesKeyboard(.interactively)
        }
        .task { await directory.load(base: settings.serverURL) }
        .sheet(item: $selected) { p in PersonDetail(person: p, live: live, settings: settings).presentationDetents([.medium, .large]) }
        .sheet(item: $selectedKnown) { p in KnownPersonSheet(person: p, settings: settings).presentationDetents([.medium, .large]) }
    }
}

struct PersonRow: View {
    let person: LiveModel.Person
    @ObservedObject var live: LiveModel
    let offset: Double

    var body: some View {
        let talking = person.speakers.contains(live.activeSpeaker ?? "")
        HStack(spacing: 14) {
            FaceDot(live: live, key: person.id, size: talking ? 16 : 12, ring: talking)
                .shadow(color: talking ? live.color(for: person.id).opacity(0.6) : .clear, radius: 6)
                .frame(width: 32, height: 32)
                .animation(.easeInOut(duration: 0.2), value: talking)
            VStack(alignment: .leading, spacing: 3) {
                Text(person.name)
                    .font(.system(size: 17, weight: .semibold, design: .serif))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                let line = [person.company, person.role].filter { !$0.isEmpty }.joined(separator: " · ")
                if !line.isEmpty {
                    Text(line).font(.system(size: 15)).foregroundStyle(Theme.inkSoft).lineLimit(1)
                }
                if !person.language.isEmpty || !person.introducedBy.isEmpty {
                    HStack(spacing: 6) {
                        if !person.language.isEmpty { Tag(text: person.language) }
                        if !person.introducedBy.isEmpty { Tag(text: "via \(live.name(for: person.introducedBy))") }
                    }
                }
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.right").font(.system(size: 17)).foregroundStyle(Theme.inkSoft)
        }
        .padding(.vertical, 4)
    }
}

/// One person: what you know, what you owe each other, what they said.
struct PersonDetail: View {
    let person: LiveModel.Person
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings

    var body: some View {
        ZStack {
            PaperBackground()
            List {
                Section {
                    HStack(alignment: .top, spacing: 14) {
                        if live.photos[person.id] != nil { FaceDot(live: live, key: person.id, size: 32, ring: true) }
                        VStack(alignment: .leading, spacing: 4) {
                        Text(person.name).font(.system(size: 26, weight: .bold, design: .serif)).foregroundStyle(Theme.ink)
                        Text([person.company, person.role].filter { !$0.isEmpty }.joined(separator: " · "))
                            .foregroundStyle(Theme.inkSoft)
                        HStack(spacing: 6) {
                            if !person.language.isEmpty { Tag(text: "speaks \(person.language)") }
                            if !person.introducedBy.isEmpty { Tag(text: "via \(live.name(for: person.introducedBy))") }
                        }
                        }
                    }
                    .padding(.vertical, 4)
                }
                .listRowBackground(Color.clear)
                let hooks = live.hooks(for: person.id)
                if !hooks.isEmpty {
                    Section(header: PaperHeader(text: "Why reach out now")) {
                        ForEach(hooks) { h in HookRow(hook: h) }
                    }
                    .listRowBackground(Theme.paperDeep)
                }
                if let h = live.history[person.id], !h.encounters.isEmpty {
                    Section(header: PaperHeader(text: "Before tonight")) {
                        ForEach(h.encounters) { e in
                            VStack(alignment: .leading, spacing: 2) {
                                Text([e.event.isEmpty ? "untitled" : e.event, dayString(e.started)].filter { !$0.isEmpty }.joined(separator: " · "))
                                    .font(.system(size: 16, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                                Text([e.venue, e.introducedBy.isEmpty ? "" : "via \(e.introducedBy)"].filter { !$0.isEmpty }.joined(separator: " · "))
                                    .font(.system(size: 14)).foregroundStyle(Theme.inkSoft)
                            }
                        }
                        ForEach(h.promises) { q in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(q.what).font(.system(size: 16)).foregroundStyle(Theme.ink)
                                Text([q.direction == "owner_owes" ? "you owed" : q.direction == "they_owe" ? "they owed you" : "", q.due, q.event].filter { !$0.isEmpty }.joined(separator: " · "))
                                    .font(.system(size: 14)).foregroundStyle(Theme.inkSoft)
                            }
                        }
                    }
                    .listRowBackground(Theme.paperDeep)
                }
                let promises = live.promiseOrder.compactMap { live.promises[$0] }
                    .filter { $0.owedTo == person.id || $0.owedBy == person.id }
                if !promises.isEmpty {
                    Section(header: PaperHeader(text: "Between you")) {
                        ForEach(promises) { p in PromiseRow(promise: p, live: live, settings: settings) }
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
        .preferredColorScheme(settings.colorScheme)
    }
}

/// One reason to reach out: what it is, why, and the lines it rests on, each with where and when.
struct HookRow: View {
    let hook: LiveModel.Hook

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Image(systemName: icon).font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.accent)
                Text(hook.title).font(.system(size: 17, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
            }
            if !hook.reason.isEmpty {
                Text(hook.reason).font(.system(size: 15)).foregroundStyle(Theme.ink).fixedSize(horizontal: false, vertical: true)
            }
            // the lines it rests on, unless the reason already quotes them
            ForEach(Array(hook.evidence.filter { !$0.quote.isEmpty && !hook.reason.contains($0.quote) }.prefix(3).enumerated()), id: \.offset) { _, e in
                if let url = URL(string: e.source), !e.source.isEmpty {
                    Link(destination: url) {
                        Label(e.quote + " · " + (url.host() ?? e.source), systemImage: "link").font(.system(size: 13))
                    }
                    .foregroundStyle(Theme.accent)
                } else {
                    Text(([e.event, e.day].filter { !$0.isEmpty }.joined(separator: " · "))
                         + (e.speaker.isEmpty ? "" : " · \(e.speaker)") + ": “\(e.quote)”")
                        .font(.system(size: 13, design: .serif)).italic().foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var icon: String {
        switch hook.type {
        case "introduction": return "person.line.dotted.person"
        case "mutual_connection": return "person.2.wave.2"
        case "timely": return "newspaper"
        default: return "arrow.uturn.left"
        }
    }
}

// MARK: - Owe

struct OwePage: View {
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings

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
                Section(header: PaperHeader(text: "You owe")) { ForEach(mine) { p in PromiseRow(promise: p, live: live, settings: settings) } }
                    .listRowBackground(Theme.paperDeep)
            }
            if !theirs.isEmpty {
                Section(header: PaperHeader(text: "They owe you")) { ForEach(theirs) { p in PromiseRow(promise: p, live: live, settings: settings) } }
                    .listRowBackground(Theme.paperDeep)
            }
            if !done.isEmpty {
                Section(header: PaperHeader(text: "Done")) { ForEach(done) { p in PromiseRow(promise: p, live: live, settings: settings) } }
                    .listRowBackground(Theme.paperDeep)
            }
        }
        .scrollContentBackground(.hidden)
    }
}

struct PromiseRow: View {
    let promise: LiveModel.Promise
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    @State private var draft: LiveModel.Move?

    var body: some View {
        let done = live.donePromises.contains(promise.id)
        let move = live.moves[promise.id]
        HStack(alignment: .top, spacing: 12) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    if done { live.markUndone(promise.id) } else { live.markDone(promise.id) }
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
            Spacer(minLength: 4)
            if let move, !done {
                // The follow-up is written; one tap to read it and send it.
                Button { draft = move } label: {
                    VStack(spacing: 3) {
                        Image(systemName: move.kind == "calendar" ? "calendar.badge.plus" : "paperplane.fill")
                            .font(.system(size: 18, weight: .semibold))
                        Text(move.kind == "calendar" ? "Invite" : move.kind == "nudge" ? "Nudge" : "Draft")
                            .font(.system(size: 11, weight: .semibold))
                    }
                    .foregroundStyle(Theme.paper)
                    .frame(width: 56, height: 52)
                    .background(RoundedRectangle(cornerRadius: 12).fill(Theme.accent))
                }
                .buttonStyle(.plain)
                .padding(.top, 2)
            }
        }
        .padding(.vertical, 2)
        .sheet(item: $draft) { m in
            MoveSheet(move: m, promise: promise, live: live, settings: settings, hook: live.hooks(for: m.personKey).first)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
    }
}

/// One follow-up, as the server wrote it: read it, copy it, share it to any app, or put the proposed time in
/// the calendar. Nothing leaves the phone until the owner taps a channel.
struct MoveSheet: View {
    let move: LiveModel.Move
    let promise: LiveModel.Promise
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    var personName: String? = nil      // from the morning report, when tonight's record is not on the phone
    var hook: LiveModel.Hook? = nil    // the reason to write, when there is one
    @State private var share: ShareItems?
    @State private var calendar = false
    @State private var copied = false

    private var person: String { personName ?? live.name(for: move.personKey) }
    private var attachment: String? { move.attach.isEmpty ? nil : settings.links[move.attach] }
    private var text: String { [move.body, attachment].compactMap { $0 }.joined(separator: "\n\n") }
    private var when: Date? { move.when.isEmpty ? nil : OwnerCalendar.parse(move.when) }

    private var kindLine: String {
        switch move.kind {
        case "calendar": return "Invitation" + (move.language.isEmpty || move.language == "English" ? "" : " · \(move.language)")
        case "email": return "Email" + (move.language.isEmpty || move.language == "English" ? "" : " · \(move.language)")
        case "nudge": return "Nudge · send in a few days"
        default: return "Message" + (move.language.isEmpty || move.language == "English" ? "" : " · \(move.language)")
        }
    }

    var body: some View {
        ZStack {
            PaperBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("To \(person)")
                            .font(.system(size: 26, weight: .bold, design: .serif))
                            .foregroundStyle(Theme.ink)
                        Text(kindLine).font(.subheadline).foregroundStyle(Theme.inkSoft)
                    }
                    HStack(spacing: 6) {
                        Image(systemName: "checklist").foregroundStyle(Theme.inkSoft)
                        Text(promise.what + (promise.due.isEmpty ? "" : " · \(promise.due)"))
                            .font(.system(size: 14)).foregroundStyle(Theme.inkSoft)
                    }
                    if let hook {
                        VStack(alignment: .leading, spacing: 4) {
                            Label(hook.tag, systemImage: "sparkle").font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.accent)
                            Text(hook.reason).font(.system(size: 14)).foregroundStyle(Theme.ink)
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(RoundedRectangle(cornerRadius: 12).fill(Theme.paperDeep))
                    }
                    if !move.subject.isEmpty {
                        Text(move.subject).font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.ink)
                    }
                    Text(move.body)
                        .font(.system(size: 18, design: .serif))
                        .foregroundStyle(Theme.ink)
                        .textSelection(.enabled)
                    if !move.bodyEnglish.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(move.bodyEnglish).font(.system(size: 15, design: .serif)).italic().foregroundStyle(Theme.inkSoft)
                            Text("\(move.language) → English, translated").font(.system(size: 12)).foregroundStyle(Theme.inkSoft)
                        }
                    }
                    if let attachment {
                        HStack(spacing: 8) {
                            Image(systemName: "paperclip").foregroundStyle(Theme.accent)
                            Text(attachment).font(.system(size: 14)).foregroundStyle(Theme.ink).lineLimit(1)
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(RoundedRectangle(cornerRadius: 10).fill(Theme.paperDeep))
                    }
                    if let when {
                        HStack(spacing: 8) {
                            Image(systemName: "calendar").foregroundStyle(Theme.accent)
                            Text(when, format: .dateTime.weekday(.wide).month().day().hour().minute())
                                .font(.system(size: 16, weight: .semibold)).foregroundStyle(Theme.ink)
                            Text("· \(move.durationMinutes) min").font(.system(size: 14)).foregroundStyle(Theme.inkSoft)
                        }
                    }
                    if !move.why.isEmpty {
                        Text(move.why).font(.system(size: 13)).foregroundStyle(Theme.inkSoft)
                    }
                    VStack(spacing: 10) {
                        HStack(spacing: 10) {
                            action(copied ? "Copied" : "Copy", icon: copied ? "checkmark" : "doc.on.doc", fill: Theme.paperDeep, text: Theme.ink) {
                                UIPasteboard.general.string = text
                                withAnimation { copied = true }
                            }
                            action("Share", icon: "square.and.arrow.up", fill: Theme.accent, text: Theme.paper) {
                                share = ShareItems(items: [text])
                            }
                        }
                        if when != nil {
                            action("Add to calendar", icon: "calendar.badge.plus", fill: Theme.ink, text: Theme.paper) { calendar = true }
                        }
                    }
                    .padding(.top, 6)
                }
                .padding(20)
                .padding(.top, 10)
            }
        }
        .preferredColorScheme(settings.colorScheme)
        .sheet(item: $share) { ShareSheet(items: $0.items) }
        .sheet(isPresented: $calendar) {
            if let when {
                CalendarEditor(title: "\(person) · \(promise.what)", start: when, minutes: move.durationMinutes, notes: text) {
                    live.calendarAdded.insert(promise.id)
                }
                .ignoresSafeArea()
            }
        }
    }

    private func action(_ title: String, icon: String, fill: Color, text: Color, run: @escaping () -> Void) -> some View {
        Button(action: run) {
            HStack(spacing: 8) {
                Image(systemName: icon).font(.system(size: 17, weight: .semibold))
                Text(title).font(.system(size: 17, weight: .semibold))
            }
            .foregroundStyle(text)
            .frame(maxWidth: .infinity)
            .frame(height: 56)
            .background(RoundedRectangle(cornerRadius: 14).fill(fill))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.rule, lineWidth: fill == Theme.paperDeep ? 1 : 0))
        }
        .buttonStyle(.plain)
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
                                .foregroundStyle(filtered ? Theme.inkSoft.opacity(0.6) : live.color(forSpeaker: line.speaker))
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
