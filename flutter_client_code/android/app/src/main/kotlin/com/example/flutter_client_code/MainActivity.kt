package com.example.flutter_client_code

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.KeyEvent
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.security.MessageDigest

class MainActivity: FlutterActivity() {
    private val KIOSK_CHANNEL = "com.example.sxb_client/kiosk"
    private val SECURITY_CHANNEL = "com.school.examapp/security"
    private var isKioskMode = false
    private var isExamActive = false

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        
        // Setup kiosk mode channel
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, KIOSK_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "startLockTask" -> {
                    try {
                        startLockTask()
                        isKioskMode = true
                        isExamActive = true
                        // Enable screenshot blocking when exam starts
                        enableSecureMode()
                        result.success(true)
                    } catch (e: Exception) {
                        // Lock task might fail without device owner permission
                        // Still enable secure mode for screenshot blocking
                        isExamActive = true
                        enableSecureMode()
                        result.success(false)
                    }
                }
                "stopLockTask" -> {
                    try {
                        stopLockTask()
                        isKioskMode = false
                        isExamActive = false
                        // Disable screenshot blocking when exam ends
                        disableSecureMode()
                        result.success(true)
                    } catch (e: Exception) {
                        isExamActive = false
                        disableSecureMode()
                        result.success(false)
                    }
                }
                "isKioskMode" -> {
                    result.success(isKioskMode)
                }
                "setExamActive" -> {
                    isExamActive = call.argument<Boolean>("active") ?: false
                    if (isExamActive) {
                        enableSecureMode()
                    } else {
                        disableSecureMode()
                    }
                    result.success(true)
                }
                "isSecureModeActive" -> {
                    result.success(isExamActive)
                }
                else -> {
                    result.notImplemented()
                }
            }
        }
        
        // Setup security channel for signature verification
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, SECURITY_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "getSignature" -> {
                    try {
                        val signature = getAppSignature()
                        result.success(signature)
                    } catch (e: Exception) {
                        result.error("SIGNATURE_ERROR", e.message, null)
                    }
                }
                "verifyNativeSignature" -> {
                    try {
                        val isValid = verifySignatureNative()
                        result.success(isValid)
                    } catch (e: Exception) {
                        result.error("VERIFY_ERROR", e.message, null)
                    }
                }
                else -> result.notImplemented()
            }
        }
    }
    
    /**
     * Get SHA-256 fingerprint of app signature
     * Used to detect if APK has been tampered with
     */
    private fun getAppSignature(): String {
        return try {
            val packageInfo = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                packageManager.getPackageInfo(packageName, PackageManager.GET_SIGNING_CERTIFICATES)
            } else {
                @Suppress("DEPRECATION")
                packageManager.getPackageInfo(packageName, PackageManager.GET_SIGNATURES)
            }
            
            val signature = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                packageInfo.signingInfo?.apkContentsSigners?.get(0)
            } else {
                @Suppress("DEPRECATION")
                packageInfo.signatures?.get(0)
            }
            
            // Return ERROR if signature is null
            if (signature == null) {
                return "ERROR"
            }
            
            // Calculate SHA-256 hash
            val md = MessageDigest.getInstance("SHA-256")
            val digest = md.digest(signature.toByteArray())
            
            // Convert to hex string with colons (format: EA:98:DB:9D:...)
            digest.joinToString(":") { "%02X".format(it) }
        } catch (e: Exception) {
            "ERROR"
        }
    }
    
    /**
     * ============================================================
     * NATIVE SIGNATURE VERIFICATION (Layer 2 Security)
     * ============================================================
     * Verify signature directly in native code for cross-validation
     * with Dart layer. Harder to tamper with than Dart code.
     */
    
    // Obfuscated expected signature (split into chunks)
    // Release keystore SHA-256: 29:7A:D1:BF:C6:ED:35:86:84:AD:69:95:69:DA:F4:A6:56:58:47:79:02:11:CE:72:6B:F5:3D:A5:80:EF:31:87
    private val sigChunk1 = byteArrayOf(0x29.toByte(), 0x7A.toByte(), 0xD1.toByte(), 0xBF.toByte())
    private val sigChunk2 = byteArrayOf(0xC6.toByte(), 0xED.toByte(), 0x35.toByte(), 0x86.toByte())
    private val sigChunk3 = byteArrayOf(0x84.toByte(), 0xAD.toByte(), 0x69.toByte(), 0x95.toByte())
    private val sigChunk4 = byteArrayOf(0x69.toByte(), 0xDA.toByte(), 0xF4.toByte(), 0xA6.toByte())
    private val sigChunk5 = byteArrayOf(0x56.toByte(), 0x58.toByte(), 0x47.toByte(), 0x79.toByte())
    private val sigChunk6 = byteArrayOf(0x02.toByte(), 0x11.toByte(), 0xCE.toByte(), 0x72.toByte())
    private val sigChunk7 = byteArrayOf(0x6B.toByte(), 0xF5.toByte(), 0x3D.toByte(), 0xA5.toByte())
    private val sigChunk8 = byteArrayOf(0x80.toByte(), 0xEF.toByte(), 0x31.toByte(), 0x87.toByte())
    
    /**
     * Reconstruct expected signature from obfuscated chunks
     */
    private fun getExpectedSignatureNative(): String {
        val allBytes = sigChunk1 + sigChunk2 + sigChunk3 + sigChunk4 +
                      sigChunk5 + sigChunk6 + sigChunk7 + sigChunk8
        return allBytes.joinToString(":") { "%02X".format(it) }
    }
    
    /**
     * Native signature verification
     * Returns true if signature matches expected, false if tampered
     */
    private fun verifySignatureNative(): Boolean {
        return try {
            // Get actual signature
            val actualSignature = getAppSignature()
            
            // Handle error case
            if (actualSignature == "ERROR") {
                return false
            }
            
            // Get expected signature
            val expectedSignature = getExpectedSignatureNative()
            
            // Compare signatures
            val isValid = actualSignature == expectedSignature
            
            // Log result (only in development)
            if (!isValid) {
                android.util.Log.w("SecurityCheck", "Native signature mismatch detected!")
            }
            
            isValid
        } catch (e: Exception) {
            android.util.Log.e("SecurityCheck", "Native verification error: ${e.message}")
            false
        }
    }

    private fun enableSecureMode() {
        runOnUiThread {
            // Block Screenshots and Screen Recording (FLAG_SECURE)
            window.setFlags(
                WindowManager.LayoutParams.FLAG_SECURE,
                WindowManager.LayoutParams.FLAG_SECURE
            )
            
            // Keep screen on during exam
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            
            // Hide navigation bar and status bar (immersive mode)
            // Use modern API for Android 11+ with fallback for older versions
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                window.insetsController?.let { controller ->
                    controller.hide(android.view.WindowInsets.Type.systemBars())
                    controller.systemBarsBehavior = 
                        android.view.WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                }
            } else {
                @Suppress("DEPRECATION")
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
    }
    
    private fun disableSecureMode() {
        runOnUiThread {
            // Re-allow screenshots
            window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
            
            // Allow screen to turn off
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            
            // Show navigation bar
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                window.insetsController?.show(android.view.WindowInsets.Type.systemBars())
            } else {
                @Suppress("DEPRECATION")
                window.decorView.systemUiVisibility = android.view.View.SYSTEM_UI_FLAG_VISIBLE
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Initially don't block screenshots (allow on login page)
        // Screenshots will be blocked when exam starts via startLockTask
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        
        // Re-apply immersive mode when focus changes during exam
        if (hasFocus && isExamActive) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                window.insetsController?.let { controller ->
                    controller.hide(android.view.WindowInsets.Type.systemBars())
                    controller.systemBarsBehavior = 
                        android.view.WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                }
            } else {
                @Suppress("DEPRECATION")
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
        
        // If lost focus during exam (attempted to leave app)
        if (!hasFocus && isExamActive) {
            // Close system dialogs - only works on Android < 12
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
                try {
                    @Suppress("DEPRECATION")
                    val closeIntent = android.content.Intent(android.content.Intent.ACTION_CLOSE_SYSTEM_DIALOGS)
                    sendBroadcast(closeIntent)
                } catch (e: Exception) {
                    // Ignore security exception
                }
            }
        }
    }
    
    // Block hardware keys during exam
    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (isExamActive) {
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
        if (isExamActive && keyCode == KeyEvent.KEYCODE_BACK) {
            return true // Block long press back
        }
        return super.onKeyLongPress(keyCode, event)
    }
    
    // Prevent activity from being destroyed during exam
    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (isExamActive) {
            // Do nothing - block back button during exam
            return
        }
        super.onBackPressed()
    }
}
