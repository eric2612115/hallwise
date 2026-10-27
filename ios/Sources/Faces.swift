import ImageIO
import UIKit

/// Faces travel with the person: a face the owner keeps tonight goes to the server under the person's
/// people-index key, and the next evening they turn up, it comes back for their dot, their strip and their card.
enum Faces {
    /// A face from the server is at most this many bytes, and this many pixels on its longer side.
    static let maxBytes = 5_000_000
    static let maxSide = 4096

    static func url(base: String, key: String, name: String = "", company: String = "") -> URL? {
        var c = URLComponents(string: ServerLink.httpBase(base) + "/api/people/\(key)/face")
        if !name.isEmpty { c?.queryItems = [URLQueryItem(name: "name", value: name), URLQueryItem(name: "company", value: company)] }
        guard let url = c?.url, url.host() != nil else { return nil }
        return url
    }

    /// Keep a face on the server; a failure only means it stays on this phone.
    static func upload(base: String, key: String, image: UIImage) async {
        guard !key.isEmpty, let url = url(base: base, key: key),
              let jpeg = image.normalised(maxSide: 480).jpegData(compressionQuality: 0.85) else { return }
        var req = URLRequest.hallwise(url, method: "POST")
        req.setValue("image/jpeg", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 30
        if let (_, response) = try? await URLSession.shared.upload(for: req, from: jpeg) { ServerAuth.shared.note(response) }
    }

    /// The face kept for this person at an earlier evening, if any. Read no further than `maxBytes`, and decoded
    /// only once its header says it is no larger than `maxSide`.
    static func fetch(base: String, key: String, name: String, company: String) async -> UIImage? {
        guard !key.isEmpty, let url = url(base: base, key: key, name: name, company: company),
              let (bytes, response) = try? await URLSession.shared.bytes(for: .hallwise(url)) else { return nil }
        guard !ServerAuth.shared.note(response), (response as? HTTPURLResponse)?.statusCode == 200,
              response.expectedContentLength <= Int64(maxBytes) else { return nil }
        var data = Data()
        do {
            for try await byte in bytes {
                data.append(byte)
                if data.count > maxBytes { return nil }
            }
        } catch { return nil }
        return decode(data)
    }

    /// An image within the size limits, else nil.
    static func decode(_ data: Data) -> UIImage? {
        guard data.count <= maxBytes, let source = CGImageSourceCreateWithData(data as CFData, nil),
              let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let w = (props[kCGImagePropertyPixelWidth] as? NSNumber)?.intValue,
              let h = (props[kCGImagePropertyPixelHeight] as? NSNumber)?.intValue,
              w > 0, h > 0, max(w, h) <= maxSide else { return nil }
        return UIImage(data: data)
    }
}
