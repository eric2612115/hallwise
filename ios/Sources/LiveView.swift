import SwiftUI

/// The owner's private view: the room around you, the last thing said, who you met, what you owe them.
/// Swipe left from the badge. This is the screen that goes into the demo video.
struct LiveView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var live: LiveModel
    @ObservedObject var link: ServerLink
    @ObservedObject var settings: BadgeSettings
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    RadarView(live: live, offset: settings.yawOffset)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 4)
                    subtitle
                }
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)

                Section {
                    HStack {
                        Circle().fill(app.listening ? Theme.live : Theme.inkSoft.opacity(0.4)).frame(width: 10, height: 10)
                        Text(link.status).font(.subheadline).foregroundStyle(Theme.inkSoft)
                        Spacer()
                        Button(app.listening ? "Stop" : "Start") { app.listening ? app.stop() : app.start() }
                            .buttonStyle(.borderedProminent)
                            .tint(app.listening ? Theme.live : Theme.accent)
                    }
                }
                .listRowBackground(Theme.paperDeep)

                Section("People") {
                    if live.peopleOrder.isEmpty { Text("Nobody yet").foregroundStyle(Theme.inkSoft) }
                    ForEach(live.peopleOrder, id: \.self) { key in
                        if let person = live.people[key] { personRow(person) }
                    }
                }
                .listRowBackground(Theme.paperDeep)

                if !live.promiseOrder.isEmpty {
                    Section("You owe · they owe") {
                        ForEach(live.promiseOrder, id: \.self) { key in
                            if let p = live.promises[key] { promiseRow(p) }
                        }
                    }
                    .listRowBackground(Theme.paperDeep)
                }

                if !live.suspects.isEmpty {
                    Section("Check these words") {
                        ForEach(live.suspects) { s in
                            HStack(spacing: 8) {
                                Text(s.heard).strikethrough().foregroundStyle(Theme.inkSoft)
                                Image(systemName: "arrow.right").font(.caption).foregroundStyle(Theme.inkSoft)
                                Text(s.likely).bold().foregroundStyle(Theme.ink)
                            }
                        }
                    }
                    .listRowBackground(Theme.paperDeep)
                }

                if !live.topics.isEmpty {
                    Section("The room is talking about") {
                        Text(live.topics.joined(separator: "  ·  ")).font(.subheadline).foregroundStyle(Theme.inkSoft)
                    }
                    .listRowBackground(Theme.paperDeep)
                }

                Section("Transcript") {
                    ForEach(live.lines.suffix(12)) { line in transcriptRow(line) }
                }
                .listRowBackground(Theme.paperDeep)
            }
            .scrollContentBackground(.hidden)
            .background(PaperBackground())
            .tint(Theme.accent)
            .navigationTitle(settings.eventName.isEmpty ? "Hallwise" : settings.eventName)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button { showSettings = true } label: { Image(systemName: "gearshape") } }
            .sheet(isPresented: $showSettings) { SettingsView(settings: settings) }
        }
    }

    /// The last thing said, big enough to read on video, with its translation when there is one.
    @ViewBuilder
    private var subtitle: some View {
        if let line = live.subtitle {
            VStack(alignment: .leading, spacing: 6) {
                Text(speakerName(line.speaker).uppercased())
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(live.ownerSpeakers.contains(line.speaker) ? Theme.inkSoft : Theme.accent)
                Text(line.text)
                    .font(.system(size: 20, weight: .medium, design: .serif))
                    .foregroundStyle(Theme.ink)
                if let tr = live.translations[line.id] {
                    Text(tr.english)
                        .font(.system(size: 15, design: .serif))
                        .italic()
                        .foregroundStyle(Theme.inkSoft)
                    + Text("  translated from \(tr.language)")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12).fill(Theme.paperDeep))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.rule, lineWidth: 0.5))
        }
    }

    private func speakerName(_ speaker: String) -> String {
        if live.ownerSpeakers.contains(speaker) { return "You" }
        if let p = live.people.values.first(where: { $0.speakers.contains(speaker) }) {
            return p.name.split(separator: " ").first.map(String.init) ?? p.name
        }
        return "Someone"
    }

    private func transcriptRow(_ line: LiveModel.Line) -> some View {
        let kind = live.turnKind[line.id] ?? "conversation"
        return VStack(alignment: .leading, spacing: 2) {
            Text("\(speakerName(line.speaker)): \(line.text)")
                .font(.footnote)
                .foregroundStyle(kind == "conversation" ? Theme.ink : Theme.inkSoft.opacity(0.6))
            if let tr = live.translations[line.id] {
                Text(tr.english).font(.footnote).italic().foregroundStyle(Theme.inkSoft)
            }
        }
    }

    private func personRow(_ p: LiveModel.Person) -> some View {
        HStack(alignment: .top, spacing: 12) {
            if let bearing = live.relativeBearing(of: p, offset: settings.yawOffset) {
                Image(systemName: "location.north.fill")
                    .rotationEffect(.degrees(-bearing))
                    .foregroundStyle(Theme.accent)
                    .frame(width: 24)
                    .accessibilityLabel("\(Int(bearing)) degrees")
            } else {
                Image(systemName: "person.fill").foregroundStyle(Theme.inkSoft).frame(width: 24)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(p.name).font(.system(.headline, design: .serif)).foregroundStyle(Theme.ink)
                Text([p.company, p.role].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.subheadline).foregroundStyle(Theme.inkSoft)
                HStack(spacing: 6) {
                    if !p.language.isEmpty { Tag(text: p.language) }
                    if !p.introducedBy.isEmpty { Tag(text: "via \(live.name(for: p.introducedBy))") }
                }
            }
        }
        .padding(.vertical, 2)
    }

    private func promiseRow(_ p: LiveModel.Promise) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(p.what).font(.body).foregroundStyle(Theme.ink)
            HStack(spacing: 6) {
                Text(p.owedBy == "owner" ? "→ \(live.name(for: p.owedTo))" : "\(live.name(for: p.owedBy)) → you")
                    .font(.subheadline).foregroundStyle(Theme.inkSoft)
                if !p.replaces.isEmpty {
                    Text(p.replaces).strikethrough().font(.subheadline).foregroundStyle(Theme.inkSoft)
                }
                if !p.due.isEmpty { Text(p.due).font(.subheadline).bold().foregroundStyle(Theme.accent) }
            }
        }
        .padding(.vertical, 2)
    }
}
