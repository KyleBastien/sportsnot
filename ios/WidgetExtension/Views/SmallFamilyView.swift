import SwiftUI
import WidgetKit

@available(iOS 17.0, *)
struct SmallFamilyView: View {
    let entry: SnapshotEntry

    var body: some View {
        let sections = WidgetScheduleLayout.pageSections(
            for: entry.snapshot,
            family: .systemSmall,
            pageIndex: entry.pageIndex
        )

        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Text(entry.snapshot?.league.name ?? "SportsNot")
                    .font(.caption2.bold())
                    .lineLimit(1)
                Spacer(minLength: 4)
                if entry.totalPages > 1 {
                    Text("\(entry.pageIndex + 1)/\(entry.totalPages)")
                        .font(.system(size: 8).monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
            }

            if let error = entry.errorMessage, entry.snapshot == nil {
                Text(error)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(4)
            } else if let section = sections.first {
                Text(WidgetScheduleLayout.headerText(for: section.game))
                    .font(.caption.bold())
                    .lineLimit(2)

                if let body = WidgetScheduleLayout.bodyText(
                    for: section,
                    family: .systemSmall
                ) {
                    Text(body)
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .lineLimit(WidgetScheduleLayout.config(for: .systemSmall).bodyLineLimit)
                } else {
                    Text("No drafted teams in this game")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            } else {
                Text("No games today")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: 0)

            if let footer = WidgetScheduleLayout.footerText(for: entry) {
                Text(footer)
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }
}
