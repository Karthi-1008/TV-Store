package org.tvstore.remotebridge

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.accessibility.AccessibilityManager
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.ListView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {

    private lateinit var tvStatus: TextView
    private lateinit var btnSettings: Button
    private lateinit var lvPackages: ListView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        tvStatus = findViewById(R.id.tvStatus)
        btnSettings = findViewById(R.id.btnSettings)
        lvPackages = findViewById(R.id.lvPackages)

        btnSettings.setOnClickListener {
            val intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            startActivity(intent)
        }
    }

    override fun onResume() {
        super.onResume()
        updateServiceStatus()
        refreshRegisteredPackages()
    }

    private fun updateServiceStatus() {
        val isEnabled = isAccessibilityServiceEnabled(this, RemoteBridgeService::class.java)
        if (isEnabled) {
            tvStatus.text = getString(R.string.status_enabled)
            tvStatus.setTextColor(ContextCompat.getColor(this, R.color.status_green))
        } else {
            tvStatus.text = getString(R.string.status_disabled)
            tvStatus.setTextColor(ContextCompat.getColor(this, R.color.status_red))
        }
    }

    private fun refreshRegisteredPackages() {
        val packages = ConvertedAppsRegistry.getRegisteredPackages(this).sorted()
        val adapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, packages)
        lvPackages.adapter = adapter
    }

    private fun isAccessibilityServiceEnabled(
        context: Context,
        serviceClass: Class<out android.accessibilityservice.AccessibilityService>
    ): Boolean {
        val am = context.getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
        val enabledServices =
            am.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
        for (service in enabledServices) {
            val id = service.resolveInfo.serviceInfo
            if (id.packageName == context.packageName && id.name == serviceClass.name) {
                return true
            }
        }
        return false
    }
}
