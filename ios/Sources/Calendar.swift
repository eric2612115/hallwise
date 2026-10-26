import EventKit
import EventKitUI
import SwiftUI

enum OwnerCalendar {
    /// Busy windows for the coming week as ISO 8601 pairs, so a proposed time never collides with what the
    /// owner already has. Empty when the owner has not granted calendar access.
    static func busyWindows(days: Int = 7) async -> [[String]] {
        let store = EKEventStore()
        guard (try? await store.requestFullAccessToEvents()) == true else { return [] }
        let start = Date()
        guard let end = Calendar.current.date(byAdding: .day, value: days, to: start) else { return [] }
        let events = store.events(matching: store.predicateForEvents(withStart: start, end: end, calendars: nil))
        let f = ISO8601DateFormatter()
        f.timeZone = .current
        return events.filter { !$0.isAllDay }.map { [f.string(from: $0.startDate), f.string(from: $0.endDate)] }
    }

    /// The calendar event happening now (or starting within the hour): tonight's name, without typing it.
    static func currentEventTitle() async -> String? {
        let store = EKEventStore()
        guard (try? await store.requestFullAccessToEvents()) == true else { return nil }
        let now = Date()
        let window = store.predicateForEvents(withStart: now.addingTimeInterval(-3 * 3600), end: now.addingTimeInterval(3600), calendars: nil)
        return store.events(matching: window)
            .filter { !$0.isAllDay && $0.endDate > now }
            .sorted { $0.startDate < $1.startDate }
            .first?.title
    }

    /// "2026-10-31T15:00:00+08:00", "2026-10-31T15:00:00" or "2026-10-31T15:00" → a date, local when no offset.
    static func parse(_ text: String) -> Date? {
        let iso = ISO8601DateFormatter()
        if let d = iso.date(from: text) { return d }
        for pattern in ["yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd HH:mm"] {
            let f = DateFormatter()
            f.locale = Locale(identifier: "en_US_POSIX")
            f.timeZone = .current
            f.dateFormat = pattern
            if let d = f.date(from: text) { return d }
        }
        return nil
    }
}

/// The system event editor, prefilled; the owner reads it and taps Add. Nothing is written until then.
struct CalendarEditor: UIViewControllerRepresentable {
    let title: String
    let start: Date
    let minutes: Int
    let notes: String
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> EKEventEditViewController {
        let store = EKEventStore()
        let vc = EKEventEditViewController()
        vc.eventStore = store
        let event = EKEvent(eventStore: store)
        event.title = title
        event.startDate = start
        event.endDate = start.addingTimeInterval(Double(max(15, minutes)) * 60)
        event.notes = notes
        vc.event = event
        vc.editViewDelegate = context.coordinator
        return vc
    }

    func updateUIViewController(_ vc: EKEventEditViewController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(dismiss: dismiss) }

    final class Coordinator: NSObject, EKEventEditViewDelegate {
        let dismiss: DismissAction
        init(dismiss: DismissAction) { self.dismiss = dismiss }
        func eventEditViewController(_ controller: EKEventEditViewController, didCompleteWith action: EKEventEditViewAction) {
            dismiss()
        }
    }
}

/// The system share sheet: Mail, Messages, WhatsApp, Telegram, LINE, whatever the phone has.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}

struct ShareItems: Identifiable {
    let id = UUID()
    let items: [Any]
}
