package id.siab1.kiosk.web

import android.webkit.JavascriptInterface
import org.json.JSONArray

class Siab1Bridge(private val listener: Listener) {
    fun interface Listener {
        fun onHandler(name: String, args: JSONArray)
    }

    @JavascriptInterface
    fun post(handlerName: String, argsJson: String): String {
        val args = try {
            JSONArray(argsJson)
        } catch (_: Exception) {
            JSONArray()
        }
        listener.onHandler(handlerName, args)
        return "true"
    }
}
