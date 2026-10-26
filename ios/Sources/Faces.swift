import UIKit

/// Faces travel with the person: a face the owner keeps tonight goes to the server under the person's
/// people-index key, and the next evening they turn up, it comes back for their dot, their strip and their card.
enum Faces {
    static func url(base: String, key: String, name: String = "", company: String = "") -> URL? {
        var c = URLComponents(string: ServerLink.httpBase(base) + "/api/people/\(key)/face")
        if !name.isEmpty { c?.queryItems = [URLQueryItem(name: "name", value: name), URLQueryItem(name: "company", value: company)] }
        return c?.url
    }

    /// Keep a face on the server; a failure only means it stays on this phone.
    static func upload(base: String, key: String, image: UIImage) async {
        guard !key.isEmpty, let url = url(base: base, key: key),
              let jpeg = image.normalised(maxSide: 480).jpegData(compressionQuality: 0.85) else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("image/jpeg", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 30
        _ = try? await URLSession.shared.upload(for: req, from: jpeg)
    }

    /// The face kept for this person at an earlier evening, if any.
    static func fetch(base: String, key: String, name: String, company: String) async -> UIImage? {
        guard !key.isEmpty, let url = url(base: base, key: key, name: name, company: company),
              let (data, response) = try? await URLSession.shared.data(from: url),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return UIImage(data: data)
    }
}
