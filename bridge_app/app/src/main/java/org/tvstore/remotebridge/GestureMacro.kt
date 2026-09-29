package org.tvstore.remotebridge

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.util.Log

object GestureMacro {

    private const val TAG = "TVRemoteBridge_Gesture"

    /**
     * Dispatch synthetic tap at (x, y) coordinates.
     * Uses moveTo + lineTo to ensure a valid non-empty path contour across all Android versions.
     */
    fun performTap(
        service: AccessibilityService,
        x: Float,
        y: Float,
        onComplete: (() -> Unit)? = null
    ): Boolean {
        return try {
            val path = Path().apply {
                moveTo(x, y)
                lineTo(x, y)
            }
            val stroke = GestureDescription.StrokeDescription(path, 0, 80)
            val gesture = GestureDescription.Builder().addStroke(stroke).build()

            service.dispatchGesture(gesture, object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) {
                    Log.d(TAG, "Tap gesture successfully dispatched at ($x, $y)")
                    onComplete?.invoke()
                }

                override fun onCancelled(gestureDescription: GestureDescription?) {
                    Log.w(TAG, "Tap gesture cancelled by system at ($x, $y)")
                }
            }, null)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to dispatch tap gesture", e)
            false
        }
    }

    /**
     * Dispatch synthetic long press at (x, y) coordinates (duration ~650ms).
     */
    fun performLongPress(
        service: AccessibilityService,
        x: Float,
        y: Float,
        durationMs: Long = 650,
        onComplete: (() -> Unit)? = null
    ): Boolean {
        return try {
            val path = Path().apply {
                moveTo(x, y)
                lineTo(x, y)
            }
            val stroke = GestureDescription.StrokeDescription(path, 0, durationMs)
            val gesture = GestureDescription.Builder().addStroke(stroke).build()

            service.dispatchGesture(gesture, object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) {
                    Log.d(TAG, "Long-press gesture completed at ($x, $y)")
                    onComplete?.invoke()
                }

                override fun onCancelled(gestureDescription: GestureDescription?) {
                    Log.w(TAG, "Long-press gesture cancelled at ($x, $y)")
                }
            }, null)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to dispatch long-press gesture", e)
            false
        }
    }

    /**
     * Dispatch synthetic swipe from (startX, startY) to (endX, endY).
     */
    fun performSwipe(
        service: AccessibilityService,
        startX: Float,
        startY: Float,
        endX: Float,
        endY: Float,
        durationMs: Long = 250,
        onComplete: (() -> Unit)? = null
    ): Boolean {
        return try {
            val path = Path().apply {
                moveTo(startX, startY)
                lineTo(endX, endY)
            }
            val stroke = GestureDescription.StrokeDescription(path, 0, durationMs)
            val gesture = GestureDescription.Builder().addStroke(stroke).build()

            service.dispatchGesture(gesture, object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) {
                    onComplete?.invoke()
                }

                override fun onCancelled(gestureDescription: GestureDescription?) {
                    // Fail-silent
                }
            }, null)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to dispatch swipe gesture", e)
            false
        }
    }
}
