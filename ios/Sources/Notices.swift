import SwiftUI
import UserNotifications

/// Local notifications at the moment a draft becomes overdue: "Deck for Kevin due tonight" at 20:00.
/// Scheduled when a draft arrives, cancelled when its promise is ticked.
enum Reminders {
    static func schedule(_ move: LiveModel.Move, promise: LiveModel.Promise?) {
        guard !move.remindAt.isEmpty, let when = OwnerCalendar.parse(move.remindAt), when > Date() else { return }
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound, .badge]) { ok, _ in
            guard ok else { return }
            let content = UNMutableNotificationContent()
            content.title = move.nudge.isEmpty ? "Hallwise" : move.nudge
            content.body = promise?.what ?? move.subject
            content.sound = .default
            content.userInfo = ["promise_key": move.promiseKey]
            let parts = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: when)
            let request = UNNotificationRequest(
                identifier: "promise:" + move.promiseKey, content: content,
                trigger: UNCalendarNotificationTrigger(dateMatching: parts, repeats: false)
            )
            center.add(request)
        }
    }

    static func cancel(_ promiseKey: String) {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ["promise:" + promiseKey])
    }
}

/// A draft the owner asked to see, from a notice or an answer.
struct DraftRef: Identifiable {
    let id: String
    let move: LiveModel.Move
    let promise: LiveModel.Promise
}

/// The bell: what Hallwise wants you to do next, one row each, biggest first. Tap a row to do it;
/// swipe it away to stop being asked.
struct NoticesSheet: View {
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    let onWords: () -> Void
    var onReport: () -> Void = {}
    @Environment(\.dismiss) private var dismiss
    @State private var draft: DraftRef?

    var body: some View {
        ZStack {
            PaperBackground()
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .firstTextBaseline) {
                    Text("For you")
                        .font(.system(size: 24, weight: .bold, design: .serif))
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    if !live.notices.isEmpty {
                        Text("\(live.notices.count)")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(Theme.paper)
                            .padding(.horizontal, 10).frame(height: 26)
                            .background(Capsule().fill(Theme.accent))
                    }
                }
                .padding(.horizontal, 20).padding(.top, 22).padding(.bottom, 8)
                reportRow
                    .padding(.horizontal, 20).padding(.bottom, 6)
                if live.notices.isEmpty {
                    Text("Nothing waiting. Hallwise taps you here when a draft is due, a time needs the calendar, or a word needs you.")
                        .font(.system(size: 15, design: .serif))
                        .foregroundStyle(Theme.inkSoft)
                        .padding(20)
                    Spacer()
                } else {
                    List {
                        ForEach(live.notices) { n in
                            Button { act(n) } label: { row(n) }
                                .buttonStyle(.plain)
                                .listRowBackground(Theme.paperDeep)
                                .swipeActions(edge: .trailing) {
                                    Button(role: .destructive) { live.dismissedNotices.insert(n.id) } label: { Label("Not now", systemImage: "bell.slash") }
                                }
                        }
                    }
                    .scrollContentBackground(.hidden)
                }
            }
        }
        .preferredColorScheme(settings.colorScheme)
        .sheet(item: $draft) { d in
            MoveSheet(move: d.move, promise: d.promise, live: live, settings: settings, hook: live.hooks(for: d.move.personKey).first)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
    }

    /// Always on top: the morning report, every follow-up with its reason to write.
    private var reportRow: some View {
        Button {
            dismiss()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { onReport() }
        } label: {
            HStack(spacing: 14) {
                Image(systemName: "sun.horizon.fill")
                    .font(.system(size: 20))
                    .foregroundStyle(Theme.paper)
                    .frame(width: 44, height: 44)
                    .background(Circle().fill(Theme.ink))
                VStack(alignment: .leading, spacing: 3) {
                    Text("Morning report").font(.system(size: 17, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                    Text("Who to write to today, and why").font(.system(size: 14)).foregroundStyle(Theme.inkSoft)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.system(size: 17)).foregroundStyle(Theme.inkSoft)
            }
            .padding(12)
            .background(RoundedRectangle(cornerRadius: 14).fill(Theme.paperDeep))
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.rule, lineWidth: 0.5))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Morning report")
    }

    private func row(_ n: LiveModel.Notice) -> some View {
        HStack(spacing: 14) {
            Image(systemName: n.kind == .calendar ? "calendar.badge.plus" : n.kind == .word ? "textformat.abc" : "paperplane.fill")
                .font(.system(size: 20))
                .foregroundStyle(Theme.paper)
                .frame(width: 44, height: 44)
                .background(Circle().fill(Theme.accent))
            VStack(alignment: .leading, spacing: 3) {
                Text(n.title).font(.system(size: 17, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                Text(n.detail).font(.system(size: 14)).foregroundStyle(Theme.inkSoft).lineLimit(2)
            }
            Spacer()
            Image(systemName: "chevron.right").font(.system(size: 17)).foregroundStyle(Theme.inkSoft)
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
    }

    private func act(_ n: LiveModel.Notice) {
        switch n.kind {
        case .word:
            dismiss()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { onWords() }
        case .send, .calendar:
            guard let key = n.promiseKey, let m = live.moves[key], let p = live.promises[key] else { return }
            draft = DraftRef(id: key, move: m, promise: p)
        }
    }
}
