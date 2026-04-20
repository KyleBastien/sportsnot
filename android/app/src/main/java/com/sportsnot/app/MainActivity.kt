package com.sportsnot.app

import com.getcapacitor.BridgeActivity
import com.sportsnot.app.plugins.WidgetBridgePlugin

class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: android.os.Bundle?) {
        registerPlugin(WidgetBridgePlugin::class.java)
        super.onCreate(savedInstanceState)
    }
}
