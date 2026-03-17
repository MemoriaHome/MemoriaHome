package com.example.MemoriaHomeWatch.presentation

import android.content.Intent
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.lifecycleScope
import androidx.wear.compose.material.Button
import androidx.wear.compose.material.ButtonDefaults
import androidx.wear.compose.material.Icon
import androidx.wear.compose.material.Text
import androidx.wear.tooling.preview.devices.WearDevices
import com.example.MemoriaHomeWatch.BuildConfig
import com.example.MemoriaHomeWatch.R
import com.example.MemoriaHomeWatch.presentation.theme.ConnectToHubTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch


class MainActivity : ComponentActivity() {

    companion object {
        lateinit var mqtt: MQTTManager

    }


    private var receivedMessage by mutableStateOf("No message received")


    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        setTheme(android.R.style.Theme_DeviceDefault)

        mqtt = MQTTManager { message ->
            receivedMessage = message
        }
        mqtt.mqttConnect(BuildConfig.MQTT_BROKER, BuildConfig.MQTT_USERNAME, BuildConfig.MQTT_PASSWORD, false ) // retrieves MQTT_BROKER from /local.properties *see gradle.kts(:app)*

        setContent {
            ConnectToHubTheme {
                WearApp(
                    message = receivedMessage,
                    onButtonClick1 = { mqtt.mqttSubscribe("to-watch", 1) },
                    onButtonClick2 = { mqtt.publish("watch-data", "this is a test", 1) },
                    onButtonClick3 = { startActivity(Intent(this, PermissionActivity::class.java)) }
                )
            }
        }
    }
}



@Composable
fun WearApp(onButtonClick1: () -> Unit, onButtonClick2: () -> Unit, onButtonClick3: () -> Unit, message: String) {
    Column(
        modifier = Modifier.fillMaxSize(),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(text = message)
        Spacer(modifier = Modifier.height(20.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center
        ) {
            Button(
                modifier = Modifier.size(ButtonDefaults.DefaultButtonSize),
                onClick = onButtonClick1,
                enabled = true
            ) {
                Icon(
                    painter = painterResource(id = R.drawable.ic_subscribe),
                    contentDescription = "subscribe",
                    modifier = Modifier.size(24.dp)
                )
            }
            Spacer(modifier = Modifier.width(20.dp))
            Button(
                modifier = Modifier.size(ButtonDefaults.DefaultButtonSize),
                onClick = onButtonClick2,
                enabled = true
            ) {
                Icon(
                    painter = painterResource(id = R.drawable.ic_send),
                    contentDescription = "send",
                    modifier = Modifier.size(24.dp)
                )
            }
            Spacer(modifier = Modifier.width(20.dp))
            Button(
                modifier = Modifier.size(ButtonDefaults.DefaultButtonSize),
                onClick = onButtonClick3,
                enabled = true
            ) {
                Icon(painter = painterResource(id = R.drawable.ic_connect),
                    contentDescription = "health", modifier = Modifier.size(24.dp))
            }

        }

    }
}

@Preview(device = WearDevices.SMALL_ROUND, showSystemUi = true)
@Composable
fun DefaultPreview() {
    WearApp (message = "No message received", onButtonClick1 = {}, onButtonClick2 = {}, onButtonClick3 = {})
}
