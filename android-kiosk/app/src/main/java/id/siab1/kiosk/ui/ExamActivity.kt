package id.siab1.kiosk.ui

import android.annotation.SuppressLint
import android.app.ActivityManager
import android.app.AlertDialog
import android.content.Intent
import android.graphics.BitmapFactory
import android.os.Build
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import id.siab1.kiosk.AppConfig
import id.siab1.kiosk.R
import id.siab1.kiosk.databinding.ActivityExamBinding
import id.siab1.kiosk.kiosk.KioskController
import id.siab1.kiosk.net.ApiClient
import id.siab1.kiosk.util.Prefs
import id.siab1.kiosk.util.SignatureUtil
import id.siab1.kiosk.web.Siab1Bridge
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors

class ExamActivity : AppCompatActivity() {
    private lateinit var binding: ActivityExamBinding
    private lateinit var kiosk: KioskController
    private val io = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityExamBinding.inflate(layoutInflater)
        setContentView(binding.root)
        kiosk = KioskController(this)
        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (!kiosk.examActive) {
                        finish()
                    }
                }
            },
        )
        setupWebView()
        loadDashboard()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val webView = binding.examWebView
        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.mediaPlaybackRequiresUserGesture = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        settings.cacheMode = WebSettings.LOAD_DEFAULT
        settings.userAgentString = ApiClient.USER_AGENT
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.safeBrowsingEnabled = true
        }
        webView.addJavascriptInterface(
            Siab1Bridge { name, args -> runOnUiThread { dispatchHandler(name, args) } },
            "SIAB1Bridge",
        )
        val startScript = documentStartScript()
        if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            WebViewCompat.addDocumentStartJavaScript(webView, startScript, setOf("*"))
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                binding.examProgress.visibility = if (newProgress >= 100) View.GONE else View.VISIBLE
            }
        }
        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                view?.evaluateJavascript(startScript, null)
            }

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                var url = request.url.toString()
                if (AppConfig.forceHttps && url.startsWith("http://")) {
                    url = "https://" + url.removePrefix("http://")
                    view.loadUrl(url, ApiClient.get().webViewHeaders())
                    return true
                }
                return !(url.startsWith("https://") || url.startsWith("http://"))
            }
        }
    }

    private fun loadDashboard() {
        binding.examWebView.loadUrl(AppConfig.studentDashboardUrl(), ApiClient.get().webViewHeaders())
    }

    private fun documentStartScript(): String {
        val token = Prefs.token
        val userJson = Prefs.userJson
        val signature = SignatureUtil.sha256Fingerprint(this)
        val tokenJs = if (token.isNullOrBlank()) "null" else JSONObject.quote(token)
        val userJs = if (userJson.isNullOrBlank()) "null" else JSONObject.quote(userJson)
        val buildJs = JSONObject.quote(AppConfig.buildToken)
        val sigJs = if (signature == "ERROR") "null" else JSONObject.quote(signature)
        return """
            window.flutter_inappwebview = { callHandler: function(name) { var args = Array.prototype.slice.call(arguments,1); return window.SIAB1Bridge.post(name, JSON.stringify(args)); } };
            try {
              var token = $tokenJs;
              var userJson = $userJs;
              var buildToken = $buildJs;
              var appSig = $sigJs;
              if (token) { localStorage.setItem('access_token', token); }
              if (userJson) { localStorage.setItem('user', userJson); }
              localStorage.setItem('sxb_build_token', buildToken);
              if (appSig) { localStorage.setItem('sxb_app_signature', appSig); }
            } catch (e) {}
        """.trimIndent()
    }

    private fun dispatchHandler(name: String, args: JSONArray) {
        when (name) {
            "openImagePreview" -> openImagePreview(args)
            "securityHandler" -> { }
            "setSessionId" -> handleSetSessionId(args)
            "answerJournalEvent" -> handleAnswerJournal(args)
            "examStateUpdate" -> handleExamState(args)
            "timerSync" -> handleTimerSync(args)
            "examSubmitted" -> handleExamSubmitted()
            "logViolation" -> handleLogViolation(args)
            "userLogout" -> handleLogout()
            "forceKicked" -> handleForceKicked(args)
            "forceSubmit" -> handleForceSubmit(args)
            "examCancelled" -> handleExamCancelled(args)
        }
    }

    private fun handleSetSessionId(args: JSONArray) {
        if (args.length() == 0) return
        Prefs.sessionId = args.optString(0)
        if (args.length() > 1) {
            Prefs.examId = args.optString(1)
        }
        kiosk.startExamLock()
    }

    private fun handleAnswerJournal(args: JSONArray) {
        if (args.length() == 0 || Prefs.sessionId.isNullOrBlank()) return
        val payload = args.optJSONObject(0) ?: return
        val existing = Prefs.answerJournal
        val queue = try {
            if (existing.isNullOrBlank()) JSONArray() else JSONArray(existing)
        } catch (_: Exception) {
            JSONArray()
        }
        queue.put(payload)
        Prefs.answerJournal = queue.toString()
    }

    private fun handleExamState(args: JSONArray) {
        if (args.length() == 0) return
        val payload = args.optJSONObject(0) ?: return
        Prefs.examState = payload.toString()
    }

    private fun handleTimerSync(args: JSONArray) {
        if (args.length() == 0 || Prefs.sessionId.isNullOrBlank()) return
        val payload = args.optJSONObject(0) ?: return
        Prefs.timerSync = payload.toString()
    }

    private fun handleExamSubmitted() {
        kiosk.stopExamLock()
        Prefs.clearSession()
        Toast.makeText(this, R.string.exam_submitted, Toast.LENGTH_LONG).show()
    }

    private fun handleLogViolation(args: JSONArray) {
        val sessionId = Prefs.sessionId ?: return
        if (args.length() < 2) return
        val type = args.optString(0)
        val count = args.optInt(1, 1)
        val details = if (args.length() > 2) args.optString(2) else null
        io.execute {
            ApiClient.get().logViolation(sessionId, type, count, details)
        }
    }

    private fun handleLogout() {
        kiosk.stopExamLock()
        Prefs.clearAuth()
        goLogin()
    }

    private fun handleForceKicked(args: JSONArray) {
        val reason = if (args.length() > 0) args.optString(0) else getString(R.string.force_kicked_body)
        kiosk.stopExamLock()
        Prefs.clearSession()
        showExitDialog(
            title = getString(R.string.force_kicked_title),
            reason = reason,
            body = getString(R.string.force_kicked_body),
            color = 0xFFEF4444.toInt(),
        )
    }

    private fun handleForceSubmit(args: JSONArray) {
        val reason = if (args.length() > 0) {
            args.optString(0)
        } else {
            "Dikumpulkan oleh pengawas"
        }
        Toast.makeText(this, "Ujian dikumpulkan: $reason", Toast.LENGTH_LONG).show()
    }

    private fun handleExamCancelled(args: JSONArray) {
        val reason = if (args.length() > 0) args.optString(0) else getString(R.string.exam_cancelled_body)
        kiosk.stopExamLock()
        Prefs.clearSession()
        showExitDialog(
            title = getString(R.string.exam_cancelled_title),
            reason = reason,
            body = getString(R.string.exam_cancelled_body),
            color = 0xFFF59E0B.toInt(),
        )
    }

    private fun showExitDialog(title: String, reason: String, body: String, color: Int) {
        val dialog = AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage("$reason\n\n$body")
            .setCancelable(false)
            .setPositiveButton(R.string.back_home) { d, _ ->
                d.dismiss()
                Prefs.clearAuth()
                goLogin()
            }
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setTextColor(color)
        }
        dialog.show()
    }

    private fun openImagePreview(args: JSONArray) {
        if (args.length() == 0) return
        val raw = args.optString(0).trim()
        if (raw.isEmpty()) return
        val title = if (args.length() > 1 && args.optString(1).isNotBlank()) {
            args.optString(1)
        } else {
            getString(R.string.image_preview)
        }
        val resolved = resolveUrl(raw) ?: return
        io.execute {
            val bytes = ApiClient.get().fetchBytes(resolved) ?: return@execute
            val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return@execute
            runOnUiThread {
                val view = layoutInflater.inflate(R.layout.dialog_image_preview, null)
                view.findViewById<TextView>(R.id.previewTitle).text = title
                view.findViewById<ImageView>(R.id.previewImage).setImageBitmap(bitmap)
                AlertDialog.Builder(this)
                    .setView(view)
                    .setPositiveButton(android.R.string.ok, null)
                    .show()
            }
        }
    }

    private fun resolveUrl(raw: String): String? {
        if (raw.startsWith("https://") || raw.startsWith("http://")) {
            return if (AppConfig.forceHttps && raw.startsWith("http://")) {
                "https://" + raw.removePrefix("http://")
            } else {
                raw
            }
        }
        val current = binding.examWebView.url
        if (!current.isNullOrBlank()) {
            return try {
                java.net.URI(current).resolve(raw).toString()
            } catch (_: Exception) {
                AppConfig.normalizedServerUrl() + raw.trimStart('/')
            }
        }
        return AppConfig.normalizedServerUrl() + raw.trimStart('/')
    }

    private fun goLogin() {
        val intent = Intent(this, LoginActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        startActivity(intent)
        finish()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus && kiosk.examActive) {
            kiosk.applyImmersive()
        }
        if (!hasFocus && kiosk.examActive) {
            try {
                val manager = getSystemService(ACTIVITY_SERVICE) as ActivityManager
                manager.moveTaskToFront(taskId, 0)
            } catch (_: Exception) {
            }
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (kiosk.examActive) {
            return when (keyCode) {
                KeyEvent.KEYCODE_VOLUME_UP,
                KeyEvent.KEYCODE_VOLUME_DOWN,
                KeyEvent.KEYCODE_HOME,
                KeyEvent.KEYCODE_BACK,
                KeyEvent.KEYCODE_MENU,
                KeyEvent.KEYCODE_APP_SWITCH,
                -> true
                else -> super.onKeyDown(keyCode, event)
            }
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onKeyLongPress(keyCode: Int, event: KeyEvent?): Boolean {
        if (kiosk.examActive && keyCode == KeyEvent.KEYCODE_BACK) {
            return true
        }
        return super.onKeyLongPress(keyCode, event)
    }

    override fun onDestroy() {
        if (kiosk.examActive) {
            kiosk.stopExamLock()
        }
        binding.examWebView.apply {
            stopLoading()
            removeJavascriptInterface("SIAB1Bridge")
            destroy()
        }
        io.shutdownNow()
        super.onDestroy()
    }
}
