import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct SmallFamilyView: View {
    let entry: SnapshotEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let error = entry.errorMessage {
                Text(error).font(.caption2).foregroundStyle(.secondary)
            } else if let snapshot = entry.snapshot {
                Text(snapshot.league.name)
                    .font(.caption.bold())
                    .lineLimit(1)
                let total = snapshot.players.reduce(0) { $0 + $1.fantasyPoints }
                Text(String(format: "%.0f pts", total))
                    .font(.title3.bold().monospacedDigit())

                let playingToday = snapshot.players
                    .filter { $0.gameId != nil }
                    .sorted(by: { $0.fantasyPoints > $1.fantasyPoints })
                if let player = playingToday[safe: entry.pageIndex] {
                    VStack(alignment: .leading, spacing: 1) {
                        HStack(spacing: 4) {
                            Text(player.teamAbbrev)
                                .font(.caption2.bold())
                                .foregroundStyle(Color.accentColor)
                            Text(player.name)
                                .font(.caption2)
                                .lineLimit(1)
                        }
                        Text(String(format: "%.0f pts", player.fantasyPoints))
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                } else if let top = snapshot.players.max(by: { $0.fantasyPoints < $1.fantasyPoints }) {
                    Text("Top: \(top.name)")
                        .font(.caption2)
                        .lineLimit(1)
                }
                if entry.totalPages > 1 {
                    Text("\(entry.pageIndex + 1)/\(entry.totalPages)")
                        .font(.system(size: 8).monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                if let liveCount = liveGameCount(snapshot) {
                    Label("\(liveCount) live", systemImage: "dot.radiowaves.left.and.right")
                        .font(.caption2)
                        .foregroundStyle(.green)
                }
            } else {
                Text("SportsNot").font(.headline)
                Text("Waiting for today's slate").font(.caption2).foregroundStyle(.secondary)
            }
            if entry.staleFromCache {
                Text("• cached").font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func liveGameCount(_ s: WidgetSnapshot) -> Int? {
        let c = s.games.filter { $0.state == "LIVE" || $0.state == "CRIT" }.count
        return c == 0 ? nil : c
    }
}

private extension Array {
    subscript(safe index: Int) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
