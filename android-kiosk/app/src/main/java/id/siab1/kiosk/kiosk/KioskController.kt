package id.siab1.kiosk.kiosk

import android.app.Activity
import android.app.ActivityManager
import android.os.Build
import android.util.Log
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager

enum class LockState {
    LOCKED,
    PINNED,
    NONE,
}

class KioskController(private val activity: Activity) {
    var examActive: Boolean = false
        private set

    fun startExamLock(): LockState {
        examActive = true
        applySecureFlags()
        applyImmersive()
        try {
            activity.startLockTask()
        } catch (exc: Exception) {
            Log.w("SIAB1-Kiosk", "Unable to start lock task", exc)
        }
        return currentLockState()
    }

    fun currentLockState(): LockState {
        val manager = activity.getSystemService(Activity.ACTIVITY_SERVICE) as ActivityManager
        return when (manager.lockTaskModeState) {
            ActivityManager.LOCK_TASK_MODE_LOCKED -> LockState.LOCKED
            ActivityManager.LOCK_TASK_MODE_PINNED -> LockState.PINNED
            else -> LockState.NONE
        }
    }

    fun stopExamLock() {
        examActive = false
        try {
            val manager = activity.getSystemService(Activity.ACTIVITY_SERVICE) as ActivityManager
            if (manager.lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE) {
                activity.stopLockTask()
            }
        } catch (_: Exception) {
        }
        clearSecureFlags()
        showSystemBars()
    }

    fun applyImmersive() {
        val window = activity.window
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.let { controller ->
                controller.hide(WindowInsets.Type.systemBars())
                controller.systemBarsBehavior =
                    WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = (
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    or View.SYSTEM_UI_FLAG_FULLSCREEN
                    or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                )
        }
    }

    private fun applySecureFlags() {
        activity.window.setFlags(
            WindowManager.LayoutParams.FLAG_SECURE,
            WindowManager.LayoutParams.FLAG_SECURE,
        )
        activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    private fun clearSecureFlags() {
        activity.window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
        activity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    private fun showSystemBars() {
        val window = activity.window
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.show(WindowInsets.Type.systemBars())
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_VISIBLE
        }
    }
}
