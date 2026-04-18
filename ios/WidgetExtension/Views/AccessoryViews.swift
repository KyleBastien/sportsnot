import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct AccessoryRectangularView: View {
    let entry: SnapshotEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(entry.snapshot?.league.name ?? "SportsNot")
                .font(.caption2.bold())
                .lineLimit(1)
            if let total = entry.snapshot.map({ $0.players.reduce(0) { $0 + $1.fantasyPoints } }) {
                Text(String(format: "%.0f pts", total))
                    .font(.headline.monospacedDigit())
            }
            if let top = entry.snapshot?.players.max(by: { $0.fantasyPoints < $1.fantasyPoints }) {
                Text("\(top.teamAbbrev) \(top.name)")
                    .font(.caption2)
                    .lineLimit(1)
            }
        }
    }
}

@available(iOS 17.0, *)
struct AccessoryCircularView: View {
    let entry: SnapshotEntry

    var body: some View {
        ZStack {
            AccessoryWidgetBackground()
            VStack(spacing: 0) {
                Image(systemName: "hockey.puck.fill").font(.caption)
                if let total = entry.snapshot.map({ $0.players.reduce(0) { $0 + $1.fantasyPoints } }) {
                    Text(String(format: "%.0f", total))
                        .font(.caption2.monospacedDigit().bold())
                }
            }
        }
    }
}

@available(iOS 17.0, *)
struct AccessoryInlineView: View {
    let entry: SnapshotEntry

    var body: some View {
        let total = entry.snapshot.map { $0.players.reduce(0) { $0 + $1.fantasyPoints } } ?? 0
        let liveCount = entry.snapshot.map { $0.games.filter { $0.state == "LIVE" }.count } ?? 0
        Text("🏒 \(String(format: "%.0f", total)) pts · \(liveCount) live")
    }
}
