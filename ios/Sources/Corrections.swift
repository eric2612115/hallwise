import Foundation

/// The owner fixes what the transcriber got wrong: a person's name and company, a misheard word, a suggestion that
/// was wrong. Each one is a POST to the server with the server key; the server appends it to the recording's log
/// and keeps the words for every later recording. Nothing changes on the phone until the server has it.
enum Corrections {
    /// Why a correction did not go through, in a few words for the screen.
    struct Failure: LocalizedError {
        let reason: String
        var errorDescription: String? { reason }
    }

    /// person: key, name, company. word: heard, use (and the suggestion it answers). word_rejected: heard, likely.
    /// Back come the logged event and the person as the record now has them, or the vocabulary.
    static func send(base: String, recording: String, _ body: [String: Any]) async throws -> [String: Any] {
        guard !recording.isEmpty else { throw Failure(reason: "No recording to save it to") }
        return try await post(base: base, path: "/api/recordings/\(recording)/corrections", body: body)
    }

    /// A person's name and company from the directory, fixed in every evening they were met. Back comes their entry.
    static func person(base: String, key: String, name: String, company: String) async throws -> [String: Any] {
        try await post(base: base, path: "/api/people/\(key)/correction", body: ["name": name, "company": company])
    }

    private static func post(base: String, path: String, body: [String: Any]) async throws -> [String: Any] {
        guard let url = URL(string: ServerLink.httpBase(base) + path), url.host() != nil else {
            throw Failure(reason: "No server address")
        }
        var req = URLRequest.hallwise(url, method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 20
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let data: Data, response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: req)
        } catch {
            throw Failure(reason: "Couldn't reach the server")
        }
        if ServerAuth.shared.note(response) { throw Failure(reason: ServerAuth.wrongKey) }
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            // FastAPI says why in "detail" (a string, or a list for a body it could not read); the guard in "error"
            let detail = (json["detail"] as? String) ?? (json["error"] as? String) ?? "the server said no"
            throw Failure(reason: String(detail.prefix(80)))
        }
        return json
    }
}
