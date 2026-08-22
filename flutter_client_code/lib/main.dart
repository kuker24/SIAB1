import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'config.dart';
import 'pages/splash_page.dart';
import 'pages/native_login_page.dart';
import 'services/api_service.dart';
import 'widgets/common_widgets.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Allow all orientations initially
  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.landscapeLeft,
    DeviceOrientation.landscapeRight,
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);

  // Set immersive mode
  await SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);

  runApp(const SXBClientApp());
}

class SXBClientApp extends StatelessWidget {
  const SXBClientApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF3b82f6),
          brightness: Brightness.dark,
        ),
        scaffoldBackgroundColor: const Color(0xFF0f172a),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF0f172a),
          foregroundColor: Colors.white,
          elevation: 0,
        ),
        fontFamily: 'Inter',
      ),
      home: const AppRouter(),
    );
  }
}

/// Main app router - native splash, native login, then authenticated WebView.
class AppRouter extends StatefulWidget {
  const AppRouter({super.key});

  @override
  State<AppRouter> createState() => _AppRouterState();
}

class _AppRouterState extends State<AppRouter> {
  bool _showSplash = true;
  bool _isConnecting = false;
  bool _connectionFailed = false;
  String _errorMessage = '';
  final _apiService = ApiService();

  @override
  void initState() {
    super.initState();
  }

  void _onSplashComplete() {
    setState(() {
      _showSplash = false;
    });
    _connectToServer();
  }

  Future<void> _connectToServer() async {
    setState(() {
      _isConnecting = true;
      _connectionFailed = false;
      _errorMessage = '';
    });

    try {
      // Load config (will use AppConfig.serverUrl if storage is empty)
      await _apiService.loadSavedConfig();

      if (!_apiService.isConfigured) {
        setState(() {
          _isConnecting = false;
          _connectionFailed = true;
          _errorMessage =
              'Server URL tidak dikonfigurasi.\nHubungi administrator.';
        });
        return;
      }

      // Verify server is accessible
      final isConnected = await _apiService.verifyConnection();

      if (isConnected && mounted) {
        Navigator.of(context).pushReplacement(
          PageRouteBuilder(
            pageBuilder: (_, __, ___) => const NativeLoginPage(),
            transitionsBuilder: (_, animation, __, child) {
              return FadeTransition(opacity: animation, child: child);
            },
            transitionDuration: const Duration(milliseconds: 500),
          ),
        );
        return;
      }

      // Connection failed
      setState(() {
        _isConnecting = false;
        _connectionFailed = true;
        _errorMessage =
            'Gagal terhubung ke ${_apiService.serverUrl}\n\nPastikan:\n• HP terhubung ke Wi-Fi yang sama dengan server\n• Server ujian sedang aktif';
      });
    } catch (e) {
      setState(() {
        _isConnecting = false;
        _connectionFailed = true;
        _errorMessage = 'Error: ${e.toString()}';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_showSplash) {
      return SplashPage(onComplete: _onSplashComplete);
    }

    // Connection error screen with retry (NO URL INPUT)
    return Scaffold(
      backgroundColor: const Color(0xFF0f172a),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF0f172a), Color(0xFF1e293b), Color(0xFF0f172a)],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const AnimatedLogo(size: 100),
                  const SizedBox(height: 32),
                  ShaderMask(
                    shaderCallback: (bounds) => const LinearGradient(
                      colors: [Color(0xFF10b981), Color(0xFF3b82f6)],
                    ).createShader(bounds),
                    child: const Text(
                      AppConfig.appName,
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 28,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  const SizedBox(height: 48),
                  if (_isConnecting) ...[
                    const CircularProgressIndicator(color: Color(0xFF3b82f6)),
                    const SizedBox(height: 16),
                    Text(
                      'Menghubungkan ke Server...',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.7),
                      ),
                    ),
                  ] else if (_connectionFailed) ...[
                    Container(
                      padding: const EdgeInsets.all(20),
                      margin: const EdgeInsets.symmetric(horizontal: 16),
                      decoration: BoxDecoration(
                        color: Colors.red.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: Colors.red.withValues(alpha: 0.3),
                        ),
                      ),
                      child: Column(
                        children: [
                          const Icon(
                            Icons.cloud_off_rounded,
                            color: Colors.red,
                            size: 56,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            _errorMessage,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 14,
                              height: 1.5,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 32),
                    SizedBox(
                      width: 220,
                      child: GradientButton(
                        text: 'Coba Lagi',
                        icon: Icons.refresh_rounded,
                        onPressed: _connectToServer,
                        colors: const [Color(0xFF3b82f6), Color(0xFF2563eb)],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
