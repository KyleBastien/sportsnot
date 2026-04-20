import Capacitor
import ActivityKit
import Foundation
import WidgetKit

@objc(WidgetBridgePlugin)
public class WidgetBridgePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "WidgetBridgePlugin"
    public let jsName = "WidgetBridge"

    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "setFeaturedLeague", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getFeaturedLeague", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "startLiveActivity", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "endLiveActivity", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "isLiveActivitySupported", returnType: CAPPluginReturnPromise)
    ]

    @objc func setFeaturedLeague(_ call: CAPPluginCall) {
        guard let shareCode = call.getString("shareCode"), !shareCode.isEmpty else {
            call.reject("shareCode is required")
            return
        }
        AppGroup.featuredShareCode = shareCode
        AppGroup.rememberShareCode(shareCode)
        let myTeamName = call.getString("myTeamName")
        AppGroup.setMyTeamName(myTeamName, forShareCode: shareCode)
        // Prime the AppGroup cache from the main process and reload the
        // widget timeline. This avoids relying solely on the extension's
        // (budget-throttled, network-constrained) own fetch.
        WidgetSnapshotPrimer.refresh(reason: "setFeaturedLeague")
        call.resolve([
            "shareCode": shareCode,
            "myTeamName": myTeamName ?? NSNull()
        ])
    }

    @objc func getFeaturedLeague(_ call: CAPPluginCall) {
        let code = AppGroup.featuredShareCode
        let myTeamName = code.flatMap { AppGroup.myTeamName(forShareCode: $0) }
        call.resolve([
            "shareCode": code ?? NSNull(),
            "allShareCodes": AppGroup.shareCodes,
            "myTeamName": myTeamName ?? NSNull()
        ])
    }

    @objc func isLiveActivitySupported(_ call: CAPPluginCall) {
        if #available(iOS 16.2, *) {
            call.resolve(["supported": ActivityAuthorizationInfo().areActivitiesEnabled])
        } else {
            call.resolve(["supported": false])
        }
    }

    @objc func startLiveActivity(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else {
            call.reject("Live Activities require iOS 16.2+")
            return
        }
        guard let shareCode = call.getString("shareCode"),
              let leagueId = call.getString("leagueId"),
              let leagueName = call.getString("leagueName") else {
            call.reject("shareCode, leagueId, and leagueName are required")
            return
        }
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            call.reject("Live Activities are disabled in Settings")
            return
        }

        let attributes = SportsNotGameAttributes(
            leagueId: leagueId,
            leagueName: leagueName,
            shareCode: shareCode
        )
        let initialState = SportsNotGameAttributes.ContentState(
            updatedAt: Date(),
            games: [:],
            players: []
        )

        do {
            let activity = try Activity.request(
                attributes: attributes,
                content: .init(state: initialState, staleDate: nil),
                pushType: .token
            )
            Task { [weak self] in
                for await tokenData in activity.pushTokenUpdates {
                    let hex = tokenData.map { String(format: "%02x", $0) }.joined()
                    self?.notifyListeners("activityTokenUpdated", data: [
                        "activityId": activity.id,
                        "token": hex,
                        "shareCode": shareCode
                    ])
                }
            }
            call.resolve(["activityId": activity.id])
        } catch {
            call.reject("Failed to start Live Activity: \(error.localizedDescription)")
        }
    }

    @objc func endLiveActivity(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else {
            call.resolve()
            return
        }
        Task {
            for activity in Activity<SportsNotGameAttributes>.activities {
                await activity.end(nil, dismissalPolicy: .immediate)
            }
            call.resolve()
        }
    }
}
