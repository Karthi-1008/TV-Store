package org.tvstore.remotebridge

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import kotlin.math.abs

enum class Direction {
    UP, DOWN, LEFT, RIGHT
}

data class FocusCandidate(
    val node: AccessibilityNodeInfo,
    val bounds: Rect
)

object SpatialNavigator {

    /**
     * Recursively collect all interactive nodes with valid screen bounds.
     */
    fun findInteractiveNodes(
        root: AccessibilityNodeInfo?,
        screenWidth: Int,
        screenHeight: Int
    ): List<FocusCandidate> {
        val results = mutableListOf<FocusCandidate>()
        if (root == null) return results

        fun traverse(node: AccessibilityNodeInfo) {
            val bounds = Rect()
            node.getBoundsInScreen(bounds)

            val isVisibleOnScreen = bounds.width() > 10 && bounds.height() > 10 &&
                    bounds.right > 0 && bounds.bottom > 0 &&
                    bounds.left < screenWidth && bounds.top < screenHeight

            if (isVisibleOnScreen && (node.isClickable || node.isFocusable || node.isCheckable)) {
                results.add(FocusCandidate(node, bounds))
            }

            for (i in 0 until node.childCount) {
                val child = node.getChild(i) ?: continue
                traverse(child)
            }
        }

        try {
            traverse(root)
        } catch (_: Exception) {
            // Fail-silent traversal
        }

        return results
    }

    /**
     * Find nearest candidate in specified Direction using weighted directional penalty.
     */
    fun findNearestInDirection(
        current: Rect,
        candidates: List<FocusCandidate>,
        direction: Direction
    ): FocusCandidate? {
        val currCx = current.centerX()
        val currCy = current.centerY()

        var bestCandidate: FocusCandidate? = null
        var minScore = Double.MAX_VALUE

        for (cand in candidates) {
            val candCx = cand.bounds.centerX()
            val candCy = cand.bounds.centerY()

            val dx = candCx - currCx
            val dy = candCy - currCy

            val isValidDirection = when (direction) {
                Direction.UP -> dy < -8
                Direction.DOWN -> dy > 8
                Direction.LEFT -> dx < -8
                Direction.RIGHT -> dx > 8
            }

            if (!isValidDirection) continue

            // Score with directional bias (primary axis 1.0x, cross axis 2.5x)
            val score = when (direction) {
                Direction.UP -> (-dy) * 1.0 + abs(dx) * 2.5
                Direction.DOWN -> dy * 1.0 + abs(dx) * 2.5
                Direction.LEFT -> (-dx) * 1.0 + abs(dy) * 2.5
                Direction.RIGHT -> dx * 1.0 + abs(dy) * 2.5
            }

            if (score < minScore) {
                minScore = score
                bestCandidate = cand
            }
        }

        return bestCandidate
    }

    /**
     * Find the web content area (WebView node or fallback largest empty leaf node covering >50% screen).
     */
    fun findWebArea(root: AccessibilityNodeInfo?, screenWidth: Int, screenHeight: Int): Rect? {
        if (root == null) return null
        var webViewRect: Rect? = null
        var largestFallbackRect: Rect? = null
        var largestFallbackArea = 0
        val totalScreenArea = screenWidth * screenHeight

        fun traverse(node: AccessibilityNodeInfo) {
            val bounds = Rect()
            node.getBoundsInScreen(bounds)
            val className = node.className?.toString() ?: ""

            if (className.contains("WebView", ignoreCase = true) || className == "android.webkit.WebView") {
                if (bounds.width() > 100 && bounds.height() > 100) {
                    webViewRect = Rect(bounds)
                    return
                }
            }

            val area = bounds.width() * bounds.height()
            if (area > (totalScreenArea * 0.45) && node.childCount == 0 && !node.isFocusable && !node.isClickable) {
                if (area > largestFallbackArea) {
                    largestFallbackArea = area
                    largestFallbackRect = Rect(bounds)
                }
            }

            for (i in 0 until node.childCount) {
                val child = node.getChild(i) ?: continue
                traverse(child)
            }
        }

        try {
            traverse(root)
        } catch (_: Exception) {
            // Fail-silent
        }

        return webViewRect ?: largestFallbackRect
    }
}
