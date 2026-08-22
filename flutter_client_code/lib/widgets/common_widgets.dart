import 'package:flutter/material.dart';
import 'dart:ui';

/// Widget glassmorphism untuk UI modern
class GlassContainer extends StatelessWidget {
  final Widget child;
  final double? width;
  final double? height;
  final EdgeInsets? padding;
  final BorderRadius? borderRadius;
  final Color? borderColor;
  final double blur;

  const GlassContainer({
    super.key,
    required this.child,
    this.width,
    this.height,
    this.padding,
    this.borderRadius,
    this.borderColor,
    this.blur = 10,
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: borderRadius ?? BorderRadius.circular(20),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
        child: Container(
          width: width,
          height: height,
          padding: padding ?? const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.1),
            borderRadius: borderRadius ?? BorderRadius.circular(20),
            border: Border.all(
              color: borderColor ?? Colors.white.withValues(alpha: 0.2),
            ),
          ),
          child: child,
        ),
      ),
    );
  }
}

/// Gradient button dengan glow effect
class GradientButton extends StatelessWidget {
  final String text;
  final IconData? icon;
  final VoidCallback? onPressed;
  final bool isLoading;
  final List<Color>? colors;

  const GradientButton({
    super.key,
    required this.text,
    this.icon,
    this.onPressed,
    this.isLoading = false,
    this.colors,
  });

  @override
  Widget build(BuildContext context) {
    final gradientColors = colors ?? [
      const Color(0xFF3b82f6),
      const Color(0xFF2563eb),
    ];

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: gradientColors.first.withValues(alpha: 0.4),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: isLoading ? null : onPressed,
          borderRadius: BorderRadius.circular(16),
          child: Ink(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: gradientColors,
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  if (isLoading)
                    const SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(
                        color: Colors.white,
                        strokeWidth: 2,
                      ),
                    )
                  else ...[
                    if (icon != null) ...[
                      Icon(icon, color: Colors.white),
                      const SizedBox(width: 12),
                    ],
                    Text(
                      text,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
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

/// Animated Logo widget
class AnimatedLogo extends StatefulWidget {
  final double size;

  const AnimatedLogo({super.key, this.size = 120});

  @override
  State<AnimatedLogo> createState() => _AnimatedLogoState();
}

class _AnimatedLogoState extends State<AnimatedLogo>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _scaleAnimation;
  late Animation<double> _glowAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(seconds: 2),
      vsync: this,
    )..repeat(reverse: true);

    _scaleAnimation = Tween<double>(begin: 1.0, end: 1.05).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );

    _glowAnimation = Tween<double>(begin: 0.3, end: 0.6).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Transform.scale(
          scale: _scaleAnimation.value,
          child: Container(
            width: widget.size,
            height: widget.size,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Color(0xFF10b981), Color(0xFF3b82f6)],
              ),
              borderRadius: BorderRadius.circular(widget.size * 0.25),
              boxShadow: [
                BoxShadow(
                  color: Color.fromRGBO(59, 130, 246, _glowAnimation.value),
                  blurRadius: 40,
                  spreadRadius: 10,
                ),
              ],
            ),
            child: Icon(
              Icons.shield,
              size: widget.size * 0.5,
              color: Colors.white,
            ),
          ),
        );
      },
    );
  }
}

/// Status indicator chip
class StatusChip extends StatelessWidget {
  final String text;
  final Color color;
  final IconData? icon;

  const StatusChip({
    super.key,
    required this.text,
    required this.color,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 6),
          ],
          Text(
            text,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

/// Loading overlay widget
class LoadingOverlay extends StatelessWidget {
  final String? message;

  const LoadingOverlay({super.key, this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: const Color(0xFF1a1a2e),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const SizedBox(
              width: 60,
              height: 60,
              child: CircularProgressIndicator(
                color: Color(0xFF3b82f6),
                strokeWidth: 3,
              ),
            ),
            if (message != null) ...[
              const SizedBox(height: 24),
              Text(
                message!,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.7),
                  fontSize: 16,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
