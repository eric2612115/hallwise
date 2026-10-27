import Foundation
import Security

/// The shared secret the Hallwise server asks for on every request, as `Authorization: Bearer <key>`.
/// It lives in the Keychain on this phone only (never in UserDefaults, never in a backup, never logged).
enum ServerKey {
    private static let service = "com.eric2612115.hallwise.server-key"
    private static let account = "hallwise-server"
    private static let lock = NSLock()
    private static var cached: String?

    /// The key as stored, "" when none is set.
    static func read() -> String {
        lock.withLock {
            if let cached { return cached }
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: account,
                kSecReturnData as String: true,
                kSecMatchLimit as String: kSecMatchLimitOne,
            ]
            var item: CFTypeRef?
            let status = SecItemCopyMatching(query as CFDictionary, &item)
            let value = status == errSecSuccess ? (item as? Data).flatMap { String(data: $0, encoding: .utf8) } ?? "" : ""
            // a locked Keychain (before the first unlock) is asked again next time
            if status == errSecSuccess || status == errSecItemNotFound { cached = value }
            return value
        }
    }

    /// Keep a new key; an empty one removes it.
    static func save(_ key: String) {
        let value = key.trimmingCharacters(in: .whitespacesAndNewlines)
        lock.withLock {
            let match: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: account,
            ]
            SecItemDelete(match as CFDictionary)
            if !value.isEmpty {
                var add = match
                add[kSecValueData as String] = Data(value.utf8)
                add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
                SecItemAdd(add as CFDictionary, nil)
            }
            cached = value
        }
        ServerAuth.shared.clear()  // a new key gets a fresh try
    }

    /// Adds the key to a request for the Hallwise server (HTTP or a WebSocket upgrade).
    static func authorize(_ request: inout URLRequest) {
        let key = read()
        guard !key.isEmpty, let scheme = request.url?.scheme?.lowercased(),
              ["http", "https", "ws", "wss"].contains(scheme), request.url?.host() != nil else { return }
        request.setValue("Bearer " + key, forHTTPHeaderField: "Authorization")
    }
}

extension URLRequest {
    /// A request to the Hallwise server, carrying the server key.
    static func hallwise(_ url: URL, method: String = "GET") -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        ServerKey.authorize(&request)
        return request
    }
}

/// Whether the server turned the key down on its last answer. A 401 (or a socket closed with 4401) sets it;
/// any answer it accepts clears it. Nothing retries on its own: the next try is the owner's.
final class ServerAuth: ObservableObject {
    static let shared = ServerAuth()
    static let wrongKey = "Server key is wrong"

    @Published private(set) var rejected = false

    /// Note an HTTP answer from the server. Returns true when it turned the key down.
    @discardableResult
    func note(_ response: URLResponse?) -> Bool {
        guard let status = (response as? HTTPURLResponse)?.statusCode else { return false }
        if status == 401 { set(true); return true }
        if (200..<300).contains(status) { set(false) }
        return false
    }

    /// A WebSocket that ended: turned down at the upgrade (401, or 403 when a server closes before accepting),
    /// or closed with the server's 4401.
    @discardableResult
    func note(_ task: URLSessionWebSocketTask) -> Bool {
        let status = (task.response as? HTTPURLResponse)?.statusCode
        if status == 401 || status == 403 || task.closeCode.rawValue == 4401 { set(true); return true }
        return false
    }

    func accepted() { set(false) }
    func clear() { set(false) }

    private func set(_ value: Bool) {
        let apply = { if self.rejected != value { self.rejected = value } }
        if Thread.isMainThread { apply() } else { DispatchQueue.main.async(execute: apply) }
    }
}

/// The server's answer turned the key down.
struct WrongServerKey: LocalizedError {
    var errorDescription: String? { ServerAuth.wrongKey }
}

/// What arrives from the server is data: links, file names, images and notification counts are all bounded here.
enum ServerData {
    /// Only plain web pages become tappable links: no tel:, sms:, shortcuts: or any other scheme.
    static func webURL(_ text: String) -> URL? {
        guard let url = URL(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
              let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https",
              let host = url.host(), !host.isEmpty else { return nil }
        return url
    }

    /// A server-supplied id or key as a file name: letters, digits, "-" and "_" only, at most 80 of them. A name
    /// that had to change carries a short hash of the original, so two different keys never share a file.
    static func fileName(_ text: String) -> String {
        var out = ""
        for ch in text.unicodeScalars.prefix(80) {
            let ok = ("a"..."z").contains(ch) || ("A"..."Z").contains(ch) || ("0"..."9").contains(ch) || ch == "-" || ch == "_"
            out.unicodeScalars.append(ok ? ch : "_")
        }
        if out == text, !out.isEmpty { return out }
        var hash: UInt64 = 0xcbf29ce484222325  // FNV-1a
        for b in text.utf8 { hash = (hash ^ UInt64(b)) &* 0x100000001b3 }
        return (out.isEmpty ? "id" : out) + "-" + String(hash, radix: 16)
    }
}
