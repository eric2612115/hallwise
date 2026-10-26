import AVFoundation
import CoreMotion

/// Captures the badge's microphones as 4-channel first-order ambisonics (ACN order W, Y, Z, X, SN3D) when the
/// phone supports it, stereo otherwise. Each buffer is converted to interleaved 16-bit PCM for the server, and a
/// full-quality copy is kept on the phone for the demo soundtrack. The phone's orientation is sampled on the same
/// clock (milliseconds of audio captured so far): which way the wearer faces, and whether the badge hangs top-down.
final class BadgeCapture: NSObject, AVCaptureAudioDataOutputSampleBufferDelegate {
    struct Format {
        let sampleRate: Int
        let channels: Int
        let layout: String  // "foa", "stereo" or "mono"
    }

    var onFormat: ((Format) -> Void)?
    var onAudio: ((Data) -> Void)?
    /// `heading`: the direction the screen faces (degrees, counter-clockwise from above), see `badgeHeading`.
    /// `inverted`: the phone hangs top-down, so the microphones' left and right are swapped.
    var onPose: ((_ tMs: Int, _ heading: Double, _ pitch: Double, _ roll: Double, _ inverted: Bool) -> Void)?
    var onError: ((String) -> Void)?
    /// While muted nothing leaves the phone (audio or pose); the local file keeps the full take.
    var muted = false
    private(set) var recordingURL: URL?

    private let session = AVCaptureSession()
    private let output = AVCaptureAudioDataOutput()
    private let queue = DispatchQueue(label: "hallwise.capture")
    private var motionListener: UUID?  // touched only on `queue`
    private var file: AVAudioFile?
    private var announced = false
    private var layout = "stereo"
    private let clockLock = NSLock()
    private var framesCaptured = 0
    private var sampleRate = 48_000.0

    func start() {
        AVCaptureDevice.requestAccess(for: .audio) { granted in
            guard granted else { self.onError?("Microphone permission denied"); return }
            self.queue.async {
                self.configureAudioSession()
                self.configureAndRun()
            }
        }
    }

    /// Recording must survive the lock button: the badge hangs on a chest for hours. With the audio
    /// background mode in Info.plist, an active record-capable session keeps the microphone open when the
    /// screen locks or the app goes to the background. Bluetooth input is never enabled, so connected AirPods
    /// cannot take over the microphone.
    private func configureAudioSession() {
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.playAndRecord, mode: .default, options: [.allowBluetoothA2DP, .defaultToSpeaker, .mixWithOthers])
            try session.setActive(true)
        } catch {
            onError?("Audio session: \(error.localizedDescription)")
        }
        self.session.automaticallyConfiguresApplicationAudioSession = false
    }

    func stop() {
        queue.async {
            self.session.stopRunning()
            self.file = nil
            if let listener = self.motionListener { BadgeMotion.shared.stopListening(listener) }
            self.motionListener = nil
        }
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
        if let listener = motionListener { BadgeMotion.shared.stopListening(listener) }
        motionListener = BadgeMotion.shared.listen { [weak self] data, inverted in
            guard let self, !self.muted else { return }
            let a = data.attitude
            let r = a.rotationMatrix
            // Not a.yaw: hanging upright the badge sits at pitch 90°, Euler's gimbal lock, where a turn can show up
            // as roll instead. The heading comes from the matrix.
            let heading = badgeHeading(m11: r.m11, m12: r.m12, m13: r.m13, m21: r.m21, m22: r.m22, m23: r.m23,
                                       m31: r.m31, m32: r.m32, m33: r.m33, inverted: inverted)
            let tMs = self.clockLock.withLock { Int(Double(self.framesCaptured) / self.sampleRate * 1000) }
            let deg = 180 / Double.pi
            self.onPose?(tMs, heading, a.pitch * deg, a.roll * deg, inverted)
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

/// The app's one CMMotionManager (Apple: more than one can slow the rate each of them receives), shared by the
/// capture (the pose sent to the server) and the badge face (which way up it hangs). Updates run at 10 Hz while
/// anyone listens; the reference frame is set when they start, so a recording keeps one frame from start to end.
/// Whether the phone hangs top-down is decided here, once, so the badge face and the server always agree.
final class BadgeMotion {
    static let shared = BadgeMotion()
    typealias Listener = (_ motion: CMDeviceMotion, _ inverted: Bool) -> Void

    private let manager = CMMotionManager()
    /// Serial: listeners, the hysteresis state and every motion update live on this queue.
    private let queue: OperationQueue = {
        let q = OperationQueue()
        q.name = "hallwise.motion"
        q.maxConcurrentOperationCount = 1
        return q
    }()
    private var listeners: [UUID: Listener] = [:]
    private var inverted = false

    func listen(_ listener: @escaping Listener) -> UUID {
        let id = UUID()
        queue.addOperation {
            self.listeners[id] = listener
            if self.listeners.count == 1 { self.start() }
        }
        return id
    }

    func stopListening(_ id: UUID) {
        queue.addOperation {
            guard self.listeners.removeValue(forKey: id) != nil, self.listeners.isEmpty else { return }
            self.manager.stopDeviceMotionUpdates()
        }
    }

    private func start() {
        guard manager.isDeviceMotionAvailable, !manager.isDeviceMotionActive else { return }
        manager.deviceMotionUpdateInterval = 0.1
        manager.startDeviceMotionUpdates(using: .xArbitraryZVertical, to: queue) { [weak self] data, _ in
            guard let self, let data else { return }
            let g = data.gravity
            self.inverted = badgeInverted(gravityX: g.x, gravityY: g.y, gravityZ: g.z, wasInverted: self.inverted)
            for listener in self.listeners.values { listener(data, self.inverted) }
        }
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
