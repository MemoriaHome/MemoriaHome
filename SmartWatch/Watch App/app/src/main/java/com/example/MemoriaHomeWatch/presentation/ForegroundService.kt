package com.example.MemoriaHomeWatch.presentation

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import com.example.MemoriaHomeWatch.BuildConfig
import com.example.MemoriaHomeWatch.R
import com.samsung.android.service.health.tracking.data.DataPoint
import com.samsung.android.service.health.tracking.data.HealthTrackerType
import com.samsung.android.service.health.tracking.data.ValueKey
import kotlinx.coroutines.*
import java.util.*

class ForegroundService : Service(), SensorEventListener {

    companion object {
        private const val CHANNEL_ID = "vitals_tracking_channel"
        private const val CHANNEL_NAME = "Vitals Tracking"
        private const val NOTIFICATION_ID = 100
        private const val TAG = "ForegroundService"

        // Broadcast actions for UI updates
        const val ACTION_VITALS_UPDATE = "com.example.MemoriaHomeWatch.VITALS_UPDATE"
        const val EXTRA_HEART_RATE = "heart_rate"
        const val EXTRA_SPO2 = "spo2"
        const val EXTRA_TIMESTAMP = "timestamp"
    }

    // Health SDK Managers
    private lateinit var healthSDKManager: HealthSDKManager
    private lateinit var healthServicesManager: HealthServicesManager

    // Sensor Manager for off-body detection
    private lateinit var sensorManager: SensorManager
    private var offBodySensor: Sensor? = null
    private var isWatchWorn = true

    // Current vitals
    private var currentHeartRate = 0
    private var currentSpO2 = 0f

    // MQTT Manager
    private lateinit var mqttManager: MQTTManager

    // Background threading
    private lateinit var serviceHandler: Handler
    private lateinit var handlerThread: HandlerThread
    private val coroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    // Wake lock to keep service alive
    private var wakeLock: PowerManager.WakeLock? = null

    // Data sync interval
    private var lastMqttPublishTime = 0L
    private val MQTT_PUBLISH_INTERVAL = 2000L // Publish every 2 seconds

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "Service onCreate")

        initializeManagers()
        setupBackgroundThread()
        setupWakeLock()
        createNotificationChannel()
        startForegroundService()
        startVitalsTracking()
        startOffBodyDetection()
    }

    private fun initializeManagers() {
        // Initialize MQTT
        mqttManager = MQTTManager { message ->
            Log.d(TAG, "MQTT message received: $message")
            // Handle incoming messages if needed
        }
        connectMQTT()

        // Initialize Samsung Health SDK
        healthSDKManager = HealthSDKManager(
            this,
            onConnected = {
                Log.d(TAG, "Samsung Health SDK connected")
                startSamsungTracking()
            },
            onResolution = { exception ->
                Log.e(TAG, "Samsung SDK resolution needed", exception)
                exception.resolve(this)
            },
            dataReceived = { type, dataPoints ->
                handleSamsungData(type, dataPoints)
            }
        )

        // Initialize Google Health Services
        healthServicesManager = HealthServicesManager(this)

        // Connect Samsung SDK
        healthSDKManager.connect()

        // Start passive monitoring with Google Health Services
        startGooglePassiveMonitoring()
    }

    private fun connectMQTT() {
        coroutineScope.launch {
            try {
                mqttManager.mqttConnect(
                    BuildConfig.MQTT_BROKER,
                    BuildConfig.MQTT_USERNAME,
                    BuildConfig.MQTT_PASSWORD,
                    false
                )
                Log.d(TAG, "MQTT Connected")
            } catch (e: Exception) {
                Log.e(TAG, "MQTT Connection failed", e)
            }
        }
    }

    private fun startGooglePassiveMonitoring() {
        try {
            healthServicesManager.startPassiveMonitoring(
                setOf(DataType.HEART_RATE_BPM),
                { dataPointContainer ->
                    handleGooglePassiveData(dataPointContainer)
                },
                false // Use callback instead of service
            )
            Log.d(TAG, "Google passive monitoring started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Google passive monitoring", e)
        }
    }

    private fun startSamsungTracking() {
        try {
            // Start continuous heart rate tracking
            healthSDKManager.startTracker(HealthTrackerType.HEART_RATE_CONTINUOUS)
            Log.d(TAG, "Samsung heart rate tracking started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Samsung tracking", e)
        }
    }

    private fun handleSamsungData(type: HealthTrackerType, dataPoints: List<DataPoint?>) {
        coroutineScope.launch {
            for (data in dataPoints) {
                data ?: continue

                when (type) {
                    HealthTrackerType.HEART_RATE_CONTINUOUS -> {
                        val heartRate = data.getValue(ValueKey.HeartRateSet.HEART_RATE)
                        if (heartRate > 0) {
                            currentHeartRate = heartRate
                            Log.d(TAG, "Samsung HR: $heartRate")
                            publishToMQTT("heart_rate", heartRate.toString())
                            updateNotification()
                            broadcastToUI()
                        }
                    }
                    else -> { /* Handle other types if needed */ }
                }
            }
        }
    }

    private fun handleGooglePassiveData(data: DataPointContainer) {
        coroutineScope.launch {
            val heartRatePoints = data.getData(DataType.HEART_RATE_BPM)
            if (heartRatePoints.isNotEmpty()) {
                val latest = heartRatePoints.last()
                val heartRate = latest.value.toInt()
                if (heartRate > 0) {
                    currentHeartRate = heartRate
                    Log.d(TAG, "Google HR: $heartRate")
                    publishToMQTT("heart_rate", heartRate.toString())
                    updateNotification()
                    broadcastToUI()
                }
            }
        }
    }

    private fun publishToMQTT(topic: String, value: String) {
        val currentTime = System.currentTimeMillis()
        // Rate limit MQTT publishes
        if (currentTime - lastMqttPublishTime >= MQTT_PUBLISH_INTERVAL) {
            lastMqttPublishTime = currentTime
            coroutineScope.launch {
                try {
                    // Create JSON payload
                    val payload = """{"type":"$topic","value":$value,"timestamp":$currentTime,"watchWorn":$isWatchWorn}"""
                    mqttManager.publish("watch-data", payload, 1)
                    Log.d(TAG, "MQTT Published: $payload")
                } catch (e: Exception) {
                    Log.e(TAG, "MQTT Publish failed", e)
                    // Attempt to reconnect
                    if (e.message?.contains("not connected") == true) {
                        connectMQTT()
                    }
                }
            }
        }
    }

    private fun updateNotification() {
        val notificationIntent = Intent(this, TrackingActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, notificationIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Memoria Home - Monitoring Active")
            .setContentText("$currentHeartRate BPM | Status: ${if (isWatchWorn) "Worn" else "Off"}")
            .setSmallIcon(R.drawable.ic_heart_rate)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setContentIntent(pendingIntent)
            .build()

        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            notification,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
            } else {
                0
            }
        )
    }

    private fun broadcastToUI() {
        val intent = Intent(ACTION_VITALS_UPDATE).apply {
            putExtra(EXTRA_HEART_RATE, currentHeartRate)
            putExtra(EXTRA_SPO2, currentSpO2)
            putExtra(EXTRA_TIMESTAMP, System.currentTimeMillis())
        }
        sendBroadcast(intent)
    }

    private fun startOffBodyDetection() {
        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        offBodySensor = sensorManager.getDefaultSensor(Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT)

        offBodySensor?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
            Log.d(TAG, "Off-body detection started")
        } ?: Log.w(TAG, "Off-body sensor not available")
    }

    override fun onSensorChanged(event: SensorEvent?) {
        event?.let {
            if (it.sensor.type == Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT) {
                val wasWorn = isWatchWorn
                isWatchWorn = it.values[0].toInt() == 1

                if (wasWorn != isWatchWorn) {
                    Log.d(TAG, "Watch wear state changed: ${if (isWatchWorn) "Worn" else "Not worn"}")

                    if (isWatchWorn) {
                        // Watch was put on - resume tracking
                        healthSDKManager.resumeAllTrackers()
                        startGooglePassiveMonitoring()
                    } else {
                        // Watch was removed - pause tracking to save battery
                        healthSDKManager.pauseAllTrackers()
                        healthServicesManager.stopPassiveCallback()
                    }
                    updateNotification()
                }
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        // Not needed
    }

    private fun setupBackgroundThread() {
        handlerThread = HandlerThread("VitalsServiceThread").apply {
            start()
        }
        serviceHandler = Handler(handlerThread.looper)
    }

    private fun setupWakeLock() {
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "MemoriaHome:VitalsWakeLock"
        ).apply {
            isReferenceCounted = false
            acquire(30 * 60 * 1000L) // 30 minutes timeout
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Continuous vitals tracking"
                setShowBadge(false)
            }

            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }

    private fun startForegroundService() {
        try {
            val notification = NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("Memoria Home")
                .setContentText("Starting vitals monitoring...")
                .setSmallIcon(R.drawable.ic_heart_rate)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build()

            ServiceCompat.startForeground(
                service = this,
                id = NOTIFICATION_ID,
                notification = notification,
                foregroundServiceType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
                } else {
                    0
                }
            )
            Log.d(TAG, "Foreground service started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start foreground service", e)
        }
    }

    private fun startVitalsTracking() {
        Log.d(TAG, "Vitals tracking started")
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "onStartCommand called")
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "Service onDestroy")

        // Cleanup
        sensorManager.unregisterListener(this)
        healthSDKManager.disconnect()
        healthServicesManager.stopPassiveCallback()
        healthServicesManager.stopPassiveService()
        handlerThread.quitSafely()
        wakeLock?.release()
        coroutineScope.cancel()
    }
}