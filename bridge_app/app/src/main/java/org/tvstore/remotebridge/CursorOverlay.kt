package org.tvstore.remotebridge

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.Rect
import android.graphics.RectF
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowManager

class CursorOverlay(private val context: Context) {

    private val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private val overlayView = FocusFrameView(context)
    private var isAttached = false

    private val layoutParams = WindowManager.LayoutParams(
        WindowManager.LayoutParams.MATCH_PARENT,
        WindowManager.LayoutParams.MATCH_PARENT,
        WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
        PixelFormat.TRANSLUCENT
    )

    fun show() {
        if (!isAttached) {
            try {
                windowManager.addView(overlayView, layoutParams)
                isAttached = true
            } catch (_: Exception) {
                // Fail-silent
            }
        }
    }

    fun hide() {
        if (isAttached) {
            try {
                windowManager.removeView(overlayView)
                isAttached = false
            } catch (_: Exception) {
                // Fail-silent
            }
        }
    }

    fun updateFocus(rect: Rect?) {
        show()
        overlayView.setFocusRect(rect)
    }

    fun updatePointer(x: Float, y: Float) {
        show()
        overlayView.setPointer(x, y)
    }

    fun setClickEffect(pressed: Boolean) {
        overlayView.setClickPressed(pressed)
    }

    fun getCurrentPosition(): Pair<Float, Float> {
        return overlayView.getPointerPosition()
    }

    fun showModeIndicator(modeText: String) {
        show()
        overlayView.showIndicator(modeText)
    }

    private class FocusFrameView(context: Context) : View(context) {
        private var focusRect: RectF? = null
        private var pointerX: Float = -1f
        private var pointerY: Float = -1f
        private var showPointer: Boolean = false
        private var isClickPressed: Boolean = false
        private var indicatorText: String? = null
        private val uiHandler = Handler(Looper.getMainLooper())

        // Focus Frame Paints
        private val outerGlowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 10f
            color = 0x663D7BFD.toInt()
        }

        private val framePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 5f
            color = 0xFFFFFFFF.toInt()
        }

        // Pointer Paints (Authentic TV browser pointer with high visibility)
        private val pointerDarkRing = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 5f
            color = 0xAA000000.toInt()
        }

        private val pointerBrightRing = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 3f
            color = 0xFFFFFFFF.toInt()
        }

        private val pointerCenterDot = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
            color = 0xFF3D7BFD.toInt()
        }

        // Click Ripple & Pressed Paints
        private val clickRipplePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 4f
            color = 0x993D7BFD.toInt()
        }

        private val clickCenterPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
            color = 0xFFFFFFFF.toInt()
        }

        // Indicator Pill Paints
        private val pillBackground = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
            color = 0xCC1A1A1A.toInt()
        }

        private val pillTextPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = 0xFFFFFFFF.toInt()
            textSize = 28f
            isFakeBoldText = true
            textAlign = Paint.Align.CENTER
        }

        fun setFocusRect(rect: Rect?) {
            showPointer = false
            focusRect = if (rect != null && !rect.isEmpty) {
                val pad = 6f
                RectF(rect.left - pad, rect.top - pad, rect.right + pad, rect.bottom + pad)
            } else {
                null
            }
            invalidate()
        }

        fun setPointer(x: Float, y: Float) {
            focusRect = null
            pointerX = x
            pointerY = y
            showPointer = true
            invalidate()
        }

        fun setClickPressed(pressed: Boolean) {
            isClickPressed = pressed
            invalidate()
        }

        fun getPointerPosition(): Pair<Float, Float> {
            return Pair(pointerX, pointerY)
        }

        fun showIndicator(text: String) {
            indicatorText = text
            invalidate()
            uiHandler.removeCallbacksAndMessages(null)
            uiHandler.postDelayed({
                indicatorText = null
                invalidate()
            }, 1400)
        }

        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)

            // 1. Draw Native Focus Bounding Box
            focusRect?.let { r ->
                val radius = 12f
                canvas.drawRoundRect(r, radius, radius, outerGlowPaint)
                canvas.drawRoundRect(r, radius, radius, framePaint)
            }

            // 2. Draw Virtual Vector Mouse Pointer
            if (showPointer && pointerX >= 0 && pointerY >= 0) {
                if (isClickPressed) {
                    // Tactile click ripple effect
                    canvas.drawCircle(pointerX, pointerY, 26f, clickRipplePaint)
                    canvas.drawCircle(pointerX, pointerY, 18f, pointerDarkRing)
                    canvas.drawCircle(pointerX, pointerY, 16f, pointerBrightRing)
                    canvas.drawCircle(pointerX, pointerY, 8f, clickCenterPaint)
                } else {
                    // Regular resting pointer
                    canvas.drawCircle(pointerX, pointerY, 18f, pointerDarkRing)
                    canvas.drawCircle(pointerX, pointerY, 16f, pointerBrightRing)
                    canvas.drawCircle(pointerX, pointerY, 6f, pointerCenterDot)
                }
            }

            // 3. Draw Brief Mode Indicator Pill
            indicatorText?.let { text ->
                val textWidth = pillTextPaint.measureText(text)
                val cx = width / 2f
                val top = 40f
                val pillRect = RectF(cx - textWidth / 2f - 30f, top, cx + textWidth / 2f + 30f, top + 52f)
                canvas.drawRoundRect(pillRect, 26f, 26f, pillBackground)
                canvas.drawText(text, cx, top + 36f, pillTextPaint)
            }
        }
    }
}
