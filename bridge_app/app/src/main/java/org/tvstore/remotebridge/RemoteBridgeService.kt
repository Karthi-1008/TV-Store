package org.tvstore.remotebridge

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.util.DisplayMetrics
import android.view.KeyEvent
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class RemoteBridgeService : AccessibilityService() {

    private lateinit var cursorOverlay: CursorOverlay
    private var screenWidth = 1280
    private var screenHeight = 720
    private var currentFocus: FocusCandidate? = null

    override fun onCreate() {
        super.onCreate()
        cursorOverlay = CursorOverlay(this)
        updateScreenDimensions()
    }

    private fun updateScreenDimensions() {
        try {
            val wm = getSystemService(WINDOW_SERVICE) as WindowManager
            val metrics = DisplayMetrics()
            @Suppress("DEPRECATION")
            wm.defaultDisplay.getRealMetrics(metrics)
            screenWidth = metrics.widthPixels
            screenHeight = metrics.heightPixels
        } catch (_: Exception) {
            screenWidth = 1280
            screenHeight = 720
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        updateScreenDimensions()
    }

    private var currentForegroundPackage: String? = null

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        event.packageName?.let {
            currentForegroundPackage = it.toString()
        }
        when (event.eventType) {
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> {
                // Window changed, invalidate old focus
                currentFocus = null
                cursorOverlay.updateFocus(null)
            }
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> {
                // If focused node still exists, re-sync its bounds
                currentFocus?.let { cand ->
                    try {
                        val freshBounds = Rect()
                        cand.node.getBoundsInScreen(freshBounds)
                        if (!freshBounds.isEmpty) {
                            cursorOverlay.updateFocus(freshBounds)
                        }
                    } catch (_: Exception) {
                        // Node may have become invalid
                    }
                }
            }
        }
    }

    override fun onInterrupt() {
        currentFocus = null
        cursorOverlay.hide()
    }

    override fun onKeyEvent(event: KeyEvent?): Boolean {
        if (event == null || event.action != KeyEvent.ACTION_DOWN) {
            return super.onKeyEvent(event)
        }

        // Per-app scoping: Only intercept if foreground app is registered as a converted app
        val foregroundPackage = rootInActiveWindow?.packageName?.toString() ?: currentForegroundPackage
        if (foregroundPackage == null || !ConvertedAppsRegistry.isRegistered(this, foregroundPackage)) {
            // Not one of our converted apps — do nothing, let OS/app handle it natively
            return super.onKeyEvent(event)
        }

        return when (event.keyCode) {
            KeyEvent.KEYCODE_DPAD_UP -> handleDirection(Direction.UP)
            KeyEvent.KEYCODE_DPAD_DOWN -> handleDirection(Direction.DOWN)
            KeyEvent.KEYCODE_DPAD_LEFT -> handleDirection(Direction.LEFT)
            KeyEvent.KEYCODE_DPAD_RIGHT -> handleDirection(Direction.RIGHT)
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER -> handleEnter()
            KeyEvent.KEYCODE_BACK -> handleBack()
            else -> super.onKeyEvent(event)
        }
    }

    private fun handleDirection(dir: Direction): Boolean {
        return try {
            val root = rootInActiveWindow ?: return false
            val nodes = SpatialNavigator.findInteractiveNodes(root, screenWidth, screenHeight)
            if (nodes.isEmpty()) return false

            val curr = currentFocus
            val next = if (curr == null || curr.bounds.isEmpty) {
                // Initial focus: find uppermost leftmost candidate
                nodes.minByOrNull { it.bounds.top * 2 + it.bounds.left }
            } else {
                SpatialNavigator.findNearestInDirection(curr.bounds, nodes, dir)
            }

            if (next != null) {
                currentFocus = next
                cursorOverlay.updateFocus(next.bounds)
                true
            } else {
                // No node in that direction: attempt swipe scroll macro
                handleScrollFallback(dir)
            }
        } catch (_: Exception) {
            false
        }
    }

    private fun handleScrollFallback(dir: Direction): Boolean {
        val cx = screenWidth / 2f
        val cy = screenHeight / 2f

        return when (dir) {
            Direction.DOWN -> {
                // Scroll down: swipe upwards
                GestureMacro.performSwipe(this, cx, cy + 200f, cx, cy - 200f, 250) {
                    // Re-evaluate focus after scroll settles
                    refreshFocusAfterScroll()
                }
                true
            }
            Direction.UP -> {
                // Scroll up: swipe downwards
                GestureMacro.performSwipe(this, cx, cy - 200f, cx, cy + 200f, 250) {
                    refreshFocusAfterScroll()
                }
                true
            }
            else -> false
        }
    }

    private fun refreshFocusAfterScroll() {
        try {
            val root = rootInActiveWindow ?: return
            val nodes = SpatialNavigator.findInteractiveNodes(root, screenWidth, screenHeight)
            val best = nodes.minByOrNull { it.bounds.top * 2 + it.bounds.left }
            if (best != null) {
                currentFocus = best
                cursorOverlay.updateFocus(best.bounds)
            }
        } catch (_: Exception) {
            // Fail-silent
        }
    }

    private fun handleEnter(): Boolean {
        val target = currentFocus ?: return false
        val cx = target.bounds.centerX().toFloat()
        val cy = target.bounds.centerY().toFloat()

        // 1. Try native accessibility click first
        val clicked = try {
            target.node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        } catch (_: Exception) {
            false
        }

        // 2. Dispatch synthetic tap to guarantee custom touch listeners receive the event
        GestureMacro.performTap(this, cx, cy)
        return true
    }

    private fun handleBack(): Boolean {
        // If cursor is active, back can either clear cursor or forward to system
        return if (currentFocus != null) {
            currentFocus = null
            cursorOverlay.updateFocus(null)
            false // allow system to receive back
        } else {
            false
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        cursorOverlay.hide()
    }
}
