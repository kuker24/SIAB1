import 'package:flutter/material.dart';

import '../config.dart';
import '../services/api_service.dart';
import '../widgets/common_widgets.dart';
import 'exam_page.dart';

class NativeLoginPage extends StatefulWidget {
  final VoidCallback? onLoginSuccess;

  const NativeLoginPage({super.key, this.onLoginSuccess});

  @override
  State<NativeLoginPage> createState() => _NativeLoginPageState();
}

class _NativeLoginPageState extends State<NativeLoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _captchaAnswerController = TextEditingController();
  final ApiService _apiService = ApiService();

  bool _isPreparingSecurity = true;
  bool _securityReady = false;
  bool _isLoading = false;
  bool _obscurePassword = true;
  String? _errorMessage;
  String? _captchaId;
  String? _captchaQuestion;

  @override
  void initState() {
    super.initState();
    _prepareSecurityContext();
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _captchaAnswerController.dispose();
    super.dispose();
  }

  Future<void> _prepareSecurityContext() async {
    setState(() {
      _isPreparingSecurity = true;
      _errorMessage = null;
    });

    try {
      await _apiService.loadSavedConfig();
      final ready = await _apiService.prepareSecurityContext();
      if (!mounted) return;
      setState(() {
        _securityReady = ready;
        _isPreparingSecurity = false;
        if (!ready) {
          _errorMessage =
              'Gagal menyiapkan keamanan APK. Tutup aplikasi lalu coba lagi.';
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _securityReady = false;
        _isPreparingSecurity = false;
        _errorMessage = 'Gagal terhubung ke server ujian.';
      });
    }
  }

  Future<void> _handleLogin() async {
    if (_isLoading || _isPreparingSecurity) return;
    if (!_securityReady) {
      await _prepareSecurityContext();
      if (!_securityReady) return;
    }
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final result = await _apiService.login(
      _usernameController.text.trim(),
      _passwordController.text,
      captchaId: _captchaId,
      captchaAnswer: _captchaQuestion == null
          ? null
          : _captchaAnswerController.text.trim(),
    );

    if (!mounted) return;

    if (result['success'] == true) {
      _captchaId = null;
      _captchaQuestion = null;
      _captchaAnswerController.clear();
      _openExamShell();
      return;
    }

    setState(() {
      _isLoading = false;
      if (result['captcha_required'] == true) {
        _captchaId = result['captcha_id']?.toString();
        _captchaQuestion = result['captcha_question']?.toString();
        _captchaAnswerController.clear();
      }
      _errorMessage = result['message']?.toString() ?? 'Login gagal';
    });
  }

  void _openExamShell() {
    if (widget.onLoginSuccess != null) {
      widget.onLoginSuccess!();
      return;
    }

    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        pageBuilder: (_, __, ___) =>
            ExamPage(examUrl: _apiService.getStudentDashboardUrl()),
        transitionsBuilder: (_, animation, __, child) {
          return FadeTransition(opacity: animation, child: child);
        },
        transitionDuration: const Duration(milliseconds: 500),
      ),
    );
  }

  InputDecoration _inputDecoration({
    required String hint,
    required IconData icon,
    Widget? suffixIcon,
  }) {
    return InputDecoration(
      hintText: hint,
      prefixIcon: Icon(icon, color: const Color(0xFF60a5fa)),
      suffixIcon: suffixIcon,
      filled: true,
      fillColor: Colors.white,
      hintStyle: const TextStyle(color: Color(0xFF94a3b8)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: const BorderSide(color: Color(0xFFE2E8F0)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: const BorderSide(color: Color(0xFF2563eb), width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: const BorderSide(color: Color(0xFFef4444)),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: const BorderSide(color: Color(0xFFef4444), width: 2),
      ),
    );
  }

  Widget _buildSecurityStatus() {
    if (_isPreparingSecurity) {
      return const _StatusBanner(
        icon: Icons.shield_rounded,
        message: 'Menyiapkan keamanan APK...',
        color: Color(0xFF2563eb),
      );
    }
    if (!_securityReady) {
      return _StatusBanner(
        icon: Icons.warning_amber_rounded,
        message: _errorMessage ?? 'Keamanan APK belum siap.',
        color: const Color(0xFFef4444),
        actionLabel: 'Coba Lagi',
        onAction: _prepareSecurityContext,
      );
    }
    return const _StatusBanner(
      icon: Icons.verified_user_rounded,
      message: 'Ujian siap dimulai.',
      color: Color(0xFF16a34a),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;

    return Scaffold(
      resizeToAvoidBottomInset: true,
      backgroundColor: const Color(0xFF0f172a),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0xFF0b2f6f), Color(0xFF0f4fb3), Color(0xFF0b2f6f)],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + bottomInset),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Form(
                  key: _formKey,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Padding(
                        padding: EdgeInsets.only(bottom: 24),
                        child: Align(
                          child: SchoolLogo(
                            size: 104,
                            shadowColor: Color(0x4D000000),
                          ),
                        ),
                      ),
                      const Text(
                        AppConfig.appName,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 32,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 0.2,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        AppConfig.appSubtitle,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.86),
                          fontSize: 16,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 28),
                      _buildSecurityStatus(),
                      const SizedBox(height: 18),
                      if (_errorMessage != null && _securityReady) ...[
                        _StatusBanner(
                          icon: Icons.error_outline_rounded,
                          message: _errorMessage!,
                          color: const Color(0xFFef4444),
                        ),
                        const SizedBox(height: 14),
                      ],
                      TextFormField(
                        controller: _usernameController,
                        enabled: !_isLoading && !_isPreparingSecurity,
                        style: const TextStyle(color: Color(0xFF0f172a)),
                        textInputAction: TextInputAction.next,
                        autofillHints: const [AutofillHints.username],
                        decoration: _inputDecoration(
                          hint: 'Username',
                          icon: Icons.person_rounded,
                        ),
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return 'Username wajib diisi';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: _passwordController,
                        enabled: !_isLoading && !_isPreparingSecurity,
                        style: const TextStyle(color: Color(0xFF0f172a)),
                        obscureText: _obscurePassword,
                        textInputAction: _captchaQuestion == null
                            ? TextInputAction.done
                            : TextInputAction.next,
                        autofillHints: const [AutofillHints.password],
                        onFieldSubmitted: (_) {
                          if (_captchaQuestion == null) {
                            _handleLogin();
                          }
                        },
                        decoration: _inputDecoration(
                          hint: 'Password',
                          icon: Icons.lock_rounded,
                          suffixIcon: IconButton(
                            color: const Color(0xFF64748b),
                            onPressed: () {
                              setState(() {
                                _obscurePassword = !_obscurePassword;
                              });
                            },
                            icon: Icon(
                              _obscurePassword
                                  ? Icons.visibility_rounded
                                  : Icons.visibility_off_rounded,
                            ),
                          ),
                        ),
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return 'Password wajib diisi';
                          }
                          return null;
                        },
                      ),
                      if (_captchaQuestion != null) ...[
                        const SizedBox(height: 14),
                        _StatusBanner(
                          icon: Icons.shield_moon_rounded,
                          message: _captchaQuestion!,
                          color: const Color(0xFFf59e0b),
                        ),
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: _captchaAnswerController,
                          enabled: !_isLoading && !_isPreparingSecurity,
                          style: const TextStyle(color: Color(0xFF0f172a)),
                          textInputAction: TextInputAction.done,
                          onFieldSubmitted: (_) => _handleLogin(),
                          decoration: _inputDecoration(
                            hint: 'Jawaban verifikasi',
                            icon: Icons.security_rounded,
                          ),
                          validator: (value) {
                            if (_captchaQuestion != null &&
                                (value == null || value.trim().isEmpty)) {
                              return 'Jawaban verifikasi wajib diisi';
                            }
                            return null;
                          },
                        ),
                      ],
                      const SizedBox(height: 22),
                      SizedBox(
                        height: 56,
                        child: ElevatedButton(
                          onPressed: (_isLoading || _isPreparingSecurity)
                              ? null
                              : _handleLogin,
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF2563eb),
                            disabledBackgroundColor: const Color(
                              0xFF2563eb,
                            ).withValues(alpha: 0.45),
                            foregroundColor: Colors.white,
                            elevation: 10,
                            shadowColor: const Color(
                              0xFF1d4ed8,
                            ).withValues(alpha: 0.45),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(18),
                            ),
                          ),
                          child: _isLoading
                              ? const SizedBox(
                                  width: 22,
                                  height: 22,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2.3,
                                    color: Colors.white,
                                  ),
                                )
                              : const Text(
                                  'Masuk',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w800,
                                    letterSpacing: 1.2,
                                  ),
                                ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _StatusBanner extends StatelessWidget {
  final IconData icon;
  final String message;
  final Color color;
  final String? actionLabel;
  final VoidCallback? onAction;

  const _StatusBanner({
    required this.icon,
    required this.message,
    required this.color,
    this.actionLabel,
    this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.55)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                height: 1.35,
              ),
            ),
          ),
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(width: 10),
            TextButton(onPressed: onAction, child: Text(actionLabel!)),
          ],
        ],
      ),
    );
  }
}
