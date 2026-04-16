import ActivityKit
import SwiftUI
import WidgetKit

@available(iOS 16.2, *)
struct SportsNotLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: SportsNotGameAttributes.self) { context in
            // Lock Screen / banner presentation
            LiveActivityLockScreenView(
                attributes: context.attributes,
                state: context.state
            )
            .padding(12)
            .activityBackgroundTint(Color.black.opacity(0.65))
            .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    DynamicIslandLeading(state: context.state, attributes: context.attributes)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    DynamicIslandTrailing(state: context.state)
                }
                DynamicIslandExpandedRegion(.center) {
                    DynamicIslandCenter(state: context.state)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    DynamicIslandBottom(state: context.state)
                }
            } compactLeading: {
                Image(systemName: "hockey.puck.fill")
            } compactTrailing: {
                Text(topPlayerLabel(state: context.state))
                    .font(.caption2)
                    .monospacedDigit()
            } minimal: {
                Image(systemName: "hockey.puck.fill")
            }
        }
    }

    private func topPlayerLabel(state: SportsNotGameAttributes.ContentState) -> String {
        guard let top = state.players.max(by: { $0.fantasyPoints < $1.fantasyPoints }) else {
            return "—"
        }
        return String(format: "%.1f", top.fantasyPoints)
    }
}

@available(iOS 16.2, *)
struct LiveActivityLockScreenView: View {
    let attributes: SportsNotGameAttributes
    let state: SportsNotGameAttributes.ContentState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(attributes.leagueName)
                .font(.headline)
                .foregroundStyle(.white)
            if state.games.isEmpty {
                Text("Waiting for tonight's games…")
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.75))
            } else {
                ForEach(state.games.sorted(by: { $0.key < $1.key }), id: \.key) { _, g in
                    HStack {
                        Text("\(g.awayAbbr) \(g.awayScore)")
                        Text("—")
                        Text("\(g.homeAbbr) \(g.homeScore)")
                        Spacer()
                        if let clock = g.clock, g.state == "LIVE" {
                            Text("P\(g.period ?? 0) \(clock)")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.yellow)
                        } else {
                            Text(g.state)
                                .font(.caption)
                                .foregroundStyle(.white.opacity(0.75))
                        }
                    }
                    .foregroundStyle(.white)
                    .font(.footnote)
                }
            }
            Divider().overlay(.white.opacity(0.2))
            let top3 = Array(state.players.sorted(by: { $0.fantasyPoints > $1.fantasyPoints }).prefix(3))
            ForEach(top3, id: \.playerId) { p in
                HStack {
                    Text(p.teamAbbrev)
                        .font(.caption2.bold())
                        .foregroundStyle(.yellow)
                        .frame(width: 36, alignment: .leading)
                    Text(p.name)
                        .font(.footnote)
                        .lineLimit(1)
                    Spacer()
                    Text(String(format: "%.1f", p.fantasyPoints))
                        .font(.footnote.monospacedDigit())
                        .foregroundStyle(.white)
                }
            }
        }
    }
}

@available(iOS 16.2, *)
struct DynamicIslandLeading: View {
    let state: SportsNotGameAttributes.ContentState
    let attributes: SportsNotGameAttributes
    var body: some View {
        VStack(alignment: .leading) {
            Text(attributes.leagueName).font(.caption2).lineLimit(1)
            Text("\(state.games.values.filter { $0.state == "LIVE" }.count) live")
                .font(.caption.monospacedDigit())
        }
    }
}

@available(iOS 16.2, *)
struct DynamicIslandTrailing: View {
    let state: SportsNotGameAttributes.ContentState
    var body: some View {
        let total = state.players.reduce(0) { $0 + $1.fantasyPoints }
        Text(String(format: "%.1f", total))
            .font(.headline.monospacedDigit())
    }
}

@available(iOS 16.2, *)
struct DynamicIslandCenter: View {
    let state: SportsNotGameAttributes.ContentState
    var body: some View {
        let top = state.players.max(by: { $0.fantasyPoints < $1.fantasyPoints })
        Text(top?.name ?? "—").font(.caption).lineLimit(1)
    }
}

@available(iOS 16.2, *)
struct DynamicIslandBottom: View {
    let state: SportsNotGameAttributes.ContentState
    var body: some View {
        let top3 = Array(state.players.sorted(by: { $0.fantasyPoints > $1.fantasyPoints }).prefix(3))
        HStack(spacing: 12) {
            ForEach(top3, id: \.playerId) { p in
                VStack {
                    Text(p.teamAbbrev).font(.caption2.bold())
                    Text(String(format: "%.1f", p.fantasyPoints))
                        .font(.caption.monospacedDigit())
                }
            }
        }
    }
}
