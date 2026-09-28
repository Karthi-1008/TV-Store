package org.tvstore.remotebridge

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path

object GestureMacro {

    /**
     * Dispatch synthetic tap at (x, y) coordinates.
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
            }
            val stroke = GestureDescription.StrokeDescription(path, 0, 50)
            val gesture = GestureDescription.Builder().addStroke(stroke).build()

            service.dispatchGesture(gesture, object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) {
                    onComplete?.invoke()
                }

                override fun onCancelled(gestureDescription: GestureDescription?) {
                    // Fail-silent
                }
            }, null)
        } catch (_: Exception) {
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
        } catch (_: Exception) {
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
        } catch (_: Exception) {
            false
        }
    }
}
