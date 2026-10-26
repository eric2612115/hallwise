import CoreMotion
import SwiftUI

@main
struct ProbeApp: App {
    var body: some Scene {
        WindowGroup { ProbeView() }
    }
}

struct ProbeView: View {
    @StateObject private var spatial = SpatialProbe()
    @StateObject private var stereo = StereoProbe()
    @StateObject private var motion = MotionProbe()

    var body: some View {
        NavigationStack {
            List {
                Section("Device") {
                    row("Model", deviceModel())
                    row("iOS", UIDevice.current.systemVersion)
                    row("Phone yaw", motion.yaw.map { String(format: "%.0f°", $0) } ?? "-")
                }

                Section("1 · Spatial capture (AVCaptureSession)") {
                    row("4-channel FOA supported", yesNo(spatial.foaSupported))
                    row("Stereo mode supported", yesNo(spatial.stereoModeSupported))
                    Button("Record 10 s") { spatial.record(seconds: 10) }
                    row("Status", spatial.status)
                    row("Mode used", spatial.modeUsed)
                    row("FOA channels received", "\(spatial.foaChannels)")
                    row("Stereo channels received", "\(spatial.stereoChannels)")
                    row("Sample rate", spatial.sampleRate > 0 ? "\(Int(spatial.sampleRate)) Hz" : "-")
                    meters("FOA  W Y Z X", spatial.foaLevels)
                    meters("Stereo  L R", spatial.stereoLevels)
                    if let az = spatial.azimuth {
                        HStack {
                            Text("Loudest sound comes from")
                            Spacer()
                            Image(systemName: "arrow.up").rotationEffect(.degrees(90 - az)).font(.title)
                            Text(String(format: "%.0f°", az)).monospacedDigit()
                        }
                    }
                    Text("Hold the phone upright, screen facing you. Clap about 1 m away in front, on the left, behind, on the right. The arrow should follow the claps.")
                        .font(.footnote).foregroundStyle(.secondary)
                }

                Section("2 · Stereo route (AVAudioSession)") {
                    Button("Record 10 s") { stereo.record(seconds: 10) }
                    row("Status", stereo.status)
                    row("Input route", stereo.route)
                    row("Mic data source", stereo.dataSource)
                    row("Channels received", "\(stereo.channels)")
                    meters("L R", stereo.levels)
                    if stereo.levels.count == 2 {
                        row("Left minus right", String(format: "%+.1f dB", stereo.levels[0] - stereo.levels[1]))
                    }
                }

                Section("Recordings") {
                    let files = spatial.files + stereo.files
                    ForEach(files, id: \.self) { Text($0.lastPathComponent).font(.footnote) }
                    if !files.isEmpty {
                        ShareLink(items: files) { Label("Share all (AirDrop to the Mac)", systemImage: "square.and.arrow.up") }
                    }
                }
            }
            .navigationTitle("Hallwise Probe")
            .onAppear {
                spatial.checkSupport()
                motion.start()
            }
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack { Text(label); Spacer(); Text(value).foregroundStyle(.secondary).multilineTextAlignment(.trailing) }
    }

    private func yesNo(_ value: Bool?) -> String {
        switch value {
        case .some(true): return "✅ yes"
        case .some(false): return "❌ no"
        case .none: return "-"
        }
    }

    @ViewBuilder
    private func meters(_ label: String, _ levels: [Float]) -> some View {
        if !levels.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text(label).font(.caption).foregroundStyle(.secondary)
                ForEach(Array(levels.enumerated()), id: \.offset) { _, db in
                    GeometryReader { geo in
                        Capsule().fill(.tint)
                            .frame(width: geo.size.width * CGFloat(max(0, min(1, (db + 80) / 80))))
                    }
                    .frame(height: 6)
                }
            }
        }
    }

    private func deviceModel() -> String {
        var info = utsname()
        uname(&info)
        return withUnsafeBytes(of: &info.machine) { raw in
            String(decoding: raw.prefix(while: { $0 != 0 }), as: UTF8.self)
        }
    }
}

final class MotionProbe: ObservableObject {
    @Published var yaw: Double?
    private let manager = CMMotionManager()

    func start() {
        guard manager.isDeviceMotionAvailable else { return }
        manager.deviceMotionUpdateInterval = 0.1
        manager.startDeviceMotionUpdates(using: .xArbitraryZVertical, to: .main) { data, _ in
            if let a = data?.attitude { self.yaw = a.yaw * 180 / .pi }
        }
    }
}
