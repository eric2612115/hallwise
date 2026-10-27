import SwiftUI
import UserNotifications

/// The morning report, as the server builds it after a recording: who to write to today and why, the
/// introductions still owed, what public sources say about the people met, and what is due.
struct MorningReport {
    struct Person {
        let key: String
        let indexKey: String
        let name: String
        let company: String
        let language: String
        let tonight: Bool
        init(_ d: [String: Any]) {
            key = d["key"] as? String ?? ""
            indexKey = d["index_key"] as? String ?? key
            name = d["name"] as? String ?? key
            company = d["company"] as? String ?? ""
            language = d["language"] as? String ?? ""
            tonight = d["tonight"] as? Bool ?? false
        }
    }

    struct Check {
        let status: String  // matched, partial, no_public_record, unchecked
        let note: String
        let sources: [String]
    }

    struct Row: Identifiable {
        let id: String
        let person: Person
        let hook: LiveModel.Hook?
        let move: LiveModel.Move?        // the recording's follow-up for this promise
        let promise: LiveModel.Promise?
        let draftLanguage: String        // else the hook's own draft
        let draftBody: String
        let draftEnglish: String
        let check: Check?
        let earlier: Bool
    }

    struct Finding: Identifiable {
        var id: String { kind + text }
        let kind: String
        let text: String
        let source: String
    }

    struct Checked: Identifiable {
        let id: String
        let name: String
        let company: String
        let status: String
        let findings: [Finding]
        let searched: Bool
    }

    struct Due: Identifiable {
        var id: String { promiseKey }
        let promiseKey: String
        let person: String
        let what: String
        let due: String
        let remindAt: String
        let nudge: String
        let overdue: Bool
    }

    let recording: String
    let event: String
    let venue: String
    let day: String
    let generatedAt: Double
    let people: Int
    let followups: Int
    let languages: [String]
    let rows: [Row]
    let introductions: [LiveModel.Hook]
    let checked: [Checked]
    let unchecked: [(name: String, reason: String)]
    let due: [Due]
    let costUSD: Double
    let lookups: Int

    init?(_ d: [String: Any]) {
        guard let rid = d["recording"] as? String else { return nil }
        recording = rid
        event = d["event"] as? String ?? ""
        venue = d["venue"] as? String ?? ""
        day = d["day"] as? String ?? ""
        generatedAt = d["generated_at"] as? Double ?? 0
        let summary = d["summary"] as? [String: Any] ?? [:]
        people = summary["people"] as? Int ?? 0
        followups = summary["followups"] as? Int ?? 0
        languages = summary["languages"] as? [String] ?? []
        rows = (d["reach_out"] as? [[String: Any]] ?? []).enumerated().map { i, r in
            let person = Person(r["person"] as? [String: Any] ?? [:])
            let f = r["followup"] as? [String: Any] ?? [:]
            let move = (f["move"] as? [String: Any]).flatMap(LiveModel.Move.init)
            let q = f["promise"] as? [String: Any]
            let promise = move.map { m in
                LiveModel.Promise(id: m.promiseKey, what: q?["what"] as? String ?? "", due: q?["due"] as? String ?? "",
                                  replaces: q?["replaces"] as? String ?? "", owedTo: q?["owed_to"] as? String ?? person.key,
                                  owedBy: q?["owed_by"] as? String ?? "owner")
            }
            let c = r["check"] as? [String: Any]
            return Row(
                id: "\(i)-\(person.key)", person: person,
                hook: (r["hook"] as? [String: Any]).map(LiveModel.Hook.init),
                move: move, promise: promise,
                draftLanguage: f["language"] as? String ?? "", draftBody: f["body"] as? String ?? "",
                draftEnglish: f["body_english"] as? String ?? "",
                check: c.map { Check(status: $0["status"] as? String ?? "", note: $0["note"] as? String ?? "", sources: $0["sources"] as? [String] ?? []) },
                earlier: r["earlier"] as? Bool ?? false
            )
        }
        introductions = (d["introductions"] as? [[String: Any]] ?? []).map(LiveModel.Hook.init)
        checked = (d["checked"] as? [[String: Any]] ?? []).map { c in
            Checked(id: c["key"] as? String ?? UUID().uuidString, name: c["name"] as? String ?? "", company: c["company"] as? String ?? "",
                    status: c["status"] as? String ?? "no_public_record",
                    findings: (c["findings"] as? [[String: Any]] ?? []).map {
                        Finding(kind: $0["kind"] as? String ?? "", text: $0["text"] as? String ?? "", source: $0["source"] as? String ?? "")
                    },
                    searched: c["searched"] as? Bool ?? true)
        }
        unchecked = (d["unchecked"] as? [[String: Any]] ?? []).map { ($0["name"] as? String ?? "", $0["reason"] as? String ?? "") }
        due = (d["due_today"] as? [[String: Any]] ?? []).map { x in
            Due(promiseKey: x["promise_key"] as? String ?? "", person: (x["person"] as? [String: Any])?["name"] as? String ?? "",
                what: x["what"] as? String ?? "", due: x["due"] as? String ?? "", remindAt: x["remind_at"] as? String ?? "",
                nudge: x["nudge"] as? String ?? "", overdue: x["overdue"] as? Bool ?? false)
        }
        let cost = d["cost"] as? [String: Any] ?? [:]
        costUSD = cost["usd"] as? Double ?? 0
        lookups = cost["research_requests"] as? Int ?? 0
    }
}

/// Fetches, and on request builds, the morning report.
@MainActor
final class ReportStore: ObservableObject {
    @Published var report: MorningReport?
    @Published var raw: [String: Any]?
    @Published var state = ""
    @Published var missing = false  // no report for this recording yet

    /// One recording's report, or the newest one.
    func load(base: String, recording: String?) async {
        state = "Loading…"
        missing = false
        let http = ServerLink.httpBase(base)
        var got = await Self.get(http + "/api/report/" + (recording ?? "latest"))
        if got == nil, recording != nil, !ServerAuth.shared.rejected {
            missing = true
            got = await Self.get(http + "/api/report/latest")
        }
        apply(got)
        if got == nil, ServerAuth.shared.rejected { state = ServerAuth.wrongKey }
    }

    /// Research, hooks, the report: about half a minute on the server; within the hour it answers from its store.
    func build(base: String, recording: String, force: Bool = false) async {
        state = "Writing the report…"
        guard var c = URLComponents(string: ServerLink.httpBase(base) + "/api/report/run") else { return }
        c.queryItems = [URLQueryItem(name: "recording", value: recording)] + (force ? [URLQueryItem(name: "force", value: "1")] : [])
        guard let url = c.url else { return }
        var req = URLRequest.hallwise(url, method: "POST")
        req.timeoutInterval = 240
        let answer = try? await URLSession.shared.data(for: req)
        if ServerAuth.shared.note(answer?.1) {
            state = ServerAuth.wrongKey
            return
        }
        guard let (data, response) = answer,
              (response as? HTTPURLResponse)?.statusCode == 200,
              let d = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            state = "The server could not write the report"
            return
        }
        missing = false
        apply(d)
    }

    private func apply(_ d: [String: Any]?) {
        raw = d
        report = d.flatMap(MorningReport.init)
        state = report == nil ? (d == nil ? "No report yet" : "The report could not be read") : ""
    }

    /// A GET to the server with the key. A 401 marks the key as turned down (ServerAuth) and reads as nil.
    static func get(_ url: String) async -> [String: Any]? {
        guard let u = URL(string: url), u.host() != nil,
              let (data, response) = try? await URLSession.shared.data(for: .hallwise(u)),
              !ServerAuth.shared.note(response),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    }
}

/// "Your morning report is ready": at eight the morning after a recording stops, or in ten seconds from Debug.
enum MorningNotice {
    static let id = "morning-report"

    /// The next 08:00: this morning when it is still early, else tomorrow.
    static func nextMorning(after now: Date = Date()) -> Date {
        let cal = Calendar.current
        let today8 = cal.date(bySettingHour: 8, minute: 0, second: 0, of: now) ?? now
        return cal.component(.hour, from: now) < 5 ? today8 : cal.date(byAdding: .day, value: 1, to: today8) ?? today8
    }

    static func scheduleMorning(recording: String) {
        let parts = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: nextMorning())
        add(UNCalendarNotificationTrigger(dateMatching: parts, repeats: false), recording: recording)
    }

    static func schedule(in seconds: TimeInterval, recording: String) {
        add(UNTimeIntervalNotificationTrigger(timeInterval: seconds, repeats: false), recording: recording)
    }

    private static func add(_ trigger: UNNotificationTrigger, recording: String) {
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound, .badge]) { ok, _ in
            guard ok else { return }
            let content = UNMutableNotificationContent()
            content.title = "Your morning report is ready"
            content.body = "Every follow-up written, with a reason to write."
            content.sound = .default
            content.userInfo = ["report": recording]
            center.add(UNNotificationRequest(identifier: id, content: content, trigger: trigger))
        }
    }
}

/// Shows Hallwise's notifications while the app is open too, and opens the morning report when its
/// notification is tapped.
final class NotificationRouter: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationRouter()
    var onReport: ((String) -> Void)?

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler done: @escaping (UNNotificationPresentationOptions) -> Void) {
        done([.banner, .list, .sound])
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler done: @escaping () -> Void) {
        if let rid = response.notification.request.content.userInfo["report"] as? String {
            DispatchQueue.main.async { self.onReport?(rid) }
        }
        done()
    }
}

/// A draft the report opens in the usual draft sheet.
struct ReportDraft: Identifiable {
    let id: String
    let move: LiveModel.Move
    let promise: LiveModel.Promise
    let person: String
    let hook: LiveModel.Hook?
}

/// The morning report on paper: reach out today, introductions to make, checked, due today.
struct MorningReportView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    let recording: String?
    @StateObject private var store = ReportStore()
    @State private var draft: ReportDraft?
    @State private var started = false

    var body: some View {
        ZStack {
            PaperBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    header
                    if let r = store.report {
                        reachOut(r)
                        introductions(r)
                        checked(r)
                        dueToday(r)
                        footer(r)
                    } else {
                        Text(store.state.isEmpty ? "Loading…" : store.state)
                            .font(.system(size: 16, design: .serif)).foregroundStyle(Theme.inkSoft)
                        if let rid = recording, !rid.isEmpty, !store.state.hasPrefix("Writing") {
                            buildButton("Write it now", rid: rid, force: false)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 20)
                .padding(.top, 8)
                .padding(.bottom, 40)
            }
        }
        .preferredColorScheme(settings.colorScheme)
        .onAppear {
            // a plain Task: SwiftUI's .task is cancelled when the presentation re-lays out mid-request
            guard !started else { return }
            started = true
            Task { await store.load(base: settings.serverURL, recording: recording?.isEmpty == false ? recording : nil) }
        }
        .sheet(item: $draft) { d in
            MoveSheet(move: d.move, promise: d.promise, live: live, settings: settings, personName: d.person, hook: d.hook)
                .closableSheet()
        }
    }

    // MARK: header

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Morning report")
                .font(.system(size: 30, weight: .bold, design: .serif))
                .foregroundStyle(Theme.ink)
            if let r = store.report {
                Text(subtitle(r)).font(.system(size: 15)).foregroundStyle(Theme.inkSoft)
                Text(summary(r))
                    .font(.system(size: 18, design: .serif))
                    .foregroundStyle(Theme.ink)
                    .padding(.top, 4)
                if store.missing, let rid = recording {
                    HStack(spacing: 8) {
                        Text("This is an earlier one; tonight's is not written yet.")
                            .font(.system(size: 13)).foregroundStyle(Theme.inkSoft)
                        Spacer()
                        buildButton("Write it", rid: rid, force: false)
                    }
                }
            }
        }
    }

    private func subtitle(_ r: MorningReport) -> String {
        let day = Self.dayFormatter.date(from: r.day).map { $0.formatted(.dateTime.weekday(.wide).month().day()) } ?? r.day
        return [day, r.event.isEmpty ? "" : "after \(r.event)"].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    private func summary(_ r: MorningReport) -> String {
        var parts = ["\(spelled(r.people).capitalized) \(r.people == 1 ? "person" : "people") last night"]
        var ready = "\(spelled(r.followups)) follow-up\(r.followups == 1 ? "" : "s") ready"
        if let lang = r.languages.first {
            let who = r.rows.first { $0.move?.language == lang }?.person.name.split(separator: " ").first.map(String.init)
            ready += who.map { ", \($0)'s in \(lang)" } ?? ", one in \(lang)"
        }
        parts.append(ready)
        if !r.introductions.isEmpty {
            parts.append("\(spelled(r.introductions.count)) introduction\(r.introductions.count == 1 ? "" : "s") you owe")
        }
        return parts.joined(separator: "; ") + "."
    }

    private func spelled(_ n: Int) -> String {
        let words = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
        return words.indices.contains(n) ? words[n] : "\(n)"
    }

    static let dayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    // MARK: sections

    private func section<Content: View>(_ title: String, _ subtitle: String? = nil, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 19, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                if let subtitle { Text(subtitle).font(.system(size: 13)).foregroundStyle(Theme.inkSoft) }
            }
            VStack(spacing: 0) { content() }
                .background(RoundedRectangle(cornerRadius: 14).fill(Theme.paperDeep))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.rule, lineWidth: 0.5))
        }
    }

    @ViewBuilder
    private func reachOut(_ r: MorningReport) -> some View {
        let tonight = r.rows.filter { !$0.earlier }
        let earlier = r.rows.filter { $0.earlier }
        if !tonight.isEmpty {
            section("Reach out today", "Written, in their language, with the reason to write") {
                ForEach(Array(tonight.enumerated()), id: \.element.id) { i, row in
                    reachRow(row, last: i == tonight.count - 1)
                }
            }
        }
        if !earlier.isEmpty {
            section("Still open from earlier evenings") {
                ForEach(Array(earlier.enumerated()), id: \.element.id) { i, row in
                    reachRow(row, last: i == earlier.count - 1)
                }
            }
        }
    }

    private func reachRow(_ row: MorningReport.Row, last: Bool) -> some View {
        Button { open(row) } label: {
            HStack(alignment: .top, spacing: 12) {
                ReportFace(live: live, settings: settings, key: row.person.key, indexKey: row.person.indexKey, name: row.person.name,
                           company: row.person.company)
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(row.person.name).font(.system(size: 17, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                        if let lang = row.move?.language ?? (row.draftLanguage.isEmpty ? nil : row.draftLanguage), lang != "English" {
                            Tag(text: lang)
                        }
                    }
                    if let hook = row.hook {
                        Text(hook.tag).font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.accent)
                        Text(hook.reason).font(.system(size: 13)).foregroundStyle(Theme.inkSoft).fixedSize(horizontal: false, vertical: true)
                    }
                    if let p = row.promise {
                        Text(p.what + (p.due.isEmpty ? "" : " · \(p.due)")).font(.system(size: 14)).foregroundStyle(Theme.ink)
                    }
                    if let c = row.check, c.status == "no_public_record" || c.status == "partial" {
                        Label(c.note, systemImage: "exclamationmark.magnifyingglass")
                            .font(.system(size: 12, weight: .medium)).foregroundStyle(Theme.live)
                    }
                }
                Spacer(minLength: 4)
                VStack(spacing: 3) {
                    Image(systemName: row.move?.kind == "calendar" ? "calendar.badge.plus" : "paperplane.fill")
                        .font(.system(size: 17, weight: .semibold))
                    Text(row.move?.kind == "calendar" ? "Invite" : "Draft").font(.system(size: 11, weight: .semibold))
                }
                .foregroundStyle(Theme.paper)
                .frame(width: 54, height: 50)
                .background(RoundedRectangle(cornerRadius: 12).fill(Theme.accent))
            }
            .padding(14)
            .contentShape(Rectangle())
            .overlay(alignment: .bottom) { if !last { Rectangle().fill(Theme.rule).frame(height: 0.5).padding(.leading, 14) } }
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func introductions(_ r: MorningReport) -> some View {
        if !r.introductions.isEmpty {
            section("Introductions to make", "Promised, and not done yet") {
                ForEach(Array(r.introductions.enumerated()), id: \.element.id) { i, h in
                    Button { openIntro(h) } label: {
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: "person.line.dotted.person.fill")
                                .font(.system(size: 18)).foregroundStyle(Theme.paper)
                                .frame(width: 40, height: 40).background(Circle().fill(Theme.ink))
                            VStack(alignment: .leading, spacing: 4) {
                                Text(h.names.joined(separator: " and ")).font(.system(size: 17, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                                Text(h.reason).font(.system(size: 13)).foregroundStyle(Theme.inkSoft).fixedSize(horizontal: false, vertical: true)
                                evidenceLines(h, limit: 2)
                            }
                            Spacer(minLength: 4)
                            if !h.draft.isEmpty {
                                Image(systemName: "paperplane.fill").font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.accent)
                                    .frame(width: 44, height: 44)
                            }
                        }
                        .padding(14)
                        .contentShape(Rectangle())
                        .overlay(alignment: .bottom) { if i < r.introductions.count - 1 { Rectangle().fill(Theme.rule).frame(height: 0.5).padding(.leading, 14) } }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func evidenceLines(_ h: LiveModel.Hook, limit: Int) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            ForEach(Array(h.evidence.prefix(limit).enumerated()), id: \.offset) { _, e in
                Text(([e.event, e.day].filter { !$0.isEmpty }.joined(separator: " · ")) + (e.speaker.isEmpty ? "" : " · \(e.speaker)") + ": “\(e.quote)”")
                    .font(.system(size: 12, design: .serif)).italic().foregroundStyle(Theme.inkSoft).lineLimit(2)
            }
        }
    }

    @ViewBuilder
    private func checked(_ r: MorningReport) -> some View {
        if !r.checked.isEmpty || !r.unchecked.isEmpty {
            section("Checked", "What public sources say, with the page") {
                ForEach(Array(r.checked.enumerated()), id: \.element.id) { i, c in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(alignment: .firstTextBaseline) {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(c.name).font(.system(size: 16, weight: .semibold, design: .serif)).foregroundStyle(Theme.ink)
                                if !c.company.isEmpty { Text(c.company).font(.system(size: 13)).foregroundStyle(Theme.inkSoft) }
                            }
                            Spacer()
                            statusPill(c.status)
                        }
                        if c.findings.isEmpty {
                            Text(c.searched ? "No public record found. Confirm before sending anything that matters." : "No search ran.")
                                .font(.system(size: 13)).foregroundStyle(Theme.inkSoft)
                        }
                        ForEach(c.findings) { f in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(f.text).font(.system(size: 14)).foregroundStyle(Theme.ink)
                                if let url = ServerData.webURL(f.source) {
                                    Link(destination: url) {
                                        Label(url.host() ?? f.source, systemImage: "link").font(.system(size: 12, weight: .medium))
                                    }
                                    .foregroundStyle(Theme.accent)
                                }
                            }
                        }
                    }
                    .padding(14)
                    .overlay(alignment: .bottom) { if i < r.checked.count - 1 || !r.unchecked.isEmpty { Rectangle().fill(Theme.rule).frame(height: 0.5).padding(.leading, 14) } }
                }
                ForEach(Array(r.unchecked.enumerated()), id: \.offset) { _, u in
                    HStack {
                        Text(u.name).font(.system(size: 15, design: .serif)).foregroundStyle(Theme.ink)
                        Spacer()
                        Text("not checked · \(u.reason)").font(.system(size: 12)).foregroundStyle(Theme.inkSoft)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 10)
                }
            }
        }
    }

    private func statusPill(_ status: String) -> some View {
        let (text, fill): (String, Color) = {
            switch status {
            case "matched": return ("matches", Theme.accent)
            case "partial": return ("company only", Theme.people[3])
            default: return ("no public record", Theme.live)
            }
        }()
        return Text(text)
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(Theme.paper)
            .padding(.horizontal, 9).frame(height: 22)
            .background(Capsule().fill(fill))
    }

    @ViewBuilder
    private func dueToday(_ r: MorningReport) -> some View {
        if !r.due.isEmpty {
            section("Due today") {
                ForEach(Array(r.due.enumerated()), id: \.element.id) { i, d in
                    HStack(spacing: 12) {
                        Image(systemName: d.overdue ? "exclamationmark.circle.fill" : "clock")
                            .font(.system(size: 18)).foregroundStyle(d.overdue ? Theme.live : Theme.accent)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(d.nudge.isEmpty ? "\(d.what) for \(d.person)" : d.nudge)
                                .font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.ink)
                            Text([d.person, d.due, time(d.remindAt), d.overdue ? "overdue" : ""].filter { !$0.isEmpty }.joined(separator: " · "))
                                .font(.system(size: 13)).foregroundStyle(Theme.inkSoft)
                        }
                        Spacer()
                    }
                    .padding(14)
                    .overlay(alignment: .bottom) { if i < r.due.count - 1 { Rectangle().fill(Theme.rule).frame(height: 0.5).padding(.leading, 14) } }
                }
            }
        }
    }

    private func time(_ iso: String) -> String {
        guard let d = OwnerCalendar.parse(iso) else { return "" }
        return d.formatted(date: .omitted, time: .shortened)
    }

    private func footer(_ r: MorningReport) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Written \(Date(timeIntervalSince1970: r.generatedAt).formatted(date: .abbreviated, time: .shortened)) from what the badge heard"
                 + (r.lookups > 0 ? " · \(r.lookups) public lookups" : "") + String(format: " · $%.2f", r.costUSD))
                .font(.system(size: 12)).foregroundStyle(Theme.inkSoft)
            buildButton("Write it again", rid: r.recording, force: true)
        }
    }

    private func buildButton(_ title: String, rid: String, force: Bool) -> some View {
        Button {
            Task { await store.build(base: settings.serverURL, recording: rid, force: force) }
        } label: {
            HStack(spacing: 6) {
                if store.state.hasPrefix("Writing") { ProgressView().tint(Theme.ink) } else { Image(systemName: "arrow.clockwise") }
                Text(store.state.hasPrefix("Writing") ? "Writing…" : title)
            }
            .font(.system(size: 14, weight: .semibold))
            .foregroundStyle(Theme.ink)
            .padding(.horizontal, 14).frame(height: 40)
            .overlay(Capsule().stroke(Theme.rule, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(store.state.hasPrefix("Writing"))
    }

    // MARK: drafts

    private func open(_ row: MorningReport.Row) {
        if let m = row.move, let p = row.promise {
            draft = ReportDraft(id: row.id, move: m, promise: p, person: row.person.name, hook: row.hook)
        } else if !row.draftBody.isEmpty, let hook = row.hook {
            draft = hookDraft(id: row.id, hook: hook, to: row.person.name, key: row.person.key, kind: "message")
        }
    }

    private func openIntro(_ h: LiveModel.Hook) {
        guard !h.draft.isEmpty else { return }
        draft = hookDraft(id: "intro:" + h.id, hook: h, to: h.names.joined(separator: " and "), key: "", kind: "email")
    }

    private func hookDraft(id: String, hook: LiveModel.Hook, to person: String, key: String, kind: String) -> ReportDraft {
        let move = LiveModel.Move(promiseKey: "hook:" + id, personKey: key, kind: kind, language: hook.language,
                                  subject: "", body: hook.draft, bodyEnglish: hook.draftEnglish, when: "", durationMinutes: 30,
                                  attach: "", why: "", remindAt: "", nudge: "")
        let promise = LiveModel.Promise(id: "hook:" + id, what: hook.title, due: "", replaces: "", owedTo: key, owedBy: "owner")
        return ReportDraft(id: id, move: move, promise: promise, person: person, hook: hook)
    }
}

/// The person's face in the report: the one on the phone, else the one kept on the server, else their colour.
struct ReportFace: View {
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings
    let key: String
    let indexKey: String
    let name: String
    var company: String = ""
    @State private var remote: UIImage?

    var body: some View {
        Group {
            if let face = live.photos[key] ?? remote {
                Image(uiImage: face).resizable().scaledToFill()
            } else {
                Text(String(name.prefix(1)))
                    .font(.system(size: 17, weight: .semibold, design: .serif))
                    .foregroundStyle(Theme.paper)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(live.people[key] != nil ? live.color(for: key) : Theme.inkSoft)
            }
        }
        .frame(width: 40, height: 40)
        .clipShape(Circle())
        .onAppear {
            guard live.photos[key] == nil, remote == nil else { return }
            Task { remote = await Faces.fetch(base: settings.serverURL, key: indexKey, name: name, company: company) }
        }
    }
}
