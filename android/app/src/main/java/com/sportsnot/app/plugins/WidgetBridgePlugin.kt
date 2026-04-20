package com.sportsnot.app.plugins

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import android.os.Build
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.sportsnot.app.notifications.LiveUpdateService
import com.sportsnot.app.widget.SportsNotWidgetSmall
import com.sportsnot.app.widget.SportsNotWidgetMedium
import com.sportsnot.app.widget.SportsNotWidgetLarge
import com.sportsnot.app.widget.WidgetPreferences

@CapacitorPlugin(name = "WidgetBridge")
class WidgetBridgePlugin : Plugin() {

    @PluginMethod
    fun setFeaturedLeague(call: PluginCall) {
        val shareCode = call.getString("shareCode")
        if (shareCode.isNullOrBlank()) {
            call.reject("shareCode is required")
            return
        }

        val context = this.context
        WidgetPreferences.setFeaturedShareCode(context, shareCode)
        val myTeamName = call.getString("myTeamName")
        WidgetPreferences.setMyTeamName(context, myTeamName, shareCode)

        reloadAllWidgets()

        val result = JSObject()
        result.put("shareCode", shareCode)
        result.put("myTeamName", myTeamName)
        call.resolve(result)
    }

    @PluginMethod
    fun getFeaturedLeague(call: PluginCall) {
        val context = this.context
        val code = WidgetPreferences.getFeaturedShareCode(context)
        val myTeamName = code?.let { WidgetPreferences.getMyTeamName(context, it) }

        val result = JSObject()
        result.put("shareCode", code)
        val allCodes = WidgetPreferences.getAllShareCodes(context)
        val codesArray = org.json.JSONArray(allCodes)
        result.put("allShareCodes", codesArray)
        result.put("myTeamName", myTeamName)
        call.resolve(result)
    }

    @PluginMethod
    fun isLiveActivitySupported(call: PluginCall) {
        val result = JSObject()
        result.put("supported", Build.VERSION.SDK_INT >= 35)
        call.resolve(result)
    }

    @PluginMethod
    fun startLiveActivity(call: PluginCall) {
        if (Build.VERSION.SDK_INT < 35) {
            call.reject("Live Updates require Android 15+")
            return
        }

        val shareCode = call.getString("shareCode")
        val leagueId = call.getString("leagueId")
        val leagueName = call.getString("leagueName")

        if (shareCode.isNullOrBlank() || leagueId.isNullOrBlank() || leagueName.isNullOrBlank()) {
            call.reject("shareCode, leagueId, and leagueName are required")
            return
        }

        val intent = Intent(context, LiveUpdateService::class.java).apply {
            action = LiveUpdateService.ACTION_START
            putExtra(LiveUpdateService.EXTRA_SHARE_CODE, shareCode)
            putExtra(LiveUpdateService.EXTRA_LEAGUE_ID, leagueId)
            putExtra(LiveUpdateService.EXTRA_LEAGUE_NAME, leagueName)
        }
        context.startForegroundService(intent)

        val result = JSObject()
        result.put("activityId", "android-live-update-$leagueId")
        call.resolve(result)
    }

    @PluginMethod
    fun endLiveActivity(call: PluginCall) {
        val intent = Intent(context, LiveUpdateService::class.java).apply {
            action = LiveUpdateService.ACTION_STOP
        }
        context.startService(intent)
        call.resolve()
    }

    private fun reloadAllWidgets() {
        val manager = AppWidgetManager.getInstance(context)
        val widgetClasses = listOf(
            SportsNotWidgetSmall::class.java,
            SportsNotWidgetMedium::class.java,
            SportsNotWidgetLarge::class.java
        )
        for (cls in widgetClasses) {
            val component = ComponentName(context, cls)
            val ids = manager.getAppWidgetIds(component)
            if (ids.isNotEmpty()) {
                val intent = Intent(AppWidgetManager.ACTION_APPWIDGET_UPDATE).apply {
                    putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids)
                    setComponent(component)
                }
                context.sendBroadcast(intent)
            }
        }
    }
}
