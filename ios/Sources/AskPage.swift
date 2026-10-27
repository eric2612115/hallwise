import SwiftUI
import UIKit

/// The page most evenings end on: ask Hallwise what happened, in whatever language you think in.
/// Typed questions go over HTTP; held-to-talk questions ride the badge's own audio stream while listening.
/// Answers can act: a promise gets ticked, a word is remembered, a draft opens.
struct AskPage: View {
    @ObservedObject var app: AppModel
    @ObservedObject var live: LiveModel
    @ObservedObject var settings: BadgeSettings

    struct Exchange: Identifiable {
        let id = UUID()
        var question: String
        var answer: String
        var actions: [String]  // what was done, in words
        var pending = false
    }

    @State private var question = ""
    @State private var thread: [Exchange] = []
    @State private var holding = false
    @State private var draft: DraftRef?
    @State private var suggested: [String] = []  // what the last answer thought you'd say next
    @FocusState private var focused: Bool

    /// Things worth saying right now, from the record: the first open promise, the last person who spoke,
    /// then the standing questions. The answer's own suggestions go first when there are any.
    private var chips: [String] {
        var out: [String] = suggested
        if let p = live.promiseOrder.compactMap({ live.promises[$0] }).first(where: { !live.donePromises.contains($0.id) && $0.owedBy == "owner" }) {
            out.append("Done: \(p.what)")
            if live.moves[p.id] != nil { out.append("Show \(live.name(for: p.owedTo))'s draft") }
        }
        if let last = live.lines.last(where: { !live.ownerSpeakers.contains($0.speaker) }) {
            out.append("What did \(live.speakerName(last.speaker)) say?")
        }
        if let w = live.suspects.first { out.append("Remember \(w.likely)") }
        out += ["What did I promise?", "Who did I meet?", "What's due tonight?", "Any drafts ready?", "我今晚答應了誰什麼？"]
        var seen: Set<String> = []
        return out.filter { seen.insert($0).inserted }
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        if thread.isEmpty { empty }
                        ForEach(thread) { ex in
                            bubble(ex.question, mine: true)
                            if ex.pending {
                                HStack(spacing: 8) {
                                    ProgressView().tint(Theme.inkSoft)
                                    Text("thinking…").font(.system(size: 14, design: .serif)).foregroundStyle(Theme.inkSoft)
                                }
                                .padding(.leading, 6)
                            } else {
                                bubble(ex.answer, mine: false)
                                if !ex.actions.isEmpty {
                                    VStack(alignment: .leading, spacing: 4) {
                                        ForEach(ex.actions, id: \.self) { a in
                                            Label(a, systemImage: "checkmark.circle.fill")
                                                .font(.system(size: 13)).foregroundStyle(Theme.accent)
                                        }
                                    }
                                    .padding(.leading, 6)
                                }
                            }
                        }
                        Color.clear.frame(height: 1).id("end")
                    }
                    .padding(16)
                }
                .onChange(of: thread.count) { _, _ in withAnimation { proxy.scrollTo("end", anchor: .bottom) } }
                .onChange(of: thread.last?.pending ?? false) { _, _ in withAnimation { proxy.scrollTo("end", anchor: .bottom) } }
            }
            .scrollDismissesKeyboard(.interactively)
            suggestionRows
            inputBar
        }
        .onAppear {
            app.link.onAsk = { msg in received(msg) }
            app.voiceAsk.onEvent = { msg in
                switch msg["type"] as? String {
                case "partial", "question":
                    if let i = thread.lastIndex(where: { $0.pending }), let t = msg["text"] as? String, !t.isEmpty {
                        thread[i].question = t
                    }
                case "answer":
                    received(msg)
                default:
                    break
                }
            }
        }
        .sheet(item: $draft) { d in
            MoveSheet(move: d.move, promise: d.promise, live: live, settings: settings)
                .closableSheet()
        }
    }

    private var empty: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Ask about tonight")
                .font(.system(size: 24, weight: .bold, design: .serif))
                .foregroundStyle(Theme.ink)
            Text("Who you met, what you owe, what someone said, which drafts are ready. Say a promise is done and it gets ticked; say a name and it is remembered. Tap a chip below when you don't know what to ask.")
                .font(.system(size: 15, design: .serif))
                .foregroundStyle(Theme.inkSoft)
        }
        .padding(.top, 8)
    }

    /// Three things to say, always there, one row: people type or talk, they don't scroll a shelf.
    private var suggestionRows: some View {
        HStack(spacing: 8) {
            ForEach(Array(chips.prefix(3)), id: \.self) { c in
                Button { ask(c) } label: {
                    Text(c)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(suggested.contains(c) ? Theme.paper : Theme.ink)
                        .multilineTextAlignment(.center)
                        .lineLimit(2)
                        .minimumScaleFactor(0.85)
                        .padding(.horizontal, 10)
                        .frame(maxWidth: .infinity)
                        .frame(height: 48)
                        .background(RoundedRectangle(cornerRadius: 14).fill(suggested.contains(c) ? Theme.accent : Theme.paperDeep))
                        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.rule, lineWidth: suggested.contains(c) ? 0 : 0.5))
                }
                .buttonStyle(.plain)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
    }

    private func bubble(_ text: String, mine: Bool) -> some View {
        HStack {
            if mine { Spacer(minLength: 40) }
            Text(text)
                .font(.system(size: mine ? 16 : 17, design: mine ? .default : .serif))
                .foregroundStyle(mine ? Theme.paper : Theme.ink)
                .textSelection(.enabled)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(RoundedRectangle(cornerRadius: 16).fill(mine ? Theme.ink : Theme.paperDeep))
                .overlay(RoundedRectangle(cornerRadius: 16).stroke(mine ? .clear : Theme.rule, lineWidth: 0.5))
            if !mine { Spacer(minLength: 40) }
        }
    }

    /// A text field, a send button, and a hold-to-talk mic: through the badge's stream while listening,
    /// through the phone's own microphone once it has stopped.
    private var inputBar: some View {
        HStack(spacing: 10) {
            TextField(holding ? "Listening… release to ask" : "Ask about tonight…", text: $question, axis: .vertical)
                .font(.system(size: 17))
                .foregroundStyle(Theme.ink)
                .lineLimit(1...4)
                .focused($focused)
                .submitLabel(.send)
                .onSubmit { ask(question) }
                .padding(.horizontal, 14)
                .frame(minHeight: 48)
                .background(RoundedRectangle(cornerRadius: 14).fill(Theme.paperDeep))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(holding ? Theme.accent : Theme.rule, lineWidth: holding ? 1.5 : 0.5))
            if question.trimmingCharacters(in: .whitespaces).isEmpty {
                mic
            } else {
                Button { ask(question) } label: {
                    Image(systemName: "arrow.up")
                        .font(.system(size: 20, weight: .bold))
                        .foregroundStyle(Theme.paper)
                        .frame(width: 48, height: 48)
                        .background(Circle().fill(Theme.accent))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Theme.paper.opacity(0.92))
        .overlay(alignment: .top) { Rectangle().fill(Theme.rule).frame(height: 0.5) }
    }

    private var mic: some View {
        Image(systemName: holding ? "waveform" : "mic.fill")
            .font(.system(size: 20, weight: .semibold))
            .foregroundStyle(Theme.paper)
            .frame(width: 48, height: 48)
            .background(Circle().fill(holding ? Theme.live : Theme.ink))
            .scaleEffect(holding ? 1.12 : 1)
            .animation(.spring(response: 0.25), value: holding)
            .contentShape(Circle())
            .onLongPressGesture(minimumDuration: 60, maximumDistance: 60, pressing: { down in
                if down, !holding {
                    holding = true
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    beginVoice()
                } else if !down, holding {
                    holding = false
                    endVoice()
                }
            }, perform: {})
            .accessibilityLabel("Hold to ask by voice")
    }

    private func beginVoice() {
        if app.link.canAskByVoice {
            app.link.askStart()
            return
        }
        let history = self.history
        Task { @MainActor in
            var found = app.link.recordingID
            if found == nil { found = await app.link.latestRecording(base: settings.serverURL) }
            guard let rid = found else {
                let why = ServerAuth.shared.rejected ? ServerAuth.wrongKey + "." : "No recording to ask about yet."
                thread.append(Exchange(question: "…", answer: why, actions: []))
                holding = false
                return
            }
            do {
                try app.voiceAsk.start(base: settings.serverURL, recording: rid, keywords: settings.keywordList, history: history)
            } catch {
                thread.append(Exchange(question: "…", answer: "Microphone: \(error.localizedDescription)", actions: []))
                holding = false
            }
        }
    }

    private func endVoice() {
        thread.append(Exchange(question: "…", answer: "", actions: [], pending: true))
        if app.link.canAskByVoice {
            app.link.askEnd(history: history)
        } else {
            app.voiceAsk.stop()
        }
    }

    private var history: [[String: String]] {
        thread.filter { !$0.pending }.suffix(6).map { ["q": $0.question, "a": $0.answer] }
    }

    private func ask(_ text: String) {
        let q = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return }
        question = ""
        focused = false
        let history = self.history
        thread.append(Exchange(question: q, answer: "", actions: [], pending: true))
        Task {
            do {
                let result = try await app.link.ask(
                    base: settings.serverURL, recording: app.link.recordingID, question: q,
                    history: history, keywords: settings.keywordList
                )
                received(result)
            } catch {
                received(["answer": "", "error": error.localizedDescription])
            }
        }
    }

    /// An answer, typed or spoken: fill the pending exchange and carry out what it asked for.
    private func received(_ msg: [String: Any]) {
        guard let i = thread.lastIndex(where: { $0.pending }) else { return }
        if let heard = msg["question"] as? String, !heard.isEmpty { thread[i].question = heard }
        var answer = msg["answer"] as? String ?? ""
        if answer.isEmpty, let err = msg["error"] as? String { answer = "Hallwise could not answer: \(err)" }
        thread[i].answer = answer
        thread[i].actions = (msg["actions"] as? [[String: Any]] ?? []).compactMap(apply)
        thread[i].pending = false
        suggested = (msg["suggestions"] as? [String] ?? []).filter { !$0.isEmpty }
    }

    private func apply(_ a: [String: Any]) -> String? {
        switch a["type"] as? String {
        case "mark_done":
            guard let key = a["promise_key"] as? String, let p = live.promises[key] else { return nil }
            live.markDone(key)
            return "Ticked off: \(p.what)"
        case "add_word":
            guard let w = a["word"] as? String, !w.isEmpty else { return nil }
            settings.remember(w)
            return "Remembered “\(w)”"
        case "open_draft":
            guard let key = a["promise_key"] as? String, let m = live.moves[key], let p = live.promises[key] else { return nil }
            draft = DraftRef(id: key, move: m, promise: p)
            return "Opened the draft for \(live.name(for: m.personKey))"
        default:
            return nil
        }
    }
}
