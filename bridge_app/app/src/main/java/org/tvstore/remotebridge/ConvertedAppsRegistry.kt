package org.tvstore.remotebridge

import android.content.Context
import android.content.pm.PackageManager
import java.util.concurrent.ConcurrentHashMap

data class AppConversionInfo(
    val isConverted: Boolean,
    val mode: String, // "auto" | "pointer" | "navigate"
    val timestamp: Long = System.currentTimeMillis()
)

object ConvertedAppsRegistry {

    const val META_CONVERTED = "org.tvstore.converted"
    const val META_MODE = "org.tvstore.mode"
    private const val CACHE_TTL_MS = 60_000L // 60 seconds cache

    private val packageCache = ConcurrentHashMap<String, AppConversionInfo>()

    // Fallback set for test/demo apps or older conversions
    private val HARDCODED_FALLBACKS = mapOf(
        "mark.via.gp" to "auto",
        "com.gokadzev.musify" to "navigate",
        "com.prismtv.gallery" to "navigate"
    )

    fun isSystemOrLauncher(packageName: String): Boolean {
        return packageName.startsWith("com.google.android.tvlauncher") ||
                packageName.startsWith("com.google.android.leanbacklauncher") ||
                packageName.startsWith("com.android.systemui") ||
                packageName.startsWith("com.android.tv.settings") ||
                packageName == "android" ||
                packageName == "org.tvstore.remotebridge"
    }

    /**
     * Check if a package was converted by TV-Store by querying its manifest meta-data.
     */
    fun isRegistered(context: Context, packageName: String): Boolean {
        if (packageName.isBlank() || isSystemOrLauncher(packageName)) {
            return false
        }

        val cached = packageCache[packageName]
        val now = System.currentTimeMillis()
        if (cached != null && (now - cached.timestamp) < CACHE_TTL_MS) {
            return cached.isConverted
        }

        val info = queryPackageInfo(context, packageName)
        packageCache[packageName] = info
        return info.isConverted
    }

    /**
     * Get preferred navigation mode for this package: "auto", "pointer", or "navigate".
     */
    fun getMode(context: Context, packageName: String): String {
        if (!isRegistered(context, packageName)) return "navigate"
        return packageCache[packageName]?.mode ?: "auto"
    }

    private fun queryPackageInfo(context: Context, packageName: String): AppConversionInfo {
        try {
            val pm = context.packageManager
            val appInfo = pm.getApplicationInfo(packageName, PackageManager.GET_META_DATA)
            val bundle = appInfo.metaData

            if (bundle != null && (bundle.containsKey(META_CONVERTED) || bundle.get(META_CONVERTED) != null)) {
                val mode = bundle.getString(META_MODE)
                    ?: (if (bundle.getInt(META_MODE, -1) != -1) bundle.getInt(META_MODE).toString() else "auto")
                return AppConversionInfo(isConverted = true, mode = mode)
            }
        } catch (_: Exception) {
            // Fail-silent
        }

        // Check fallback
        if (HARDCODED_FALLBACKS.containsKey(packageName)) {
            return AppConversionInfo(isConverted = true, mode = HARDCODED_FALLBACKS[packageName] ?: "auto")
        }

        return AppConversionInfo(isConverted = false, mode = "navigate")
    }

    /**
     * Query all installed apps that declare org.tvstore.converted meta-data.
     */
    fun getInstalledConvertedApps(context: Context): List<Pair<String, String>> {
        val results = mutableListOf<Pair<String, String>>()
        try {
            val pm = context.packageManager
            val apps = pm.getInstalledApplications(PackageManager.GET_META_DATA)
            for (app in apps) {
                if (isSystemOrLauncher(app.packageName)) continue
                val bundle = app.metaData
                if (bundle != null && (bundle.containsKey(META_CONVERTED) || bundle.get(META_CONVERTED) != null)) {
                    val mode = bundle.getString(META_MODE) ?: "auto"
                    results.add(Pair(app.packageName, mode))
                    packageCache[app.packageName] = AppConversionInfo(true, mode)
                } else if (HARDCODED_FALLBACKS.containsKey(app.packageName)) {
                    val mode = HARDCODED_FALLBACKS[app.packageName] ?: "auto"
                    results.add(Pair(app.packageName, mode))
                    packageCache[app.packageName] = AppConversionInfo(true, mode)
                }
            }
        } catch (_: Exception) {
            // Fail-silent
        }
        return results
    }
}
