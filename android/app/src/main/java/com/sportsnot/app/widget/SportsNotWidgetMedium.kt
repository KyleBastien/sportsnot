package com.sportsnot.app.widget

import android.app.AlarmManager
import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.os.SystemClock
import android.view.View
import android.widget.RemoteViews
import com.sportsnot.app.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class SportsNotWidgetMedium : AppWidgetProvider() {

    companion object {
        const val ACTION_ROTATE_PAGE = "com.sportsnot.app.ROTATE_PAGE_MEDIUM"
        const val EXTRA_WIDGET_ID = "widget_id"
        private const val PAGE_INTERVAL_MS = 30_000L
    }

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        for (appWidgetId in appWidgetIds) {
            updateWidget(context, appWidgetManager, appWidgetId)
            schedulePageRotation(context, appWidgetId)
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action == ACTION_ROTATE_PAGE) {
            val widgetId = intent.getIntExtra(EXTRA_WIDGET_ID, -1)
            if (widgetId != -1) {
                val manager = AppWidgetManager.getInstance(context)
                updateWidget(context, manager, widgetId)
                schedulePageRotation(context, widgetId)
            }
        }
    }

    override fun onDeleted(context: Context, appWidgetIds: IntArray) {
        for (id in appWidgetIds) {
            cancelPageRotation(context, id)
            WidgetPreferences.clearPageIndex(context, id)
        }
    }

    private fun schedulePageRotation(context: Context, widgetId: Int) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val intent = Intent(context, SportsNotWidgetMedium::class.java).apply {
            action = ACTION_ROTATE_PAGE
            putExtra(EXTRA_WIDGET_ID, widgetId)
        }
        val pending = PendingIntent.getBroadcast(
            context,
            widgetId,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        alarmManager.set(
            AlarmManager.ELAPSED_REALTIME,
            SystemClock.elapsedRealtime() + PAGE_INTERVAL_MS,
            pending
        )
    }

    private fun cancelPageRotation(context: Context, widgetId: Int) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val intent = Intent(context, SportsNotWidgetMedium::class.java).apply {
            action = ACTION_ROTATE_PAGE
            putExtra(EXTRA_WIDGET_ID, widgetId)
        }
        val pending = PendingIntent.getBroadcast(
            context,
            widgetId,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        alarmManager.cancel(pending)
    }

    private fun updateWidget(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetId: Int
    ) {
        CoroutineScope(Dispatchers.IO).launch {
            val snapshot = fetchOrCached(context)
            val views = RemoteViews(context.packageName, R.layout.widget_medium)

            if (snapshot != null) {
                views.setTextViewText(R.id.league_name, snapshot.league.name)
                val pageIndex = bindPageIndicator(
                    context,
                    views,
                    snapshot,
                    appWidgetId
                )
                val sections = WidgetScheduleLayout.pageSections(
                    snapshot,
                    WidgetHomeSize.MEDIUM,
                    pageIndex
                )
                bindSection(
                    views,
                    R.id.game_section_1,
                    R.id.game_1_header,
                    R.id.game_1_body,
                    sections.getOrNull(0),
                    WidgetHomeSize.MEDIUM
                )
                bindSection(
                    views,
                    R.id.game_section_2,
                    R.id.game_2_header,
                    R.id.game_2_body,
                    sections.getOrNull(1),
                    WidgetHomeSize.MEDIUM
                )
                val footer = WidgetScheduleLayout.footerText(
                    snapshot,
                    WidgetPreferences.getMyTeamName(context, snapshot.league.shareCode)
                ) ?: "Full playoff slate"
                views.setTextViewText(R.id.footer_text, footer)
            } else {
                views.setTextViewText(R.id.league_name, "SportsNot")
                views.setViewVisibility(R.id.page_indicator, View.GONE)
                bindEmptyState(
                    views,
                    R.id.game_section_1,
                    R.id.game_1_header,
                    R.id.game_1_body,
                    "Tap to configure",
                    "Feature a league in SportsNot to load grouped playoff games."
                )
                views.setViewVisibility(R.id.game_section_2, View.GONE)
                views.setTextViewText(R.id.footer_text, "")
            }

            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }

    private fun bindPageIndicator(
        context: Context,
        views: RemoteViews,
        snapshot: com.sportsnot.app.widget.models.WidgetSnapshot,
        appWidgetId: Int
    ): Int {
        val totalPages = WidgetScheduleLayout.totalPages(
            snapshot,
            WidgetHomeSize.MEDIUM
        )
        val pageIndex = WidgetPreferences.consumePageIndex(
            context,
            appWidgetId,
            totalPages
        )
        if (totalPages > 1) {
            views.setViewVisibility(R.id.page_indicator, View.VISIBLE)
            views.setTextViewText(R.id.page_indicator, "${pageIndex + 1}/$totalPages")
        } else {
            views.setViewVisibility(R.id.page_indicator, View.GONE)
        }
        return pageIndex
    }

    private fun bindSection(
        views: RemoteViews,
        containerId: Int,
        headerId: Int,
        bodyId: Int,
        section: WidgetScheduleLayout.GameSection?,
        size: WidgetHomeSize
    ) {
        if (section == null) {
            views.setViewVisibility(containerId, View.GONE)
            return
        }
        views.setViewVisibility(containerId, View.VISIBLE)
        views.setTextViewText(headerId, WidgetScheduleLayout.headerText(section.game))
        val body = WidgetScheduleLayout.bodyText(section, size)
        if (body.isNullOrBlank()) {
            views.setViewVisibility(bodyId, View.GONE)
        } else {
            views.setTextViewText(bodyId, body)
            views.setViewVisibility(bodyId, View.VISIBLE)
        }
    }

    private fun bindEmptyState(
        views: RemoteViews,
        containerId: Int,
        headerId: Int,
        bodyId: Int,
        header: String,
        body: String
    ) {
        views.setViewVisibility(containerId, View.VISIBLE)
        views.setTextViewText(headerId, header)
        views.setTextViewText(bodyId, body)
        views.setViewVisibility(bodyId, View.VISIBLE)
    }
}
