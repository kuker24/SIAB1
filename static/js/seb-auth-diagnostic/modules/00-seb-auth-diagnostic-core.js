/**
 * SEB Builder Authentication Diagnostic Tool
 *
 * Run this in Browser Console (F12) to diagnose 401 errors
 *
 * USAGE:
 * 1. Open browser console (F12)
 * 2. Copy and paste this entire script
 * 3. Press Enter
 * 4. Review the diagnostic output
 */

function runSebAuthDiagnostic() {
    console.log('='.repeat(60));
    console.log('🔍 SEB BUILDER AUTHENTICATION DIAGNOSTIC');
    console.log('='.repeat(60));

    // Check 1: Token exists?
    const token = localStorage.getItem('access_token');
    console.log('\n✅ CHECK 1: Token Storage');
    console.log('Token exists:', !!token);
    if (token) {
        console.log('Token preview:', token.substring(0, 50) + '...');
        console.log('Token length:', token.length);

        // Decode JWT to check expiration
        try {
            const parts = token.split('.');
            if (parts.length === 3) {
                const payload = JSON.parse(atob(parts[1]));
                console.log('Token payload:', payload);

                if (payload.exp) {
                    const expDate = new Date(payload.exp * 1000);
                    const now = new Date();
                    const isExpired = now > expDate;

                    console.log('Expires at:', expDate.toLocaleString());
                    console.log('Current time:', now.toLocaleString());
                    console.log('Is expired:', isExpired);

                    if (isExpired) {
                        console.error('❌ TOKEN IS EXPIRED! You need to re-login.');
                    } else {
                        const timeLeft = Math.floor((expDate - now) / 1000 / 60);
                        console.log(`✅ Token valid for ${timeLeft} more minutes`);
                    }
                }
            }
        } catch (e) {
            console.error('❌ Failed to decode token:', e.message);
        }
    } else {
        console.error('❌ NO TOKEN FOUND! You need to login first.');
    }

    // Check 2: User data exists?
    console.log('\n✅ CHECK 2: User Data');
    const userData = localStorage.getItem('user');
    if (userData) {
        try {
            const user = JSON.parse(userData);
            console.log('User:', user.username);
            console.log('Role:', user.role);
            console.log('Is Admin:', user.role === 'admin');

            if (user.role !== 'admin') {
                console.error('❌ USER IS NOT ADMIN! SEB Builder requires admin role.');
            }
        } catch (e) {
            console.error('❌ Failed to parse user data:', e.message);
        }
    } else {
        console.error('❌ NO USER DATA! You need to login.');
    }

    // Check 3: Test API call
    console.log('\n✅ CHECK 3: Testing SEB Builder API');
    console.log('Testing endpoint: /api/v1/seb-builder/builds');

    fetch('/api/v1/seb-builder/builds?limit=5', {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    })
        .then(response => {
            console.log('Response status:', response.status);
            if (response.status === 401) {
                console.error('❌ 401 UNAUTHORIZED - Token is rejected by server');
                console.log('Possible causes:');
                console.log('  1. Token expired (check expiration above)');
                console.log('  2. Token blacklisted (e.g., after logout on another tab)');
                console.log('  3. Server restarted and Redis cache was cleared');
                console.log('\n💡 SOLUTION: Try logging out and logging back in.');
            } else if (response.ok) {
                console.log('✅ API call successful!');
                return response.json();
            } else {
                console.error(`❌ Unexpected status: ${response.status}`);
            }
        })
        .then(data => {
            if (data) {
                console.log('API Response:', data);
                console.log('✅ Authentication is working correctly!');
            }
        })
        .catch(error => {
            console.error('❌ API call failed:', error.message);
        });

    // Check 4: Verify seb-builder.js is using correct token key
    console.log('\n✅ CHECK 4: Verifying seb-builder.js code');
    console.log('Expected: localStorage.getItem(\'access_token\')');
    console.log('If you see localStorage.getItem(\'token\') in errors, you need to hard-refresh (Ctrl+F5)');

    console.log('\n' + '='.repeat(60));
    console.log('📋 SUMMARY');
    console.log('='.repeat(60));
    console.log('\nIf you see 401 errors:');
    console.log('1. Check if token is expired (see CHECK 1)');
    console.log('2. Try hard refresh (Ctrl+F5 or Ctrl+Shift+R)');
    console.log('3. Try logging out and logging back in');
    console.log('4. Clear browser cache and reload');
    console.log('\nIf issues persist, contact system administrator.');
    console.log('='.repeat(60));
}
