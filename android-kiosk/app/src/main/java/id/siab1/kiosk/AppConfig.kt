package id.siab1.kiosk

object AppConfig {
    const val serverUrl: String = "https://man1rokanhulu.cloud/"
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

    fun apiUrl(path: String): String {
        val base = normalizedServerUrl().trimEnd('/')
        val suffix = if (path.startsWith("/")) path else "/$path"
        return base + suffix
    }
}
