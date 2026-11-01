import SwiftUI
import UserNotifications

/// A page the server has ready for someone met tonight (server/hallwise/onepager.py): the owner's deck rebuilt for
/// what they said they want ("one page, numbers first"), or, in the demo, a page made beforehand and put in on cue.
/// From the `rebuilt` event, whose `url` says where the page is, HTML or PDF.
struct RebuiltPage: Identifiable, Equatable {
    var id: String { recording + "/" + personKey }
    let recording: String
    let personKey: String
    let name: String       // "Margaux Lefèvre"
    let title: String      // the page's title: "Hallwise"
    let shape: String      // what this version is, for the owner: "one page, numbers first"
    let act: String        // the edge's act it follows, when the server gave no shape
    let slides: [String]   // the deck's slide titles, which the viewer folds into the page
    let path: String       // where the page is on the server, HTML or PDF

    init?(_ d: [String: Any], recording: String) {
        guard let key = d["person_key"] as? String, !key.isEmpty, !recording.isEmpty,
              (d["status"] as? String ?? "ok") == "ok" else { return nil }
        self.recording = recording
        personKey = key
        name = String((d["name"] as? String ?? "").prefix(80))
        title = String((d["title"] as? String ?? "").prefix(80))
        shape = String((d["shape"] as? String ?? "").prefix(60))
        act = String(((d["acts"] as? [String])?.first ?? "").prefix(60))
        slides = ((d["slides"] as? [String]) ?? []).prefix(20).map { String($0.prefix(60)) }
        path = (d["url"] as? String).flatMap { $0.hasPrefix("/api/recordings/") ? $0 : nil }
            ?? OnePager.path(recording: recording, personKey: key)
    }

    init(recording: String, personKey: String, name: String, shape: String, slides: [String] = [], path: String = "") {
        self.recording = recording
        self.path = path.isEmpty ? OnePager.path(recording: recording, personKey: personKey) : path
        self.personKey = personKey
        self.name = name
        title = ""
        self.shape = shape
        act = ""
        self.slides = slides
    }

    var firstName: String { name.split(separator: " ").first.map(String.init) ?? name }
    /// "one page, numbers first": what the notification and the viewer say this version is.
    var what: String { shape.isEmpty ? act : shape }
    /// "Margaux · your deck, rebuilt", then "One page, numbers first. Ready.": one line each on a banner.
    var headline: String { firstName.isEmpty ? "Your deck, rebuilt" : "\(firstName) · your deck, rebuilt" }
    var subline: String { what.isEmpty ? "Ready." : what.prefix(1).uppercased() + what.dropFirst() + ". Ready." }
}

/// Pages rebuilt tonight: the buzz and the notification when one is ready (with a picture of the page), and the
/// one to open when it is tapped. Once per person per recording, and never for a recording being replayed.
final class RebuiltPages: ObservableObject {
    static let shared = RebuiltPages()
    static let userInfoKey = "onepager"

    @Published var open: RebuiltPage?                                // the viewer shows this one
    @Published private(set) var ready: [String: RebuiltPage] = [:]   // by person key, this recording's
    private(set) var pages: [String: OnePager.Page] = [:]            // page id -> the page, fetched for the notice
    private var told: Set<String> = []                               // ids already announced

    /// A `rebuilt` event. `live`: the recording is happening now (not a replay, not the morning's backlog). The
    /// page is fetched first, so the notification shows it and the viewer opens at once; the buzz comes with it.
    @MainActor
    func arrived(_ event: [String: Any], recording: String, base: String, live: Bool) async {
        guard let page = RebuiltPage(event, recording: recording) else { return }
        ready[page.personKey] = page
        guard live, !told.contains(page.id) else { return }
        told.insert(page.id)
        var picture: URL?
        if let fetched = try? await OnePager.fetch(base: base, path: page.path) {
            pages[page.id] = fetched
            picture = await RebuiltNotice.picture(fetched, id: page.personKey)
        }
        UINotificationFeedbackGenerator().notificationOccurred(.success)  // felt on the chest, screen out
        RebuiltNotice.post(page, picture: picture)
    }

    /// A tapped notification: true when it was a rebuilt page's, which is now open.
    @discardableResult
    func open(from userInfo: [AnyHashable: Any]) -> Bool {
        guard let info = userInfo[Self.userInfoKey] as? [String: String], let key = info["person_key"],
              let recording = info["recording"], !key.isEmpty, !recording.isEmpty else { return false }
        let page = ready[key].flatMap { $0.recording == recording ? $0 : nil }
            ?? RebuiltPage(recording: recording, personKey: key, name: info["name"] ?? "", shape: info["shape"] ?? "",
                           path: info["path"] ?? "")
        DispatchQueue.main.async { self.open = page }
        return true
    }

    /// A new recording starts with none ready.
    func reset() {
        ready = [:]
        pages = [:]
        open = nil
    }
}

/// The local notification: right away, one per person per recording (a second one for the same person replaces
/// the first rather than stacking), with the page's top as its picture when it could be drawn.
enum RebuiltNotice {
    static func post(_ page: RebuiltPage, picture: URL?) {
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound, .badge]) { ok, _ in
            guard ok else { return }
            let content = UNMutableNotificationContent()
            content.title = String(page.headline.prefix(100))
            content.subtitle = String(page.subline.prefix(100))
            content.body = page.name.isEmpty ? "Tap to read it before you send it."
                : "For \(page.name). Tap to read it before you send it."
            content.sound = .default
            content.threadIdentifier = "onepager:" + page.recording
            content.userInfo = [RebuiltPages.userInfoKey: [
                "person_key": page.personKey, "recording": page.recording, "name": page.name, "shape": page.what,
                "path": page.path,
            ]]
            // the page itself, shown when the notification is opened out
            if let picture, let attachment = try? UNNotificationAttachment(identifier: "page", url: picture, options: nil) {
                content.attachments = [attachment]
            }
            center.add(UNNotificationRequest(identifier: "onepager:" + page.id, content: content, trigger: nil))
        }
    }

    /// The page drawn as a PNG for the notification (the notification takes the file over); nil if it cannot be.
    @MainActor
    static func picture(_ page: OnePager.Page, id: String) async -> URL? {
        guard let pdf = try? await page.pdf(), let image = OnePagerPDF.image(pdf, width: 600),
              let png = image.pngData() else { return nil }
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("onepager-\(ServerData.fileName(id)).png")
        return (try? png.write(to: file, options: .atomic)) != nil ? file : nil
    }
}

/// The viewer, over whatever is showing, when a rebuilt page's notification is tapped (or `open` is set).
private struct RebuiltPageSheet: ViewModifier {
    @ObservedObject var pages: RebuiltPages
    @ObservedObject var settings: BadgeSettings

    func body(content: Content) -> some View {
        content.sheet(item: $pages.open) { page in
            OnePagerView(
                source: pages.pages[page.id].map { .page($0) } ?? .server(base: settings.serverURL, path: page.path),
                person: page.name.isEmpty ? "them" : page.name, act: page.what, slides: page.slides
            )
            .closableSheet()
        }
    }
}

extension View {
    func rebuiltPages(_ pages: RebuiltPages = .shared, settings: BadgeSettings) -> some View {
        modifier(RebuiltPageSheet(pages: pages, settings: settings))
    }
}
