import 'dart:async';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../config.dart';
import '../services/api_service.dart';
import '../widgets/common_widgets.dart';
import 'exam_page.dart';

/// Professional Loading Screen with Game-Like Animation
class ConfigPage extends StatefulWidget {
  const ConfigPage({super.key});

  @override
  State<ConfigPage> createState() => _ConfigPageState();
}

class _ConfigPageState extends State<ConfigPage> with TickerProviderStateMixin {
  final _apiService = ApiService();

  bool _isLoading = true;
  bool _showQrScanner = false;
  double _loadingProgress = 0.0;
  String _loadingText = 'Memuat aplikasi...';

  late AnimationController _progressController;
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();

    // Progress animation controller
    _progressController = AnimationController(
      duration: const Duration(milliseconds: 2000),
      vsync: this,
    );

    // Pulse animation for logo
    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.95, end: 1.05).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    // Start loading sequence
    _startLoadingSequence();
  }

  Future<void> _startLoadingSequence() async {
    await _loadSavedConfig();

    // Simulate game-like loading with stages
    final stages = [
      {'progress': 0.2, 'text': 'Memuat sistem keamanan...'},
      {'progress': 0.4, 'text': 'Memeriksa koneksi...'},
      {'progress': 0.6, 'text': 'Menghubungkan ke server...'},
      {'progress': 0.8, 'text': 'Memproses data...'},
      {'progress': 1.0, 'text': 'Siap!'},
    ];

    for (var stage in stages) {
      await Future.delayed(const Duration(milliseconds: 400));
      if (!mounted) return;

      setState(() {
        _loadingProgress = stage['progress'] as double;
        _loadingText = stage['text'] as String;
      });

      // Try to connect at 60% progress
      if (_loadingProgress == 0.6) {
        final connected = await _tryAutoConnect();
        if (!connected) {
          // Connection failed, but continue to show menu
          await Future.delayed(const Duration(milliseconds: 400));
        }
      }
    }

    // Loading complete - show main menu
    await Future.delayed(const Duration(milliseconds: 500));
    if (mounted) {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _loadSavedConfig() async {
    await _apiService.loadSavedConfig();
  }

  Future<bool> _tryAutoConnect() async {
    try {
      if (_apiService.isConfigured) {
        final isConnected = await _apiService.verifyConnection();
        if (isConnected) {
          return true;
        }
      }
    } catch (e) {
      // Silent fail, will show in menu
    }
    return false;
  }

  void _startExam() async {
    if (_apiService.isConfigured) {
      final isConnected = await _apiService.verifyConnection();
      if (!mounted) return;
      if (isConnected) {
        Navigator.of(context).pushReplacement(
          PageRouteBuilder(
            pageBuilder: (_, __, ___) =>
                ExamPage(examUrl: _apiService.getExamUrl()),
            transitionsBuilder: (_, animation, __, child) {
              return FadeTransition(opacity: animation, child: child);
            },
            transitionDuration: const Duration(milliseconds: 500),
          ),
        );
        return;
      }
    }

    if (!mounted) return;

    // Show connection dialog if not connected
    _showConnectionDialog();
  }

  void _showConnectionDialog() {
    showDialog(
      context: context,
      builder: (context) => _ConnectionDialog(
        onConnected: () {
          Navigator.pop(context);
          _startExam();
        },
      ),
    );
  }

  void _clearCache() async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) =>
          const Center(child: CircularProgressIndicator(color: Colors.white)),
    );

    await Future.delayed(const Duration(seconds: 1));
    await _apiService.clearConfig();

    if (mounted) {
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Cache berhasil dibersihkan'),
          backgroundColor: const Color(0xFF10b981),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF0f172a), Color(0xFF1e293b), Color(0xFF334155)],
          ),
        ),
        child: SafeArea(
          child: _showQrScanner
              ? _buildQrScanner()
              : _isLoading
                  ? _buildLoadingScreen()
                  : _buildMainMenu(),
        ),
      ),
    );
  }

  Widget _buildLoadingScreen() {
    return Stack(
      children: [
        // Animated background particles
        ...List.generate(15, (index) => _buildFloatingParticle(index)),

        Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Animated Logo
              ScaleTransition(
                scale: _pulseAnimation,
                child: const SchoolLogo(size: 120),
              ),

              const SizedBox(height: 60),

              // App Name
              ShaderMask(
                shaderCallback: (bounds) => const LinearGradient(
                  colors: [Color(0xFF60a5fa), Color(0xFFa78bfa)],
                ).createShader(bounds),
                child: const Text(
                  AppConfig.appName,
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 32,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 2,
                  ),
                ),
              ),

              const SizedBox(height: 8),

              Text(
                AppConfig.appSubtitle,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.6),
                  fontSize: 14,
                  letterSpacing: 1,
                ),
              ),

              const SizedBox(height: 60),

              // Progress Bar
              Container(
                width: 280,
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(20),
                  gradient: LinearGradient(
                    colors: [
                      Colors.white.withValues(alpha: 0.1),
                      Colors.white.withValues(alpha: 0.05),
                    ],
                  ),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: Stack(
                    children: [
                      // Background
                      Container(
                        height: 8,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(16),
                        ),
                      ),
                      // Progress
                      FractionallySizedBox(
                        widthFactor: _loadingProgress,
                        child: Container(
                          height: 8,
                          decoration: BoxDecoration(
                            gradient: const LinearGradient(
                              colors: [Color(0xFF3b82f6), Color(0xFF8b5cf6)],
                            ),
                            borderRadius: BorderRadius.circular(16),
                            boxShadow: [
                              BoxShadow(
                                color: const Color(
                                  0xFF3b82f6,
                                ).withValues(alpha: 0.6),
                                blurRadius: 8,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 24),

              // Loading Text
              Text(
                _loadingText,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.7),
                  fontSize: 14,
                ),
              ),

              const SizedBox(height: 8),

              // Percentage
              Text(
                '${(_loadingProgress * 100).toInt()}%',
                style: const TextStyle(
                  color: Color(0xFF60a5fa),
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildMainMenu() {
    return Stack(
      children: [
        // Animated background
        ...List.generate(10, (index) => _buildFloatingParticle(index)),

        Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // Logo
                const SchoolLogo(size: 100),

                const SizedBox(height: 32),

                // Welcome Text
                ShaderMask(
                  shaderCallback: (bounds) => const LinearGradient(
                    colors: [Color(0xFF60a5fa), Color(0xFFa78bfa)],
                  ).createShader(bounds),
                  child: const Text(
                    'SELAMAT DATANG',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1.5,
                    ),
                  ),
                ),

                const SizedBox(height: 8),

                Text(
                  'Pilih menu untuk melanjutkan',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.6),
                    fontSize: 14,
                  ),
                ),

                const SizedBox(height: 60),

                // Menu Buttons
                _buildMenuButton(
                  icon: Icons.play_circle_filled_rounded,
                  title: 'Mulai Ujian',
                  subtitle: 'Bergabung ke sesi ujian',
                  gradient: const [Color(0xFF10b981), Color(0xFF059669)],
                  onTap: _startExam,
                ),

                const SizedBox(height: 16),

                _buildMenuButton(
                  icon: Icons.cleaning_services_rounded,
                  title: 'Bersihkan Cache',
                  subtitle: 'Hapus data tersimpan',
                  gradient: const [Color(0xFF3b82f6), Color(0xFF2563eb)],
                  onTap: _clearCache,
                ),

                const SizedBox(height: 16),

                _buildMenuButton(
                  icon: Icons.exit_to_app_rounded,
                  title: 'Keluar',
                  subtitle: 'Tutup aplikasi',
                  gradient: const [Color(0xFFef4444), Color(0xFFdc2626)],
                  onTap: () => Navigator.of(context).pop(),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildMenuButton({
    required IconData icon,
    required String title,
    required String subtitle,
    required List<Color> gradient,
    required VoidCallback onTap,
  }) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: LinearGradient(colors: gradient),
        boxShadow: [
          BoxShadow(
            color: gradient[0].withValues(alpha: 0.4),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(20),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(icon, color: Colors.white, size: 28),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.8),
                          fontSize: 13,
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(
                  Icons.arrow_forward_ios_rounded,
                  color: Colors.white.withValues(alpha: 0.7),
                  size: 20,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFloatingParticle(int index) {
    final random = index * 0.1;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0.0, end: 1.0),
      duration: Duration(milliseconds: 3000 + (index * 200)),
      curve: Curves.easeInOut,
      builder: (context, value, child) {
        return Positioned(
          left: (index % 5) * 80.0 + (value * 20),
          top: (index ~/ 5) * 200.0 + (value * 100),
          child: Opacity(
            opacity: (0.1 + random * 0.2) * (1 - value * 0.5),
            child: Container(
              width: 4 + (index % 3) * 2,
              height: 4 + (index % 3) * 2,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    const Color(0xFF60a5fa).withValues(alpha: 0.8),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
        );
      },
      onEnd: () {
        // Loop animation
        if (mounted) {
          setState(() {});
        }
      },
    );
  }

  Widget _buildQrScanner() {
    return Stack(
      children: [
        MobileScanner(
          onDetect: (capture) {
            final barcodes = capture.barcodes;
            if (barcodes.isEmpty) return;
            final code = barcodes.first.rawValue;
            if (code != null) {
              setState(() => _showQrScanner = false);
              _apiService.initialize(code).then((_) => _startExam());
            }
          },
        ),
        Container(color: Colors.black.withValues(alpha: 0.3)),
        Center(
          child: Container(
            width: 280,
            height: 280,
            decoration: BoxDecoration(
              border: Border.all(color: const Color(0xFF3b82f6), width: 3),
              borderRadius: BorderRadius.circular(24),
            ),
          ),
        ),
        Positioned(
          top: 16,
          left: 16,
          child: IconButton(
            onPressed: () => setState(() => _showQrScanner = false),
            icon: const Icon(Icons.close, color: Colors.white, size: 32),
          ),
        ),
      ],
    );
  }

  @override
  void dispose() {
    _progressController.dispose();
    _pulseController.dispose();
    super.dispose();
  }
}

// Connection Dialog Widget
class _ConnectionDialog extends StatefulWidget {
  final VoidCallback onConnected;

  const _ConnectionDialog({required this.onConnected});

  @override
  State<_ConnectionDialog> createState() => _ConnectionDialogState();
}

class _ConnectionDialogState extends State<_ConnectionDialog> {
  final _urlController = TextEditingController();
  final _apiService = ApiService();
  bool _isConnecting = false;
  String? _error;

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF1e293b), Color(0xFF334155)],
          ),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.wifi_off_rounded,
              color: Color(0xFFef4444),
              size: 48,
            ),
            const SizedBox(height: 16),
            const Text(
              'Tidak Terhubung',
              style: TextStyle(
                color: Colors.white,
                fontSize: 20,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Masukkan alamat server untuk melanjutkan',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.7),
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _urlController,
              style: const TextStyle(color: Colors.white),
              decoration: InputDecoration(
                hintText: '192.168.1.100:8000',
                hintStyle: TextStyle(
                  color: Colors.white.withValues(alpha: 0.3),
                ),
                filled: true,
                fillColor: Colors.white.withValues(alpha: 0.05),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(
                _error!,
                style: const TextStyle(color: Color(0xFFef4444), fontSize: 12),
              ),
            ],
            const SizedBox(height: 24),
            Row(
              children: [
                Expanded(
                  child: TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text(
                      'Batal',
                      style: TextStyle(color: Colors.white),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton(
                    onPressed: _isConnecting ? null : _connect,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF3b82f6),
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: _isConnecting
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              color: Colors.white,
                              strokeWidth: 2,
                            ),
                          )
                        : const Text('Hubungkan'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _connect() async {
    setState(() {
      _isConnecting = true;
      _error = null;
    });

    try {
      String url = _urlController.text.trim();
      if (!url.startsWith('http')) url = 'http://$url';

      await _apiService.initialize(url);
      final connected = await _apiService.verifyConnection();

      if (connected) {
        widget.onConnected();
      } else {
        setState(() => _error = 'Tidak dapat terhubung ke server');
      }
    } catch (e) {
      setState(() => _error = 'Terjadi kesalahan');
    } finally {
      setState(() => _isConnecting = false);
    }
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }
}
