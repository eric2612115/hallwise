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
            out.append("Mark “\(p.what)” done")
            if live.moves[p.id] != nil { out.append("Open the draft for \(live.name(for: p.owedTo))") }
        }
        if let last = live.lines.last(where: { !live.ownerSpeakers.contains($0.speaker) }) {
            out.append("What did \(live.speakerName(last.speaker)) say?")
        }
        if !live.suspects.isEmpty, let w = live.suspects.first { out.append("Remember “\(w.likely)”") }
        out += ["What do I owe?", "Who did I meet?", "What's due tonight?", "Any drafts ready?", "我今晚答應了誰什麼？"]
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
        }
        .sheet(item: $draft) { d in
            MoveSheet(move: d.move, promise: d.promise, live: live, settings: settings)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
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

    /// Two rows of things to say, always there, so a full evening never leaves you staring at an empty box.
    private var suggestionRows: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            LazyHGrid(rows: [GridItem(.fixed(40), spacing: 8), GridItem(.fixed(40), spacing: 8)], alignment: .top, spacing: 8) {
                ForEach(chips, id: \.self) { c in
                    Button { ask(c) } label: {
                        Text(c)
                            .font(.system(size: 15, weight: .medium))
                            .foregroundStyle(suggested.contains(c) ? Theme.paper : Theme.ink)
                            .lineLimit(1)
                            .padding(.horizontal, 14)
                            .frame(height: 40)
                            .background(Capsule().fill(suggested.contains(c) ? Theme.accent : Theme.paperDeep))
                            .overlay(Capsule().stroke(Theme.rule, lineWidth: suggested.contains(c) ? 0 : 0.5))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
        .frame(height: 104)
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

    /// A text field, a send button, and a hold-to-talk mic that is live only while the badge is streaming.
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
        let live = app.link.canAskByVoice
        return Image(systemName: holding ? "waveform" : "mic.fill")
            .font(.system(size: 20, weight: .semibold))
            .foregroundStyle(live ? Theme.paper : Theme.inkSoft)
            .frame(width: 48, height: 48)
            .background(Circle().fill(live ? (holding ? Theme.live : Theme.ink) : Theme.paperDeep))
            .scaleEffect(holding ? 1.12 : 1)
            .animation(.spring(response: 0.25), value: holding)
            .contentShape(Circle())
            .onLongPressGesture(minimumDuration: 60, maximumDistance: 60, pressing: { down in
                guard live else { return }
                if down, !holding {
                    holding = true
                    UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    app.link.askStart()
                } else if !down, holding {
                    holding = false
                    thread.append(Exchange(question: "…", answer: "", actions: [], pending: true))
                    app.link.askEnd(history: history)
                }
            }, perform: {})
            .accessibilityLabel(live ? "Hold to ask by voice" : "Start listening to ask by voice")
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
