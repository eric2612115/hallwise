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

                ForEach(laidOut(r: r)) { b in
                    let a = b.drawn * .pi / 180
                    let p = CGPoint(x: c.x - b.radius * sin(a), y: c.y - b.radius * cos(a))
                    blipView(b)
                        .position(x: p.x, y: p.y)
                        .transition(.scale(scale: 0.4).combined(with: .opacity))
                        .animation(.spring(response: 0.6, dampingFraction: 0.85), value: b.drawn)
                        .animation(.spring(response: 0.6, dampingFraction: 0.85), value: b.distance)
                        .animation(.easeInOut(duration: 0.2), value: b.active)
                        .onTapGesture { if let person = b.person { onTap?(person) } }
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
                Circle()
                    .fill(b.color)
                    .frame(width: b.active ? 22 : 16, height: b.active ? 22 : 16)
                    .overlay(Circle().stroke(Theme.paper, lineWidth: 2))
                    .overlay(Circle().stroke(b.active || b.recent ? b.color : .clear, lineWidth: 1.5).padding(-3))
                    .shadow(color: b.active ? b.color.opacity(0.7) : .clear, radius: 10)
            }
            .frame(width: 32, height: 32)
            let label = Text(b.label)
                .font(.system(size: 15, weight: .semibold, design: .serif))
                .foregroundStyle(Theme.ink)
                .shadow(color: Theme.paper, radius: 2)
                .shadow(color: Theme.paper, radius: 1)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            let w: CGFloat = 84, h: CGFloat = 18
            Group {
                switch b.side {
                case .left:
                    HStack(spacing: 4) { label.frame(width: w, alignment: .trailing); dot; Color.clear.frame(width: w, height: 1) }
                case .right:
                    HStack(spacing: 4) { Color.clear.frame(width: w, height: 1); dot; label.frame(width: w, alignment: .leading) }
                case .above:
                    VStack(spacing: 1) { label.frame(width: w, height: h); dot; Color.clear.frame(width: 1, height: h) }
                case .below:
                    VStack(spacing: 1) { Color.clear.frame(width: 1, height: h); dot; label.frame(width: w, height: h) }
                }
            }
            .contentShape(Rectangle())
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
                recent: p.speakers.contains(live.recentSpeaker ?? "")
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
