import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../widgets/common_widgets.dart';
import '../services/security_service.dart';
import '../services/api_service.dart';
import '../config.dart';

/// Animated Splash Page with modern design and securitycheck
class SplashPage extends StatefulWidget {
  final VoidCallback onComplete;

  const SplashPage({super.key, required this.onComplete});

  @override
  State<SplashPage> createState() => _SplashPageState();
}

class _SplashPageState extends State<SplashPage>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  // Security check state
  bool _isCheckingSecurity = true;
  bool _securityCheckPassed = false;
  String _securityErrorMessage = '';

  @override
  void initState() {
    super.initState();

    _controller = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    );

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _controller,
        curve: const Interval(0.0, 0.6, curve: Curves.easeOut),
      ),
    );

    _slideAnimation =
        Tween<Offset>(begin: const Offset(0, 0.3), end: Offset.zero).animate(
          CurvedAnimation(
            parent: _controller,
            curve: const Interval(0.2, 0.8, curve: Curves.easeOut),
          ),
        );

    _controller.forward();

    // Perform security check BEFORE allowing app to proceed
    _performSecurityCheck();
  }

  /// Perform comprehensive security check on startup
  Future<void> _performSecurityCheck() async {
    try {
      // Wait for splash animation to start
      await Future.delayed(const Duration(milliseconds: 500));

      // Perform full security check
      final securityCheck = await SecurityService.performFullSecurityCheck();

      if (!mounted) return;

      if (!securityCheck.isSecure) {
        setState(() {
          _isCheckingSecurity = false;
          _securityCheckPassed = false;
          _securityErrorMessage = securityCheck.violations.join('\n');
        });
        return;
      }

      // Security passed, now validate build token with server
      await _validateBuildToken();
    } catch (e) {
      // If error during check, fail secure (block access)
      if (mounted) {
        setState(() {
          _isCheckingSecurity = false;
          _securityCheckPassed = false;
          _securityErrorMessage = 'Gagal melakukan verifikasi keamanan';
        });
      }
    }
  }

  /// Validate build token against server
  Future<void> _validateBuildToken() async {
    try {
      // Load API service config first
      final apiService = ApiService();
      await apiService.loadSavedConfig();

      // Skip token validation if server not configured
      if (!apiService.isConfigured) {
        _proceedToApp();
        return;
      }

      // Validate build token with server
      final tokenResult = await apiService.validateBuildToken();

      if (!mounted) return;

      if (tokenResult['update_required'] == true) {
        // Token is outdated, show update required screen
        setState(() {
          _isCheckingSecurity = false;
          _securityCheckPassed = false;
          _securityErrorMessage =
              tokenResult['message'] ??
              'Versi aplikasi sudah tidak berlaku.\nSilakan download versi terbaru.';
        });
        return;
      }

      // Token is valid, proceed
      _proceedToApp();
    } catch (e) {
      // On error, allow app to continue (backward compatibility)
      debugPrint('Token validation error: $e');
      _proceedToApp();
    }
  }

  /// Proceed to main app after all checks pass
  void _proceedToApp() async {
    if (!mounted) return;

    setState(() {
      _isCheckingSecurity = false;
      _securityCheckPassed = true;
    });

    await Future.delayed(const Duration(milliseconds: 500));
    if (mounted) {
      widget.onComplete();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // If security check failed, show error screen
    if (!_isCheckingSecurity && !_securityCheckPassed) {
      return _buildSecurityBlockedScreen();
    }

    // Otherwise show normal splash with loading
    return _buildNormalSplash();
  }

  /// Build normal splash screen with animation
  Widget _buildNormalSplash() {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF0f172a), Color(0xFF1e293b), Color(0xFF0f172a)],
          ),
        ),
        child: Stack(
          children: [
            // Background patterns
            Positioned(
              top: -100,
              right: -100,
              child: Container(
                width: 300,
                height: 300,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      const Color(0xFF3b82f6).withValues(alpha: 0.2),
                      Colors.transparent,
                    ],
                  ),
                ),
              ),
            ),
            Positioned(
              bottom: -50,
              left: -50,
              child: Container(
                width: 200,
                height: 200,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      const Color(0xFF10b981).withValues(alpha: 0.2),
                      Colors.transparent,
                    ],
                  ),
                ),
              ),
            ),

            // Main content
            Center(
              child: AnimatedBuilder(
                animation: _controller,
                builder: (context, child) {
                  return FadeTransition(
                    opacity: _fadeAnimation,
                    child: SlideTransition(
                      position: _slideAnimation,
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          // Animated logo
                          const AnimatedLogo(size: 140),

                          const SizedBox(height: 40),

                          // Title
                          ShaderMask(
                            shaderCallback: (bounds) => const LinearGradient(
                              colors: [Color(0xFF10b981), Color(0xFF3b82f6)],
                            ).createShader(bounds),
                            child: const Text(
                              AppConfig.appName,
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 32,
                                fontWeight: FontWeight.bold,
                                letterSpacing: 4,
                              ),
                            ),
                          ),

                          const SizedBox(height: 8),

                          Text(
                            AppConfig.appSubtitle,
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.7),
                              fontSize: 18,
                              fontWeight: FontWeight.w300,
                              letterSpacing: 8,
                            ),
                          ),

                          const SizedBox(height: 60),

                          // Loading indicator
                          SizedBox(
                            width: 40,
                            height: 40,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor: AlwaysStoppedAnimation<Color>(
                                Colors.white.withValues(alpha: 0.5),
                              ),
                            ),
                          ),

                          const SizedBox(height: 16),

                          Text(
                            _isCheckingSecurity
                                ? 'Memverifikasi keamanan...'
                                : 'Mempersiapkan...',
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.5),
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),

            // Bottom version info
            Positioned(
              bottom: 40,
              left: 0,
              right: 0,
              child: FadeTransition(
                opacity: _fadeAnimation,
                child: Column(
                  children: [
                    Text(
                      AppConfig.appName,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.4),
                        fontSize: 12,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      AppConfig.appSubtitle,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.3),
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Build security blocked screen when APK is modified
  Widget _buildSecurityBlockedScreen() {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFF1e1b4b), // Dark purple
              Color(0xFF450a0a), // Dark red
              Color(0xFF1e1b4b),
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // Security icon with pulsing animation
                  Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: Colors.red.withValues(alpha: 0.2),
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: Colors.red.withValues(alpha: 0.5),
                        width: 2,
                      ),
                    ),
                    child: const Icon(
                      Icons.security,
                      size: 80,
                      color: Colors.red,
                    ),
                  ),

                  const SizedBox(height: 40),

                  // Error title
                  const Text(
                    '🚫 AKSES DITOLAK',
                    style: TextStyle(
                      color: Colors.red,
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 2,
                    ),
                    textAlign: TextAlign.center,
                  ),

                  const SizedBox(height: 24),

                  // Error message container
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.3),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: Colors.red.withValues(alpha: 0.3),
                        width: 1,
                      ),
                    ),
                    child: Column(
                      children: [
                        const Text(
                          'Verifikasi Keamanan Gagal',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 16),
                        Text(
                          _securityErrorMessage.isNotEmpty
                              ? _securityErrorMessage
                              : 'Aplikasi ini tidak dapat diverifikasi',
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.9),
                            fontSize: 14,
                            height: 1.5,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 32),

                  // Warning box
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.orange.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: Colors.orange.withValues(alpha: 0.3),
                      ),
                    ),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.warning_amber_rounded,
                          color: Colors.orange,
                          size: 24,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            'Anda tidak dapat login atau mengikuti ujian dengan aplikasi ini.',
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.8),
                              fontSize: 12,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 32),

                  // Instructions
                  Text(
                    'Silakan gunakan APK resmi dari penyelenggara ujian',
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.6),
                      fontSize: 13,
                    ),
                    textAlign: TextAlign.center,
                  ),

                  const SizedBox(height: 40),

                  // Exit button
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: () {
                        SystemNavigator.pop(); // Exit app
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.red,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                        elevation: 8,
                      ),
                      child: const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.exit_to_app, size: 20),
                          SizedBox(width: 8),
                          Text(
                            'TUTUP APLIKASI',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                              letterSpacing: 1,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
