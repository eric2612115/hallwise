import SwiftUI
import UIKit

@main
struct HallwiseApp: App {
    @StateObject private var app = AppModel()

    var body: some Scene {
        WindowGroup {
            TabView {
                BadgeView(settings: app.settings, listening: app.listening)
                LiveView(app: app, live: app.live, link: app.link, settings: app.settings)
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            .ignoresSafeArea()
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
