package id.siab1.kiosk.ui

import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import id.siab1.kiosk.R
import id.siab1.kiosk.databinding.ActivityLoginBinding
import id.siab1.kiosk.net.ApiClient
import java.util.concurrent.Executors

class LoginActivity : AppCompatActivity() {
    private lateinit var binding: ActivityLoginBinding
    private val io = Executors.newSingleThreadExecutor()
    private var securityReady = false
    private var loading = false
    private var passwordVisible = false
    private var captchaId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(binding.root)
        binding.togglePassword.setOnClickListener { togglePassword() }
        binding.loginButton.setOnClickListener { submit() }
        binding.securityRetry.setOnClickListener { prepareSecurity() }
        binding.password.setOnEditorActionListener { _, _, _ ->
            if (binding.captchaRow.visibility != View.VISIBLE) {
                submit()
                true
            } else {
                false
            }
        }
        binding.captchaAnswer.setOnEditorActionListener { _, _, _ ->
            submit()
            true
        }
        prepareSecurity()
    }

    private fun prepareSecurity() {
        setSecurityBanner(getString(R.string.security_preparing), R.color.status_blue, false)
        binding.loginButton.isEnabled = false
        io.execute {
            var ready = false
            for (attempt in 0 until 3) {
                ready = try {
                    ApiClient.get().prepareSecurityContext()
                } catch (_: Exception) {
                    false
                }
                if (ready) break
                if (attempt < 2) Thread.sleep(180L * (attempt + 1))
            }
            runOnUiThread {
                securityReady = ready
                if (ready) {
                    setSecurityBanner(getString(R.string.security_ready), R.color.status_green, false)
                    binding.loginButton.isEnabled = !loading
                } else {
                    setSecurityBanner(getString(R.string.security_failed), R.color.status_red, true)
                    binding.loginButton.isEnabled = false
                }
            }
        }
    }

    private fun submit() {
        if (loading) return
        if (!securityReady) {
            prepareSecurity()
            return
        }
        val username = binding.username.text?.toString()?.trim().orEmpty()
        val password = binding.password.text?.toString().orEmpty()
        if (username.isEmpty()) {
            Toast.makeText(this, R.string.username_required, Toast.LENGTH_SHORT).show()
            return
        }
        if (password.isEmpty()) {
            Toast.makeText(this, R.string.password_required, Toast.LENGTH_SHORT).show()
            return
        }
        val captchaAnswer = binding.captchaAnswer.text?.toString()?.trim().orEmpty()
        if (binding.captchaRow.visibility == View.VISIBLE && captchaAnswer.isEmpty()) {
            Toast.makeText(this, R.string.captcha_required, Toast.LENGTH_SHORT).show()
            return
        }
        setLoading(true)
        hideError()
        io.execute {
            val result = try {
                ApiClient.get().login(
                    username = username,
                    password = password,
                    captchaId = captchaId,
                    captchaAnswer = captchaAnswer.ifBlank { null },
                )
            } catch (_: Exception) {
                ApiClient.LoginResult(false, "Terjadi kesalahan koneksi")
            }
            runOnUiThread {
                if (result.success) {
                    startActivity(Intent(this, ExamActivity::class.java))
                    finish()
                    return@runOnUiThread
                }
                setLoading(false)
                if (result.captchaRequired) {
                    captchaId = result.captchaId
                    showCaptcha(result.captchaQuestion.orEmpty())
                }
                showError(result.message)
            }
        }
    }

    private fun setLoading(value: Boolean) {
        loading = value
        binding.loginButton.isEnabled = !value && securityReady
        binding.loginButton.text = if (value) "" else getString(R.string.login)
        binding.loginProgress.visibility = if (value) View.VISIBLE else View.GONE
        binding.username.isEnabled = !value
        binding.password.isEnabled = !value
        binding.captchaAnswer.isEnabled = !value
    }

    private fun setSecurityBanner(message: String, colorRes: Int, retry: Boolean) {
        binding.securityMessage.text = message
        binding.securityIcon.setColorFilter(ContextCompat.getColor(this, colorRes))
        binding.securityRetry.visibility = if (retry) View.VISIBLE else View.GONE
    }

    private fun showError(message: String) {
        binding.errorBanner.visibility = View.VISIBLE
        binding.errorMessage.text = message
    }

    private fun hideError() {
        binding.errorBanner.visibility = View.GONE
    }

    private fun showCaptcha(question: String) {
        binding.captchaBanner.visibility = View.VISIBLE
        binding.captchaRow.visibility = View.VISIBLE
        binding.captchaQuestion.text = question
        binding.captchaAnswer.setText("")
    }

    private fun togglePassword() {
        passwordVisible = !passwordVisible
        binding.password.inputType = if (passwordVisible) {
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
        } else {
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        binding.password.setSelection(binding.password.text?.length ?: 0)
        binding.togglePassword.setImageResource(
            if (passwordVisible) R.drawable.ic_visibility_off else R.drawable.ic_visibility,
        )
    }

    override fun onDestroy() {
        io.shutdownNow()
        super.onDestroy()
    }
}
