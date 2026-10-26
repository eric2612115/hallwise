import ActivityKit
import SwiftUI
import UIKit

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
        capture.onAudio = { [weak self] data in self?.link.sendAudio(data) }
        capture.onPose = { [weak self] t, heading, pitch, roll, inverted in
            self?.link.sendPose(tMs: t, yaw: heading, pitch: pitch, roll: roll, inverted: inverted)
            DispatchQueue.main.async { self?.live.yaw = heading }
        }
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

    func start() {
        live.reset()
        paused = false
        capture.muted = false
        listening = true
        showBadgeOnLockScreen()
        let settings = self.settings
        if !settings.followRecording.isEmpty {
            link.follow(base: settings.serverURL, recording: settings.followRecording, pace: settings.replayPace)
            return
        }
        Task { @MainActor in
            // Tonight names itself: the calendar event happening now, and the place the phone is.
            if settings.eventName.isEmpty, let title = await OwnerCalendar.currentEventTitle() { settings.eventName = title }
            if settings.venue.isEmpty, let venue = await whereabouts.venue() { settings.venue = venue }
            // The week's busy windows ride along, so the times Hallwise proposes afterwards are free ones.
            let busy = await OwnerCalendar.busyWindows()
            let iso = ISO8601DateFormatter()
            iso.timeZone = .current
            capture.onFormat = { [weak self] format in
                let hello: [String: Any] = [
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
                self?.link.open(base: settings.serverURL, hello: hello)
            }
            capture.start()
        }
    }

    func stop() {
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
