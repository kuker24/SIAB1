import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/api_service.dart';

/// Safe landing page used after logout, force-kick, or emergency exits.
///
/// The mobile app enters through the native login flow. This lightweight page
/// avoids a black screen when an active exam session is terminated and gives
/// the student an explicit way to close/reopen the app.
class SessionEndedPage extends StatefulWidget {
  const SessionEndedPage({super.key});

  @override
  State<SessionEndedPage> createState() => _SessionEndedPageState();
}

class _SessionEndedPageState extends State<SessionEndedPage> {
  final ApiService _apiService = ApiService();
  bool _clearing = false;

  Future<void> _clearSessionAndClose() async {
    if (_clearing) return;
    setState(() {
      _clearing = true;
    });
    try {
      await _apiService.logout();
      await _apiService.clearConfig();
    } finally {
      if (mounted) {
        SystemNavigator.pop();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0f172a),
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 88,
                  height: 88,
                  decoration: const BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: LinearGradient(
                      colors: [Color(0xFF3b82f6), Color(0xFF10b981)],
                    ),
                  ),
                  child: const Icon(
                    Icons.school_rounded,
                    color: Colors.white,
                    size: 44,
                  ),
                ),
                const SizedBox(height: 24),
                const Text(
                  'Sesi Ujian Berakhir',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 12),
                const Text(
                  'Silakan tutup aplikasi, lalu buka kembali jika pengawas atau admin meminta Anda masuk ulang.',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 15,
                    height: 1.5,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 28),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _clearing ? null : _clearSessionAndClose,
                    icon: _clearing
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.logout_rounded),
                    label: Text(_clearing ? 'Menutup...' : 'Tutup Aplikasi'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF3b82f6),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
