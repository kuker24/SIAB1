package com.example.sxb_client

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.os.Bundle
import android.view.KeyEvent
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity: FlutterActivity() {
    private val CHANNEL = "com.example.sxb_client/kiosk"
    private var isKioskMode = false

    // Anti-debug detection
    private fun isDebuggerConnected(): Boolean {
        return android.os.Debug.isDebuggerConnected()
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        
        // Prevent debugging in release mode
        if (!BuildConfig.DEBUG && isDebuggerConnected()) {
            finishAffinity()
            return
        }
        
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "startLockTask" -> {
                    try {
                        startLockTask()
                        isKioskMode = true
                        result.success(true)
                    } catch (e: Exception) {
                        result.error("LOCK_TASK_ERROR", e.message, null)
                    }
                }
                "stopLockTask" -> {
                    try {
                        stopLockTask()
                        isKioskMode = false
                        result.success(true)
                    } catch (e: Exception) {
                        result.error("UNLOCK_TASK_ERROR", e.message, null)
                    }
                }
                "isKioskMode" -> {
                    result.success(isKioskMode)
                }
                else -> {
                    result.notImplemented()
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Block Screenshots and Screen Recording (FLAG_SECURE)
        window.setFlags(
            WindowManager.LayoutParams.FLAG_SECURE,
            WindowManager.LayoutParams.FLAG_SECURE
        )
        
        // Keep screen on during exam
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        
        // Hide navigation bar and status bar
        window.decorView.systemUiVisibility = (
            android.view.View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            or android.view.View.SYSTEM_UI_FLAG_FULLSCREEN
            or android.view.View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            or android.view.View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            or android.view.View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            or android.view.View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
        )
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (!hasFocus && isKioskMode) {
            // Close system dialogs (notification bar, etc.)
            val closeIntent = android.content.Intent(android.content.Intent.ACTION_CLOSE_SYSTEM_DIALOGS)
            try {
                sendBroadcast(closeIntent)
            } catch (e: Exception) {
                // Ignore security exception on newer Android versions
            }
        }
        
        // Re-apply immersive mode when focus changes
        if (hasFocus) {
            window.decorView.systemUiVisibility = (
                android.view.View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or android.view.View.SYSTEM_UI_FLAG_FULLSCREEN
                or android.view.View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or android.view.View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or android.view.View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                or android.view.View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            )
        }
    }
    
    // Block hardware keys
    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (isKioskMode) {
            return when (keyCode) {
                KeyEvent.KEYCODE_VOLUME_UP,
                KeyEvent.KEYCODE_VOLUME_DOWN,
                KeyEvent.KEYCODE_HOME,
                KeyEvent.KEYCODE_BACK,
                KeyEvent.KEYCODE_MENU,
                KeyEvent.KEYCODE_APP_SWITCH -> true // Block these keys
                else -> super.onKeyDown(keyCode, event)
            }
        }
        return super.onKeyDown(keyCode, event)
    }
    
    // Block long press
    override fun onKeyLongPress(keyCode: Int, event: KeyEvent?): Boolean {
        if (isKioskMode && keyCode == KeyEvent.KEYCODE_BACK) {
            return true // Block long press back
        }
        return super.onKeyLongPress(keyCode, event)
    }
    
    // Prevent activity from being destroyed
    override fun onBackPressed() {
        if (isKioskMode) {
            // Do nothing - block back button
            return
        }
        super.onBackPressed()
    }
}
