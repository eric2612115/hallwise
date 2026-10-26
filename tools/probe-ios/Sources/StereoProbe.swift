import AVFoundation
import Combine

/// AVAudioSession route test: built-in mic, a data source that supports the stereo polar pattern,
/// portrait input orientation, recorded through AVAudioEngine. Bluetooth (HFP) input is never
/// enabled, so connected AirPods cannot take over the microphone.
final class StereoProbe: ObservableObject {
    @Published var status = "idle"
    @Published var channels = 0
    @Published var dataSource = "-"
    @Published var route = "-"
    @Published var levels: [Float] = []
    @Published var files: [URL] = []

    private let engine = AVAudioEngine()
    private var file: AVAudioFile?

    func record(seconds: Double) {
        AVAudioApplication.requestRecordPermission { granted in
            DispatchQueue.main.async {
                guard granted else { self.status = "microphone permission denied"; return }
                self.start(seconds: seconds)
            }
        }
    }

    private func start(seconds: Double) {
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.playAndRecord, mode: .default, options: [.allowBluetoothA2DP, .defaultToSpeaker])
            try session.setActive(true)
            guard let builtIn = session.availableInputs?.first(where: { $0.portType == .builtInMic }) else {
                status = "no built-in microphone"
                return
            }
            try session.setPreferredInput(builtIn)
            guard let source = builtIn.dataSources?.first(where: { $0.supportedPolarPatterns?.contains(.stereo) == true }) else {
                status = "no microphone data source supports stereo"
                return
            }
            try source.setPreferredPolarPattern(.stereo)
            try builtIn.setPreferredDataSource(source)
            try session.setPreferredInputOrientation(.portrait)
            dataSource = source.dataSourceName
            route = session.currentRoute.inputs.map { $0.portName }.joined(separator: ", ")
        } catch {
            status = "audio session error: \(error.localizedDescription)"
            return
        }

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        channels = Int(format.channelCount)
        do {
            let url = recordingURL("session-stereo")
            file = try AVAudioFile(forWriting: url, settings: format.settings,
                                   commonFormat: format.commonFormat, interleaved: format.isInterleaved)
            files.append(url)
        } catch {
            status = "file error: \(error.localizedDescription)"
            return
        }
        input.installTap(onBus: 0, bufferSize: 4096, format: format) { buffer, _ in
            try? self.file?.write(from: buffer)
            let levels = channelSamples(buffer).map(dbfs)
            DispatchQueue.main.async { self.levels = levels }
        }
        do {
            try engine.start()
        } catch {
            status = "engine error: \(error.localizedDescription)"
            return
        }
        status = "recording \(Int(seconds)) s — clap on your left, then your right"
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { self.stop() }
    }

    private func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        file = nil
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        status = "done"
    }
}
