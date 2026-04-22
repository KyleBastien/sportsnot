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
import com.sportsnot.app.widget.models.WidgetSnapshot
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class SportsNotWidgetSmall : AppWidgetProvider() {

    companion object {
        const val ACTION_ROTATE_PAGE = "com.sportsnot.app.ROTATE_PAGE_SMALL"
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
        val intent = Intent(context, SportsNotWidgetSmall::class.java).apply {
            action = ACTION_ROTATE_PAGE
            putExtra(EXTRA_WIDGET_ID, widgetId)
        }
        val pending = PendingIntent.getBroadcast(
            context,
            20000 + widgetId,
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
        val intent = Intent(context, SportsNotWidgetSmall::class.java).apply {
            action = ACTION_ROTATE_PAGE
            putExtra(EXTRA_WIDGET_ID, widgetId)
        }
        val pending = PendingIntent.getBroadcast(
            context,
            20000 + widgetId,
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
            val views = RemoteViews(context.packageName, R.layout.widget_small)

            if (snapshot != null) {
                bindSnapshot(context, views, snapshot, appWidgetId)
            } else {
                views.setTextViewText(R.id.league_name, "SportsNot")
                views.setViewVisibility(R.id.page_indicator, View.GONE)
                views.setTextViewText(R.id.game_header, "Tap to configure")
                views.setTextViewText(
                    R.id.game_body,
                    "Feature a league in SportsNot to load playoff games."
                )
                views.setViewVisibility(R.id.game_body, View.VISIBLE)
                views.setTextViewText(R.id.footer_text, "")
            }

            appWidgetManager.updateAppWidget(appWidgetId, views)
        }
    }

    private fun bindSnapshot(
        context: Context,
        views: RemoteViews,
        snapshot: WidgetSnapshot,
        appWidgetId: Int
    ) {
        views.setTextViewText(R.id.league_name, snapshot.league.name)

        val totalPages = WidgetScheduleLayout.totalPages(
            snapshot,
            WidgetHomeSize.SMALL
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

        val section = WidgetScheduleLayout.pageSections(
            snapshot,
            WidgetHomeSize.SMALL,
            pageIndex
        ).firstOrNull()

        if (section == null) {
            views.setTextViewText(R.id.game_header, "No games today")
            views.setViewVisibility(R.id.game_body, View.GONE)
        } else {
            views.setTextViewText(
                R.id.game_header,
                WidgetScheduleLayout.headerText(section.game)
            )
            val body = WidgetScheduleLayout.bodyText(
                section,
                WidgetHomeSize.SMALL
            ) ?: "No drafted teams in this game"
            views.setTextViewText(R.id.game_body, body)
            views.setViewVisibility(R.id.game_body, View.VISIBLE)
        }

        val footer = WidgetScheduleLayout.footerText(
            snapshot,
            WidgetPreferences.getMyTeamName(context, snapshot.league.shareCode)
        ) ?: "Full playoff slate"
        views.setTextViewText(R.id.footer_text, footer)
    }
}

internal const val WIDGET_STALE_CACHE_MAX_AGE_MS: Long = 60L * 60L * 1000L

internal fun fetchOrCached(context: Context): WidgetSnapshot? {
    val shareCode = WidgetPreferences.getFeaturedShareCode(context) ?: return null
    return try {
        val snapshot = SnapshotAPI.fetchSnapshot(shareCode)
        WidgetPreferences.cacheSnapshot(context, snapshot)
        snapshot
    } catch (_: Exception) {
        WidgetPreferences.getCachedSnapshot(context, WIDGET_STALE_CACHE_MAX_AGE_MS)
    }
}

internal fun formatPoints(points: Double): String =
    if (points == points.toLong().toDouble()) {
        points.toLong().toString()
    } else {
        "%.1f".format(points)
    }
