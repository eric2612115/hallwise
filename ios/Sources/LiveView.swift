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
                        Circle().fill(app.listening ? Color.red : Color.gray).frame(width: 10, height: 10)
                        Text(link.status).font(.subheadline).foregroundStyle(.secondary)
                        Spacer()
                        Button(app.listening ? "Stop" : "Start") { app.listening ? app.stop() : app.start() }
                            .buttonStyle(.borderedProminent)
                            .tint(app.listening ? .red : .accentColor)
                    }
                }

                Section("People") {
                    if live.peopleOrder.isEmpty { Text("Nobody yet").foregroundStyle(.secondary) }
                    ForEach(live.peopleOrder, id: \.self) { key in
                        if let person = live.people[key] { personRow(person) }
                    }
                }

                if !live.promiseOrder.isEmpty {
                    Section("You owe / they owe") {
                        ForEach(live.promiseOrder, id: \.self) { key in
                            if let p = live.promises[key] { promiseRow(p) }
                        }
                    }
                }

                if !live.suspects.isEmpty {
                    Section("Check these words") {
                        ForEach(live.suspects) { s in
                            HStack {
                                Text(s.heard).strikethrough()
                                Image(systemName: "arrow.right").foregroundStyle(.secondary)
                                Text(s.likely).bold()
                            }
                        }
                    }
                }

                if !live.topics.isEmpty {
                    Section("The room is talking about") {
                        Text(live.topics.joined(separator: " · ")).font(.subheadline)
                    }
                }

                Section("Transcript") {
                    ForEach(live.lines.suffix(12)) { line in
                        let kind = live.turnKind[line.id] ?? "conversation"
                        let who = live.ownerSpeakers.contains(line.speaker) ? "You" : line.speaker
                        Text("\(who): \(line.text)")
                            .font(.footnote)
                            .foregroundStyle(kind == "conversation" ? .primary : .tertiary)
                    }
                }
            }
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
                    .foregroundStyle(.tint)
                    .frame(width: 24)
            } else {
                Image(systemName: "person.fill").foregroundStyle(.secondary).frame(width: 24)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(p.name).font(.headline)
                Text([p.company, p.role].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.subheadline).foregroundStyle(.secondary)
                HStack(spacing: 6) {
                    if !p.language.isEmpty { tag(p.language) }
                    if !p.introducedBy.isEmpty { tag("via \(live.name(for: p.introducedBy))") }
                }
            }
        }
    }

    private func promiseRow(_ p: LiveModel.Promise) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(p.what).font(.body)
            HStack(spacing: 6) {
                Text(p.owedBy == "owner" ? "→ \(live.name(for: p.owedTo))" : "\(live.name(for: p.owedBy)) → you")
                    .font(.subheadline).foregroundStyle(.secondary)
                if !p.replaces.isEmpty { Text(p.replaces).strikethrough().font(.subheadline).foregroundStyle(.secondary) }
                if !p.due.isEmpty { Text(p.due).font(.subheadline).bold() }
            }
        }
    }

    private func tag(_ text: String) -> some View {
        Text(text).font(.caption).padding(.horizontal, 6).padding(.vertical, 2)
            .background(Capsule().fill(Color.secondary.opacity(0.15)))
    }
}
