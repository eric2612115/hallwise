import ActivityKit
import SwiftUI
import UIKit
import UserNotifications

@main
struct HallwiseApp: App {
    @StateObject private var app = AppModel()
    @State private var badgeShown = true

    var body: some Scene {
        WindowGroup {
            ZStack {
                PaperBackground()  // under the status bar and the home indicator too
                // Two pages: the badge (worn, facing out) and the app. Swipe, or use the menu.
                TabView(selection: $badgeShown) {
                    BadgeView(settings: app.settings).tag(true)
                    MainView(app: app, showBadge: $badgeShown).tag(false)
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
            }
            .preferredColorScheme(app.settings.colorScheme)
            .onAppear { UIApplication.shared.isIdleTimerDisabled = true }
        }
    }
}

/// Wires the microphones, the server and the live record together.
final class AppModel: ObservableObject {
    @Published var listening = false
    @Published var paused = false
    @Published var reportRequests = 0        // each one opens the morning report
    var reportRecording: String?             // which recording's report; nil = the newest
    let settings = BadgeSettings()
    let live = LiveModel()
    let link = ServerLink()
    let voiceAsk = VoiceAsk()
    private let capture = BadgeCapture()
    private var badgeActivity: Activity<BadgeActivityAttributes>?
    private let whereabouts = Whereabouts()

    init() {
        link.onEvent = { [weak self] event in self?.live.apply(event) }
        link.$recordingID.sink { [weak self] rid in self?.live.recordingID = rid ?? "" }.store(in: &bag)
        link.objectWillChange.sink { [weak self] _ in self?.objectWillChange.send() }.store(in: &bag)
        settings.objectWillChange.sink { [weak self] _ in self?.objectWillChange.send() }.store(in: &bag)
        live.objectWillChange.sink { [weak self] _ in self?.objectWillChange.send() }.store(in: &bag)
        ServerAuth.shared.objectWillChange.sink { [weak self] _ in self?.objectWillChange.send() }.store(in: &bag)
        link.onRejected = { [weak self] in self?.keyRejected() }
        DispatchQueue.global(qos: .utility).async { BadgeCapture.tidyLocalCopies() }
        capture.onAudio = { [weak self] data in self?.link.sendAudio(data) }
        capture.onPose = { [weak self] t, heading, pitch, roll, inverted in
            self?.link.sendPose(tMs: t, yaw: heading, pitch: pitch, roll: roll, inverted: inverted)
            DispatchQueue.main.async { self?.live.yaw = heading }
        }
        UNUserNotificationCenter.current().delegate = NotificationRouter.shared
        NotificationRouter.shared.onReport = { [weak self] rid in self?.openReport(rid.isEmpty ? nil : rid) }
        capture.onError = { [weak self] message in
            DispatchQueue.main.async {
                self?.link.status = message
                self?.listening = false
            }
        }
    }

    private var bag = Set<AnyCancellable>()

    /// Pause keeps the recording open but sends nothing; resume carries on in the same recording.
    func pause() {
        paused = true
        capture.muted = true
        link.status = "paused"
    }

    func resume() {
        paused = false
        capture.muted = false
        link.status = link.replaying ? "replaying" : "listening"
    }

    /// The recording just made or followed, for its report.
    var currentRecording: String? {
        link.recordingID ?? (settings.followRecording.isEmpty ? nil : settings.followRecording)
    }

    func openReport(_ rid: String?) {
        reportRecording = rid ?? currentRecording
        reportRequests += 1
    }

    /// Debug: the morning notification in ten seconds.
    func scheduleReportSoon() {
        MorningNotice.schedule(in: 10, recording: currentRecording ?? "")
    }

    /// Starts listening (or following), unless there is no usable server address: then the Start button's
    /// caption says what is missing, and nothing starts. Returns whether it started.
    @discardableResult
    func start() -> Bool {
        if let problem = settings.serverAddressProblem {
            link.status = problem
            return false
        }
        ServerAuth.shared.clear()  // every Start is a fresh try; nothing retries by itself
        live.reset()
        live.serverBase = settings.serverURL
        paused = false
        capture.muted = false
        capture.keepLocalCopy = settings.keepLocalAudio
        listening = true
        showBadgeOnLockScreen()
        let settings = self.settings
        if !settings.followRecording.isEmpty {
            link.follow(base: settings.serverURL, recording: settings.followRecording, pace: settings.replayPace)
            // a recording that already has its report: its hooks show up as the people do
            let rid = settings.followRecording
            Task { @MainActor [weak self] in
                if let report = await ReportStore.get(ServerLink.httpBase(settings.serverURL) + "/api/report/" + rid) {
                    self?.live.applyReport(report)
                }
            }
            return true
        }
        Task { @MainActor in
            // Tonight names itself: the calendar event happening now, and the place the phone is.
            if settings.eventName.isEmpty, let title = await OwnerCalendar.currentEventTitle() { settings.eventName = title }
            // One fix every Start, so every recording has a place. Its name fills the venue unless the owner typed one.
            // A guess left from an earlier evening names somewhere else, so it goes even when this fix has no name.
            let place = await whereabouts.place()
            if let place, settings.venue.isEmpty || settings.venue == settings.venueGuessed {
                settings.venue = place.name ?? ""
                settings.venueGuessed = settings.venue
            }
            // The week's busy windows ride along, so the times Hallwise proposes afterwards are free ones.
            let busy = await OwnerCalendar.busyWindows()
            let iso = ISO8601DateFormatter()
            iso.timeZone = .current
            capture.onFormat = { [weak self] format in
                var hello: [String: Any] = [
                    "sample_rate": format.sampleRate,
                    "channels": format.channels,
                    "layout": format.layout,
                    "device": "iPhone badge",
                    "owner_name": settings.ownerName,
                    "owner_company": settings.ownerCompany,
                    "keywords": settings.keywordList,
                    "event": settings.eventName,
                    "venue": settings.venue,
                    "links": settings.links,
                    "busy": busy,
                    "tz": TimeZone.current.identifier,
                    "now": iso.string(from: Date()),
                ]
                // the fix as taken; whatever is published from it is rounded on the server's side
                if let place {
                    hello["place"] = ["name": settings.venue.isEmpty ? (place.name ?? "") : settings.venue,
                                      "lat": place.latitude, "lon": place.longitude]
                }
                self?.link.open(base: settings.serverURL, hello: hello)
            }
            capture.start()
        }
        return true
    }

    /// The server turned the key down: stop capturing (nothing should pile up on the phone for a server that
    /// will not take it) and leave "Server key is wrong" showing. The owner fixes the key and taps Start again.
    private func keyRejected() {
        guard listening else { return }
        if settings.followRecording.isEmpty {
            capture.stop()
            if link.canAskByVoice { link.close() }  // the record socket was turned down after /ingest opened
        } else {
            link.unfollow()
        }
        listening = false
        paused = false
        hideBadgeFromLockScreen()
    }

    func stop() {
        // the follow-ups land now; the morning report waits for eight o'clock
        MorningNotice.scheduleMorning(recording: currentRecording ?? "")
        if settings.followRecording.isEmpty {
            capture.stop()
            link.close()
        } else {
            link.unfollow()
        }
        listening = false
        paused = false
        hideBadgeFromLockScreen()
    }

    /// The name card on the lock screen and in the Dynamic Island while listening: a pressed side button
    /// or a pocket sleep must not turn the badge into a black slab. Ends with Stop.
    private func showBadgeOnLockScreen() {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        let attributes = BadgeActivityAttributes(
            name: settings.ownerName, company: settings.ownerCompany, title: settings.ownerTitle, vcard: settings.vCard
        )
        hideBadgeFromLockScreen()
        do {
            badgeActivity = try Activity.request(attributes: attributes, content: .init(state: .init(), staleDate: nil))
        } catch {
            link.status = "lock-screen badge: \(error.localizedDescription)"
        }
    }

    private func hideBadgeFromLockScreen() {
        let mine = badgeActivity
        badgeActivity = nil
        Task {
            await mine?.end(nil, dismissalPolicy: .immediate)
            for stale in Activity<BadgeActivityAttributes>.activities where stale.id != mine?.id {
                await stale.end(nil, dismissalPolicy: .immediate)
            }
        }
    }
}

import Combine
