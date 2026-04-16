import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct LargeFamilyView: View {
    let entry: SnapshotEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(entry.snapshot?.league.name ?? "SportsNot").font(.headline).lineLimit(1)
                Spacer()
                if let total = entry.snapshot.map({ $0.players.reduce(0) { $0 + $1.fantasyPoints } }) {
                    Text(String(format: "%.1f pts", total))
                        .font(.subheadline.monospacedDigit().bold())
                }
            }
            Text("Today's games").font(.caption).foregroundStyle(.secondary)
            if let games = entry.snapshot?.games {
                ForEach(games.prefix(6)) { g in
                    HStack(spacing: 6) {
                        Text("\(g.awayTeamAbbrev) \(g.awayScore)")
                            .font(.caption.monospacedDigit())
                        Text("@").font(.caption2).foregroundStyle(.secondary)
                        Text("\(g.homeTeamAbbrev) \(g.homeScore)")
                            .font(.caption.monospacedDigit())
                        Spacer()
                        statusLabel(for: g)
                    }
                }
            }

            Divider()

            Text("Drafted players").font(.caption).foregroundStyle(.secondary)
            if let players = entry.snapshot?.players {
                ForEach(players.sorted(by: { $0.fantasyPoints > $1.fantasyPoints }).prefix(6), id: \.id) { p in
                    HStack {
                        Text(p.teamAbbrev).font(.caption2.bold()).foregroundStyle(Color.accentColor)
                            .frame(width: 36, alignment: .leading)
                        Text(p.name).font(.caption).lineLimit(1)
                        Spacer()
                        Text(p.ownedByTeamName).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                        Text(String(format: "%.1f", p.fantasyPoints))
                            .font(.caption.monospacedDigit())
                            .frame(width: 44, alignment: .trailing)
                    }
                }
            }
            if entry.staleFromCache {
                Text("• showing cached snapshot").font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    @ViewBuilder
    private func statusLabel(for g: WidgetSnapshot.Game) -> some View {
        switch g.state {
        case "LIVE":
            Text("P\(g.period ?? 0) \(g.timeRemaining ?? "")")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.green)
        case "FINAL", "OFF":
            Text("F").font(.caption2).foregroundStyle(.secondary)
        default:
            Text(g.state).font(.caption2).foregroundStyle(.secondary)
        }
    }
}
