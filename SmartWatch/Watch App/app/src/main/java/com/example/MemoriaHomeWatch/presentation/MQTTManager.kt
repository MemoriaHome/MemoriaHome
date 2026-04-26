package com.example.MemoriaHomeWatch.presentation

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken
import org.eclipse.paho.client.mqttv3.MqttCallback
import org.eclipse.paho.client.mqttv3.MqttClient
import org.eclipse.paho.client.mqttv3.MqttConnectOptions
import org.eclipse.paho.client.mqttv3.MqttException
import org.eclipse.paho.client.mqttv3.MqttMessage
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence

class MQTTManager(
    private val onMessageReceived: (String) -> Unit
) {
    private lateinit var mqttClient: MqttClient
    private lateinit var connOptions: MqttConnectOptions

    fun mqttConnect(brokeraddr: String, username: String, password: String, isCleanSession: Boolean) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                if (::mqttClient.isInitialized && mqttClient.isConnected) {
                    Log.d("MQTT", "Already connected, skipping.")
                    return@launch
                }

                connOptions = MqttConnectOptions().apply {
                    userName = username         // retrieves MQTT_USERNAME from local.properties *see gradle.kts(:app)*
                    this.password = password.toCharArray() // retrieves MQTT_PASSWORD from local.properties

                    this.isCleanSession = isCleanSession   // (false) -> both the client and server will maintain state across restarts of the client, the server and the connection.
                    //             Server will keep track of Subscription & QOS if the client, server or connection are restarted.
                    // (true) -> the client and server will not maintain state across restarts of the client, the server or the connection.
                    //            Server will not keep track of Subscriptions & QOS cannot be maintained if the client, server or connection are restarted

                    this.connectionTimeout = 5
                }

                if (!::mqttClient.isInitialized) {
                    val clientId = "MemoriaWatch_${android.os.Build.MODEL}" // Consistent ID
                    mqttClient = MqttClient("tcp://$brokeraddr:1883", clientId, MemoryPersistence())
                } else if (mqttClient.serverURI != "tcp://$brokeraddr:1883") {
                    // IP changed, recreate client
                    if (mqttClient.isConnected) mqttClient.disconnect()
                    val clientId = "MemoriaWatch_${android.os.Build.MODEL}"
                    mqttClient = MqttClient("tcp://$brokeraddr:1883", clientId, MemoryPersistence())
                }

                mqttClient.connect(connOptions)
                Log.d("MQTT", "Connected!")

                mqttSetReceiveListener()

            } catch (e: MqttException) {
                Log.e("MQTT", "Connection failed: ${e.message}")
                e.printStackTrace()
            }
        }
    }

    fun publish(topic: String, msg: String, qos: Int) {
        try {
            val mqttMessage = MqttMessage(msg.toByteArray(charset("UTF-8")))

            mqttMessage.qos = qos   // quality of service :
            // 0 -> (at most once, fire & forget, no delivery guarantee, fast);
            // 1 -> (at least once, guarantees message delivery, may result in duplicates, best for IoT)
            // 2 -> (Exactly once, ensures a message is delivered once via a four-step handshake, highest reliability level)
            mqttMessage.isRetained = false // (True) : the broker stores the latest message for a topic for when subscribers reconnect
            // Publish the message
            mqttClient.publish(topic, mqttMessage)
        } catch (e: Exception) {
            Log.e("MQTT", "Publish failed: ${e.message}")
        }
    }

    fun mqttSubscribe(topic: String, qos: Int) {
        try {
            mqttClient.subscribe(topic, qos)
        } catch (e: Exception) {
            Log.e("MQTT", "Subscribe failed: ${e.message}")
        }

    }

    fun mqttSetReceiveListener() {
        mqttClient.setCallback(object : MqttCallback {
            override fun connectionLost(cause: Throwable) {
                Log.e("MQTT", "Connection lost: ${cause.message}")
                CoroutineScope(Dispatchers.IO).launch {
                    var attempts = 0
                    while (!mqttClient.isConnected && attempts < 5) {
                        attempts++
                        Log.d("MQTT", "Reconnect attempt $attempts...")
                        try {
                            delay(3000L * attempts)
                            mqttClient.connect(connOptions)
                            Log.d("MQTT", "Reconnected on attempt $attempts!")
                        } catch (e: MqttException) {
                            Log.e("MQTT", "Attempt $attempts failed: ${e.message}")
                        }
                    }
                    if(!mqttClient.isConnected) Log.e("MQTT", "Gave up reconnecting after $attempts attempts, Restart tracking to connect")
                }
            }
            override fun messageArrived(topic: String, message: MqttMessage) {
                // A message has been received
                val data = String(message.payload, charset("UTF-8")) // payload is the inner text or value of a mqtt message
                Log.d("MQTT", "Message Arrived : $data")
                // Place the message onto screen
                CoroutineScope(Dispatchers.Main).launch {
                    onMessageReceived(data)
                }
            }
            override fun deliveryComplete(token: IMqttDeliveryToken) {
            }
        })
    }
}