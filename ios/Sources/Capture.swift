import AVFoundation
import CoreMotion
import os

/// Who sets up the phone's audio session for a recording (Debug, "Capture setup", applied at Start).
/// On the owner's iPhone 17 Pro, A delivered four channels with W live and Y, Z, X all zero. Apple's header says
/// a capture session left to configure the app's audio session "picks an appropriate microphone and polar
/// pattern", and one told not to "will not change any of its properties. If the session is not set up correctly
/// for input, audio recording may fail." Hence B by default.
enum CaptureSetup: String, CaseIterable, Identifiable {
    case appSession = "app"
    case captureDecides = "capture"
    case videoRecording = "video"
    case recordOnly = "record"
    case captureMixes = "captureMix"

    static let standard = CaptureSetup.captureDecides
    var id: String { rawValue }

    var letter: String {
        switch self {
        case .appSession: "A"
        case .captureDecides: "B"
        case .videoRecording: "C"
        case .recordOnly: "D"
        case .captureMixes: "E"
        }
    }

    var title: String {
        switch self {
        case .appSession: "A · App session"
        case .captureDecides: "B · Capture session decides"
        case .videoRecording: "C · Video recording"
        case .recordOnly: "D · Record only"
        case .captureMixes: "E · Capture decides, mixes"
        }
    }

    var detail: String {
        switch self {
        case .appSession: "The app sets play-and-record, default mode, speaker, mixing; the capture session keeps its hands off (before this build)."
        case .captureDecides: "The capture session sets up the audio session and picks the microphones itself."
        case .videoRecording: "The app sets play-and-record in video-recording mode, Bluetooth output only, no mixing."
        case .recordOnly: "The app sets the record category, default mode. Other audio on the phone goes quiet."
        case .captureMixes: "As B, and music from other apps keeps playing (the capture session's own mix switch)."
        }
    }

    /// Whether the capture session configures the app's audio session itself.
    var captureConfigures: Bool { self == .captureDecides || self == .captureMixes }
}

/// One second of per-channel levels: of the samples exactly as the capture output hands them over (read from the
/// sample buffer itself, before any copy or conversion) and of the 16-bit samples that went to the server.
struct ChannelLevels {
    let names: [String]
    let mic: [Double]      // dBFS, -infinity for digital silence
    let sent: [Double]?    // nil while paused: nothing went out
    let format: String     // what the capture output delivers
    let audioSession: String
    let setup: CaptureSetup

    static func db(_ x: Double) -> String { x.isFinite ? String(Int(x.rounded())) : "silent" }

    private static func line(_ names: [String], _ levels: [Double]) -> String {
        zip(names, levels).map { "\($0) \(db($1))" }.joined(separator: " · ") + " dB"
    }

    /// "W -23 · Y -31 · Z -40 · X -28 dB"
    var micLine: String { Self.line(names, mic) }

    /// What went to the server, only when it does not match what the microphones gave (a conversion bug).
    var sentMismatchLine: String? {
        guard let sent, sent.count == mic.count else { return nil }
        let differs = zip(mic, sent).contains { m, s in
            m.isFinite != s.isFinite || (m.isFinite && abs(m - s) > 1.5)
        }
        return differs ? "sent " + Self.line(names, sent) : nil
    }
}

/// Sums squares per channel on the capture queue and hands out a `ChannelLevels` about once a second.
private struct ChannelMeter {
    private var mic: [Double] = []
    private var sent: [Double] = []
    private var micFrames = 0
    private var sentFrames = 0
    private(set) var format = ""

    mutating func reset() {
        mic = []; sent = []; micFrames = 0; sentFrames = 0; format = ""
    }

    /// The sample buffer's own audio, read in place: whatever the copy into AVAudioPCMBuffer or the Int16
    /// conversion does afterwards, these are the numbers the microphones gave.
    mutating func addMic(_ sampleBuffer: CMSampleBuffer, _ asbd: AudioStreamBasicDescription) {
        let channels = Int(asbd.mChannelsPerFrame)
        guard channels > 0 else { return }
        if mic.count != channels { mic = Array(repeating: 0, count: channels); micFrames = 0 }
        let isFloat = asbd.mFormatFlags & kAudioFormatFlagIsFloat != 0
        let bits = Int(asbd.mBitsPerChannel)
        let readable = isFloat ? bits == 32 : (bits == 16 || bits == 32)
        if format.isEmpty {
            let planar = asbd.mFormatFlags & kAudioFormatFlagIsNonInterleaved != 0
            format = "\(channels) ch · \(isFloat ? "Float" : "Int")\(bits) \(planar ? "planar" : "interleaved") · \(Int(asbd.mSampleRate / 1000)) kHz"
            if !readable { format += " (mic levels unreadable)" }
        }
        guard readable else { return }
        var frames = 0
        _ = try? sampleBuffer.withAudioBufferList { list, _ in
            var first = 0  // the channel this buffer starts at: one per buffer when planar, all in one when interleaved
            for buffer in list {
                let n = Int(buffer.mNumberChannels)
                defer { first += n }
                guard n > 0, let data = buffer.mData, first + n <= channels else { continue }
                let count = Int(buffer.mDataByteSize) / (bits / 8)
                frames = max(frames, count / n)
                switch (isFloat, bits) {
                case (true, _):
                    let s = data.assumingMemoryBound(to: Float32.self)
                    for i in 0..<count { let x = Double(s[i]); mic[first + i % n] += x * x }
                case (false, 16):
                    let s = data.assumingMemoryBound(to: Int16.self)
                    for i in 0..<count { let x = Double(s[i]) / 32768; mic[first + i % n] += x * x }
                default:
                    let s = data.assumingMemoryBound(to: Int32.self)
                    for i in 0..<count { let x = Double(s[i]) / 2_147_483_648; mic[first + i % n] += x * x }
                }
            }
        }
        micFrames += frames
    }

    /// The interleaved Int16 that went to the server.
    mutating func addSent(_ data: Data, channels: Int) {
        guard channels > 0 else { return }
        if sent.count != channels { sent = Array(repeating: 0, count: channels); sentFrames = 0 }
        data.withUnsafeBytes { raw in
            let s = raw.bindMemory(to: Int16.self)
            for i in 0..<s.count {
                let x = Double(s[i]) / 32768
                sent[i % channels] += x * x
            }
            sentFrames += s.count / channels
        }
    }

    /// A reading once a second of audio has gone by, then the sums start over.
    mutating func reading(sampleRate: Double, layout: String, setup: CaptureSetup) -> ChannelLevels? {
        guard micFrames > 0, Double(micFrames) >= sampleRate else { return nil }
        func dB(_ sums: [Double], _ frames: Int) -> [Double] {
            sums.map { $0 > 0 ? 10 * log10($0 / Double(frames)) : -.infinity }
        }
        let names: [String] = switch (layout, mic.count) {
        case ("foa", 4): ["W", "Y", "Z", "X"]  // ACN order
        case (_, 2): ["L", "R"]
        case (_, 1): ["M"]
        default: (0..<mic.count).map { "c\($0)" }
        }
        let levels = ChannelLevels(
            names: names, mic: dB(mic, micFrames),
            sent: sentFrames > 0 && sent.count == mic.count ? dB(sent, sentFrames) : nil,
            format: format + " · " + layout, audioSession: Self.describeAudioSession(), setup: setup)
        mic = Array(repeating: 0, count: mic.count); micFrames = 0
        sent = Array(repeating: 0, count: sent.count); sentFrames = 0
        return levels
    }

    /// The shared audio session as it stands: category, mode, how many input channels, which microphone.
    private static func describeAudioSession() -> String {
        let s = AVAudioSession.sharedInstance()
        let category = s.category.rawValue.replacingOccurrences(of: "AVAudioSessionCategory", with: "")
        let mode = s.mode.rawValue.replacingOccurrences(of: "AVAudioSessionMode", with: "")
        let input = s.currentRoute.inputs.first
        var mic = input?.portName ?? "no input"
        if let source = input?.selectedDataSource {
            mic += ", " + source.dataSourceName
            if let pattern = source.selectedPolarPattern { mic += " " + pattern.rawValue }
        }
        return "\(category)/\(mode) · in \(s.inputNumberOfChannels) ch · \(mic)"
    }
}

private let captureLog = Logger(subsystem: "com.eric2612115.hallwise", category: "capture")

/// Captures the badge's microphones as 4-channel first-order ambisonics (ACN order W, Y, Z, X, SN3D) when the
/// phone supports it, stereo otherwise. Each buffer is converted to interleaved 16-bit PCM for the server; a
/// full-quality copy stays on the phone only when the owner asks for one (Debug, "Keep a copy on this phone"), for
/// the demo soundtrack, and only for a week. The phone's orientation is sampled on the same
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
    /// Per-channel levels about once a second, on the capture queue (Debug, "Channel levels").
    var onLevels: ((ChannelLevels) -> Void)?
    /// The capture session stopped with an error, was interrupted or came back (Debug, under the levels).
    var onNote: ((String) -> Void)?
    /// While muted nothing leaves the phone (audio or pose), and nothing goes into the local copy either.
    var muted = false
    /// Write a raw copy of the take to Documents (opt-in; set before `start`).
    var keepLocalCopy = false
    /// Who configures the audio session (Debug; set before `start`).
    var setup = CaptureSetup.standard
    private(set) var recordingURL: URL?
    /// Local copies older than this are deleted at launch.
    static let localCopyDays = 7

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
    private var meter = ChannelMeter()  // touched only on `queue`
    private var activeSetup = CaptureSetup.standard  // the setup this take started with, on `queue`

    override init() {
        super.init()
        // A capture that stops or is interrupted says nothing on its own; the Debug row shows it, so a setup that
        // breaks the microphones (or the lock screen) is visible on the phone.
        let center = NotificationCenter.default
        center.addObserver(self, selector: #selector(runtimeError), name: AVCaptureSession.runtimeErrorNotification, object: session)
        center.addObserver(self, selector: #selector(interrupted), name: AVCaptureSession.wasInterruptedNotification, object: session)
        center.addObserver(self, selector: #selector(interruptionEnded), name: AVCaptureSession.interruptionEndedNotification, object: session)
    }

    @objc private func runtimeError(_ notification: Notification) {
        let error = notification.userInfo?[AVCaptureSessionErrorKey] as? NSError
        let codes = [error?.code, (error?.userInfo[NSUnderlyingErrorKey] as? NSError)?.code].compactMap { $0 }
        note("capture stopped: \(error?.localizedDescription ?? "unknown error") (\(codes.map(String.init).joined(separator: ", ")))")
    }

    @objc private func interrupted(_ notification: Notification) {
        let raw = notification.userInfo?[AVCaptureSessionInterruptionReasonKey] as? Int
        let reason: String = switch raw.flatMap(AVCaptureSession.InterruptionReason.init(rawValue:)) {
        case .audioDeviceInUseByAnotherClient: "microphone taken by another app"
        case .videoDeviceNotAvailableInBackground: "in the background"
        case .some(let other): "reason \(other.rawValue)"
        case nil: "no reason given"
        }
        note("capture interrupted: \(reason)")
    }

    @objc private func interruptionEnded(_ notification: Notification) {
        note("capture resumed")
    }

    private func note(_ text: String) {
        let stamp = Date().formatted(date: .omitted, time: .standard)
        #if DEBUG
        captureLog.info("\(text, privacy: .public)")
        #endif
        onNote?("\(stamp) \(text)")
    }

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
    /// cannot take over the microphone (no option here allows HFP or Bluetooth high-quality recording).
    ///
    /// Who sets that session up is the Debug "Capture setup" (see `CaptureSetup`). In B and E the capture session
    /// does it at startRunning: Apple's header says it then "ensures the application's audio session is set to the
    /// PlayAndRecord category, and picks an appropriate microphone and polar pattern". In A, C and D the app does
    /// it and the capture session "will not change any of its properties".
    private func configureAudioSession() {
        activeSetup = setup
        session.usesApplicationAudioSession = true
        session.automaticallyConfiguresApplicationAudioSession = setup.captureConfigures
        session.configuresApplicationAudioSessionToMixWithOthers = setup == .captureMixes
        guard !setup.captureConfigures else { return }
        let audio = AVAudioSession.sharedInstance()
        do {
            switch setup {
            case .videoRecording:
                try audio.setCategory(.playAndRecord, mode: .videoRecording, options: [.allowBluetoothA2DP])
            case .recordOnly:
                try audio.setCategory(.record, mode: .default)
            default:
                try audio.setCategory(.playAndRecord, mode: .default, options: [.allowBluetoothA2DP, .defaultToSpeaker, .mixWithOthers])
            }
            try audio.setActive(true)
        } catch {
            onError?("Audio session: \(error.localizedDescription)")
        }
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
        meter.reset()
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
        if let asbd = desc.audioStreamBasicDescription { meter.addMic(sampleBuffer, asbd) }
        if !muted {
            try? file?.write(from: buffer)
            let pcm = interleavedInt16(buffer)
            meter.addSent(pcm, channels: Int(format.channelCount))
            onAudio?(pcm)
            clockLock.withLock { framesCaptured += Int(frames) }
        }
        if let levels = meter.reading(sampleRate: sampleRate, layout: layout, setup: activeSetup) {
            #if DEBUG
            captureLog.info("levels setup \(levels.setup.letter, privacy: .public): \(levels.micLine, privacy: .public)\(levels.sentMismatchLine.map { " | " + $0 } ?? "", privacy: .public) | \(levels.format, privacy: .public) | \(levels.audioSession, privacy: .public)")
            #endif
            onLevels?(levels)
        }
    }

    private func openFile(_ format: AVAudioFormat) {
        file = nil
        recordingURL = nil
        guard keepLocalCopy else { return }
        let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let stamp = ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: ":", with: "-")
        let url = dir.appendingPathComponent("hallwise-\(layout)-\(stamp).caf")
        file = try? AVAudioFile(forWriting: url, settings: format.settings,
                                commonFormat: format.commonFormat, interleaved: format.isInterleaved)
        guard file != nil else { return }
        Self.protectLocalCopy(url)
        recordingURL = url
    }

    /// Open files stay writable through the lock (the badge records on a locked phone); closed ones are sealed
    /// until the next unlock. Never in an iCloud or Finder backup.
    private static func protectLocalCopy(_ url: URL) {
        try? FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUnlessOpen], ofItemAtPath: url.path)
        var url = url
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try? url.setResourceValues(values)
    }

    /// At launch: local copies older than a week go; the rest (some from before these rules) are protected and
    /// kept out of backups. Face photos are kept out of backups too.
    static func tidyLocalCopies(now: Date = Date()) {
        let fm = FileManager.default
        let dir = fm.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let cutoff = now.addingTimeInterval(-Double(localCopyDays) * 86_400)
        let names = (try? fm.contentsOfDirectory(at: dir, includingPropertiesForKeys: [.creationDateKey, .contentModificationDateKey])) ?? []
        for url in names where url.lastPathComponent.hasPrefix("hallwise-") && url.pathExtension == "caf" {
            let values = try? url.resourceValues(forKeys: [.creationDateKey, .contentModificationDateKey])
            let when = values?.contentModificationDate ?? values?.creationDate ?? now
            if when < cutoff {
                try? fm.removeItem(at: url)
            } else {
                protectLocalCopy(url)
            }
        }
        if fm.fileExists(atPath: LiveModel.photosRoot.path) { LiveModel.excludeFromBackup(LiveModel.photosRoot) }
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
