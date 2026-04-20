package com.sportsnot.app.notifications

import android.content.Intent
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.sportsnot.app.BuildConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.security.MessageDigest

class FCMService : FirebaseMessagingService() {

    private val client = OkHttpClient()
    private val json = Json { ignoreUnknownKeys = true }

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        registerTokenWithBackend(token)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        val data = message.data

        val contentBody = data["content"] ?: return

        val intent = Intent(this, LiveUpdateService::class.java).apply {
            action = LiveUpdateService.ACTION_UPDATE
            putExtra(LiveUpdateService.EXTRA_CONTENT, contentBody)
        }
        startService(intent)
    }

    private fun registerTokenWithBackend(token: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val supabaseUrl = BuildConfig.SUPABASE_URL
                val anonKey = BuildConfig.SUPABASE_ANON_KEY

                // Read share code from preferences
                val prefs = getSharedPreferences("com.sportsnot.widget", MODE_PRIVATE)
                val shareCode = prefs.getString("featuredShareCode", null) ?: return@launch

                val body = """
                    {
                        "shareCode": "$shareCode",
                        "token": "$token",
                        "kind": "fcm",
                        "bundleId": "com.sportsnot.app",
                        "platform": "android"
                    }
                """.trimIndent()

                val request = Request.Builder()
                    .url("$supabaseUrl/functions/v1/register-live-activity-token")
                    .addHeader("apikey", anonKey)
                    .addHeader("Authorization", "Bearer $anonKey")
                    .addHeader("Content-Type", "application/json")
                    .post(body.toRequestBody("application/json".toMediaType()))
                    .build()

                client.newCall(request).execute().close()
            } catch (_: Exception) {
                // Token registration failed — will retry on next token refresh
            }
        }
    }
}
