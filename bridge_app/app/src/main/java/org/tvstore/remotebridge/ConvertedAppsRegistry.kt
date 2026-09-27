package org.tvstore.remotebridge

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import java.io.File

object ConvertedAppsRegistry {

    private const val PREFS_NAME = "tv_bridge_registry"
    private const val KEY_PACKAGES = "registered_packages"

    // Default pre-registered packages for testing/demo
    private val DEFAULT_PACKAGES = setOf(
        "com.gokadzev.musify",
        "com.prismtv.gallery"
    )

    private fun getPrefs(context: Context): SharedPreferences {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    }

    /**
     * Retrieve all currently registered package names.
     */
    fun getRegisteredPackages(context: Context): Set<String> {
        val prefs = getPrefs(context)
        val saved = prefs.getStringSet(KEY_PACKAGES, null)
        val result = (saved ?: DEFAULT_PACKAGES).toMutableSet()

        // Also check if a JSON file was placed in external storage
        try {
            val extFile = File(context.getExternalFilesDir(null), "converted_packages.json")
            if (extFile.exists()) {
                val jsonStr = extFile.readText()
                val jsonArr = JSONArray(jsonStr)
                for (i in 0 until jsonArr.length()) {
                    result.add(jsonArr.getString(i))
                }
            }
        } catch (_: Exception) {
            // Fail-silent
        }

        return result
    }

    /**
     * Check if the given package is allowed to be handled by the bridge.
     */
    fun isRegistered(context: Context, packageName: String): Boolean {
        // Never intercept Android TV Launcher or System UI
        if (isSystemOrLauncher(packageName)) {
            return false
        }
        return getRegisteredPackages(context).contains(packageName)
    }

    /**
     * Register a new package name.
     */
    fun registerPackage(context: Context, packageName: String): Boolean {
        if (packageName.isBlank() || isSystemOrLauncher(packageName)) return false
        val current = getRegisteredPackages(context).toMutableSet()
        current.add(packageName.trim())
        return getPrefs(context).edit().putStringSet(KEY_PACKAGES, current).commit()
    }

    /**
     * Unregister a package name.
     */
    fun unregisterPackage(context: Context, packageName: String): Boolean {
        val current = getRegisteredPackages(context).toMutableSet()
        val removed = current.remove(packageName.trim())
        if (removed) {
            getPrefs(context).edit().putStringSet(KEY_PACKAGES, current).apply()
        }
        return removed
    }

    private fun isSystemOrLauncher(packageName: String): Boolean {
        return packageName.startsWith("com.google.android.tvlauncher") ||
                packageName.startsWith("com.google.android.leanbacklauncher") ||
                packageName.startsWith("com.android.systemui") ||
                packageName.startsWith("com.android.tv.settings") ||
                packageName == "android" ||
                packageName == "org.tvstore.remotebridge"
    }
}
