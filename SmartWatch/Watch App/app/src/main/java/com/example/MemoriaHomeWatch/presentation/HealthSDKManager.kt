package com.example.MemoriaHomeWatch.presentation

import android.content.Context
import android.util.Log
import com.samsung.android.service.health.tracking.ConnectionListener
import com.samsung.android.service.health.tracking.HealthTracker
import com.samsung.android.service.health.tracking.HealthTracker.TrackerError
import com.samsung.android.service.health.tracking.HealthTracker.TrackerEventListener
import com.samsung.android.service.health.tracking.HealthTrackerException
import com.samsung.android.service.health.tracking.HealthTrackingService
import com.samsung.android.service.health.tracking.data.DataPoint
import com.samsung.android.service.health.tracking.data.HealthTrackerType

class HealthSDKManager (
    private val context: Context,
    private val onConnected: () -> Unit,
    private val onResolution: (HealthTrackerException) -> Unit,         // function to be called when resolution is required (see the onConnectionFailed function bellow)
    private val dataReceived: (HealthTrackerType, List<DataPoint?>) -> Unit    // function to be called when data is received (see the onDataReceived function bellow) (mainly to pass data to another activity)
    ) {
    private val TAG = "TrackActivityy"
    private var isConnected = false
    private var activeTrackers = mutableMapOf<HealthTrackerType, HealthTracker>()
    private var activeListeners = mutableMapOf<HealthTrackerType, TrackerEventListener>()
    lateinit var healthTrackingService: HealthTrackingService

    // handles connection to Health Tracking Service
    val connectionListener = object : ConnectionListener {
        override fun onConnectionSuccess() {  // do when connected
            Log.d(TAG, "Connection success")
            Log.d(TAG, "SDK Connection success")
            isConnected = true
            onConnected()
        }

        override fun onConnectionEnded() { // do when disconnects (or when app/activity is closed)
            resetAllTrackers()
            isConnected = false
            Log.d(TAG, "Connection ENDED")
        }

        override fun onConnectionFailed(e: HealthTrackerException) { // do when connection fails
            isConnected = false
            if (e.hasResolution()) {
                onResolution(e)
                Log.d(TAG, "Connection FAILED")
            }
        }
    }

    // creates a listener for each sensor type (when u start monitoring multiple sensors)
    private fun createListenerForType(type: HealthTrackerType): TrackerEventListener{
        return object : TrackerEventListener {
            override fun onError(error: TrackerError?) {
                Log.d(TAG, "TRACKER ERRORRRR!!!!!!!!!!! : $error")
            }

            override fun onDataReceived(p0: List<DataPoint?>) { // do when listener receives data
                if (p0.isNotEmpty()) {
                    dataReceived(type, p0)  // passes the data to the function defined in the trackingActivity
                } else {
                    Log.d(TAG, "No heart rate data received")
                }
            }
            override fun onFlushCompleted() {

            }
        }
    }
    fun connect() {
        Log.d(TAG, "Connecting to Health Tracking Service..")
        healthTrackingService = HealthTrackingService(connectionListener, context)
        healthTrackingService.connectService()
    }
    fun disconnect(){   // reset all trackers and disconnect from service
        resetAllTrackers()
        if(::healthTrackingService.isInitialized) { healthTrackingService.disconnectService() }
        isConnected = false
    }

    fun startTracker(type: HealthTrackerType) {
        if(!isConnected) {
            Log.d(TAG, "Health Tracking service is not connected")
            return
        }
        try{
            val tracker = healthTrackingService.getHealthTracker(type)
            val listener = createListenerForType(type)

            tracker.setEventListener(listener)

            activeTrackers[type] = tracker
            activeListeners[type] = listener

            Log.d(TAG, "Started tracking ${type.name}")
        } catch (e: Exception){
            Log.d(TAG, "Error starting ${type.name} ${e.message}:")
        }
    }

    fun stopTracker(type: HealthTrackerType) {
        activeTrackers[type]?.let { tracker ->
            tracker.unsetEventListener()
            activeTrackers.remove(type)
            activeListeners.remove(type)
            Log.d(TAG, "Stopped tracking")
            return
        }
        Log.d(TAG, "Tracker ${type.name} is not active")
    }

    fun pauseAllTrackers(){     // used for when the watch is removed (pauses but never deletes registered sensors - can be resumed through the resumeAllTrackers())
        activeTrackers.values.forEach { it.unsetEventListener() }
        Log.d(TAG, "All trackers paused")
    }

    fun resumeAllTrackers(){   // gets called when the watch is re-added (resumes all registered sensors)
        val types = activeTrackers.keys.toList()
        resetAllTrackers()
        types.forEach { startTracker(it) }
    }

    fun flushTracker(tracker: HealthTrackerType) {   // Flushing data gives collected data instantly.
        if(tracker in activeTrackers.keys){
            activeTrackers[tracker]?.flush()
            Log.d(TAG, "Flushed tracker ${tracker.name}")
        }
    }

    fun resetAllTrackers(){   // gets called when the app is closed or service disconnect (deletes all registered sensors)
        pauseAllTrackers()
        activeTrackers.clear()
        activeListeners.clear()
    }
}