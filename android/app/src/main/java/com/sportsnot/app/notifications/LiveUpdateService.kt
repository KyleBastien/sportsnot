package com.sportsnot.app.notifications

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import com.sportsnot.app.MainActivity
import com.sportsnot.app.R

class LiveUpdateService : Service() {

    companion object {
        const val ACTION_START = "com.sportsnot.app.LIVE_UPDATE_START"
        const val ACTION_STOP = "com.sportsnot.app.LIVE_UPDATE_STOP"
        const val ACTION_UPDATE = "com.sportsnot.app.LIVE_UPDATE_UPDATE"
        const val EXTRA_SHARE_CODE = "shareCode"
        const val EXTRA_LEAGUE_ID = "leagueId"
        const val EXTRA_LEAGUE_NAME = "leagueName"
        const val EXTRA_CONTENT = "content"
        const val NOTIFICATION_ID = 9001
        const val CHANNEL_ID = "sportsnot_live_scores"
    }

    private var leagueName: String = "SportsNot"
    private var shareCode: String = ""

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                shareCode = intent.getStringExtra(EXTRA_SHARE_CODE) ?: ""
                leagueName = intent.getStringExtra(EXTRA_LEAGUE_NAME) ?: "SportsNot"
                val notification = buildNotification(
                    title = "$leagueName — Live",
                    body = "Waiting for game updates…"
                )
                startForeground(NOTIFICATION_ID, notification)
            }
            ACTION_STOP -> {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
            ACTION_UPDATE -> {
                val content = intent.getStringExtra(EXTRA_CONTENT) ?: return START_NOT_STICKY
                updateNotification(content)
            }
        }
        return START_NOT_STICKY
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.live_update_channel),
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = getString(R.string.live_update_channel_desc)
            setShowBadge(false)
        }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(title: String, body: String): Notification {
        val openAppIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, openAppIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val builder = Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(title)
            .setContentText(body)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)

        if (Build.VERSION.SDK_INT >= 35) {
            builder.setStyle(Notification.ProgressStyle())
        }

        return builder.build()
    }

    private fun updateNotification(content: String) {
        val notification = buildNotification(
            title = "$leagueName — Live",
            body = content
        )
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, notification)
    }
}
