package org.tvstore.remotebridge

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class PackageReceiver : BroadcastReceiver() {

    companion object {
        const val ACTION_REGISTER = "org.tvstore.remotebridge.ACTION_REGISTER_PACKAGE"
        const val ACTION_UNREGISTER = "org.tvstore.remotebridge.ACTION_UNREGISTER_PACKAGE"
        const val EXTRA_PACKAGE = "package_name"
    }

    override fun onReceive(context: Context?, intent: Intent?) {
        if (context == null || intent == null) return
        val pkg = intent.getStringExtra(EXTRA_PACKAGE) ?: return

        when (intent.action) {
            ACTION_REGISTER -> {
                ConvertedAppsRegistry.registerPackage(context, pkg)
            }
            ACTION_UNREGISTER -> {
                ConvertedAppsRegistry.unregisterPackage(context, pkg)
            }
        }
    }
}
