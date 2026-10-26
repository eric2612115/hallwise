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
                    BadgeView(settings: app.settings, listening: app.listening).tag(true)
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
    @ObservedObject var settings = BadgeSettings()
    let live = LiveModel()
    let link = ServerLink()
    private let capture = BadgeCapture()

    init() {
        link.onEvent = { [weak self] event in self?.live.apply(event) }
        link.objectWillChange.sink { [weak self] _ in self?.objectWillChange.send() }.store(in: &bag)
        capture.onAudio = { [weak self] data in self?.link.sendAudio(data) }
        capture.onPose = { [weak self] t, yaw, pitch, roll in
            self?.link.sendPose(tMs: t, yaw: yaw, pitch: pitch, roll: roll)
            DispatchQueue.main.async { self?.live.yaw = yaw }
        }
        capture.onError = { [weak self] message in
            DispatchQueue.main.async {
                self?.link.status = message
                self?.listening = false
            }
        }
    }

    private var bag = Set<AnyCancellable>()

    func start() {
        live.reset()
        let settings = self.settings
        if !settings.followRecording.isEmpty {
            link.follow(base: settings.serverURL, recording: settings.followRecording)
            listening = true
            return
        }
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
            ]
            self?.link.open(base: settings.serverURL, hello: hello)
        }
        capture.start()
        listening = true
    }

    func stop() {
        if settings.followRecording.isEmpty {
            capture.stop()
            link.close()
        }
        listening = false
    }
}

import Combine
