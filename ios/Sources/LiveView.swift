import SwiftUI

/// The owner's private view: who you met, where they are, what you owe them. Swipe left from the badge.
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
                    ForEach(live.lines.suffix(12)) { line in
                        let kind = live.turnKind[line.id] ?? "conversation"
                        let who = live.ownerSpeakers.contains(line.speaker) ? "You" : line.speaker
                        Text("\(who): \(line.text)")
                            .font(.footnote)
                            .foregroundStyle(kind == "conversation" ? Theme.ink : Theme.inkSoft.opacity(0.6))
                    }
                }
                .listRowBackground(Theme.paperDeep)
            }
            .scrollContentBackground(.hidden)
            .background(PaperBackground())
            .tint(Theme.accent)
            .navigationTitle("Hallwise")
            .toolbar { Button { showSettings = true } label: { Image(systemName: "gearshape") } }
            .sheet(isPresented: $showSettings) { SettingsView(settings: settings) }
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
