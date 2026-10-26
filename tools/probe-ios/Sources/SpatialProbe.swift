import AVFoundation
import Combine

/// Audio-only AVCaptureSession test. In first-order ambisonics mode it connects two audio data
/// outputs: one asking for 4-channel FOA, one for 2-channel stereo, as Apple's rules for
/// `spatialAudioChannelLayoutTag` require. Each output is written to its own .caf file.
final class SpatialProbe: NSObject, ObservableObject, AVCaptureAudioDataOutputSampleBufferDelegate {
    @Published var foaSupported: Bool?
    @Published var stereoModeSupported: Bool?
    @Published var status = "idle"
    @Published var modeUsed = "-"
    @Published var foaChannels = 0
    @Published var stereoChannels = 0
    @Published var sampleRate: Double = 0
    @Published var foaLevels: [Float] = []
    @Published var stereoLevels: [Float] = []
    /// Direction of the loudest sound around the phone, from FOA active intensity (degrees, 0 = +X).
    @Published var azimuth: Double?
    @Published var files: [URL] = []

    private let session = AVCaptureSession()
    private let foaOutput = AVCaptureAudioDataOutput()
    private let stereoOutput = AVCaptureAudioDataOutput()
    private let queue = DispatchQueue(label: "probe.capture")
    private var foaFile: AVAudioFile?
    private var stereoFile: AVAudioFile?
    private var ix = 0.0
    private var iy = 0.0

    func checkSupport() {
        guard let mic = AVCaptureDevice.default(for: .audio),
              let input = try? AVCaptureDeviceInput(device: mic) else {
            status = "no microphone"
            return
        }
        foaSupported = input.isMultichannelAudioModeSupported(.firstOrderAmbisonics)
        stereoModeSupported = input.isMultichannelAudioModeSupported(.stereo)
    }

    func record(seconds: Double) {
        AVCaptureDevice.requestAccess(for: .audio) { granted in
            guard granted else { return self.publish("microphone permission denied") }
            self.queue.async { self.start(seconds: seconds) }
        }
    }

    private func start(seconds: Double) {
        session.beginConfiguration()
        session.inputs.forEach { session.removeInput($0) }
        session.outputs.forEach { session.removeOutput($0) }
        guard let mic = AVCaptureDevice.default(for: .audio),
              let input = try? AVCaptureDeviceInput(device: mic),
              session.canAddInput(input) else {
            session.commitConfiguration()
            return publish("cannot open the microphone")
        }
        let foa = input.isMultichannelAudioModeSupported(.firstOrderAmbisonics)
        let stereo = input.isMultichannelAudioModeSupported(.stereo)
        input.multichannelAudioMode = foa ? .firstOrderAmbisonics : (stereo ? .stereo : .none)
        session.addInput(input)

        if foa {
            foaOutput.spatialAudioChannelLayoutTag = kAudioChannelLayoutTag_HOA_ACN_SN3D | 4
            stereoOutput.spatialAudioChannelLayoutTag = kAudioChannelLayoutTag_Stereo
            for output in [foaOutput, stereoOutput] where session.canAddOutput(output) {
                session.addOutput(output)
                output.setSampleBufferDelegate(self, queue: queue)
            }
        } else {
            stereoOutput.spatialAudioChannelLayoutTag = kAudioChannelLayoutTag_Unknown
            if session.canAddOutput(stereoOutput) {
                session.addOutput(stereoOutput)
                stereoOutput.setSampleBufferDelegate(self, queue: queue)
            }
        }
        session.commitConfiguration()

        let mode = foa ? "first-order ambisonics" : (stereo ? "stereo" : "none (mono)")
        DispatchQueue.main.async {
            self.modeUsed = mode
            self.foaChannels = 0
            self.stereoChannels = 0
            self.azimuth = nil
            self.status = "recording \(Int(seconds)) s — clap around the phone"
        }
        ix = 0
        iy = 0
        session.startRunning()
        queue.asyncAfter(deadline: .now() + seconds) { self.stop() }
    }

    private func stop() {
        session.stopRunning()
        foaFile = nil
        stereoFile = nil
        publish("done")
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard let desc = sampleBuffer.formatDescription else { return }
        let format = AVAudioFormat(cmAudioFormatDescription: desc)
        let frames = AVAudioFrameCount(sampleBuffer.numSamples)
        guard frames > 0, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames) else { return }
        buffer.frameLength = frames
        let err = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer, at: 0, frameCount: Int32(frames), into: buffer.mutableAudioBufferList)
        guard err == noErr else { return }

        let isFOA = output === foaOutput
        do {
            if isFOA {
                if foaFile == nil { foaFile = try makeFile("spatial-foa", format) }
                try foaFile?.write(from: buffer)
            } else {
                if stereoFile == nil { stereoFile = try makeFile("capture-stereo", format) }
                try stereoFile?.write(from: buffer)
            }
        } catch {
            publish("write error: \(error.localizedDescription)")
        }
        analyse(buffer, isFOA: isFOA)
    }

    private func analyse(_ buffer: AVAudioPCMBuffer, isFOA: Bool) {
        let channels = channelSamples(buffer)
        let levels = channels.map(dbfs)
        var az: Double?
        if isFOA, channels.count >= 4 {
            // ACN channel order with SN3D weights: 0 = W, 1 = Y, 2 = Z, 3 = X.
            // Active intensity W·X, W·Y points toward the dominant source.
            var sx = 0.0
            var sy = 0.0
            for k in 0..<channels[0].count {
                let w = Double(channels[0][k])
                sx += w * Double(channels[3][k])
                sy += w * Double(channels[1][k])
            }
            ix = 0.85 * ix + 0.15 * sx
            iy = 0.85 * iy + 0.15 * sy
            if abs(ix) + abs(iy) > 1e-12 { az = atan2(iy, ix) * 180 / .pi }
        }
        let rate = buffer.format.sampleRate
        let count = channels.count
        DispatchQueue.main.async {
            self.sampleRate = rate
            if isFOA {
                self.foaChannels = count
                self.foaLevels = levels
                self.azimuth = az
            } else {
                self.stereoChannels = count
                self.stereoLevels = levels
            }
        }
    }

    private func makeFile(_ name: String, _ format: AVAudioFormat) throws -> AVAudioFile {
        let url = recordingURL(name)
        let file = try AVAudioFile(forWriting: url, settings: format.settings,
                                   commonFormat: format.commonFormat, interleaved: format.isInterleaved)
        DispatchQueue.main.async { self.files.append(url) }
        return file
    }

    private func publish(_ text: String) {
        DispatchQueue.main.async { self.status = text }
    }
}

/// Samples per channel as Float in -1...1, whatever the buffer's sample format and layout.
func channelSamples(_ buffer: AVAudioPCMBuffer) -> [[Float]] {
    let n = Int(buffer.frameLength)
    let ch = Int(buffer.format.channelCount)
    let interleaved = buffer.format.isInterleaved
    if let f = buffer.floatChannelData {
        return (0..<ch).map { c in
            interleaved ? (0..<n).map { f[0][$0 * ch + c] } : Array(UnsafeBufferPointer(start: f[c], count: n))
        }
    }
    if let i = buffer.int16ChannelData {
        return (0..<ch).map { c in
            (0..<n).map { Float(interleaved ? i[0][$0 * ch + c] : i[c][$0]) / 32768 }
        }
    }
    if let i = buffer.int32ChannelData {
        return (0..<ch).map { c in
            (0..<n).map { Float(interleaved ? i[0][$0 * ch + c] : i[c][$0]) / 2_147_483_648 }
        }
    }
    return []
}

func dbfs(_ samples: [Float]) -> Float {
    guard !samples.isEmpty else { return -120 }
    let rms = sqrt(samples.reduce(0) { $0 + $1 * $1 } / Float(samples.count))
    return 20 * log10(max(rms, 1e-6))
}

func recordingURL(_ name: String) -> URL {
    let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
    return dir.appendingPathComponent("\(name)-\(stamp).caf")
}
