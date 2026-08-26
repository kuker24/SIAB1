import 'package:flutter_test/flutter_test.dart';
import 'package:siab1/security/trusted_origin.dart';

void main() {
  const serverUrl = 'https://siab.man1rokanhulu.cloud/';

  test('accepts only the configured server origin', () {
    expect(
      isTrustedWebOrigin(
        'https://siab.man1rokanhulu.cloud/student/exam.html?id=1',
        serverUrl,
      ),
      isTrue,
    );
    expect(
      isTrustedWebOrigin(
        'https://evil.siab.man1rokanhulu.cloud/student/exam.html',
        serverUrl,
      ),
      isFalse,
    );
    expect(
      isTrustedWebOrigin('http://siab.man1rokanhulu.cloud/', serverUrl),
      isFalse,
    );
    expect(
      isTrustedWebOrigin('https://siab.man1rokanhulu.cloud:444/', serverUrl),
      isFalse,
    );
    expect(
      isTrustedWebOrigin(
        'https://siab.man1rokanhulu.cloud@evil.example/',
        serverUrl,
      ),
      isFalse,
    );
  });

  test('builds an exact origin rule for user scripts', () {
    expect(
      trustedWebOrigin(serverUrl),
      'https://siab.man1rokanhulu.cloud',
    );
    expect(trustedWebOrigin('javascript:alert(1)'), isNull);
  });
}
