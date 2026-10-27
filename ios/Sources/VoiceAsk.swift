import AVFoundation
import Foundation

/// A spoken question once the badge has stopped: the phone's own microphone, resampled to 16 kHz mono,
/// streamed to /ask/{recording}; partials, the question as heard, and the answer come back the same way.
/// While the badge is listening, questions ride the badge's stream instead (see ServerLink.askStart).
final class VoiceAsk {
    var onEvent: (([String: Any]) -> Void)?

    private let engine = AVAudioEngine()
    private let session = URLSession(configuration: .default)
    private var task: URLSessionWebSocketTask?
    private var converter: AVAudioConverter?
    private var outFormat: AVAudioFormat?

    var active: Bool { task != nil }

    func start(base: String, recording: String, keywords: [String], history: [[String: String]]) throws {
        let ws = base.trimmingCharacters(in: CharacterSet(charactersIn: "/ "))
        guard let url = URL(string: ws + "/ask/" + recording), url.host() != nil else { throw URLError(.badURL) }
        let audio = AVAudioSession.sharedInstance()
        try audio.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetoothA2DP])
        try audio.setActive(true)

        let input = engine.inputNode
        let inFormat = input.outputFormat(forBus: 0)
        guard inFormat.channelCount > 0,
              let out = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true),
              let conv = AVAudioConverter(from: inFormat, to: out) else { throw URLError(.cannotOpenFile) }
        converter = conv
        outFormat = out

        let t = session.webSocketTask(with: .hallwise(url))
        task = t
        t.resume()
        send(["sample_rate": 16_000, "keywords": keywords, "history": history])
        receive()

        input.installTap(onBus: 0, bufferSize: 4096, format: inFormat) { [weak self] buffer, _ in
            self?.push(buffer, from: inFormat)
        }
        engine.prepare()
        try engine.start()
    }

    func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        send(["type": "end"])
    }

    private func push(_ buffer: AVAudioPCMBuffer, from inFormat: AVAudioFormat) {
        guard let converter, let outFormat else { return }
        let ratio = outFormat.sampleRate / inFormat.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 32
        guard let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: capacity) else { return }
        var handed = false
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if handed {
                status.pointee = .noDataNow
                return nil
            }
            handed = true
            status.pointee = .haveData
            return buffer
        }
        guard error == nil, out.frameLength > 0, let pcm = out.int16ChannelData else { return }
        let data = Data(bytes: pcm[0], count: Int(out.frameLength) * 2)
        task?.send(.data(data)) { _ in }
    }

    private func send(_ object: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: object),
              let text = String(data: data, encoding: .utf8) else { return }
        task?.send(.string(text)) { _ in }
    }

    private func receive() {
        task?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(.string(let text)):
                ServerAuth.shared.accepted()
                if let event = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any] {
                    DispatchQueue.main.async { self.onEvent?(event) }
                    if event["type"] as? String == "answer" {
                        self.task?.cancel(with: .normalClosure, reason: nil)
                        self.task = nil
                        return
                    }
                }
                self.receive()
            case .success:
                self.receive()
            case .failure(let error):
                // a key the server turned down (401, or close code 4401) says so; nothing retries
                let reason = self.task.map { ServerAuth.shared.note($0) } == true ? ServerAuth.wrongKey : error.localizedDescription
                DispatchQueue.main.async { self.onEvent?(["type": "answer", "answer": "", "actions": [], "error": reason]) }
                self.task = nil
            }
        }
    }
}
