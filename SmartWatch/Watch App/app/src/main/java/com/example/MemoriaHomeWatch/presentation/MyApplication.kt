package com.example.MemoriaHomeWatch.presentation

import android.os.Bundle
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.example.MemoriaHomeWatch.R
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import androidx.core.app.NotificationCompat
import android.content.Context


class MyApplication: AppCompatActivity() {
    companion object {
        lateinit var context: Context
            private set
    }


    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        context = applicationContext

        // Create the notification channel (required for Android 8.0 and above)
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                "ForegroundServiceChannelId",
                "Foreground Service Channel",
                NotificationManager.IMPORTANCE_DEFAULT
            )

            // service provided by Android Operating system to show notification outside of our app
            val notificationManager = getSystemService(
                Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }
}


object NotificationUtils {
    const val CHANNEL_ID = "MyForegroundServiceChannel"
    const val CHANNEL_NAME = "Channel name"
    const val NOTIFICATION_ID = 1

    fun createNotificationChannel() {
        val notificationChannel = NotificationChannel(CHANNEL_ID, CHANNEL_NAME, NotificationManager.IMPORTANCE_DEFAULT)
        val notificationManager = MyApplication.context.getSystemService(NotificationManager::class.java)
        notificationManager.createNotificationChannel(notificationChannel)
    }

    fun startForeground(service: Service) {
        val notification = NotificationCompat.Builder(service, CHANNEL_ID).build()
        service.startForeground(NOTIFICATION_ID, notification)
    }
}


