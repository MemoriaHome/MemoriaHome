package com.example.MemoriaHomeWatch.presentation

import android.content.Context
import android.util.Log
import androidx.health.services.client.HealthServices
import androidx.health.services.client.MeasureCallback
import androidx.health.services.client.PassiveListenerCallback
import androidx.health.services.client.PassiveListenerService
import androidx.health.services.client.data.Availability
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import androidx.health.services.client.data.DataTypeAvailability
import androidx.health.services.client.data.DeltaDataType
import androidx.health.services.client.data.PassiveListenerConfig

class PassiveDataService : PassiveListenerService() {
    override fun onNewDataPointsReceived(dataPoints: DataPointContainer) {
        val heartRatePoints = dataPoints.getData(DataType.HEART_RATE_BPM)
        for (point in heartRatePoints) {
            Log.d("PassiveDataService", "Background HR: ${point.value}")
        }
    }
}

class HealthServicesManager(
    private val context: Context
) {
    private val TAG = "HealthServicesManager" // FIX: was "TrackActivityy", copy-pasted from another file

    val healthClient = HealthServices.getClient(context)
    val measureClient = healthClient.measureClient
    private val activeMeasureCallbacks = mutableMapOf<DeltaDataType<*, *>, MeasureCallback>()
    private val activeDataReceivers = mutableMapOf<DeltaDataType<*, *>, (DataType<*, *>, DataPointContainer) -> Unit>()

    private var isPaused = false

    val passiveMonitoringClient = healthClient.passiveMonitoringClient

    fun startMeasuring(dataType: DeltaDataType<*, *>, dataReceived: (DataType<*, *>, DataPointContainer) -> Unit) {
        activeDataReceivers[dataType] = dataReceived
        val callback = object : MeasureCallback {
            override fun onAvailabilityChanged(dataType: DeltaDataType<*, *>, availability: Availability) {
                if (availability is DataTypeAvailability) {
                    Log.d(TAG, "Availability changed for ${dataType.name}: $availability")
                }
            }
            override fun onDataReceived(data: DataPointContainer) {
                if (!isPaused) dataReceived(dataType, data)
            }
        }
        // FIX: registerMeasureCallback can throw if the data type isn't supported
        // on this device or the permission hasn't been granted yet — was unguarded.
        try {
            measureClient.registerMeasureCallback(dataType, callback)
            activeMeasureCallbacks[dataType] = callback
            Log.d(TAG, "Started measuring ${dataType.name}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start measuring ${dataType.name}: ${e.message}")
        }
    }

    fun stopMeasuring(dataType: DeltaDataType<*, *>) {
        activeDataReceivers.remove(dataType)
        activeMeasureCallbacks[dataType]?.let { callback ->
            try {
                measureClient.unregisterMeasureCallbackAsync(dataType, callback)
                Log.d(TAG, "Stopped measuring ${dataType.name}")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to stop measuring ${dataType.name}: ${e.message}")
            } finally {
                activeMeasureCallbacks.remove(dataType)
            }
        } ?: Log.d(TAG, "Tracker ${dataType.name} is not active")
    }

    fun pauseAllMeasuring() {
        isPaused = true
        activeMeasureCallbacks.forEach { (dataType, callback) ->
            try {
                measureClient.unregisterMeasureCallbackAsync(dataType, callback)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to pause ${dataType.name}: ${e.message}")
            }
        }
        activeMeasureCallbacks.clear()
        Log.d(TAG, "All measuring paused")
    }

    fun resumeAllMeasuring() {
        activeDataReceivers.forEach { (dataType, dataReceived) ->
            val callback = object : MeasureCallback {
                override fun onAvailabilityChanged(dataType: DeltaDataType<*, *>, availability: Availability) {
                    if (availability is DataTypeAvailability) {
                        Log.d(TAG, "Availability changed for ${dataType.name}: $availability")
                    }
                }
                override fun onDataReceived(data: DataPointContainer) {
                    if (!isPaused) dataReceived(dataType, data)
                }
            }
            try {
                measureClient.registerMeasureCallback(dataType, callback)
                activeMeasureCallbacks[dataType] = callback
            } catch (e: Exception) {
                Log.e(TAG, "Failed to resume ${dataType.name}: ${e.message}")
            }
        }
        isPaused = false
        Log.d(TAG, "All measuring resumed")
    }

    fun resetAllMeasuring() {
        pauseAllMeasuring()
        activeDataReceivers.clear()
        isPaused = false
        Log.d(TAG, "All measuring reset")
    }

    fun startPassiveMonitoring(dataType: Set<DataType<*, *>>, dataReceived: (DataPointContainer) -> Unit, useService: Boolean) {
        val passiveListenerConfig = PassiveListenerConfig.builder()
            .setDataTypes(dataType)
            .build()
        Log.d(TAG, "Starting passive monitoring")

        // FIX: this can throw if BODY_SENSORS_BACKGROUND / READ_HEALTH_DATA_IN_BACKGROUND
        // hasn't been granted yet — critical now that StartupReceiver calls this on boot,
        // before the user has necessarily opened PermissionActivity.
        try {
            if (useService) {
                Log.d(TAG, "Using Passive Data Service")
                passiveMonitoringClient.setPassiveListenerServiceAsync(PassiveDataService::class.java, passiveListenerConfig)
            } else {
                Log.d(TAG, "Using Passive Data Callback")
                val passiveListenerCallback: PassiveListenerCallback =
                    object : PassiveListenerCallback {
                        override fun onNewDataPointsReceived(dataPoints: DataPointContainer) {
                            dataReceived(dataPoints)
                        }
                    }
                passiveMonitoringClient.setPassiveListenerCallback(passiveListenerConfig, passiveListenerCallback)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start passive monitoring: ${e.message}")
        }
    }

    fun stopPassiveCallback() {
        try {
            passiveMonitoringClient.clearPassiveListenerCallbackAsync()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to clear passive callback: ${e.message}")
        }
    }

    fun stopPassiveService() {
        try {
            passiveMonitoringClient.clearPassiveListenerServiceAsync()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to clear passive service: ${e.message}")
        }
    }
}