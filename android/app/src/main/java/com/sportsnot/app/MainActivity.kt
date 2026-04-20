package com.sportsnot.app

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import com.getcapacitor.BridgeActivity
import com.sportsnot.app.plugins.WidgetBridgePlugin
import com.sportsnot.app.widget.SportsNotWidgetSmall
import com.sportsnot.app.widget.SportsNotWidgetMedium
import com.sportsnot.app.widget.SportsNotWidgetLarge

class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: android.os.Bundle?) {
        registerPlugin(WidgetBridgePlugin::class.java)
        super.onCreate(savedInstanceState)
    }

    override fun onResume() {
        super.onResume()
        // Force all home screen widgets to refresh so they pick up
        // latest data even if the AlarmManager rotation chain broke.
        val manager = AppWidgetManager.getInstance(this)
        val widgetClasses = listOf(
            SportsNotWidgetSmall::class.java,
            SportsNotWidgetMedium::class.java,
            SportsNotWidgetLarge::class.java
        )
        for (cls in widgetClasses) {
            val component = ComponentName(this, cls)
            val ids = manager.getAppWidgetIds(component)
            if (ids.isNotEmpty()) {
                val intent = Intent(AppWidgetManager.ACTION_APPWIDGET_UPDATE).apply {
                    putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids)
                    setComponent(component)
                }
                sendBroadcast(intent)
            }
        }
    }
}
