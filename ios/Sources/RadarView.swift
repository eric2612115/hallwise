import SwiftUI

/// The room around the badge, seen from above, ahead = up. Each person sits where their voice comes from and
/// lights while they talk. Positions are held in room coordinates by the server, so when the wearer turns the
/// whole ring rotates and nobody drifts.
struct RadarView: View {
    @ObservedObject var live: LiveModel
    let offset: Double  // the badge's forward calibration, degrees

    struct Blip: Identifiable {
        let id: String
        let label: String
        let initials: String
        let bearing: Double  // degrees, 0 = ahead, positive = left
        let distance: Double // 0 = close, 1 = far
        let active: Bool
        let named: Bool
        var radius: CGFloat = 0
    }

    /// Close voices on the inner ring, far ones at the edge; named neighbours closer than 20° are staggered
    /// in and out so their labels don't overlap when three people stand on one side of you.
    private func laidOut(r: CGFloat) -> [Blip] {
        var out = blips.map { b -> Blip in
            var b = b
            b.radius = r * (0.64 + 0.36 * b.distance)
            return b
        }
        let named = out.indices.filter { out[$0].named }.sorted { out[$0].bearing < out[$1].bearing }
        var push = false
        for (k, i) in named.enumerated() where k > 0 {
            let gap = abs(out[i].bearing - out[named[k - 1]].bearing)
            push = gap < 20 ? !push : false
            if push { out[i].radius += 30 }
        }
        return out
    }

    var body: some View {
        GeometryReader { geo in
            let size = min(geo.size.width, geo.size.height)
            let c = CGPoint(x: geo.size.width / 2, y: size / 2)
            let r = size * 0.38
            ZStack {
                Canvas { ctx, _ in
                    for k in [1.0, 0.55] {
                        let ring = Path(ellipseIn: CGRect(x: c.x - r * k, y: c.y - r * k, width: 2 * r * k, height: 2 * r * k))
                        ctx.stroke(ring, with: .color(Theme.rule), style: StrokeStyle(lineWidth: 1, dash: k == 1 ? [] : [3, 5]))
                    }
                    // the badge's field of view, ahead
                    var wedge = Path()
                    wedge.move(to: c)
                    wedge.addArc(center: c, radius: r + 14, startAngle: .degrees(-90 - 28), endAngle: .degrees(-90 + 28), clockwise: false)
                    wedge.closeSubpath()
                    ctx.fill(wedge, with: .color(Theme.accent.opacity(0.08)))
                    var ahead = Path()
                    ahead.move(to: c)
                    ahead.addLine(to: CGPoint(x: c.x, y: c.y - r * 0.3))
                    ctx.stroke(ahead, with: .color(Theme.inkSoft), style: StrokeStyle(lineWidth: 2, lineCap: .round))
                    ctx.fill(Path(ellipseIn: CGRect(x: c.x - 7, y: c.y - 7, width: 14, height: 14)), with: .color(Theme.ink))
                }
                ForEach(laidOut(r: r)) { b in
                    let a = b.bearing * .pi / 180
                    let p = CGPoint(x: c.x - b.radius * sin(a), y: c.y - b.radius * cos(a))
                    VStack(spacing: 4) {
                        let d: CGFloat = b.named ? (b.active ? 40 : 30) : (b.active ? 16 : 10)
                        Text(b.initials)
                            .font(.system(size: b.active ? 15 : 12, weight: .semibold, design: .serif))
                            .foregroundStyle(b.active ? Theme.paper : Theme.ink)
                            .frame(width: d, height: d)
                            .background(Circle().fill(b.active ? Theme.accent : (b.named ? Theme.paperDeep : Theme.rule)))
                            .overlay(Circle().stroke(b.active ? Theme.accent : (b.named ? Theme.inkSoft : .clear), lineWidth: 1.5))
                            .shadow(color: b.active ? Theme.accent.opacity(0.5) : .clear, radius: 10)
                        if b.named {
                            Text(b.label)
                                .font(.system(size: 12, design: .serif))
                                .foregroundStyle(Theme.ink)
                                .lineLimit(1)
                        }
                    }
                    .position(x: p.x, y: p.y + (b.named ? 8 : 0))
                    .animation(.easeInOut(duration: 0.4), value: b.bearing)
                    .animation(.easeInOut(duration: 0.2), value: b.active)
                }
                if blips.isEmpty {
                    Text(live.lines.isEmpty ? "listening…" : "placing voices…")
                        .font(.system(size: 13, design: .serif))
                        .foregroundStyle(Theme.inkSoft)
                        .position(x: c.x, y: c.y - r * 0.6)
                }
                Text("you")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.inkSoft)
                    .position(x: c.x, y: c.y + 18)
            }
        }
        .aspectRatio(1, contentMode: .fit)
    }

    private var blips: [Blip] {
        var out: [Blip] = []
        var placedSpeakers: Set<String> = []
        for key in live.peopleOrder {
            guard let p = live.people[key], let b = live.relativeBearing(of: p, offset: offset) else { continue }
            placedSpeakers.formUnion(p.speakers)
            let words = p.name.split(separator: " ").map(String.init)
            let first = words.first ?? p.name
            // "Kenji Watanabe" -> "KW", "Kevin" -> "Ke": tells two Ke… apart on the ring.
            let initials = words.count >= 2 ? words.prefix(2).compactMap(\.first).map(String.init).joined() : String(first.prefix(2))
            out.append(Blip(
                id: key, label: first, initials: initials, bearing: b, distance: live.distance(ofSpeakers: p.speakers),
                active: p.speakers.contains(live.activeSpeaker ?? ""), named: true
            ))
        }
        // Voices nobody has introduced yet: a faint dot, no label.
        for (speaker, az) in live.speakerAzimuth where !placedSpeakers.contains(speaker) && !live.ownerSpeakers.contains(speaker) {
            out.append(Blip(
                id: speaker, label: "", initials: "", bearing: live.relative(az, offset: offset),
                distance: live.distance(ofSpeakers: [speaker]), active: speaker == live.activeSpeaker, named: false
            ))
        }
        return out
    }
}
