String? trustedWebOrigin(String? serverUrl) {
  final uri = Uri.tryParse(serverUrl?.trim() ?? '');
  if (uri == null ||
      !uri.hasAuthority ||
      uri.host.isEmpty ||
      (uri.scheme != 'https' && uri.scheme != 'http')) {
    return null;
  }
  return uri.origin;
}

bool isTrustedWebOrigin(String? targetUrl, String? serverUrl) {
  final target = Uri.tryParse(targetUrl?.trim() ?? '');
  final trusted = Uri.tryParse(serverUrl?.trim() ?? '');
  if (target == null || trusted == null) return false;
  if (!target.hasAuthority || !trusted.hasAuthority) return false;
  if (target.scheme != 'https' && target.scheme != 'http') return false;

  return target.scheme == trusted.scheme &&
      target.host.toLowerCase() == trusted.host.toLowerCase() &&
      target.port == trusted.port;
}
