import Foundation

/// The two WebSockets to the Hallwise server: /ingest carries the badge's audio and orientation up,
/// /events/{recording} brings the live record back down.
final class ServerLink: ObservableObject {
    @Published var status = "idle"
    @Published var recordingID: String?

    var onEvent: (([String: Any]) -> Void)?
    /// The answer to a spoken question (asked while listening), from the ingest socket.
    var onAsk: (([String: Any]) -> Void)?
    /// The server turned the key down (401 or close code 4401): the capture stops, nothing retries.
    var onRejected: (() -> Void)?
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
    /// Set once the server turns the key down, so the failures that follow do not cover "Server key is wrong".
    private var turnedDown = false

    /// The hello (calendar busy windows, place, links) is queued on the task and only goes out once the server
    /// has accepted the upgrade: a server that answers 401 never receives it.
    func open(base: String, hello: [String: Any]) {
        self.base = base.trimmingCharacters(in: CharacterSet(charactersIn: "/ "))
        turnedDown = false
        guard let url = URL(string: self.base + "/ingest"), url.host() != nil else {
            publish("bad server address")
            return
        }
        let task = urlSession.webSocketTask(with: .hallwise(url))
        ingest = task
        task.resume()
        sendJSON(hello)
        receiveIngest(task)
        publish("connecting")
    }

    /// Watch an existing recording without capturing anything (previews, the simulator, a second screen).
    /// A finished recording replays at `pace` (1 = as it happened, 2 = twice as fast, 0 = everything at once);
    /// a live one streams as it happens whatever the pace: the server decides.
    func follow(base: String, recording: String, pace: Double) {
        self.base = base.trimmingCharacters(in: CharacterSet(charactersIn: "/ "))
        turnedDown = false
        DispatchQueue.main.async { self.recordingID = recording }
        publish("following \(recording)")
        watch(recording, pace: pace)
    }

    /// Stop following: the server stops sending, and a later follow starts over.
    func unfollow() {
        events?.cancel(with: .goingAway, reason: nil)
        events = nil
    }

    /// The server is replaying a finished recording at its own pace (it sends replay_clock ticks only then).
    private(set) var replaying = false

    func sendAudio(_ data: Data) {
        ingest?.send(.data(data)) { [weak self] error in
            if let error, self?.turnedDown == false { self?.publish("audio send failed: \(error.localizedDescription)") }
        }
    }

    /// `yaw` is the badge's heading (see `badgeHeading`), not CoreMotion's Euler yaw; `inverted` means it hangs
    /// top-down, so the server mirrors the microphones' left and right.
    func sendPose(tMs: Int, yaw: Double, pitch: Double, roll: Double, inverted: Bool) {
        sendJSON(["type": "pose", "t_ms": tMs, "yaw": yaw, "pitch": pitch, "roll": roll, "inverted": inverted])
    }

    func close() {
        sendJSON(["type": "end"])
        publish("finishing")
    }

    /// A photo of the people around the badge, with who is where; back come the faces and who each one is.
    func matchPhoto(base: String, recording: String, jpeg: Data, people: [[String: Any]], hint: String) async throws -> [String: Any] {
        guard let url = URL(string: Self.httpBase(base) + "/api/recordings/\(recording)/photo") else { throw URLError(.badURL) }
        var req = URLRequest.hallwise(url, method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 120
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "image_b64": jpeg.base64EncodedString(), "mime": "image/jpeg", "people": people, "hint": hint,
        ])
        let (data, response) = try await urlSession.data(for: req)
        if ServerAuth.shared.note(response) { throw WrongServerKey() }
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw URLError(.badServerResponse) }
        return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }

    /// A GET to the server with the key; nil when it fails or turns the key down.
    private func getJSON(_ path: String, base: String) async -> Any? {
        guard let url = URL(string: Self.httpBase(base) + path), url.host() != nil,
              let (data, response) = try? await urlSession.data(for: .hallwise(url)) else { return nil }
        guard !ServerAuth.shared.note(response), (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return try? JSONSerialization.jsonObject(with: data)
    }

    /// Everyone the owner has met, across recordings, newest encounter first.
    func fetchPeople(base: String) async -> [[String: Any]] {
        await getJSON("/api/people", base: base) as? [[String: Any]] ?? []
    }

    /// Every recording on the server, newest first, each with its event, start and place.
    func fetchRecordings(base: String) async -> [[String: Any]] {
        await getJSON("/api/recordings", base: base) as? [[String: Any]] ?? []
    }

    /// The newest recording on the server: what a question after Stop is about when nothing is live.
    func latestRecording(base: String) async -> String? {
        (await getJSON("/api/recordings", base: base) as? [[String: Any]])?.first?["id"] as? String
    }

    /// A typed question about a recording, answered over HTTP. With no recording id, the newest one.
    func ask(base: String, recording: String?, question: String, history: [[String: String]], keywords: [String]) async throws -> [String: Any] {
        let http = Self.httpBase(base)
        var rid = recording
        if rid == nil {
            guard let url = URL(string: http + "/api/recordings"), url.host() != nil else { throw URLError(.badURL) }
            let (data, response) = try await urlSession.data(for: .hallwise(url))
            if ServerAuth.shared.note(response) { throw WrongServerKey() }
            let list = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []
            rid = list.first?["id"] as? String
        }
        guard let rid, let url = URL(string: http + "/api/recordings/\(rid)/ask") else {
            throw URLError(.badURL)
        }
        var req = URLRequest.hallwise(url, method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 90
        req.httpBody = try JSONSerialization.data(withJSONObject: ["question": question, "history": history, "keywords": keywords])
        let (data, response) = try await urlSession.data(for: req)
        if ServerAuth.shared.note(response) { throw WrongServerKey() }
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }

    private func sendJSON(_ object: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: object),
              let text = String(data: data, encoding: .utf8) else { return }
        ingest?.send(.string(text)) { [weak self] error in
            if let error, self?.turnedDown == false { self?.publish("send failed: \(error.localizedDescription)") }
        }
    }

    /// The server turned the key down: say so, drop the socket, and let the app stop. No retry.
    private func turnDown(_ task: URLSessionWebSocketTask) {
        turnedDown = true
        if task === ingest { ingest = nil }
        if task === events { events = nil }
        task.cancel(with: .normalClosure, reason: nil)
        publish(ServerAuth.wrongKey)
        DispatchQueue.main.async { self.onRejected?() }
    }

    private func receiveIngest(_ task: URLSessionWebSocketTask) {
        task.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(.string(let text)):
                if let msg = Self.parse(text), let id = msg["recording"] as? String {
                    if msg["type"] as? String == "ready" {
                        ServerAuth.shared.accepted()
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
                self.receiveIngest(task)
            case .success:
                self.receiveIngest(task)
            case .failure(let error):
                if ServerAuth.shared.note(task) {
                    self.turnDown(task)
                } else if !self.turnedDown {
                    self.publish("disconnected: \(error.localizedDescription)")
                }
            }
        }
    }

    private func watch(_ id: String, pace: Double = 0) {
        let query = pace > 0 ? "?pace=" + String(format: "%g", pace) : ""
        guard let url = URL(string: base + "/events/" + id + query), url.host() != nil else {
            publish("bad server address")
            return
        }
        events?.cancel(with: .goingAway, reason: nil)  // one stream into the record at a time
        replaying = false
        let task = urlSession.webSocketTask(with: .hallwise(url))
        events = task
        task.resume()
        receiveEvents(task)
    }

    private func receiveEvents(_ task: URLSessionWebSocketTask) {
        task.receive { [weak self] result in
            guard let self, task === self.events else { return }  // a socket we have moved on from
            switch result {
            case .success(.string(let text)):
                ServerAuth.shared.accepted()
                if let event = Self.parse(text) {
                    if event["type"] as? String == "replay_clock", !self.replaying {
                        self.replaying = true
                        self.publish("replaying")
                    }
                    DispatchQueue.main.async { self.onEvent?(event) }
                }
                self.receiveEvents(task)
            case .success:
                self.receiveEvents(task)
            case .failure:
                if ServerAuth.shared.note(task) {
                    self.turnDown(task)
                } else if self.replaying {
                    self.publish("replay ended")
                }
            }
        }
    }

    private func publish(_ text: String) {
        DispatchQueue.main.async { self.status = text }
    }

    private static func parse(_ text: String) -> [String: Any]? {
        try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]
    }
}
