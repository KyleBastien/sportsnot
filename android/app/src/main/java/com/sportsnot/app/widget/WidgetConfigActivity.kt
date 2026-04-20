package com.sportsnot.app.widget

import android.app.Activity
import android.appwidget.AppWidgetManager
import android.content.Intent
import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.ListView
import com.sportsnot.app.R

class WidgetConfigActivity : Activity() {

    private var appWidgetId = AppWidgetManager.INVALID_APPWIDGET_ID

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // If cancelled, the widget should not be placed
        setResult(RESULT_CANCELED)

        appWidgetId = intent?.extras?.getInt(
            AppWidgetManager.EXTRA_APPWIDGET_ID,
            AppWidgetManager.INVALID_APPWIDGET_ID
        ) ?: AppWidgetManager.INVALID_APPWIDGET_ID

        if (appWidgetId == AppWidgetManager.INVALID_APPWIDGET_ID) {
            finish()
            return
        }

        val shareCodes = WidgetPreferences.getAllShareCodes(this)

        if (shareCodes.isEmpty()) {
            // No share codes configured yet — use featured or skip config
            val featured = WidgetPreferences.getFeaturedShareCode(this)
            if (featured != null) {
                confirmWidget()
            } else {
                // Nothing to configure, place widget anyway (will show placeholder)
                confirmWidget()
            }
            return
        }

        if (shareCodes.size == 1) {
            // Only one league — auto-select
            WidgetPreferences.setFeaturedShareCode(this, shareCodes.first())
            confirmWidget()
            return
        }

        val listView = ListView(this)
        val adapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, shareCodes)
        listView.adapter = adapter
        listView.setOnItemClickListener { _, _, position, _ ->
            WidgetPreferences.setFeaturedShareCode(this, shareCodes[position])
            confirmWidget()
        }
        setContentView(listView)
    }

    private fun confirmWidget() {
        val resultValue = Intent().apply {
            putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, appWidgetId)
        }
        setResult(RESULT_OK, resultValue)

        // Trigger initial widget update
        val manager = AppWidgetManager.getInstance(this)
        val views = android.widget.RemoteViews(packageName, R.layout.widget_small)
        views.setTextViewText(R.id.player_name, "Loading…")
        manager.updateAppWidget(appWidgetId, views)

        finish()
    }
}
