import 'native_login_page.dart';

/// Backward-compatible alias for the restored native APK login page.
/// New code should import/use [NativeLoginPage] directly.
class LoginPage extends NativeLoginPage {
  const LoginPage({super.key, super.onLoginSuccess});
}
