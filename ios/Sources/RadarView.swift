import SwiftUI

/// The room around the badge, seen from above, ahead = up. Each person is a coloured dot where their voice
/// comes from, close voices on the inner ring, far ones at the edge, lit while they talk. Positions are held
/// in room coordinates by the server, so when the wearer turns the whole ring rotates and nobody drifts.
struct RadarView: View {
    @ObservedObject var live: LiveModel
    let offset: Double  // the badge's forward calibration, degrees
    let ownerInitial: String
    let listening: Bool
    var onTap: ((LiveModel.Person) -> Void)? = nil

    @State private var breathe = false
    @State private var rippleTurn = -1

    struct Blip: Identifiable {
        let id: String
        let person: LiveModel.Person?
        let label: String
        let color: Color
        let bearing: Double  // degrees, 0 = ahead, positive = left
        let distance: Double // 0 = close, 1 = far
        let active: Bool     // talking now
        let recent: Bool     // spoke within the last while
        var known = false    // met at an earlier event
        var tag = ""         // a reason to reach out, under the name ("Chloé's colleague · Oct 23")
        var radius: CGFloat = 0
        var drawn: Double = 0  // bearing after neighbours are spread apart
        var named: Bool { person != nil }

        /// Where the name goes: away from the centre, so labels fan outward and never sit under a neighbour.
        enum Side { case above, below, left, right }
        var side: Side {
            let a = drawn
            if abs(a) < 40 { return .above }
            if abs(a) > 140 { return .below }
            return a > 0 ? .left : .right
        }
    }

    var body: some View {
        GeometryReader { geo in
            let size = min(geo.size.width, geo.size.height)
            let c = CGPoint(x: geo.size.width / 2, y: geo.size.height / 2)
            let r = size * 0.42
            ZStack {
                Canvas { ctx, _ in
                    let outer = Path(ellipseIn: CGRect(x: c.x - r, y: c.y - r, width: 2 * r, height: 2 * r))
                    ctx.stroke(outer, with: .color(Theme.inkSoft.opacity(0.45)), lineWidth: 1.5)
                    let k = 0.55
                    let inner = Path(ellipseIn: CGRect(x: c.x - r * k, y: c.y - r * k, width: 2 * r * k, height: 2 * r * k))
                    ctx.stroke(inner, with: .color(Theme.inkSoft.opacity(0.30)), style: StrokeStyle(lineWidth: 1, dash: [3, 5]))
                    // the badge's field of view, ahead
                    var wedge = Path()
                    wedge.move(to: c)
                    wedge.addArc(center: c, radius: r + 14, startAngle: .degrees(-90 - 28), endAngle: .degrees(-90 + 28), clockwise: false)
                    wedge.closeSubpath()
                    let top = breathe && listening ? 0.16 : 0.10
                    ctx.fill(wedge, with: .radialGradient(
                        Gradient(colors: [Theme.accent.opacity(top), Theme.accent.opacity(0.03)]),
                        center: c, startRadius: 0, endRadius: r + 14))
                    ctx.stroke(wedge, with: .color(Theme.accent.opacity(0.30)), lineWidth: 1)
                    var ahead = Path()
                    ahead.move(to: c)
                    ahead.addLine(to: CGPoint(x: c.x, y: c.y - r * 0.3))
                    ctx.stroke(ahead, with: .color(Theme.inkSoft), style: StrokeStyle(lineWidth: 2, lineCap: .round))
                }
                // the wearer, mirroring the badge's monogram
                VStack(spacing: 3) {
                    Text(ownerInitial)
                        .font(.system(size: 11, weight: .semibold, design: .serif))
                        .foregroundStyle(Theme.paper)
                        .frame(width: 22, height: 22)
                        .background(Circle().fill(Theme.ink))
                    Text("you").font(.system(size: 12)).foregroundStyle(Theme.inkSoft)
                }
                .position(x: c.x, y: c.y + 8)

                let shown = laidOut(r: r)
                let points = Dictionary(uniqueKeysWithValues: shown.map { b -> (String, CGPoint) in
                    let a = b.drawn * .pi / 180
                    return (b.id, CGPoint(x: c.x - b.radius * sin(a), y: c.y - b.radius * cos(a)))
                })
                let labels = Self.placeLabels(
                    shown.filter(\.named).map { b in
                        LabelItem(id: b.id, dot: points[b.id] ?? c, size: Self.labelSize(b), side: b.side)
                    },
                    dots: shown.map { (id: $0.id, point: points[$0.id] ?? c) },
                    bounds: CGRect(origin: .zero, size: geo.size)
                )
                ForEach(shown) { b in
                    let p = points[b.id] ?? c
                    blipView(b)
                        .position(x: p.x, y: p.y)
                        .transition(.scale(scale: 0.4).combined(with: .opacity))
                        .animation(.spring(response: 0.6, dampingFraction: 0.85), value: b.drawn)
                        .animation(.spring(response: 0.6, dampingFraction: 0.85), value: b.distance)
                        .animation(.easeInOut(duration: 0.2), value: b.active)
                        .onTapGesture { if let person = b.person { onTap?(person) } }
                }
                ForEach(shown.filter(\.named)) { b in
                    if let rect = labels[b.id] {
                        labelView(b)
                            .frame(width: rect.width, height: rect.height, alignment: Self.alignment(b.side))
                            .position(x: rect.midX, y: rect.midY)
                            .animation(.spring(response: 0.6, dampingFraction: 0.85), value: rect)
                            .transition(.opacity)
                            .onTapGesture { if let person = b.person { onTap?(person) } }
                    }
                }
                if blips.isEmpty {
                    Text(listening ? "listening…" : "Start, then walk up to someone")
                        .font(.system(size: 14, design: .serif))
                        .foregroundStyle(Theme.inkSoft)
                        .position(x: c.x, y: c.y - r * 0.6)
                }
            }
            .animation(.spring(response: 0.45, dampingFraction: 0.7), value: blips.map(\.id))
        }
        .aspectRatio(1, contentMode: .fit)
        .onAppear {
            withAnimation(.easeInOut(duration: 2.4).repeatForever(autoreverses: true)) { breathe = true }
        }
        .onChange(of: live.lines.count) { _, _ in
            rippleTurn = live.lines.last?.id ?? -1
        }
    }

    @ViewBuilder
    private func blipView(_ b: Blip) -> some View {
        if b.named {
            let dot = ZStack {
                // a ripple when this person just said something
                if b.active {
                    Circle()
                        .stroke(b.color, lineWidth: 1.5)
                        .frame(width: 30, height: 30)
                        .modifier(Ripple(trigger: rippleTurn))
                }
                Group {
                    if let person = b.person, let face = live.photos[person.id] {
                        Image(uiImage: face).resizable().scaledToFill()
                            .frame(width: b.active ? 30 : 24, height: b.active ? 30 : 24).clipShape(Circle())
                            .overlay(Circle().stroke(b.color, lineWidth: 2))
                    } else {
                        Circle()
                            .fill(b.color)
                            .frame(width: b.active ? 22 : 16, height: b.active ? 22 : 16)
                            .overlay(Circle().stroke(Theme.paper, lineWidth: 2))
                    }
                }
                .overlay(Circle().stroke(b.active || b.recent || b.known ? b.color : .clear, lineWidth: 1.5).padding(-3))
                .shadow(color: b.active ? b.color.opacity(0.7) : .clear, radius: 10)
            }
            .frame(width: 32, height: 32)
            dot.contentShape(Rectangle())
        } else {
            // a voice that has not introduced itself yet
            VStack(spacing: 4) {
                Circle()
                    .fill(b.active ? Theme.accent : Theme.inkSoft.opacity(0.35))
                    .overlay(Circle().stroke(b.active ? Theme.accent : Theme.inkSoft.opacity(0.5), lineWidth: 1))
                    .frame(width: b.active ? 18 : 12, height: b.active ? 18 : 12)
                    .shadow(color: b.active ? Theme.accent.opacity(0.5) : .clear, radius: 8)
                if b.active {
                    Text("new voice")
                        .font(.system(size: 12, design: .serif))
                        .foregroundStyle(Theme.inkSoft)
                        .shadow(color: Theme.paper, radius: 2)
                }
            }
        }
    }

    /// The name, and under it the reason to reach out when there is one.
    private func labelView(_ b: Blip) -> some View {
        VStack(alignment: Self.horizontal(b.side), spacing: 0) {
            Text(b.label)
                .font(.system(size: Self.nameSize, weight: .semibold, design: .serif))
                .foregroundStyle(Theme.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            if !b.tag.isEmpty {
                Text(b.tag)
                    .font(.system(size: Self.tagSize, weight: .semibold))
                    .foregroundStyle(Theme.live)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
            }
        }
        .shadow(color: Theme.paper, radius: 2)
        .shadow(color: Theme.paper, radius: 1)
    }

    // MARK: label layout

    static let nameSize: CGFloat = 15
    static let tagSize: CGFloat = 11
    static let tagMaxWidth: CGFloat = 132

    struct LabelItem {
        let id: String
        let dot: CGPoint
        let size: CGSize
        let side: Blip.Side
    }

    static func horizontal(_ side: Blip.Side) -> HorizontalAlignment {
        side == .left ? .trailing : side == .right ? .leading : .center
    }

    static func alignment(_ side: Blip.Side) -> Alignment {
        side == .left ? .trailing : side == .right ? .leading : .center
    }

    private static func width(_ text: String, size: CGFloat, serif: Bool) -> CGFloat {
        var font = UIFont.systemFont(ofSize: size, weight: .semibold)
        if serif, let d = font.fontDescriptor.withDesign(.serif) { font = UIFont(descriptor: d, size: size) }
        return ceil((text as NSString).size(withAttributes: [.font: font]).width)
    }

    /// How much room a label takes: the wider of its two lines, the tag capped.
    static func labelSize(_ b: Blip) -> CGSize {
        let name = width(b.label, size: nameSize, serif: true) + 6
        guard !b.tag.isEmpty else { return CGSize(width: name, height: 19) }
        return CGSize(width: max(name, min(tagMaxWidth, width(b.tag, size: tagSize, serif: false) + 4)), height: 33)
    }

    /// Where each name goes. It starts on the outward side of its dot (above for people ahead, below behind,
    /// left on the left, right on the right) and, when that spot is taken by a neighbour's label or dot, slides
    /// along that side, then steps further out, so two people standing close never share one line of text
    /// ("MargotLeo"). Labels are placed in a fixed order (who turned up first), so nothing jumps while people talk.
    static func placeLabels(_ items: [LabelItem], dots: [(id: String, point: CGPoint)], bounds: CGRect) -> [String: CGRect] {
        var placed: [String: CGRect] = [:]
        let area = bounds.insetBy(dx: 2, dy: 2)
        for item in items {
            let w = item.size.width, h = item.size.height, d = item.dot
            let base: CGRect
            switch item.side {
            case .above: base = CGRect(x: d.x - w / 2, y: d.y - 14 - h, width: w, height: h)
            case .below: base = CGRect(x: d.x - w / 2, y: d.y + 14, width: w, height: h)
            case .left: base = CGRect(x: d.x - 16 - w, y: d.y - h / 2, width: w, height: h)
            case .right: base = CGRect(x: d.x + 16, y: d.y - h / 2, width: w, height: h)
            }
            let obstacles = placed.values.map { $0.insetBy(dx: -3, dy: -2) }
                + dots.filter { $0.id != item.id }.map { CGRect(x: $0.point.x - 13, y: $0.point.y - 13, width: 26, height: 26) }
            func clamp(_ r: CGRect) -> CGRect {
                var r = r
                if r.minX < area.minX { r.origin.x = area.minX }
                if r.maxX > area.maxX { r.origin.x = area.maxX - r.width }
                if r.minY < area.minY { r.origin.y = area.minY }
                if r.maxY > area.maxY { r.origin.y = area.maxY - r.height }
                return r
            }
            func overlap(_ r: CGRect) -> CGFloat {
                obstacles.reduce(0) { sum, o in
                    let x = r.intersection(o)
                    return x.isNull ? sum : sum + x.width * x.height
                }
            }
            // slide along the side first (sideways above and below, up and down at the sides), then step out
            let vertical = item.side == .above || item.side == .below
            let out: CGFloat = item.side == .above || item.side == .left ? -1 : 1
            var best = clamp(base), bestOverlap = overlap(best)
            search: for step in 0..<3 {
                let stepped = vertical ? base.offsetBy(dx: 0, dy: out * CGFloat(step) * (h + 2))
                                       : base.offsetBy(dx: out * CGFloat(step) * 12, dy: 0)
                for k in 0...8 {
                    for sign in (k == 0 ? [CGFloat(1)] : [CGFloat(-1), 1]) {
                        let shift = sign * CGFloat(k) * 8
                        let r = clamp(vertical ? stepped.offsetBy(dx: shift, dy: 0) : stepped.offsetBy(dx: 0, dy: shift))
                        let o = overlap(r)
                        if o == 0 { best = r; bestOverlap = 0; break search }
                        if o < bestOverlap { best = r; bestOverlap = o }
                    }
                }
            }
            placed[item.id] = best
        }
        return placed
    }

    /// Close voices on the inner ring, far ones at the edge. Named neighbours are spread apart until there is
    /// room between them, so four people on your left read as four, not a pile; the true bearing is kept for
    /// the arrow in the People list.
    private func laidOut(r: CGFloat) -> [Blip] {
        var out = blips.map { b -> Blip in
            var b = b
            b.radius = r * (0.64 + 0.36 * b.distance)
            b.drawn = b.bearing
            return b
        }
        let named = out.indices.filter { out[$0].named }.sorted { out[$0].bearing < out[$1].bearing }
        guard named.count > 1 else { return out }
        let minGap = 22.0
        for _ in 0..<12 {
            for k in named.indices {
                let i = named[k], j = named[(k + 1) % named.count]
                var gap = out[j].drawn - out[i].drawn
                if k == named.count - 1 { gap += 360 }  // the pair across the seam behind you
                if gap < minGap {
                    let push = (minGap - gap) / 2
                    out[i].drawn -= push
                    out[j].drawn += push
                }
            }
        }
        for i in named { out[i].drawn = (out[i].drawn + 540).truncatingRemainder(dividingBy: 360) - 180 }
        return out
    }

    private var blips: [Blip] {
        var out: [Blip] = []
        var placedSpeakers: Set<String> = []
        for p in live.peopleOrder.compactMap({ live.people[$0] }) {
            guard let b = live.relativeBearing(of: p, offset: offset) else { continue }
            placedSpeakers.formUnion(p.speakers)
            let first = p.name.split(separator: " ").first.map(String.init) ?? p.name
            out.append(Blip(
                id: p.id, person: p, label: first, color: live.color(for: p.id), bearing: b,
                distance: live.distance(ofSpeakers: p.speakers),
                active: p.speakers.contains(live.activeSpeaker ?? ""),
                recent: p.speakers.contains(live.recentSpeaker ?? ""),
                known: live.history[p.id] != nil,
                tag: live.hooks(for: p.id).first?.tag ?? ""
            ))
        }
        for (speaker, az) in live.speakerAzimuth where !placedSpeakers.contains(speaker) && !live.ownerSpeakers.contains(speaker) {
            out.append(Blip(
                id: speaker, person: nil, label: "", color: Theme.inkSoft, bearing: live.relative(az, offset: offset),
                distance: live.distance(ofSpeakers: [speaker]),
                active: speaker == live.activeSpeaker, recent: speaker == live.recentSpeaker
            ))
        }
        return out
    }
}

/// A ring that expands and fades once per trigger change.
struct Ripple: ViewModifier {
    let trigger: Int
    @State private var scale: CGFloat = 1
    @State private var opacity: Double = 0

    func body(content: Content) -> some View {
        content
            .scaleEffect(scale)
            .opacity(opacity)
            .onChange(of: trigger) { _, _ in
                scale = 1
                opacity = 0.5
                withAnimation(.easeOut(duration: 0.9)) {
                    scale = 2.4
                    opacity = 0
                }
            }
    }
}
