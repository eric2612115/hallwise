import Foundation

/// The two WebSockets to the Hallwise server: /ingest carries the badge's audio and orientation up,
/// /events/{recording} brings the live record back down.
final class ServerLink: ObservableObject {
    @Published var status = "idle"
    @Published var recordingID: String?

    var onEvent: (([String: Any]) -> Void)?
    /// The answer to a spoken question (asked while listening), from the ingest socket.
    var onAsk: (([String: Any]) -> Void)?
    /// Whether a spoken question can be asked right now: the ingest socket is up.
    var canAskByVoice: Bool { ingest != nil }

    /// "ws://host:8790" → "http://host:8790", for the plain HTTP calls.
    static func httpBase(_ ws: String) -> String {
        let b = ws.trimmingCharacters(in: CharacterSet(charactersIn: "/ "))
        if b.hasPrefix("wss://") { return "https://" + b.dropFirst(6) }
        if b.hasPrefix("ws://") { return "http://" + b.dropFirst(5) }
        return b
    }

    /// Hold to talk: the badge's audio keeps flowing; the server listens to it as a question until askEnd.
    func askStart() {
        sendJSON(["type": "ask_start"])
    }

    func askEnd(history: [[String: String]]) {
        sendJSON(["type": "ask_end", "history": history])
    }

    private let urlSession = URLSession(configuration: .default)
    private var ingest: URLSessionWebSocketTask?
    private var events: URLSessionWebSocketTask?
    private var base = ""

    func open(base: String, hello: [String: Any]) {
        self.base = base.trimmingCharacters(in: CharacterSet(charactersIn: "/ "))
        guard let url = URL(string: self.base + "/ingest") else {
            publish("bad server address")
            return
        }
        let task = urlSession.webSocketTask(with: url)
        ingest = task
        task.resume()
        sendJSON(hello)
        receiveIngest()
        publish("connecting")
    }

    /// Watch an existing recording without capturing anything (previews, the simulator, a second screen).
    func follow(base: String, recording: String) {
        self.base = base.trimmingCharacters(in: CharacterSet(charactersIn: "/ "))
        DispatchQueue.main.async { self.recordingID = recording }
        publish("following \(recording)")
        watch(recording)
    }

    func sendAudio(_ data: Data) {
        ingest?.send(.data(data)) { [weak self] error in
            if let error { self?.publish("audio send failed: \(error.localizedDescription)") }
        }
    }

    func sendPose(tMs: Int, yaw: Double, pitch: Double, roll: Double) {
        sendJSON(["type": "pose", "t_ms": tMs, "yaw": yaw, "pitch": pitch, "roll": roll])
    }

    func close() {
        sendJSON(["type": "end"])
        publish("finishing")
    }

    /// A typed question about a recording, answered over HTTP. With no recording id, the newest one.
    func ask(base: String, recording: String?, question: String, history: [[String: String]], keywords: [String]) async throws -> [String: Any] {
        let http = Self.httpBase(base)
        var rid = recording
        if rid == nil {
            let (data, _) = try await urlSession.data(from: URL(string: http + "/api/recordings")!)
            let list = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []
            rid = list.first?["id"] as? String
        }
        guard let rid, let url = URL(string: http + "/api/recordings/\(rid)/ask") else {
            throw URLError(.badURL)
        }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 90
        req.httpBody = try JSONSerialization.data(withJSONObject: ["question": question, "history": history, "keywords": keywords])
        let (data, response) = try await urlSession.data(for: req)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }

    private func sendJSON(_ object: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: object),
              let text = String(data: data, encoding: .utf8) else { return }
        ingest?.send(.string(text)) { [weak self] error in
            if let error { self?.publish("send failed: \(error.localizedDescription)") }
        }
    }

    private func receiveIngest() {
        ingest?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(.string(let text)):
                if let msg = Self.parse(text), let id = msg["recording"] as? String {
                    if msg["type"] as? String == "ready" {
                        DispatchQueue.main.async { self.recordingID = id }
                        self.publish("listening")
                        self.watch(id)
                    } else if msg["type"] as? String == "closed" {
                        self.publish("saved")
                        self.ingest?.cancel(with: .normalClosure, reason: nil)
                        self.ingest = nil
                        return
                    }
                }
                if let msg = Self.parse(text), msg["type"] as? String == "ask_answer" {
                    DispatchQueue.main.async { self.onAsk?(msg) }
                }
                self.receiveIngest()
            case .success:
                self.receiveIngest()
            case .failure(let error):
                self.publish("disconnected: \(error.localizedDescription)")
            }
        }
    }

    private func watch(_ id: String) {
        guard let url = URL(string: base + "/events/" + id) else { return }
        let task = urlSession.webSocketTask(with: url)
        events = task
        task.resume()
        receiveEvents()
    }

    private func receiveEvents() {
        events?.receive { [weak self] result in
            guard let self else { return }
            if case .success(.string(let text)) = result, let event = Self.parse(text) {
                DispatchQueue.main.async { self.onEvent?(event) }
            }
            if case .failure = result { return }
            self.receiveEvents()
        }
    }

    private func publish(_ text: String) {
        DispatchQueue.main.async { self.status = text }
    }

    private static func parse(_ text: String) -> [String: Any]? {
        try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]
    }
}
