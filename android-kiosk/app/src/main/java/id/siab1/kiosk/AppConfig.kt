package id.siab1.kiosk

import java.net.URI

object AppConfig {
    val serverUrl: String = BuildConfig.SIAB1_SERVER_URL
    const val buildToken: String = "BUILD-20260617045040-S3O97D"
    const val appName: String = "SIAB1"
    const val appSubtitle: String = "Sistem Informasi Asesmen Berintegritas"
    const val forceHttps: Boolean = true

    fun normalizedServerUrl(): String {
        var value = serverUrl.trim()
        if (forceHttps && value.startsWith("http://")) {
            value = "https://" + value.removePrefix("http://")
        }
        if (!value.endsWith("/")) {
            value += "/"
        }
        return value
    }

    fun studentDashboardUrl(): String = normalizedServerUrl() + "student/dashboard.html"

    fun trustedOrigin(): String {
        val uri = URI(normalizedServerUrl())
        val port = if (uri.port == -1) "" else ":${uri.port}"
        return "${uri.scheme}://${uri.host}$port"
    }

    fun isTrustedUrl(rawUrl: String): Boolean {
        return try {
            val expected = URI(normalizedServerUrl())
            val candidate = URI(rawUrl)
            candidate.scheme.equals(expected.scheme, ignoreCase = true) &&
                candidate.host.equals(expected.host, ignoreCase = true) &&
                effectivePort(candidate) == effectivePort(expected) &&
                candidate.userInfo == null
        } catch (_: Exception) {
            false
        }
    }

    fun apiUrl(path: String): String {
        val base = normalizedServerUrl().trimEnd('/')
        val suffix = if (path.startsWith("/")) path else "/$path"
        return base + suffix
    }

    private fun effectivePort(uri: URI): Int {
        if (uri.port != -1) return uri.port
        return if (uri.scheme.equals("https", ignoreCase = true)) 443 else 80
    }
}
