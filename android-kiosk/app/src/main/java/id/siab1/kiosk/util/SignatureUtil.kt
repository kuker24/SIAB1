package id.siab1.kiosk.util

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import java.security.MessageDigest

object SignatureUtil {
    fun sha256Fingerprint(context: Context): String {
        return try {
            val packageInfo = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                context.packageManager.getPackageInfo(
                    context.packageName,
                    PackageManager.GET_SIGNING_CERTIFICATES,
                )
            } else {
                @Suppress("DEPRECATION")
                context.packageManager.getPackageInfo(
                    context.packageName,
                    PackageManager.GET_SIGNATURES,
                )
            }

            val signature = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                packageInfo.signingInfo?.apkContentsSigners?.getOrNull(0)
            } else {
                @Suppress("DEPRECATION")
                packageInfo.signatures?.getOrNull(0)
            } ?: return "ERROR"

            val digest = MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())
            digest.joinToString(":") { "%02X".format(it) }
        } catch (_: Exception) {
            "ERROR"
        }
    }
}
