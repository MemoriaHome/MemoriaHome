package com.example.MemoriaHomeWatch.presentation

import android.app.AlarmManager
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
import android.os.SystemClock
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import com.example.MemoriaHomeWatch.BuildConfig
import com.example.MemoriaHomeWatch.R
import com.samsung.android.service.health.tracking.data.DataPoint
import com.samsung.android.service.health.tracking.data.HealthTrackerType
import com.samsung.android.service.health.tracking.data.ValueKey
import kotlinx.coroutines.*

class ForegroundService : Service(), SensorEventListener {

    companion object {
        private const val CHANNEL_ID = "vitals_tracking_channel"
        private const val CHANNEL_NAME = "Vitals Tracking"
        private const val NOTIFICATION_ID = 100
        private const val TAG = "ForegroundService"

        private const val WATCHDOG_INTERVAL_MS = 5 * 60 * 1000L

        const val ACTION_VITALS_UPDATE = "com.example.MemoriaHomeWatch.VITALS_UPDATE"
        const val EXTRA_HEART_RATE = "heart_rate"
        const val EXTRA_SPO2 = "spo2"
        const val EXTRA_TIMESTAMP = "timestamp"

        // FIX: Explicit stop action — the only reliable way to stop a
        // foreground service on Wear OS is to have it stop itself
        const val ACTION_STOP_SERVICE = "com.example.MemoriaHomeWatch.ACTION_STOP_SERVICE"

        var userStopped = false
    }

    private lateinit var healthSDKManager: HealthSDKManager
    private lateinit var healthServicesManager: HealthServicesManager

    private lateinit var sensorManager: SensorManager
    private var offBodySensor: Sensor? = null
    private var heartRateSensor: Sensor? = null
    private var isWatchWorn = true

    private var currentHeartRate = 0
    private var currentSpO2 = 0f

    private lateinit var mqttManager: MQTTManager

    private lateinit var serviceHandler: Handler
    private lateinit var handlerThread: HandlerThread
    private val coroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private var wakeLock: PowerManager.WakeLock? = null

    private val watchdogHandler = Handler(Looper.getMainLooper())
    private val watchdogRunnable = object : Runnable {
        override fun run() {
            Log.d(TAG, "Watchdog: re-registering heart rate sensor")
            registerHeartRateSensor()
            watchdogHandler.postDelayed(this, WATCHDOG_INTERVAL_MS)
        }
    }

    private var lastMqttPublishTime = 0L
    private val MQTT_PUBLISH_INTERVAL = 2000L

    // ─────────────────────────────────────────────────────────────────────────
    // Lifecycle
    // ─────────────────────────────────────────────────────────────────────────

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "Service onCreate")
        userStopped = false

        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager

        initializeManagers()
        setupBackgroundThread()
        setupWakeLock()
        createNotificationChannel()
        startForegroundService()
        startVitalsTracking()
        startHeartRateSensor()
        startOffBodyDetection()
        watchdogHandler.post(watchdogRunnable)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // FIX: Handle explicit stop action — call stopForeground + stopSelf
        // from WITHIN the service. This is more reliable than stopService()
        // called from outside, especially on Wear OS foreground services.
        if (intent?.action == ACTION_STOP_SERVICE) {
            Log.d(TAG, "Stop action received — shutting down cleanly")
            userStopped = true
            @Suppress("DEPRECATION")
            stopForeground(true)
            stopSelf()
            return START_NOT_STICKY
        }
        Log.d(TAG, "onStartCommand")
        return START_NOT_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        if (!userStopped) {
            Log.d(TAG, "onTaskRemoved — scheduling restart")
            val restartIntent = Intent(applicationContext, ForegroundService::class.java)
            val pendingIntent = PendingIntent.getService(
                this, 1, restartIntent,
                PendingIntent.FLAG_IMMUTABLE
            )
            (getSystemService(Context.ALARM_SERVICE) as AlarmManager).set(
                AlarmManager.ELAPSED_REALTIME,
                SystemClock.elapsedRealtime() + 1000L,
                pendingIntent
            )
        } else {
            Log.d(TAG, "onTaskRemoved — skipping restart, user stopped manually")
        }
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "Service onDestroy")

        // FIX: Wrap each cleanup step in try-catch so one failure can't
        // prevent the rest from running (e.g. Samsung SDK throwing on disconnect)
        try { watchdogHandler.removeCallbacks(watchdogRunnable) } catch (e: Exception) { Log.e(TAG, "watchdog cleanup failed", e) }
        try { sensorManager.unregisterListener(this) } catch (e: Exception) { Log.e(TAG, "sensor unregister failed", e) }
        try { healthSDKManager.disconnect() } catch (e: Exception) { Log.e(TAG, "Samsung SDK disconnect failed", e) }
        try { healthServicesManager.stopPassiveCallback() } catch (e: Exception) { Log.e(TAG, "stopPassiveCallback failed", e) }
        try { healthServicesManager.stopPassiveService() } catch (e: Exception) { Log.e(TAG, "stopPassiveService failed", e) }
        try { handlerThread.quitSafely() } catch (e: Exception) { Log.e(TAG, "handlerThread quit failed", e) }
        try { wakeLock?.release() } catch (e: Exception) { Log.e(TAG, "wakeLock release failed", e) }
        try { coroutineScope.cancel() } catch (e: Exception) { Log.e(TAG, "coroutineScope cancel failed", e) }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ─────────────────────────────────────────────────────────────────────────
    // Wake-Up Heart Rate Sensor
    // ─────────────────────────────────────────────────────────────────────────

    private fun startHeartRateSensor() {
        heartRateSensor = sensorManager.getDefaultSensor(Sensor.TYPE_HEART_RATE, true)
            ?: sensorManager.getDefaultSensor(Sensor.TYPE_HEART_RATE)

        if (heartRateSensor != null) {
            sensorManager.registerListener(
                this,
                heartRateSensor,
                SensorManager.SENSOR_DELAY_NORMAL
            )
            Log.d(TAG, "HR sensor registered — isWakeUpSensor: ${heartRateSensor?.isWakeUpSensor}")
        } else {
            Log.w(TAG, "Heart rate sensor not available on this device")
        }
    }

    private fun registerHeartRateSensor() {
        heartRateSensor?.let { sensor ->
            sensorManager.unregisterListener(this, sensor)
            sensorManager.registerListener(this, sensor, SensorManager.SENSOR_DELAY_NORMAL)
            Log.d(TAG, "HR sensor re-registered by watchdog")
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Sensor Callbacks
    // ─────────────────────────────────────────────────────────────────────────

    override fun onSensorChanged(event: SensorEvent?) {
        event ?: return

        when (event.sensor.type) {

            Sensor.TYPE_HEART_RATE -> {
                val bpm = event.values[0].toInt()
                if (bpm > 0) {
                    currentHeartRate = bpm
                    Log.d(TAG, "Wake-up sensor HR: $bpm BPM")
                    publishToMQTT("heart_rate", bpm.toString())
                    updateNotification()
                    broadcastToUI()
                }
            }

            Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT -> {
                val wasWorn = isWatchWorn
                isWatchWorn = event.values[0].toInt() == 1

                if (wasWorn != isWatchWorn) {
                    Log.d(TAG, "Watch wear state: ${if (isWatchWorn) "Worn" else "Removed"}")
                    if (isWatchWorn) {
                        healthSDKManager.resumeAllTrackers()
                        startGooglePassiveMonitoring()
                        registerHeartRateSensor()
                    } else {
                        healthSDKManager.pauseAllTrackers()
                        healthServicesManager.stopPassiveCallback()
                    }
                    updateNotification()
                }
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    // ─────────────────────────────────────────────────────────────────────────
    // Setup Helpers
    // ─────────────────────────────────────────────────────────────────────────

    private fun initializeManagers() {
        mqttManager = MQTTManager { message ->
            Log.d(TAG, "MQTT message received: $message")
        }
        connectMQTT()

        healthSDKManager = HealthSDKManager(
            this,
            onConnected = {
                Log.d(TAG, "Samsung Health SDK connected")
                startSamsungTracking()
            },
            onResolution = { exception ->
                Log.e(TAG, "Samsung SDK resolution needed", exception)
                val resolutionIntent = Intent(this, TrackingActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    putExtra("samsung_sdk_resolution", true)
                }
                startActivity(resolutionIntent)
            },
            dataReceived = { type, dataPoints ->
                handleSamsungData(type, dataPoints)
            }
        )

        healthServicesManager = HealthServicesManager(this)
        healthSDKManager.connect()
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
                { dataPointContainer -> handleGooglePassiveData(dataPointContainer) },
                false
            )
            Log.d(TAG, "Google passive monitoring started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Google passive monitoring", e)
        }
    }

    private fun startSamsungTracking() {
        try {
            healthSDKManager.startTracker(HealthTrackerType.HEART_RATE_CONTINUOUS)
            Log.d(TAG, "Samsung heart rate tracking started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Samsung tracking", e)
        }
    }

    private fun setupBackgroundThread() {
        handlerThread = HandlerThread("VitalsServiceThread").apply { start() }
        serviceHandler = Handler(handlerThread.looper)
    }

    private fun setupWakeLock() {
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "MemoriaHome:VitalsWakeLock"
        ).apply {
            setReferenceCounted(false)
            acquire()
        }
        Log.d(TAG, "WakeLock acquired indefinitely")
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
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                .createNotificationChannel(channel)
        }
    }

    private fun startForegroundService() {
        try {
            val notification = NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("Memoria Home")
                .setContentText("Starting vitals monitoring...")
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build()

            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification,
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R)
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
                else 0
            )
            Log.d(TAG, "Foreground service started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start foreground service", e)
        }
    }

    private fun startVitalsTracking() {
        Log.d(TAG, "Vitals tracking started")
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Data Handlers
    // ─────────────────────────────────────────────────────────────────────────

    private fun handleSamsungData(type: HealthTrackerType, dataPoints: List<DataPoint?>) {
        coroutineScope.launch {
            for (data in dataPoints) {
                data ?: continue
                when (type) {
                    HealthTrackerType.HEART_RATE_CONTINUOUS -> {
                        val heartRate = data.getValue(ValueKey.HeartRateSet.HEART_RATE)
                        if (heartRate > 0) {
                            currentHeartRate = heartRate
                            Log.d(TAG, "Samsung SDK HR: $heartRate")
                            publishToMQTT("heart_rate", heartRate.toString())
                            updateNotification()
                            broadcastToUI()
                        }
                    }
                    else -> {}
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
                    Log.d(TAG, "Google Health Services HR: $heartRate")
                    publishToMQTT("heart_rate", heartRate.toString())
                    updateNotification()
                    broadcastToUI()
                }
            }
        }
    }

    private fun publishToMQTT(topic: String, value: String) {
        val currentTime = System.currentTimeMillis()
        if (currentTime - lastMqttPublishTime >= MQTT_PUBLISH_INTERVAL) {
            lastMqttPublishTime = currentTime
            coroutineScope.launch {
                try {
                    val payload = """{"type":"$topic","value":$value,"timestamp":$currentTime,"watchWorn":$isWatchWorn}"""
                    mqttManager.publish("watch-data", payload, 1)
                    Log.d(TAG, "MQTT Published: $payload")
                } catch (e: Exception) {
                    Log.e(TAG, "MQTT Publish failed", e)
                    if (e.message?.contains("not connected") == true) connectMQTT()
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
            .setContentTitle("Memoria Home — Monitoring Active")
            .setContentText("$currentHeartRate BPM | ${if (isWatchWorn) "Worn" else "Off Wrist"}")
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setContentIntent(pendingIntent)
            .build()

        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            notification,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R)
                ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
            else 0
        )
    }

    private fun broadcastToUI() {
        val intent = Intent(ACTION_VITALS_UPDATE).apply {
            putExtra(EXTRA_HEART_RATE, currentHeartRate)
            putExtra(EXTRA_SPO2, currentSpO2)
            putExtra(EXTRA_TIMESTAMP, System.currentTimeMillis())
        }
        LocalBroadcastManager.getInstance(this).sendBroadcast(intent)
    }

    private fun startOffBodyDetection() {
        offBodySensor = sensorManager.getDefaultSensor(Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT)
        offBodySensor?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
            Log.d(TAG, "Off-body detection started")
        } ?: Log.w(TAG, "Off-body sensor not available on this device")
    }
}