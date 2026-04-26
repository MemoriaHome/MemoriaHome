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
import kotlin.math.log
import kotlin.text.clear
import kotlin.text.set

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
    val TAG = "TrackActivityy"

    val healthClient = HealthServices.getClient(context)
    val measureClient = healthClient.measureClient
    private val activeMeasureCallbacks = mutableMapOf<DeltaDataType<*, *>, MeasureCallback>()
    private val activeDataReceivers = mutableMapOf<DeltaDataType<*, *>, (DataType<*, *>, DataPointContainer) -> Unit>()

    private var isPaused = false

    val passiveMonitoringClient = healthClient.passiveMonitoringClient


    fun startMeasuring(dataType: DeltaDataType<*, *>, dataReceived: (DataType<*, *>, DataPointContainer) -> Unit){
        Log.d(TAG, "Connected to Health client")
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
        measureClient.registerMeasureCallback(dataType, callback)
        activeMeasureCallbacks[dataType] = callback
    }

    fun stopMeasuring(dataType: DeltaDataType<*, *>){
        activeDataReceivers.remove(dataType)
        activeMeasureCallbacks[dataType]?.let {
            callback ->
            measureClient.unregisterMeasureCallbackAsync(dataType, callback)
            activeMeasureCallbacks.remove(dataType)
            Log.d(TAG, "Stopped measuring ${dataType.name}")
        } ?: Log.d(TAG, "Tracker ${dataType.name} is not active")

    }


    fun pauseAllMeasuring() {
        isPaused = true
        activeMeasureCallbacks.forEach { (dataType, callback) ->
            measureClient.unregisterMeasureCallbackAsync(dataType, callback)
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
            measureClient.registerMeasureCallback(dataType, callback)
            activeMeasureCallbacks[dataType] = callback
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

    // passive monitoring Service's not ready yet
    // PassiveMonitoringClient only allows one callback to be registered at a time for the whole app
    // the second call will replace the first one
    fun startPassiveMonitoring(dataType: Set<DataType<*, *>>, dataReceived: (DataPointContainer) -> Unit, useService: Boolean){
        val passiveListenerConfig = PassiveListenerConfig.builder()
            .setDataTypes(dataType)
            .build()
        Log.d(TAG, "Starting passive monitoring")

        if(useService){
            Log.d(TAG, "Using Passive Data Service")
            passiveMonitoringClient.setPassiveListenerServiceAsync(PassiveDataService::class.java, passiveListenerConfig)
        } else{
            Log.d(TAG, "Using Passive Data Callback")
            val passiveListenerCallback: PassiveListenerCallback =
                object : PassiveListenerCallback {
                    override fun onNewDataPointsReceived(dataPoints: DataPointContainer) {
                        dataReceived(dataPoints)
                    }
                }
            passiveMonitoringClient.setPassiveListenerCallback(passiveListenerConfig, passiveListenerCallback)
        }
    }

    fun stopPassiveCallback(){
        passiveMonitoringClient.clearPassiveListenerCallbackAsync()
    }
    fun stopPassiveService(){
        passiveMonitoringClient.clearPassiveListenerServiceAsync()
    }

}

