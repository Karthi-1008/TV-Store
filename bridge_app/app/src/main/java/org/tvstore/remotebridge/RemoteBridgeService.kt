package org.tvstore.remotebridge

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.util.DisplayMetrics
import android.view.KeyEvent
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import kotlin.math.abs

class RemoteBridgeService : AccessibilityService() {

    private lateinit var cursorOverlay: CursorOverlay
    private var screenWidth = 1280
    private var screenHeight = 720

    // Navigation and Pointer state
    private var configuredAppMode = "auto" // "auto" | "pointer" | "navigate"
    private var activeMode = "navigate"     // Current active state: "pointer" | "navigate"
    private var currentFocus: FocusCandidate? = null
    private var pointerX = 640f
    private var pointerY = 360f

    // Explicit Movement Loop for TV Remotes (Smooth continuous movement while held)
    private val moveHandler = Handler(Looper.getMainLooper())
    private var moveDx = 0f
    private var moveDy = 0f
    private var moveSpeed = MIN_STEP
    private var isMoving = false

    private val moveTick = object : Runnable {
        override fun run() {
            if (!isMoving) return
            applyPointerMove(moveDx * moveSpeed, moveDy * moveSpeed)
            moveSpeed = (moveSpeed + ACCELERATION).coerceAtMost(MAX_STEP)
            moveHandler.postDelayed(this, FRAME_MS)
        }
    }

    // OK click & long-press handler
    private val okHandler = Handler(Looper.getMainLooper())
    private var okLongPressTriggered = false
    private val longPressRunnable = Runnable {
        okLongPressTriggered = true
        GestureMacro.performLongPress(this, pointerX, pointerY)
    }

    private var currentForegroundPackage: String? = null

    companion object {
        private const val FRAME_MS = 16L     // ~60fps, matches TV panel refresh
        private const val MIN_STEP = 6f      // dp per frame at the start of a hold
        private const val MAX_STEP = 30f     // dp per frame after ramping up
        private const val ACCELERATION = 0.5f // dp added per frame while held
    }

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
            pointerX = screenWidth / 2f
            pointerY = screenHeight / 2f
        } catch (_: Exception) {
            screenWidth = 1280
            screenHeight = 720
            pointerX = 640f
            pointerY = 360f
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        updateScreenDimensions()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        event.packageName?.let {
            val pkg = it.toString()
            if (pkg != currentForegroundPackage) {
                currentForegroundPackage = pkg
                stopMoving()
                configuredAppMode = ConvertedAppsRegistry.getMode(this, pkg)
                // If package is configured as pointer-only, activate pointer immediately
                if (configuredAppMode == "pointer") {
                    activeMode = "pointer"
                    cursorOverlay.updatePointer(pointerX, pointerY)
                } else {
                    activeMode = "navigate"
                    currentFocus = null
                    cursorOverlay.updateFocus(null)
                }
            }
        }

        when (event.eventType) {
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> {
                stopMoving()
                currentFocus = null
                if (activeMode == "navigate") {
                    cursorOverlay.updateFocus(null)
                }
            }
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> {
                if (activeMode == "navigate") {
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
    }

    override fun onInterrupt() {
        stopMoving()
        okHandler.removeCallbacks(longPressRunnable)
        currentFocus = null
        cursorOverlay.hide()
    }

    override fun onKeyEvent(event: KeyEvent?): Boolean {
        if (event == null) return false

        // Per-app scoping: Only intercept if foreground app is registered as a converted app
        val foregroundPackage = rootInActiveWindow?.packageName?.toString() ?: currentForegroundPackage
        if (foregroundPackage == null || !ConvertedAppsRegistry.isRegistered(this, foregroundPackage)) {
            // Not one of our converted apps — let OS handle natively
            return super.onKeyEvent(event)
        }

        // 1. Manual Toggle Key (KEYCODE_MENU toggles Pointer vs Navigate)
        if (event.keyCode == KeyEvent.KEYCODE_MENU && event.action == KeyEvent.ACTION_DOWN) {
            return toggleMode()
        }

        // 2. Direct Page Scroll Keys (Channel Up/Down, Page Up/Down)
        if (event.action == KeyEvent.ACTION_DOWN) {
            when (event.keyCode) {
                KeyEvent.KEYCODE_PAGE_UP, KeyEvent.KEYCODE_CHANNEL_UP -> {
                    GestureMacro.performSwipe(this, pointerX, 200f, pointerX, 650f, 240)
                    return true
                }
                KeyEvent.KEYCODE_PAGE_DOWN, KeyEvent.KEYCODE_CHANNEL_DOWN -> {
                    GestureMacro.performSwipe(this, pointerX, 650f, pointerX, 200f, 240)
                    return true
                }
            }
        }

        // 3. Handle Pointer Mode vs Navigate Mode
        return if (activeMode == "pointer") {
            handlePointerKeyEvent(event)
        } else {
            handleNavigateKeyEvent(event)
        }
    }

    private fun toggleMode(): Boolean {
        stopMoving()
        okHandler.removeCallbacks(longPressRunnable)
        activeMode = if (activeMode == "pointer") "navigate" else "pointer"
        val indicator = if (activeMode == "pointer") "Pointer Mode" else "D-pad Mode"
        cursorOverlay.showModeIndicator(indicator)

        if (activeMode == "pointer") {
            currentFocus = null
            cursorOverlay.updatePointer(pointerX, pointerY)
        } else {
            cursorOverlay.updatePointer(-1f, -1f)
            val root = rootInActiveWindow
            val nodes = SpatialNavigator.findInteractiveNodes(root, screenWidth, screenHeight)
            val first = nodes.minByOrNull { it.bounds.top * 2 + it.bounds.left }
            if (first != null) {
                currentFocus = first
                cursorOverlay.updateFocus(first.bounds)
            } else {
                cursorOverlay.updateFocus(null)
            }
        }
        return true
    }

    // =========================================================================
    // POINTER MODE: 60fps Loop Movement, Dynamic Acceleration, and Click Handling
    // =========================================================================

    private fun startMoving(dx: Float, dy: Float) {
        moveDx = dx
        moveDy = dy
        moveSpeed = MIN_STEP
        if (!isMoving) {
            isMoving = true
            moveHandler.post(moveTick)
        }
    }

    private fun stopMoving() {
        isMoving = false
        moveHandler.removeCallbacks(moveTick)
        moveSpeed = MIN_STEP
        moveDx = 0f
        moveDy = 0f
    }

    private fun applyPointerMove(dx: Float, dy: Float) {
        val root = rootInActiveWindow
        val webArea = SpatialNavigator.findWebArea(root, screenWidth, screenHeight)

        if (dy < 0) { // moving up
            val topBoundary = webArea?.top?.toFloat() ?: 0f
            if (pointerY <= topBoundary + 15f) {
                // In auto mode, returning past top edge hands control back to native toolbar focus
                if (configuredAppMode == "auto") {
                    val toolbarNodes = SpatialNavigator.findInteractiveNodes(root, screenWidth, screenHeight)
                        .filter { cand -> (webArea == null || cand.bounds.bottom <= webArea.top + 30) }
                    val best = toolbarNodes.minByOrNull {
                        abs(it.bounds.centerX() - pointerX) + (topBoundary - it.bounds.bottom)
                    }
                    if (best != null) {
                        stopMoving()
                        activeMode = "navigate"
                        currentFocus = best
                        cursorOverlay.updateFocus(best.bounds)
                        return
                    }
                }
                // Edge scroll: swipe down to scroll content up
                GestureMacro.performSwipe(this, pointerX, pointerY, pointerX, (pointerY + 280f).coerceAtMost(screenHeight.toFloat()), 220)
                return
            }
        }
        if (dy > 0) { // moving down
            val bottomBoundary = webArea?.bottom?.toFloat() ?: screenHeight.toFloat()
            if (pointerY >= bottomBoundary - 25f) {
                // Edge scroll: swipe up to scroll content down
                GestureMacro.performSwipe(this, pointerX, pointerY, pointerX, (pointerY - 280f).coerceAtLeast(0f), 220)
                return
            }
        }

        pointerX = (pointerX + dx).coerceIn(0f, screenWidth.toFloat())
        pointerY = (pointerY + dy).coerceIn(0f, screenHeight.toFloat())
        cursorOverlay.updatePointer(pointerX, pointerY)
    }

    private fun handlePointerKeyEvent(event: KeyEvent): Boolean {
        val keyCode = event.keyCode
        val action = event.action

        // 1. OK / Enter Button: Visual feedback + Tap on release + Long-press if held
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER || keyCode == KeyEvent.KEYCODE_NUMPAD_ENTER) {
            when (action) {
                KeyEvent.ACTION_DOWN -> {
                    if (event.repeatCount == 0) {
                        okLongPressTriggered = false
                        cursorOverlay.setClickEffect(true)
                        okHandler.removeCallbacks(longPressRunnable)
                        okHandler.postDelayed(longPressRunnable, 500)
                    }
                }
                KeyEvent.ACTION_UP -> {
                    okHandler.removeCallbacks(longPressRunnable)
                    cursorOverlay.setClickEffect(false)
                    if (!okLongPressTriggered) {
                        GestureMacro.performTap(this, pointerX, pointerY)
                    }
                }
            }
            return true
        }

        // 2. D-pad Directions: 60fps Movement Loop on ACTION_DOWN, stop on ACTION_UP
        when (keyCode) {
            KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN,
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT -> {
                when (action) {
                    KeyEvent.ACTION_DOWN -> {
                        val (dx, dy) = when (keyCode) {
                            KeyEvent.KEYCODE_DPAD_UP -> 0f to -1f
                            KeyEvent.KEYCODE_DPAD_DOWN -> 0f to 1f
                            KeyEvent.KEYCODE_DPAD_LEFT -> -1f to 0f
                            else -> 1f to 0f
                        }
                        startMoving(dx, dy)
                    }
                    KeyEvent.ACTION_UP -> {
                        stopMoving()
                    }
                }
                return true
            }
            KeyEvent.KEYCODE_BACK -> {
                if (action != KeyEvent.ACTION_DOWN) return super.onKeyEvent(event)
                stopMoving()
                // In auto mode, Back clears pointer and returns to toolbar if available
                if (configuredAppMode == "auto") {
                    val rootNow = rootInActiveWindow
                    val webAreaNow = SpatialNavigator.findWebArea(rootNow, screenWidth, screenHeight)
                    val toolbarNodes = SpatialNavigator.findInteractiveNodes(rootNow, screenWidth, screenHeight)
                        .filter { cand -> (webAreaNow == null || cand.bounds.bottom <= webAreaNow.top + 30) }
                    if (toolbarNodes.isNotEmpty()) {
                        activeMode = "navigate"
                        currentFocus = toolbarNodes.first()
                        cursorOverlay.updateFocus(currentFocus!!.bounds)
                        return true
                    }
                }
                return super.onKeyEvent(event)
            }
            else -> {
                if (action != KeyEvent.ACTION_DOWN) return super.onKeyEvent(event)
                return super.onKeyEvent(event)
            }
        }
    }

    // =========================================================================
    // NAVIGATE MODE: Spatial Focus Navigation with Seamless Transition to Web
    // =========================================================================

    private fun handleNavigateKeyEvent(event: KeyEvent): Boolean {
        if (event.action != KeyEvent.ACTION_DOWN) {
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
            val webArea = SpatialNavigator.findWebArea(root, screenWidth, screenHeight)

            // Auto Mode transition: Moving DOWN into web content switches to pointer mode
            if (configuredAppMode == "auto" && dir == Direction.DOWN && webArea != null) {
                val candidates = SpatialNavigator.findInteractiveNodes(root, screenWidth, screenHeight)
                val toolbarCandidates = candidates.filter { it.bounds.bottom <= webArea.top + 25 }
                val nextToolbar = currentFocus?.let {
                    SpatialNavigator.findNearestInDirection(it.bounds, toolbarCandidates, Direction.DOWN)
                }
                if (nextToolbar == null) {
                    // No further toolbar buttons below; switch to pointer mode inside web area
                    activeMode = "pointer"
                    pointerX = currentFocus?.bounds?.centerX()?.toFloat() ?: (screenWidth / 2f)
                    pointerY = (webArea.top + 60f).coerceAtMost(screenHeight - 80f)
                    currentFocus = null
                    cursorOverlay.updatePointer(pointerX, pointerY)
                    return true
                }
            }

            val nodes = SpatialNavigator.findInteractiveNodes(root, screenWidth, screenHeight)
            if (nodes.isEmpty()) return false

            val curr = currentFocus
            val next = if (curr == null || curr.bounds.isEmpty) {
                nodes.minByOrNull { it.bounds.top * 2 + it.bounds.left }
            } else {
                SpatialNavigator.findNearestInDirection(curr.bounds, nodes, dir)
            }

            if (next != null) {
                currentFocus = next
                cursorOverlay.updateFocus(next.bounds)
                true
            } else {
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
                GestureMacro.performSwipe(this, cx, cy + 200f, cx, cy - 200f, 250) {
                    refreshFocusAfterScroll()
                }
                true
            }
            Direction.UP -> {
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

        try {
            target.node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        } catch (_: Exception) {
            // Fail-silent
        }

        GestureMacro.performTap(this, cx, cy)
        return true
    }

    private fun handleBack(): Boolean {
        return if (currentFocus != null) {
            currentFocus = null
            cursorOverlay.updateFocus(null)
            false
        } else {
            false
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        stopMoving()
        okHandler.removeCallbacks(longPressRunnable)
        cursorOverlay.hide()
    }
}
