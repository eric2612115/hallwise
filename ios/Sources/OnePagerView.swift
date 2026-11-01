import PDFKit
import SwiftUI
import WebKit

/// The deck, rebuilt for one person (server/hallwise/onepager.py): the page the server keeps for them, HTML or
/// PDF, rebuilt from the owner's deck or put in on cue, read here as it will be sent and shared as a PDF. It opens
/// with the deck's slides folding into the one page. An HTML page is shown with no JavaScript, no website data
/// kept and no link followed.
struct OnePagerView: View {
    enum Source {
        /// a path on the server, as the `rebuilt` event gives it: /api/recordings/{recording}/onepager/{personKey}
        case server(base: String, path: String)
        /// a page already on the phone
        case page(OnePager.Page)
    }

    let source: Source
    let person: String       // whose page it is: the title and the PDF's name
    var act: String = ""     // what it was shaped by, for the owner's eyes only: "one page, numbers first"
    var slides: [String] = []  // the deck's slide titles, folded into the page as it opens
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var page: OnePager.Page?
    @State private var problem: String?
    @State private var share: ShareItems?
    @State private var making = false
    @State private var started = false
    @State private var fold = Fold.waiting
    @State private var pageReady = false  // the web view has the page: it never rises blank

    /// The reveal: the slides are dealt out, fold into one, and the page rises where they were.
    enum Fold { case waiting, dealt, folded, page }

    private var firstName: String { person.split(separator: " ").first.map(String.init) ?? person }

    var body: some View {
        ZStack {
            PaperBackground()
            VStack(alignment: .leading, spacing: 16) {
                header
                ZStack {
                    if !slides.isEmpty && fold != .page {
                        SlideFan(titles: slides, fold: fold)
                    }
                    if let page {
                        shown(page)
                            .clipShape(RoundedRectangle(cornerRadius: 16))
                            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.rule, lineWidth: 0.5))
                            .shadow(color: Theme.ink.opacity(0.12), radius: 18, y: 8)
                            .opacity(fold == .page ? 1 : 0.02)  // drawn underneath the slides, so it never rises blank
                            .scaleEffect(fold == .page ? 1 : 0.94, anchor: .top)
                            .offset(y: fold == .page ? 0 : 18)
                    } else {
                        Text(problem ?? "")
                            .font(.system(size: 17, design: .serif)).foregroundStyle(Theme.inkSoft)
                            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                if let problem, page != nil {
                    Text(problem).font(.system(size: 13)).foregroundStyle(Theme.live)
                }
                shareButton
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 12)
        }
        .onAppear {
            // a plain Task, as the morning report does: .task is cancelled when the sheet re-lays out mid-request
            guard !started else { return }
            started = true
            Task { await load() }
        }
        .sheet(item: $share) { ShareSheet(items: $0.items) }
    }

    @ViewBuilder
    private func shown(_ page: OnePager.Page) -> some View {
        switch page {
        case .html(let html): OnePagerWeb(html: html) { pageReady = true }
        case .pdf(let data): OnePagerPDFView(data: data) { pageReady = true }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Rebuilt from your deck", systemImage: "sparkle")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.accent)
            Text("For \(firstName)")
                .font(.system(size: 34, weight: .bold, design: .serif))
                .foregroundStyle(Theme.inkStrong)
                .lineLimit(1).minimumScaleFactor(0.7)
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(act.isEmpty ? person : act)
                    .font(.system(size: 17, design: .serif)).italic()
                    .foregroundStyle(Theme.inkSoft)
                    .lineLimit(1).minimumScaleFactor(0.8)
                Spacer(minLength: 8)
                if !slides.isEmpty {
                    Text(fold == .folded || fold == .page ? "1 page" : "\(slides.count) slides")
                        .font(.system(size: 13, weight: .semibold).monospacedDigit())
                        .contentTransition(.numericText(countsDown: true))
                        .foregroundStyle(fold == .page ? Theme.paper : Theme.ink)
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .background(Capsule().fill(fold == .page ? Theme.accent : Theme.paperDeep))
                }
            }
        }
    }

    private var shareButton: some View {
        Button { Task { await sharePDF() } } label: {
            HStack(spacing: 8) {
                if making { ProgressView().tint(Theme.paper) } else {
                    Image(systemName: "square.and.arrow.up").font(.system(size: 17, weight: .semibold))
                }
                Text(making ? "Making the PDF…" : "Share as PDF").font(.system(size: 17, weight: .semibold))
            }
            .foregroundStyle(Theme.paper)
            .frame(maxWidth: .infinity)
            .frame(height: 54)
            .background(RoundedRectangle(cornerRadius: 16).fill(page == nil ? Theme.inkSoft : Theme.accent))
        }
        .buttonStyle(.plain)
        .disabled(page == nil || making)
        .opacity(fold == .page || page == nil ? 1 : 0.4)
    }

    private func load() async {
        switch source {
        case .page(let given):
            page = given
        case .server(let base, let path):
            do {
                page = try await OnePager.fetch(base: base, path: path)
            } catch {
                problem = (error as? LocalizedError)?.errorDescription ?? "The page could not be loaded."
            }
        }
        guard page != nil else { return }
        await reveal()
    }

    /// Dealt, a beat to see them, folded, then the page: about a second and a half in all.
    private func reveal() async {
        guard !slides.isEmpty, !reduceMotion else {
            await untilPageReady()
            withAnimation(.easeOut(duration: 0.3)) { fold = .page }
            return
        }
        withAnimation(.spring(duration: 0.55, bounce: 0.2)) { fold = .dealt }
        try? await Task.sleep(for: .milliseconds(700))
        await untilPageReady()
        withAnimation(.spring(duration: 0.5, bounce: 0.05)) { fold = .folded }
        UIImpactFeedbackGenerator(style: .soft).impactOccurred()
        try? await Task.sleep(for: .milliseconds(320))
        withAnimation(.spring(duration: 0.55, bounce: 0.15)) { fold = .page }
    }

    /// The web view says it has drawn the page; two seconds at most, then the page shows anyway.
    private func untilPageReady() async {
        for _ in 0..<40 where !pageReady {
            try? await Task.sleep(for: .milliseconds(50))
        }
        try? await Task.sleep(for: .milliseconds(80))  // its first paint, just after it says it finished
    }

    private func sharePDF() async {
        guard let page, !making else { return }
        making = true
        defer { making = false }
        do {
            let pdf = try await page.pdf()
            let file = FileManager.default.temporaryDirectory
                .appendingPathComponent("Hallwise-" + ServerData.fileName(person.replacingOccurrences(of: " ", with: "-")) + ".pdf")
            try pdf.write(to: file, options: .atomic)
            problem = nil
            share = ShareItems(items: [file])
        } catch {
            problem = "The PDF could not be made: \(error.localizedDescription)"
        }
    }
}

/// The deck as a fan of slide cards, each with its title, that folds into one card where the page will rise.
private struct SlideFan: View {
    let titles: [String]
    let fold: OnePagerView.Fold

    var body: some View {
        GeometryReader { geo in
            let width = min(geo.size.width * 0.84, 360)
            let height = width * 9 / 16
            let count = titles.count
            let step = min(22, max(8, (geo.size.height * 0.55 - height) / CGFloat(max(count - 1, 1))))
            ZStack {
                ForEach(Array(titles.enumerated()), id: \.offset) { i, title in
                    let behind = CGFloat(i)  // slide 1 in front, each next one a step further back
                    SlideCard(number: i == 0 ? 1 : nil, title: title)  // behind the first, only their edges show
                        .frame(width: width, height: height)
                        .scaleEffect(fold == .dealt ? 1 - behind * 0.018 : 1)
                        .rotationEffect(.degrees(fold == .dealt ? (i.isMultiple(of: 2) ? 1 : -1) * (0.4 + Double(i) * 0.25) : 0))
                        .offset(x: fold == .dealt ? (i.isMultiple(of: 2) ? 3 : -3) : 0,
                                y: fold == .dealt ? (CGFloat(count - 1) / 2 - behind) * step
                                    : (fold == .waiting ? 60 : -geo.size.height * 0.2))
                        .scaleEffect(fold == .folded ? 0.6 : 1)
                        .opacity(fold == .dealt ? 1 : 0)
                        .zIndex(Double(count - i))
                        .animation(.spring(duration: 0.5, bounce: 0.12).delay(Double(fold == .dealt ? i : count - 1 - i) * 0.025),
                                   value: fold)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// One slide of the deck: white, 16:9, its number and title, a few lines standing for what was on it.
private struct SlideCard: View {
    let number: Int?
    let title: String

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(number.map(String.init) ?? " ")
                .font(.system(size: 11, weight: .semibold).monospacedDigit()).foregroundStyle(Theme.inkSoft)
            if title.isEmpty {
                Capsule().fill(Color(hex: 0xD3CBB9)).frame(width: 150, height: 9)
            } else {
                Text(title)
                    .font(.system(size: 17, weight: .semibold, design: .serif))
                    .foregroundStyle(Color(hex: 0x1A1613))
                    .lineLimit(2)
            }
            Spacer(minLength: 2)
            ForEach(0..<3, id: \.self) { line in
                Capsule().fill(Color(hex: 0xE2DBC9)).frame(height: 5).frame(maxWidth: line == 2 ? 120 : .infinity)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 12).fill(Color.white))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color(hex: 0xD3CBB9), lineWidth: 0.5))
        .shadow(color: Color.black.opacity(0.08), radius: 8, y: 3)
    }
}

/// The server's side of it: the page a person has, HTML or PDF, bounded like everything else from the server.
enum OnePager {
    static let maxBytes = 10_000_000

    enum Page: Equatable {
        case html(String)
        case pdf(Data)

        /// As a PDF to share: an HTML page laid out as A4; a PDF as it is.
        @MainActor
        func pdf() async throws -> Data {
            switch self {
            case .html(let html): return try await OnePagerPDF.make(html: html)
            case .pdf(let data): return data
            }
        }
    }

    struct Missing: LocalizedError {
        var errorDescription: String? { "No page was rebuilt for this person." }
    }

    /// Where a person's page is, when no event said.
    static func path(recording: String, personKey: String) -> String {
        "/api/recordings/\(ServerData.fileName(recording))/onepager/\(ServerData.fileName(personKey))"
    }

    /// Only a page route on the Hallwise server: the event's path is data, never a way elsewhere.
    static func url(base: String, path: String) -> URL? {
        let parts = path.split(separator: "/", omittingEmptySubsequences: false).map(String.init)
        guard parts.count == 6, parts[0].isEmpty, parts[1] == "api", parts[2] == "recordings", parts[4] == "onepager",
              [parts[3], parts[5]].allSatisfy({ !$0.isEmpty && ServerData.fileName($0) == $0 }),
              let url = URL(string: ServerLink.httpBase(base) + path), url.host() != nil else { return nil }
        return url
    }

    static func fetch(base: String, path: String) async throws -> Page {
        guard let url = url(base: base, path: path) else { throw URLError(.badURL) }
        var request = URLRequest.hallwise(url)
        request.timeoutInterval = 30
        let (data, response) = try await URLSession.shared.data(for: request)
        if ServerAuth.shared.note(response) { throw WrongServerKey() }
        let http = response as? HTTPURLResponse
        if http?.statusCode == 404 { throw Missing() }
        let type = http?.value(forHTTPHeaderField: "Content-Type")?.lowercased() ?? ""
        guard http?.statusCode == 200, data.count <= maxBytes else { throw URLError(.badServerResponse) }
        if type.hasPrefix("application/pdf"), data.starts(with: Data("%PDF".utf8)) { return .pdf(data) }
        if type.hasPrefix("text/html"), let html = String(data: data, encoding: .utf8) { return .html(html) }
        throw URLError(.cannotDecodeContentData)
    }
}

/// A PDF page, read only: fitted to the width, white, one page under the next.
struct OnePagerPDFView: UIViewRepresentable {
    let data: Data
    var onReady: () -> Void = {}

    func makeUIView(context: Context) -> PDFView {
        let view = PDFView()
        view.autoScales = true
        view.displayMode = .singlePageContinuous
        view.displayDirection = .vertical
        view.pageShadowsEnabled = false
        view.backgroundColor = .white
        view.document = PDFDocument(data: data)
        DispatchQueue.main.async { onReady() }
        return view
    }

    func updateUIView(_ view: PDFView, context: Context) {}
}

/// A web view for a page that is only read: no JavaScript, nothing kept, no link followed.
struct OnePagerWeb: UIViewRepresentable {
    let html: String
    var onReady: () -> Void = {}

    static func configuration() -> WKWebViewConfiguration {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = false
        config.websiteDataStore = .nonPersistent()
        config.dataDetectorTypes = []
        return config
    }

    func makeUIView(context: Context) -> WKWebView {
        let web = WKWebView(frame: .zero, configuration: Self.configuration())
        web.navigationDelegate = context.coordinator
        web.isOpaque = true
        web.backgroundColor = .white
        web.scrollView.backgroundColor = .white
        context.coordinator.shown = html
        context.coordinator.ready = onReady
        web.loadHTMLString(html, baseURL: nil)
        return web
    }

    func updateUIView(_ web: WKWebView, context: Context) {
        guard context.coordinator.shown != html else { return }
        context.coordinator.shown = html
        web.loadHTMLString(html, baseURL: nil)
    }

    func makeCoordinator() -> OnlyThePage { OnlyThePage() }
}

/// Lets the page itself load (loadHTMLString is a navigation of type "other") and nothing it links to.
final class OnlyThePage: NSObject, WKNavigationDelegate {
    var shown = ""
    var ready: (() -> Void)?
    private var finished: CheckedContinuation<Void, Error>?

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction) async -> WKNavigationActionPolicy {
        navigationAction.navigationType == .other ? .allow : .cancel
    }

    /// Waits for the page in `web` to finish loading (see OnePagerPDF).
    func load(_ html: String, in web: WKWebView) async throws {
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            finished = c
            web.navigationDelegate = self
            web.loadHTMLString(html, baseURL: nil)
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        finished?.resume()
        finished = nil
        guard let ready else { return }
        // a snapshot comes back once the page has been drawn: the viewer shows it then, never blank
        webView.takeSnapshot(with: nil) { _, _ in ready() }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        finished?.resume(throwing: error)
        finished = nil
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        finished?.resume(throwing: error)
        finished = nil
    }
}

/// The page as a PDF, through createPDF: laid out off screen as a browser prints A4 (794 CSS px wide) and drawn at
/// A4's 595 pt, so it reads as the printed page does rather than at the phone's width; one page, A4 high, or as
/// long as the content when longer.
@MainActor
enum OnePagerPDF {
    static let a4 = CGSize(width: 595, height: 842)
    static let zoom = 595.0 / 794.0  // A4 in points over A4 in CSS px

    static func make(html: String) async throws -> Data {
        // The page's width=device-width is the view's width, whatever the zoom: 794 wide lays it out as print
        // does, and the zoom draws that into A4's top-left 595 pt. A4 high, so the content alone can make it longer.
        let web = WKWebView(frame: CGRect(x: 0, y: 0, width: 794, height: a4.height), configuration: OnePagerWeb.configuration())
        web.backgroundColor = .white
        web.pageZoom = zoom
        let delegate = OnlyThePage()  // the web view holds its delegate weakly; this keeps it for the whole call
        try await delegate.load(html, in: web)
        // where the page's content ends, in CSS px; the scroll view's own size, should the page not say
        let bottom = (try? await web.evaluateJavaScript("Math.ceil(document.body.getBoundingClientRect().bottom)")) as? Double ?? 0
        let height = max(a4.height, bottom > 0 ? CGFloat(bottom * zoom) : web.scrollView.contentSize.height)
        let config = WKPDFConfiguration()
        config.rect = CGRect(x: 0, y: 0, width: a4.width, height: height)
        return try await withCheckedThrowingContinuation { (c: CheckedContinuation<Data, Error>) in
            web.createPDF(configuration: config) { c.resume(with: $0) }
        }
    }

    /// The first page of a PDF as an image `width` points wide, on white: the notification's picture of the page.
    static func image(_ pdf: Data, width: CGFloat) -> UIImage? {
        guard let provider = CGDataProvider(data: pdf as CFData), let document = CGPDFDocument(provider),
              let page = document.page(at: 1) else { return nil }
        let box = page.getBoxRect(.mediaBox)
        let scale = width / max(box.width, 1)
        let size = CGSize(width: width, height: box.height * scale)
        return UIGraphicsImageRenderer(size: size).image { context in
            UIColor.white.setFill()
            context.fill(CGRect(origin: .zero, size: size))
            context.cgContext.translateBy(x: 0, y: size.height)
            context.cgContext.scaleBy(x: scale, y: -scale)
            context.cgContext.drawPDFPage(page)
        }
    }
}

#Preview {
    OnePagerView(
        source: .page(.html("<!doctype html><meta name=viewport content='width=device-width'><h1>Hallwise</h1><p>A name badge that remembers the room.</p>")),
        person: "Margaux Lefèvre", act: "one page, numbers first",
        slides: ["Hallwise", "Great conversation. Gone by morning.", "What is missing", "The insight", "The evening"]
    )
}
