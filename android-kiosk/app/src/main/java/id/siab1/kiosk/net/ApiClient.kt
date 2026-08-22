package id.siab1.kiosk.net

import android.content.Context
import android.content.pm.PackageManager
import id.siab1.kiosk.AppConfig
import id.siab1.kiosk.util.Prefs
import id.siab1.kiosk.util.SignatureUtil
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

class ApiClient private constructor(private val context: Context) {
    data class LoginResult(
        val success: Boolean,
        val message: String,
        val captchaRequired: Boolean = false,
        val captchaId: String? = null,
        val captchaQuestion: String? = null,
    )

    private val jsonType = "application/json; charset=utf-8".toMediaType()
    private var cachedSignature: String? = null
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val original = chain.request()
            val builder = original.newBuilder()
            if (AppConfig.isTrustedUrl(original.url.toString())) {
                defaultHeaders().forEach { (key, value) ->
                    builder.header(key, value)
                }
            }
            chain.proceed(builder.build())
        }
        .build()

    fun defaultHeaders(): Map<String, String> {
        val headers = linkedMapOf(
            "Accept" to "application/json",
            "Content-Type" to "application/json",
            "User-Agent" to USER_AGENT,
            "X-Build-Token" to AppConfig.buildToken,
            "X-App-Timestamp" to (System.currentTimeMillis() / 1000L).toString(),
        )
        val signature = signature()
        if (signature != null && signature != "ERROR") {
            headers["X-App-Signature"] = signature
        }
        val pkg = packageMeta()
        headers["X-App-Version"] = pkg.first
        headers["X-App-Build"] = pkg.second
        val configHash = storedConfigKeyHash()
        if (!configHash.isNullOrBlank()) {
            headers["X-SafeExamBrowser-ConfigKeyHash"] = configHash
        }
        val token = Prefs.token
        if (!token.isNullOrBlank()) {
            headers["Authorization"] = "Bearer $token"
        }
        return headers
    }

    fun webViewHeaders(): Map<String, String> {
        return defaultHeaders().filterKeys { it != "Content-Type" && it != "Accept" }
    }

    fun prepareSecurityContext(): Boolean {
        val signature = signature()
        return !signature.isNullOrBlank() && signature != "ERROR"
    }

    fun login(
        username: String,
        password: String,
        captchaId: String? = null,
        captchaAnswer: String? = null,
    ): LoginResult {
        val payload = JSONObject()
            .put("username", username)
            .put("password", password)
        if (!captchaId.isNullOrBlank() && !captchaAnswer.isNullOrBlank()) {
            payload.put("captcha_id", captchaId)
            payload.put("captcha_answer", captchaAnswer)
        }
        val request = Request.Builder()
            .url(AppConfig.apiUrl("/api/auth/login"))
            .post(payload.toString().toRequestBody(jsonType))
            .build()
        client.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            val json = body.toJsonObject()
            if (response.isSuccessful) {
                val token = json?.optString("access_token").orEmpty()
                val user = json?.optJSONObject("user")
                val role = user?.optString("role").orEmpty()
                if (token.isBlank()) {
                    return LoginResult(false, "Login gagal: Respon tidak valid")
                }
                if (role != "student" && role != "guruplus") {
                    return LoginResult(false, "Portal APK ini khusus untuk peserta ujian")
                }
                Prefs.token = token
                Prefs.userJson = user?.toString()
                return LoginResult(true, "ok")
            }
            return parseLoginError(response.code, json, body)
        }
    }

    fun logViolation(sessionId: String, type: String, count: Int, details: String?) {
        val sessionInt = sessionId.toIntOrNull() ?: return
        val examInt = Prefs.examId?.toIntOrNull() ?: 0
        val payload = JSONObject()
            .put("session_id", sessionInt)
            .put("exam_id", examInt)
            .put("event_type", type)
            .put(
                "event_data",
                JSONObject()
                    .put("violation_count", count)
                    .put("details", details ?: "")
                    .put("source", "android_kiosk")
                    .put("raw_type", type),
            )
            .put("timestamp", java.time.Instant.now().toString())
            .put("user_agent", "SIAB1 Android Kiosk")
            .put("screen_resolution", "mobile")
        val request = Request.Builder()
            .url(AppConfig.apiUrl("/api/exams/log-violation"))
            .post(payload.toString().toRequestBody(jsonType))
            .build()
        try {
            client.newCall(request).execute().close()
        } catch (_: Exception) {
        }
    }

    fun fetchBytes(url: String): ByteArray? {
        if (!AppConfig.isTrustedUrl(url)) return null
        val request = Request.Builder().url(url).get().build()
        return try {
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) null else response.body?.bytes()
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun parseLoginError(code: Int, json: JSONObject?, body: String): LoginResult {
        val detail = json?.opt("detail")
        val detailObj = detail as? JSONObject
        val detailMap = if (detailObj != null) detailObj else json
        if (code == 428 || isCaptcha(detailObj)) {
            return LoginResult(
                success = false,
                message = detailMap?.optString("message")?.ifBlank { null }
                    ?: "CAPTCHA diperlukan",
                captchaRequired = true,
                captchaId = detailMap?.optString("challenge_id")
                    ?: detailMap?.optString("captcha_id"),
                captchaQuestion = detailMap?.optString("question"),
            )
        }
        val message = when {
            detailObj != null -> detailObj.optString("message").ifBlank {
                detailObj.optString("detail").ifBlank { "Login gagal" }
            }
            detail is String -> detail
            json?.optString("detail")?.isNotBlank() == true -> json.optString("detail")
            body.isNotBlank() -> "Login gagal"
            else -> "Terjadi kesalahan koneksi"
        }
        return LoginResult(false, message)
    }

    private fun isCaptcha(detail: JSONObject?): Boolean {
        if (detail == null) return false
        val type = detail.optString("type")
        return type == "captcha_required" || type == "captcha_wrong" ||
            detail.has("challenge_id") || detail.has("question")
    }

    private fun signature(): String? {
        cachedSignature?.let { return it }
        val value = SignatureUtil.sha256Fingerprint(context)
        if (value != "ERROR") {
            cachedSignature = value
        }
        return value
    }

    private fun packageMeta(): Pair<String, String> {
        return try {
            val info = context.packageManager.getPackageInfo(context.packageName, 0)
            val version = info.versionName ?: "2.0.0"
            val build = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.P) {
                info.longVersionCode.toString()
            } else {
                @Suppress("DEPRECATION")
                info.versionCode.toString()
            }
            version to build
        } catch (_: PackageManager.NameNotFoundException) {
            "2.0.0" to "2"
        }
    }

    private fun storedConfigKeyHash(): String? {
        Prefs.configKeyHash?.takeIf { it.isNotBlank() }?.let { return it }
        val key = Prefs.configKey ?: return null
        val digest = MessageDigest.getInstance("SHA-256").digest(key.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }

    private fun String.toJsonObject(): JSONObject? {
        if (isBlank()) return null
        return try {
            JSONObject(this)
        } catch (_: Exception) {
            null
        }
    }

    companion object {
        const val USER_AGENT =
            "Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 SEB/3.5 Exambro/1.0"

        @Volatile
        private var instance: ApiClient? = null

        fun init(context: Context) {
            if (instance == null) {
                instance = ApiClient(context.applicationContext)
            }
        }

        fun get(): ApiClient = instance ?: error("ApiClient not initialized")
    }
}
