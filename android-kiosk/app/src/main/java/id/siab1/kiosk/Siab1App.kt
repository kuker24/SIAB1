package id.siab1.kiosk

import android.app.Application
import id.siab1.kiosk.net.ApiClient
import id.siab1.kiosk.util.Prefs

class Siab1App : Application() {
    override fun onCreate() {
        super.onCreate()
        Prefs.init(this)
        ApiClient.init(this)
    }
}
