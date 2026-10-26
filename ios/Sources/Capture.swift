import AVFoundation
import CoreMotion

/// Captures the badge's microphones as 4-channel first-order ambisonics (ACN order W, Y, Z, X, SN3D) when the
/// phone supports it, stereo otherwise. Each buffer is converted to interleaved 16-bit PCM for the server, and a
/// full-quality copy is kept on the phone for the demo soundtrack. The phone's orientation is sampled on the same
/// clock (milliseconds of audio captured so far).
final class BadgeCapture: NSObject, AVCaptureAudioDataOutputSampleBufferDelegate {
    struct Format {
        let sampleRate: Int
        let channels: Int
        let layout: String  // "foa", "stereo" or "mono"
    }

    var onFormat: ((Format) -> Void)?
    var onAudio: ((Data) -> Void)?
    var onPose: ((_ tMs: Int, _ yaw: Double, _ pitch: Double, _ roll: Double) -> Void)?
    var onError: ((String) -> Void)?
    /// While muted nothing leaves the phone (audio or pose); the local file keeps the full take.
    var muted = false
    private(set) var recordingURL: URL?

    private let session = AVCaptureSession()
    private let output = AVCaptureAudioDataOutput()
    private let queue = DispatchQueue(label: "hallwise.capture")
    private let motion = CMMotionManager()
    private var file: AVAudioFile?
    private var announced = false
    private var layout = "stereo"
    private let clockLock = NSLock()
    private var framesCaptured = 0
    private var sampleRate = 48_000.0

    func start() {
        AVCaptureDevice.requestAccess(for: .audio) { granted in
            guard granted else { self.onError?("Microphone permission denied"); return }
            self.queue.async { self.configureAndRun() }
        }
    }

    func stop() {
        queue.async {
            self.session.stopRunning()
            self.file = nil
        }
        motion.stopDeviceMotionUpdates()
    }

    private func configureAndRun() {
        session.beginConfiguration()
        session.inputs.forEach { session.removeInput($0) }
        session.outputs.forEach { session.removeOutput($0) }
        guard let mic = AVCaptureDevice.default(for: .audio),
              let input = try? AVCaptureDeviceInput(device: mic),
              session.canAddInput(input) else {
            session.commitConfiguration()
            onError?("Cannot open the microphone")
            return
        }
        if input.isMultichannelAudioModeSupported(.firstOrderAmbisonics) {
            input.multichannelAudioMode = .firstOrderAmbisonics
            output.spatialAudioChannelLayoutTag = kAudioChannelLayoutTag_HOA_ACN_SN3D | 4
            layout = "foa"
        } else if input.isMultichannelAudioModeSupported(.stereo) {
            input.multichannelAudioMode = .stereo
            output.spatialAudioChannelLayoutTag = kAudioChannelLayoutTag_Unknown
            layout = "stereo"
        } else {
            output.spatialAudioChannelLayoutTag = kAudioChannelLayoutTag_Unknown
            layout = "mono"
        }
        session.addInput(input)
        if session.canAddOutput(output) {
            session.addOutput(output)
            output.setSampleBufferDelegate(self, queue: queue)
        }
        session.commitConfiguration()
        announced = false
        clockLock.withLock { framesCaptured = 0 }
        session.startRunning()
        startMotion()
    }

    private func startMotion() {
        guard motion.isDeviceMotionAvailable else { return }
        motion.deviceMotionUpdateInterval = 0.1
        motion.startDeviceMotionUpdates(using: .xArbitraryZVertical, to: OperationQueue()) { [weak self] data, _ in
            guard let self, !self.muted, let a = data?.attitude else { return }
            let tMs = self.clockLock.withLock { Int(Double(self.framesCaptured) / self.sampleRate * 1000) }
            let deg = 180 / Double.pi
            self.onPose?(tMs, a.yaw * deg, a.pitch * deg, a.roll * deg)
        }
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard let desc = sampleBuffer.formatDescription else { return }
        let format = AVAudioFormat(cmAudioFormatDescription: desc)
        let frames = AVAudioFrameCount(sampleBuffer.numSamples)
        guard frames > 0, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames) else { return }
        buffer.frameLength = frames
        guard CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer, at: 0, frameCount: Int32(frames), into: buffer.mutableAudioBufferList) == noErr else { return }

        if !announced {
            announced = true
            sampleRate = format.sampleRate
            let channels = Int(format.channelCount)
            if layout == "foa" && channels != 4 { layout = channels == 2 ? "stereo" : "mono" }
            openFile(format)
            onFormat?(Format(sampleRate: Int(format.sampleRate), channels: channels, layout: layout))
        }
        try? file?.write(from: buffer)
        if !muted {
            onAudio?(interleavedInt16(buffer))
            clockLock.withLock { framesCaptured += Int(frames) }
        }
    }

    private func openFile(_ format: AVAudioFormat) {
        let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        let url = dir.appendingPathComponent("hallwise-\(layout)-\(stamp).caf")
        file = try? AVAudioFile(forWriting: url, settings: format.settings,
                                commonFormat: format.commonFormat, interleaved: format.isInterleaved)
        recordingURL = url
    }
}

/// Interleaved little-endian Int16, whatever the capture buffer's sample format and layout.
func interleavedInt16(_ buffer: AVAudioPCMBuffer) -> Data {
    let n = Int(buffer.frameLength)
    let ch = Int(buffer.format.channelCount)
    var out = [Int16](repeating: 0, count: n * ch)
    let interleaved = buffer.format.isInterleaved
    func clamp(_ x: Float) -> Int16 { Int16(max(-1, min(1, x)) * 32767) }
    if let f = buffer.floatChannelData {
        for c in 0..<ch {
            for i in 0..<n { out[i * ch + c] = clamp(interleaved ? f[0][i * ch + c] : f[c][i]) }
        }
    } else if let s = buffer.int16ChannelData {
        for c in 0..<ch {
            for i in 0..<n { out[i * ch + c] = interleaved ? s[0][i * ch + c] : s[c][i] }
        }
    } else if let s = buffer.int32ChannelData {
        for c in 0..<ch {
            for i in 0..<n { out[i * ch + c] = Int16(truncatingIfNeeded: (interleaved ? s[0][i * ch + c] : s[c][i]) >> 16) }
        }
    }
    return out.withUnsafeBufferPointer { Data(buffer: $0) }
}
