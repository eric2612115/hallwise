import SwiftUI

/// Everything after the badge: a header with the menu and the big listen button, one page of content, and a
/// tab bar you can hit without looking. Settings and the badge live behind the menu.
struct MainView: View {
    @ObservedObject var app: AppModel
    @Binding var showBadge: Bool
    @State private var tab: Page = .room
    @State private var showMenu = false
    @State private var showSettings = false

    var body: some View {
        ZStack {
            PaperBackground()
            VStack(spacing: 0) {
                header
                Group {
                    switch tab {
                    case .room: RoomPage(live: app.live, settings: app.settings)
                    case .people: PeoplePage(live: app.live, settings: app.settings)
                    case .owe: OwePage(live: app.live)
                    case .words: WordsPage(live: app.live, settings: app.settings)
                    default: TranscriptPage(live: app.live)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                BigTabBar(selected: $tab)
            }
        }
        .sheet(isPresented: $showMenu) {
            MenuSheet(app: app, showBadge: $showBadge, showSettings: $showSettings)
                .presentationDetents([.medium])
        }
        .sheet(isPresented: $showSettings) { SettingsView(settings: app.settings) }
    }

    private var header: some View {
        HStack(spacing: 12) {
            Button { showMenu = true } label: {
                Image(systemName: "line.3.horizontal")
                    .font(.system(size: 22, weight: .medium))
                    .foregroundStyle(Theme.ink)
                    .frame(width: 48, height: 48)
                    .background(Circle().fill(Theme.paperDeep))
            }
            .accessibilityLabel("Menu")
            VStack(alignment: .leading, spacing: 1) {
                Text(app.settings.eventName.isEmpty ? "Hallwise" : app.settings.eventName)
                    .font(.system(size: 18, weight: .semibold, design: .serif))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                Text(app.link.status)
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            Button { app.listening ? app.stop() : app.start() } label: {
                HStack(spacing: 8) {
                    Circle().fill(app.listening ? Theme.live : Theme.paper).frame(width: 10, height: 10)
                    Text(app.listening ? "Listening" : "Start")
                        .font(.system(size: 17, weight: .semibold))
                }
                .foregroundStyle(app.listening ? Theme.ink : Theme.paper)
                .padding(.horizontal, 18)
                .frame(height: 48)
                .background(Capsule().fill(app.listening ? Theme.paperDeep : Theme.accent))
                .overlay(Capsule().stroke(app.listening ? Theme.live : .clear, lineWidth: 1.5))
            }
            .accessibilityLabel(app.listening ? "Stop listening" : "Start listening")
        }
        .padding(.horizontal, 16)
        .padding(.top, 6)
        .padding(.bottom, 10)
        .overlay(alignment: .bottom) { Rectangle().fill(Theme.rule).frame(height: 0.5) }
    }
}

/// Five big targets: icon plus word, the whole cell tappable.
struct BigTabBar: View {
    @Binding var selected: Page

    private let tabs: [(Page, String)] = [
        (.room, "scope"),
        (.people, "person.2"),
        (.owe, "checklist"),
        (.words, "textformat.abc"),
        (.transcript, "text.bubble"),
    ]

    var body: some View {
        HStack(spacing: 4) {
            ForEach(tabs, id: \.0) { page, icon in
                Button { withAnimation(.easeInOut(duration: 0.15)) { selected = page } } label: {
                    VStack(spacing: 5) {
                        Image(systemName: icon)
                            .font(.system(size: 24, weight: selected == page ? .semibold : .regular))
                        Text(page.title)
                            .font(.system(size: 13, weight: selected == page ? .semibold : .regular))
                    }
                    .foregroundStyle(selected == page ? Theme.accent : Theme.inkSoft)
                    .frame(maxWidth: .infinity)
                    .frame(height: 64)
                    .background(RoundedRectangle(cornerRadius: 14).fill(selected == page ? Theme.paperDeep : .clear))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 8)
        .padding(.top, 6)
        .padding(.bottom, 2)
        .background(Theme.paper.opacity(0.92))
        .overlay(alignment: .top) { Rectangle().fill(Theme.rule).frame(height: 0.5) }
    }
}

/// The menu: big rows, nothing clever.
struct MenuSheet: View {
    @ObservedObject var app: AppModel
    @Binding var showBadge: Bool
    @Binding var showSettings: Bool
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            PaperBackground()
            VStack(spacing: 10) {
                Capsule().fill(Theme.rule).frame(width: 40, height: 5).padding(.top, 10)
                row("person.text.rectangle", "Show my badge", "Wear the phone, name out") {
                    dismiss()
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { showBadge = true }
                }
                row("calendar", "Tonight", app.settings.eventName.isEmpty ? "Set the event and venue" : [app.settings.eventName, app.settings.venue].filter { !$0.isEmpty }.joined(separator: " · ")) {
                    dismiss()
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { showSettings = true }
                }
                row("gearshape", "Settings", "Name, server, words, appearance") {
                    dismiss()
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { showSettings = true }
                }
                Spacer()
            }
            .padding(.horizontal, 16)
        }
    }

    private func row(_ icon: String, _ title: String, _ subtitle: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: icon)
                    .font(.system(size: 22))
                    .foregroundStyle(Theme.accent)
                    .frame(width: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.system(size: 19, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                    Text(subtitle).font(.subheadline).foregroundStyle(Theme.inkSoft).lineLimit(1)
                }
                Spacer()
                Image(systemName: "chevron.right").foregroundStyle(Theme.inkSoft)
            }
            .padding(16)
            .frame(maxWidth: .infinity, minHeight: 64)
            .background(RoundedRectangle(cornerRadius: 14).fill(Theme.paperDeep))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.rule, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }
}
