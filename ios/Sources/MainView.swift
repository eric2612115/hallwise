import SwiftUI

/// Everything after the badge: a header with the menu and the state, one page of content, and a tab bar you
/// can hit without looking. Settings and the badge live behind the menu.
struct MainView: View {
    @ObservedObject var app: AppModel
    @Binding var showBadge: Bool
    @State private var tab: Page = .room
    @State private var showMenu = false
    @State private var showTranscript = false

    var body: some View {
        ZStack {
            PaperBackground()
            VStack(spacing: 0) {
                header
                Group {
                    switch tab {
                    case .room: RoomPage(app: app, live: app.live, settings: app.settings, showBadge: $showBadge)
                    case .people: PeoplePage(live: app.live, settings: app.settings)
                    case .ask: AskPage(app: app, live: app.live, settings: app.settings)
                    case .owe: OwePage(live: app.live, settings: app.settings)
                    case .words: WordsPage(live: app.live, settings: app.settings)
                    default: TranscriptPage(live: app.live)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                BigTabBar(selected: $tab, counts: counts)
            }
        }
        .sheet(isPresented: $showMenu) {
            MenuSheet(settings: app.settings, showBadge: $showBadge, showTranscript: $showTranscript)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
        .sheet(isPresented: $showTranscript) {
            ZStack {
                PaperBackground()
                VStack(spacing: 0) {
                    Text("Transcript")
                        .font(.system(size: 20, weight: .semibold, design: .serif))
                        .foregroundStyle(Theme.ink)
                        .padding(.top, 18).padding(.bottom, 8)
                    TranscriptPage(live: app.live)
                }
            }
            .preferredColorScheme(app.settings.colorScheme)
            .presentationDetents([.large])
            .presentationDragIndicator(.visible)
        }
    }

    private var counts: [Page: Int] {
        let openOwe = app.live.promiseOrder.filter { key in
            !app.live.donePromises.contains(key) && app.live.promises[key]?.owedBy == "owner"
        }.count
        return [.people: app.live.peopleOrder.count, .owe: openOwe, .words: app.live.suspects.count]
    }

    /// Plain words, never an id: what the app is doing right now.
    private var stateText: String {
        let s = app.link.status
        if s.hasPrefix("disconnected") || s.contains("failed") || s.contains("error") || s.contains("denied") { return s }
        if !app.listening { return "Not listening" }
        if app.paused { return "Paused" }
        if s == "connecting" { return "Connecting…" }
        return "Live"
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
                    .minimumScaleFactor(0.85)
                Text(stateText)
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .lineLimit(1)
            }
            .layoutPriority(1)
            Spacer(minLength: 8)
            if app.listening {
                HStack(spacing: 6) {
                    Circle().fill(app.paused ? Theme.inkSoft : Theme.live).frame(width: 9, height: 9)
                    Text(mmss(app.live.tMs))
                        .font(.system(size: 17, weight: .semibold).monospacedDigit())
                        .foregroundStyle(Theme.ink)
                }
                .padding(.horizontal, 12)
                .frame(height: 36)
                .background(Capsule().fill(Theme.paperDeep))
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 6)
        .padding(.bottom, 10)
        .overlay(alignment: .bottom) { Rectangle().fill(Theme.rule).frame(height: 0.5) }
    }
}

/// Five big targets: icon plus word, the whole cell tappable, a count where it helps.
struct BigTabBar: View {
    @Binding var selected: Page
    let counts: [Page: Int]

    private let tabs: [(Page, String)] = [
        (.room, "scope"),
        (.people, "person.2"),
        (.ask, "sparkles"),
        (.owe, "checklist"),
        (.words, "textformat.abc"),
    ]

    var body: some View {
        HStack(spacing: 4) {
            ForEach(tabs, id: \.0) { page, icon in
                if page == .ask {
                    askButton
                } else {
                Button { withAnimation(.easeInOut(duration: 0.15)) { selected = page } } label: {
                    VStack(spacing: 5) {
                        ZStack(alignment: .topTrailing) {
                            Image(systemName: icon)
                                .font(.system(size: 24, weight: selected == page ? .semibold : .regular))
                                .frame(width: 32, height: 28)
                            if let n = counts[page], n > 0 {
                                Text("\(n)")
                                    .font(.system(size: 11, weight: .semibold))
                                    .foregroundStyle(Theme.paper)
                                    .padding(.horizontal, 5)
                                    .frame(minWidth: 18, minHeight: 18)
                                    .background(Capsule().fill(Theme.accent))
                                    .offset(x: 12, y: -6)
                            }
                        }
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
        }
        .padding(.horizontal, 8)
        .padding(.top, 6)
        .padding(.bottom, 2)
        .background(Theme.paper.opacity(0.92))
        .overlay(alignment: .top) { Rectangle().fill(Theme.rule).frame(height: 0.5) }
    }
}

extension BigTabBar {
    /// The middle of the bar is the point of the app: ask. Bigger, raised, ink on paper.
    var askButton: some View {
        Button { withAnimation(.easeInOut(duration: 0.15)) { selected = .ask } } label: {
            VStack(spacing: 4) {
                Image(systemName: "sparkles")
                    .font(.system(size: 26, weight: .semibold))
                    .foregroundStyle(selected == .ask ? Theme.paper : Theme.paper)
                    .frame(width: 60, height: 60)
                    .background(Circle().fill(selected == .ask ? Theme.accent : Theme.ink))
                    .shadow(color: Theme.ink.opacity(0.25), radius: 8, y: 3)
                Text("Ask")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(selected == .ask ? Theme.accent : Theme.ink)
            }
            .frame(maxWidth: .infinity)
            .offset(y: -14)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// The menu is one page: everything you can change sits right here, nothing hides behind a second screen.
/// Appearance first, because it is the one people reach for; then the badge, then tonight, then the plumbing.
struct MenuSheet: View {
    @ObservedObject var settings: BadgeSettings
    @Binding var showBadge: Bool
    @Binding var showTranscript: Bool
    @Environment(\.dismiss) private var dismiss
    @State private var share: ShareItems?
    @State private var copiedBlurb = false

    var body: some View {
        ZStack {
            PaperBackground()
            ScrollView {
                VStack(spacing: 18) {
                    appearance
                    badgeButton
                    transcriptButton
                    group("Your links", "What people ask for; the follow-ups attach them") {
                        field("Deck", text: $settings.deckURL, placeholder: "https://…", keyboard: .URL)
                        field("One-pager", text: $settings.onePagerURL, placeholder: "https://…", keyboard: .URL)
                        field("Blurb", text: $settings.blurb, placeholder: "two lines about you", last: true)
                    }
                    shareRow
                    group("Your badge", "What people see on your chest") {
                        field("Name", text: $settings.ownerName)
                        field("Company", text: $settings.ownerCompany)
                        field("Title", text: $settings.ownerTitle, placeholder: "optional")
                        field("Contact", text: $settings.contact, placeholder: "email or handle, goes in the QR", keyboard: .emailAddress, last: true)
                    }
                    group("Tonight", "Kept with every recording") {
                        field("Event", text: $settings.eventName, placeholder: "ETH Taipei afterparty")
                        field("Venue", text: $settings.venue, placeholder: "where", last: true)
                    }
                    group("Listening", nil) {
                        field("Server", text: $settings.serverURL, keyboard: .URL)
                        field("Words", text: $settings.keywords, placeholder: "names to recognise, comma-separated")
                        forwardRow
                    }
                    group("Debug", nil) {
                        field("Follow", text: $settings.followRecording, placeholder: "recording id, no capture", keyboard: .URL, last: true)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 22)
                .padding(.bottom, 32)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .preferredColorScheme(settings.colorScheme)
    }

    /// One tap hands someone the deck, the one-pager or the blurb, through whatever app they use.
    @ViewBuilder
    private var shareRow: some View {
        if !settings.links.isEmpty {
            HStack(spacing: 8) {
                if let deck = settings.links["deck"] {
                    shareButton("Share deck", icon: "square.and.arrow.up") { share = ShareItems(items: [deck]) }
                }
                if let one = settings.links["one_pager"] {
                    shareButton("Share one-pager", icon: "square.and.arrow.up") { share = ShareItems(items: [one]) }
                }
                if let blurb = settings.links["blurb"] {
                    shareButton(copiedBlurb ? "Copied" : "Copy blurb", icon: copiedBlurb ? "checkmark" : "doc.on.doc") {
                        UIPasteboard.general.string = blurb
                        withAnimation { copiedBlurb = true }
                    }
                }
            }
            .sheet(item: $share) { ShareSheet(items: $0.items) }
        }
    }

    private func shareButton(_ title: String, icon: String, run: @escaping () -> Void) -> some View {
        Button(action: run) {
            VStack(spacing: 5) {
                Image(systemName: icon).font(.system(size: 20, weight: .semibold))
                Text(title).font(.system(size: 13, weight: .semibold)).lineLimit(1).minimumScaleFactor(0.8)
            }
            .foregroundStyle(Theme.accent)
            .frame(maxWidth: .infinity)
            .frame(height: 60)
            .background(RoundedRectangle(cornerRadius: 14).fill(Theme.paperDeep))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.rule, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }

    private var appearance: some View {
        HStack(spacing: 8) {
            appearanceButton(.system, icon: "circle.lefthalf.filled", title: "Auto")
            appearanceButton(.light, icon: "sun.max.fill", title: "Light")
            appearanceButton(.dark, icon: "moon.fill", title: "Dark")
        }
    }

    private func appearanceButton(_ a: Theme.Appearance, icon: String, title: String) -> some View {
        let on = settings.appearance == a.rawValue
        return Button {
            withAnimation(.easeInOut(duration: 0.2)) { settings.appearance = a.rawValue }
        } label: {
            VStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 22))
                Text(title).font(.system(size: 14, weight: .semibold))
            }
            .foregroundStyle(on ? Theme.paper : Theme.ink)
            .frame(maxWidth: .infinity)
            .frame(height: 64)
            .background(RoundedRectangle(cornerRadius: 14).fill(on ? Theme.ink : Theme.paperDeep))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.rule, lineWidth: on ? 0 : 0.5))
        }
        .buttonStyle(.plain)
    }

    private var badgeButton: some View {
        Button {
            dismiss()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { withAnimation { showBadge = true } }
        } label: {
            HStack(spacing: 14) {
                Image(systemName: "person.text.rectangle").font(.system(size: 22)).frame(width: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Show my badge").font(.system(size: 19, weight: .semibold, design: .serif))
                    Text("Wear the phone, name out").font(.subheadline).opacity(0.85)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.system(size: 17)).opacity(0.7)
            }
            .foregroundStyle(Theme.paper)
            .padding(16)
            .frame(maxWidth: .infinity, minHeight: 64)
            .background(RoundedRectangle(cornerRadius: 14).fill(Theme.accent))
        }
        .buttonStyle(.plain)
    }

    /// Everything that was said, for the rare evening you need to check a line, edit or delete.
    private var transcriptButton: some View {
        Button {
            dismiss()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { showTranscript = true }
        } label: {
            HStack(spacing: 14) {
                Image(systemName: "text.bubble").font(.system(size: 22)).foregroundStyle(Theme.accent).frame(width: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Transcript").font(.system(size: 19, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                    Text("Every line, who said it, translations").font(.subheadline).foregroundStyle(Theme.inkSoft)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.system(size: 17)).foregroundStyle(Theme.inkSoft)
            }
            .padding(16)
            .frame(maxWidth: .infinity, minHeight: 64)
            .background(RoundedRectangle(cornerRadius: 14).fill(Theme.paperDeep))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.rule, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }

    private func group<Content: View>(_ title: String, _ subtitle: String?, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.system(size: 17, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                if let subtitle { Text(subtitle).font(.system(size: 13)).foregroundStyle(Theme.inkSoft) }
            }
            .padding(.leading, 4)
            VStack(spacing: 0) { content() }
                .background(RoundedRectangle(cornerRadius: 14).fill(Theme.paperDeep))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.rule, lineWidth: 0.5))
        }
    }

    private func field(_ label: String, text: Binding<String>, placeholder: String = "",
                       keyboard: UIKeyboardType = .default, last: Bool = false) -> some View {
        HStack(spacing: 12) {
            Text(label)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(Theme.inkSoft)
                .frame(width: 72, alignment: .leading)
            TextField(placeholder, text: text)
                .font(.system(size: 17))
                .foregroundStyle(Theme.ink)
                .keyboardType(keyboard)
                .textInputAutocapitalization(keyboard == .default ? .words : .never)
                .autocorrectionDisabled()
        }
        .padding(.horizontal, 14)
        .frame(height: 52)
        .overlay(alignment: .bottom) {
            if !last { Rectangle().fill(Theme.rule).frame(height: 0.5).padding(.leading, 14) }
        }
    }

    private var forwardRow: some View {
        HStack(spacing: 12) {
            Text("Forward")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(Theme.inkSoft)
                .frame(width: 72, alignment: .leading)
            Text("\(Int(settings.yawOffset))°").font(.system(size: 17)).foregroundStyle(Theme.ink)
            Spacer()
            Stepper("", value: $settings.yawOffset, in: -180...180, step: 15).labelsHidden()
        }
        .padding(.horizontal, 14)
        .frame(height: 52)
    }
}
