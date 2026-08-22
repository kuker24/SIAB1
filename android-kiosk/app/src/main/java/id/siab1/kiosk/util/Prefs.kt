package id.siab1.kiosk.util

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKeys

object Prefs {
    private const val FILE = "siab1_secure"
    private const val FALLBACK = "siab1_prefs"
    private const val KEY_TOKEN = "auth_token"
    private const val KEY_USER = "user_json"
    private const val KEY_CONFIG_KEY = "config_key"
    private const val KEY_CONFIG_KEY_HASH = "config_key_hash"
    private const val KEY_SESSION_ID = "session_id"
    private const val KEY_EXAM_ID = "exam_id"
    private const val KEY_ANSWER_JOURNAL = "answer_journal"
    private const val KEY_EXAM_STATE = "exam_state"
    private const val KEY_TIMER_SYNC = "timer_sync"

    private lateinit var prefs: SharedPreferences

    fun init(context: Context) {
        val app = context.applicationContext
        prefs = try {
            val masterKeyAlias = MasterKeys.getOrCreate(MasterKeys.AES256_GCM_SPEC)
            EncryptedSharedPreferences.create(
                FILE,
                masterKeyAlias,
                app,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            )
        } catch (_: Exception) {
            app.getSharedPreferences(FALLBACK, Context.MODE_PRIVATE)
        }
    }

    var token: String?
        get() = prefs.getString(KEY_TOKEN, null)
        set(value) {
            prefs.edit().putString(KEY_TOKEN, value).apply()
        }

    var userJson: String?
        get() = prefs.getString(KEY_USER, null)
        set(value) {
            prefs.edit().putString(KEY_USER, value).apply()
        }

    var configKey: String?
        get() = prefs.getString(KEY_CONFIG_KEY, null)
        set(value) {
            prefs.edit().putString(KEY_CONFIG_KEY, value).apply()
        }

    var configKeyHash: String?
        get() = prefs.getString(KEY_CONFIG_KEY_HASH, null)
        set(value) {
            prefs.edit().putString(KEY_CONFIG_KEY_HASH, value).apply()
        }

    var sessionId: String?
        get() = prefs.getString(KEY_SESSION_ID, null)
        set(value) {
            prefs.edit().putString(KEY_SESSION_ID, value).apply()
        }

    var examId: String?
        get() = prefs.getString(KEY_EXAM_ID, null)
        set(value) {
            prefs.edit().putString(KEY_EXAM_ID, value).apply()
        }

    var answerJournal: String?
        get() = prefs.getString(KEY_ANSWER_JOURNAL, null)
        set(value) {
            prefs.edit().putString(KEY_ANSWER_JOURNAL, value).apply()
        }

    var examState: String?
        get() = prefs.getString(KEY_EXAM_STATE, null)
        set(value) {
            prefs.edit().putString(KEY_EXAM_STATE, value).apply()
        }

    var timerSync: String?
        get() = prefs.getString(KEY_TIMER_SYNC, null)
        set(value) {
            prefs.edit().putString(KEY_TIMER_SYNC, value).apply()
        }

    fun clearSession() {
        prefs.edit()
            .remove(KEY_SESSION_ID)
            .remove(KEY_EXAM_ID)
            .remove(KEY_ANSWER_JOURNAL)
            .remove(KEY_EXAM_STATE)
            .remove(KEY_TIMER_SYNC)
            .apply()
    }

    fun clearAuth() {
        prefs.edit()
            .remove(KEY_TOKEN)
            .remove(KEY_USER)
            .apply()
        clearSession()
    }
}
