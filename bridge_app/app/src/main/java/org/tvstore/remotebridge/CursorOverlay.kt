package org.tvstore.remotebridge

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.Rect
import android.graphics.RectF
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

    private class FocusFrameView(context: Context) : View(context) {
        private var focusRect: RectF? = null

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

        fun setFocusRect(rect: Rect?) {
            focusRect = if (rect != null && !rect.isEmpty) {
                // Expand rect by 4dp padding
                val pad = 6f
                RectF(rect.left - pad, rect.top - pad, rect.right + pad, rect.bottom + pad)
            } else {
                null
            }
            invalidate()
        }

        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            val r = focusRect ?: return
            val radius = 12f
            canvas.drawRoundRect(r, radius, radius, outerGlowPaint)
            canvas.drawRoundRect(r, radius, radius, framePaint)
        }
    }
}
