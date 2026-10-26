import Foundation

/// The two WebSockets to the Hallwise server: /ingest carries the badge's audio and orientation up,
/// /events/{recording} brings the live record back down.
final class ServerLink: ObservableObject {
    @Published var status = "idle"
    @Published var recordingID: String?

    var onEvent: (([String: Any]) -> Void)?

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
                        return
                    }
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
