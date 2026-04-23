package com.example.MemoriaHomeWatch.presentation

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.wear.compose.material.Button
import androidx.wear.compose.material.Text
import androidx.wear.tooling.preview.devices.WearDevices
import com.example.MemoriaHomeWatch.BuildConfig
import com.example.MemoriaHomeWatch.presentation.theme.ConnectToHubTheme


class MainActivity : ComponentActivity() {

    companion object {
        lateinit var mqtt: MQTTManager
        var ipAddress by mutableStateOf("")
    }

    private var receivedMessage by mutableStateOf("No message received")

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        setTheme(android.R.style.Theme_DeviceDefault)

        mqtt = MQTTManager { message ->
            receivedMessage = message
        }

        setContent {
            ConnectToHubTheme {
                WearApp(
                    message = receivedMessage,
                    ipAddress = ipAddress,
                    onIpChange = { ipAddress = it },
                    startClicked = { mqtt.mqttConnect(ipAddress, BuildConfig.MQTT_USERNAME, BuildConfig.MQTT_PASSWORD, false)
                        receivedMessage = "reconnecting to $ipAddress.." },
                    reconnectClicked = {
                        mqtt.mqttConnect(ipAddress, BuildConfig.MQTT_USERNAME, BuildConfig.MQTT_PASSWORD, false)
                        receivedMessage = "connecting to $ipAddress.."
                        startActivity(Intent(this, PermissionActivity::class.java))
                    }
                )
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
    }
}

@Composable
fun WearApp(
    startClicked: () -> Unit,
    reconnectClicked: () -> Unit,
    message: String,
    ipAddress: String,
    onIpChange: (String) -> Unit
) {
    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "Enter MQTT Server IP",
            style = androidx.wear.compose.material.MaterialTheme.typography.caption2,
            color = androidx.compose.ui.graphics.Color.Gray,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center
        )
        Spacer(modifier = Modifier.height(6.dp))
        BasicTextField(
            value = ipAddress,
            onValueChange = onIpChange,
            singleLine = true,
            textStyle = androidx.compose.ui.text.TextStyle(
                color = androidx.compose.ui.graphics.Color.White,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center
            ),
            decorationBox = { inner ->
                if (ipAddress.isEmpty()) {
                    Text(
                        "e.g. 192.168.1.1",
                        style = androidx.wear.compose.material.MaterialTheme.typography.caption2,
                        color = androidx.compose.ui.graphics.Color.DarkGray
                    )
                }
                inner()
            }
        )
        Spacer(modifier = Modifier.height(4.dp))
        Text(
            text = message,
            style = androidx.wear.compose.material.MaterialTheme.typography.caption3,
            color = androidx.compose.ui.graphics.Color.Gray,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center
        )
        Spacer(modifier = Modifier.height(10.dp))
        Button(
            onClick = reconnectClicked,
            modifier = Modifier.fillMaxWidth(0.7f).height(32.dp)
        ) {
            Text(
                text = "Connect & Start",
                style = androidx.wear.compose.material.MaterialTheme.typography.caption2
            )
        }
        Spacer(modifier = Modifier.height(6.dp))
        Button(
            onClick = startClicked,
            modifier = Modifier.fillMaxWidth(0.7f).height(32.dp),
            colors = androidx.wear.compose.material.ButtonDefaults.buttonColors(
                backgroundColor = androidx.compose.ui.graphics.Color(0xFF424242)
            )
        ) {
            Text(
                text = "Reconnect MQTT",
                style = androidx.wear.compose.material.MaterialTheme.typography.caption2
            )
        }
    }
}

@Preview(device = WearDevices.SMALL_ROUND, showSystemUi = true)
@Composable
fun DefaultPreview() {
    WearApp(
        message = "No message received",
        ipAddress = "",
        onIpChange = {},
        startClicked = {},
        reconnectClicked = {}
    )
}