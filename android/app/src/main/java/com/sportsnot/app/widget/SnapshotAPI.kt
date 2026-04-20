package com.sportsnot.app.widget

import com.sportsnot.app.BuildConfig
import com.sportsnot.app.widget.models.WidgetSnapshot
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import java.util.concurrent.TimeUnit

object SnapshotAPI {
    private val json = Json { ignoreUnknownKeys = true }
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    @Throws(IOException::class)
    fun fetchSnapshot(shareCode: String, date: String? = null): WidgetSnapshot {
        val supabaseUrl = BuildConfig.SUPABASE_URL
        val anonKey = BuildConfig.SUPABASE_ANON_KEY

        var url = "$supabaseUrl/functions/v1/widget-league-snapshot?shareCode=$shareCode"
        if (date != null) {
            url += "&date=$date"
        }

        val request = Request.Builder()
            .url(url)
            .addHeader("apikey", anonKey)
            .addHeader("Authorization", "Bearer $anonKey")
            .get()
            .build()

        val response = client.newCall(request).execute()
        val body = response.body?.string()
            ?: throw IOException("Empty response from widget-league-snapshot")

        if (!response.isSuccessful) {
            throw IOException("widget-league-snapshot returned ${response.code}: $body")
        }

        return json.decodeFromString<WidgetSnapshot>(body)
    }
}
