"""
Canonical violation metadata and normalization helpers.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# Stabilization mode for current exam period:
# raise threshold to reduce noisy auto-submit caused by low-confidence signals.
AUTO_SUBMIT_VIOLATION_THRESHOLD = 8


VIOLATION_TYPE_METADATA: Dict[str, Dict[str, str]] = {
    "tab_switch": {
        "label": "Pindah Tab",
        "severity": "medium",
        "category": "browser",
        "description": "Berpindah tab atau aplikasi saat ujian berlangsung.",
    },
    "focus_lost": {
        "label": "Fokus Hilang",
        "severity": "medium",
        "category": "browser",
        "description": "Jendela ujian kehilangan fokus.",
    },
    "browser_minimize": {
        "label": "Browser Diminimize",
        "severity": "low",
        "category": "browser",
        "description": "Jendela browser diminimize saat ujian.",
    },
    "copy": {
        "label": "Copy",
        "severity": "high",
        "category": "clipboard",
        "description": "Percobaan menyalin teks.",
    },
    "paste": {
        "label": "Paste",
        "severity": "high",
        "category": "clipboard",
        "description": "Percobaan menempelkan teks.",
    },
    "cut": {
        "label": "Cut",
        "severity": "medium",
        "category": "clipboard",
        "description": "Percobaan memotong teks.",
    },
    "clipboard_violation": {
        "label": "Akses Clipboard",
        "severity": "high",
        "category": "clipboard",
        "description": "Akses clipboard terdeteksi.",
    },
    "right_click": {
        "label": "Klik Kanan",
        "severity": "low",
        "category": "browser",
        "description": "Percobaan klik kanan.",
    },
    "devtools_open": {
        "label": "Developer Tools",
        "severity": "critical",
        "category": "browser",
        "description": "Percobaan membuka developer tools.",
    },
    "screenshot_attempt": {
        "label": "Screenshot",
        "severity": "high",
        "category": "capture",
        "description": "Percobaan mengambil tangkapan layar.",
    },
    "overlay_app": {
        "label": "Overlay App",
        "severity": "critical",
        "category": "mobile",
        "description": "Aplikasi overlay/floating terdeteksi.",
    },
    "screen_recording": {
        "label": "Rekam Layar",
        "severity": "critical",
        "category": "mobile",
        "description": "Perekaman layar aktif.",
    },
    "external_display": {
        "label": "Display Eksternal",
        "severity": "high",
        "category": "mobile",
        "description": "Display eksternal atau mirroring terdeteksi.",
    },
    "accessibility_risk": {
        "label": "Aksesibilitas Berisiko",
        "severity": "high",
        "category": "mobile",
        "description": "Layanan aksesibilitas berisiko terdeteksi.",
    },
    "apk_tampering": {
        "label": "APK Dimodifikasi",
        "severity": "critical",
        "category": "mobile",
        "description": "APK tidak resmi atau dimodifikasi terdeteksi.",
    },
    "security_warning": {
        "label": "Peringatan Keamanan",
        "severity": "medium",
        "category": "security",
        "description": "Indikator keamanan berisiko terdeteksi.",
    },
}


VIOLATION_EXPLANATIONS: Dict[str, Dict[str, Any]] = {
    "tab_switch": {
        "simple": "Peserta keluar dari halaman ujian atau berpindah ke tab/aplikasi lain saat ujian masih berjalan.",
        "why": "Saat ujian fokus seharusnya tetap di layar ujian. Pindah tab bisa berarti membuka materi lain, chat, atau aplikasi bantuan.",
        "analogy": "Bayangkan saat ujian di kelas, peserta beberapa kali berdiri lalu melihat catatan di luar ruangan. Belum tentu curang, tapi jelas perlu diperhatikan karena fokusnya keluar dari ruang ujian.",
        "guide": [
            "Kalau jumlahnya 1 kali, lihat dulu konteks waktunya apakah sebentar atau berulang.",
            "Kalau sering muncul dalam waktu dekat, artinya peserta berulang kali meninggalkan layar ujian.",
            "Cocokkan dengan log detail untuk melihat kapan kejadian itu paling sering terjadi.",
        ],
    },
    "focus_lost": {
        "simple": "Layar ujian kehilangan fokus. Ini biasanya terjadi saat peserta menyentuh notifikasi, pindah jendela, atau sistem menampilkan layar lain.",
        "why": "Fokus hilang berarti aplikasi ujian tidak lagi berada di posisi utama. Ini penting dipantau karena soal sedang tidak menjadi layar aktif.",
        "analogy": "Seperti pengawas melihat kepala peserta beberapa kali menoleh jauh dari meja ujiannya. Menoleh sekali bisa wajar, tetapi kalau berulang perlu dicatat.",
        "guide": [
            "Lihat apakah fokus hilang beriringan dengan tab switch atau minimize.",
            "Jika terjadi sesekali, bisa karena gangguan teknis atau notifikasi sistem.",
            "Jika sering berulang, perlu dipertanyakan apa yang dibuka saat itu.",
        ],
    },
    "browser_minimize": {
        "simple": "Jendela browser atau aplikasi ujian dikecilkan sehingga tidak lagi tampil penuh.",
        "why": "Saat jendela dikecilkan, peserta bisa lebih mudah membuka layar lain di belakangnya.",
        "analogy": "Ibarat lembar soal ditutup sebagian supaya peserta bisa melihat catatan yang disimpan di bawah meja.",
        "guide": [
            "Nilai pelanggaran ini lebih ringan, tetapi tetap penting bila sering terjadi.",
            "Cek apakah minimize terjadi berdekatan dengan pelanggaran lain.",
            "Kalau sering berulang pada peserta yang sama, tandai untuk pengawasan lebih dekat.",
        ],
    },
    "copy": {
        "simple": "Peserta mencoba menyalin teks dari layar ujian.",
        "why": "Copy sering dipakai untuk memindahkan isi soal atau jawaban ke tempat lain seperti chat, catatan, atau aplikasi bantuan.",
        "analogy": "Seperti peserta menyalin isi soal ke kertas kecil untuk dibawa keluar ruang ujian.",
        "guide": [
            "Lihat siapa yang paling sering melakukan copy dan di ujian mana.",
            "Jika disertai tab switch atau overlay app, tingkat risikonya lebih tinggi.",
            "Perhatikan waktu kejadian untuk melihat apakah terjadi saat soal tertentu.",
        ],
    },
    "paste": {
        "simple": "Peserta mencoba menempelkan teks ke jawaban atau ke area ujian.",
        "why": "Paste bisa berarti jawaban berasal dari sumber lain, bukan diketik langsung saat ujian.",
        "analogy": "Ibarat peserta membawa jawaban jadi dari luar lalu langsung menempelkannya ke lembar jawaban.",
        "guide": [
            "Pelanggaran ini biasanya perlu perhatian lebih tinggi daripada tab switch biasa.",
            "Jika sering berulang, cek juga log copy atau clipboard.",
            "Gunakan log detail untuk melihat konteks waktunya.",
        ],
    },
    "cut": {
        "simple": "Peserta mencoba memotong teks dari area ujian atau jawaban.",
        "why": "Meskipun tidak selalu curang, aksi cut menunjukkan interaksi clipboard yang seharusnya dibatasi.",
        "analogy": "Seperti peserta mencabut bagian tulisan dari kertas jawaban untuk dipindah ke tempat lain.",
        "guide": [
            "Biasanya tidak seserius paste, tetapi tetap perlu dicatat.",
            "Lihat apakah cut muncul bersama copy atau paste.",
            "Kalau hanya sekali dan tanpa pola lain, bisa jadi kesalahan penggunaan keyboard.",
        ],
    },
    "clipboard_violation": {
        "simple": "Sistem mendeteksi akses ke clipboard, yaitu area sementara untuk copy dan paste.",
        "why": "Clipboard adalah jalur utama memindahkan soal atau jawaban ke luar dan memasukkan teks dari luar ke ujian.",
        "analogy": "Ibarat ada laci kecil di meja yang dipakai bolak-balik untuk menyelundupkan kertas masuk dan keluar.",
        "guide": [
            "Cek apakah sistem mencatat detail copy, paste, atau cut di waktu yang sama.",
            "Kalau sering muncul, artinya peserta berulang kali menyentuh jalur perpindahan teks.",
            "Gunakan data detail untuk melihat sumber dan pola waktunya.",
        ],
    },
    "right_click": {
        "simple": "Peserta menekan klik kanan pada area ujian.",
        "why": "Klik kanan sendiri belum tentu curang, tetapi sering dipakai untuk membuka menu tambahan, inspect, atau fitur copy.",
        "analogy": "Seperti peserta mencoba membuka sudut kecil dari meja ujian untuk mencari jalan pintas.",
        "guide": [
            "Ini termasuk pelanggaran ringan.",
            "Nilainya naik kalau terjadi bersama devtools atau clipboard.",
            "Gunakan sebagai sinyal tambahan, bukan bukti tunggal.",
        ],
    },
    "devtools_open": {
        "simple": "Peserta mencoba membuka Developer Tools atau alat inspeksi browser.",
        "why": "Fitur ini bisa dipakai untuk melihat struktur halaman, mencari celah, atau memanipulasi alur ujian.",
        "analogy": "Seperti peserta bukan hanya mengerjakan soal, tetapi mencoba membongkar meja ujian untuk melihat mekanisme di dalamnya.",
        "guide": [
            "Ini termasuk pelanggaran berat dan harus diprioritaskan pengawasannya.",
            "Kalau muncul sekali pun, langsung cek peserta dan waktu kejadiannya.",
            "Perhatikan apakah setelah itu ada pelanggaran lain seperti copy atau tab switch.",
        ],
    },
    "screenshot_attempt": {
        "simple": "Peserta mencoba mengambil tangkapan layar soal atau tampilan ujian.",
        "why": "Screenshot bisa dipakai untuk menyimpan soal, membagikannya, atau meminta bantuan dari luar.",
        "analogy": "Ibarat peserta memotret lembar soal untuk dikirim keluar ruang ujian.",
        "guide": [
            "Semakin sering terjadi, semakin besar risiko soal bocor.",
            "Cek apakah terjadi pada peserta yang sama berkali-kali.",
            "Gunakan log detail untuk melihat konteks perangkat atau sumber kejadian.",
        ],
    },
    "overlay_app": {
        "simple": "Sistem mendeteksi aplikasi lain yang tampil menumpuk di atas aplikasi ujian, misalnya chat bubble atau tools bantu.",
        "why": "Aplikasi overlay bisa dipakai untuk membuka bantuan tanpa terlihat jelas jika hanya melihat layar utama ujian.",
        "analogy": "Seperti peserta menempelkan sticky note transparan di atas lembar soal. Soal tetap terlihat, tetapi ada bantuan tambahan di atasnya.",
        "guide": [
            "Ini termasuk pelanggaran berat karena menunjukkan ada aplikasi luar yang ikut aktif.",
            "Periksa nama aplikasi pada detail jika tersedia.",
            "Jika berulang, peserta perlu ditindak lebih cepat daripada pelanggaran ringan.",
        ],
    },
    "screen_recording": {
        "simple": "Perangkat terdeteksi sedang merekam layar saat ujian berjalan.",
        "why": "Rekaman layar bisa dipakai untuk menyimpan seluruh soal dan aktivitas ujian untuk dipakai ulang atau dibagikan.",
        "analogy": "Seperti ada kamera yang terus merekam seluruh isi lembar soal selama ujian berlangsung.",
        "guide": [
            "Ini kategori sangat serius karena berisiko pada kebocoran soal.",
            "Cek apakah terjadi pada banyak peserta atau hanya satu perangkat tertentu.",
            "Jika sering terjadi pada peserta yang sama, prioritaskan penanganannya.",
        ],
    },
    "external_display": {
        "simple": "Perangkat diduga terhubung ke layar eksternal, mirroring, atau tampilan tambahan.",
        "why": "Display eksternal bisa dipakai untuk membagi tampilan ujian dengan layar lain yang lebih mudah dipantau orang lain.",
        "analogy": "Ibarat soal ujian ditayangkan ke layar kedua di samping meja agar orang lain juga bisa melihatnya.",
        "guide": [
            "Periksa apakah kejadian ini muncul bersama screen recording atau overlay.",
            "Jika iya, tingkat risikonya makin tinggi.",
            "Gunakan sebagai indikator bahwa perangkat peserta perlu dicek.",
        ],
    },
    "accessibility_risk": {
        "simple": "Sistem mendeteksi layanan aksesibilitas yang berisiko dipakai untuk bantuan otomatis atau pembacaan layar.",
        "why": "Sebagian layanan aksesibilitas aman, tetapi beberapa bisa dipakai untuk membantu peserta membaca atau mengontrol perangkat secara tidak wajar.",
        "analogy": "Seperti ada asisten yang berdiri di samping peserta dan sesekali membantu membacakan atau mengarahkan jawaban.",
        "guide": [
            "Jangan langsung dianggap curang total; lihat detail layanan yang terdeteksi.",
            "Kalau layanan itu memang tidak semestinya aktif saat ujian, baru naikkan kewaspadaan.",
            "Cocokkan dengan pelanggaran lain sebelum mengambil kesimpulan.",
        ],
    },
    "apk_tampering": {
        "simple": "Aplikasi ujian di perangkat terdeteksi tidak asli, sudah dimodifikasi, atau tanda tangannya tidak sesuai.",
        "why": "APK yang dimodifikasi berisiko menghilangkan proteksi, mem-bypass aturan, atau menyisipkan celah.",
        "analogy": "Seperti peserta datang dengan kalkulator yang casing-nya tampak resmi, tetapi bagian dalamnya sudah diubah supaya bisa menyimpan contekan.",
        "guide": [
            "Ini salah satu indikator paling serius.",
            "Perlu dicek apakah perangkat memakai aplikasi resmi sekolah atau bukan.",
            "Jika berulang, peserta sebaiknya tidak dibiarkan lanjut tanpa verifikasi.",
        ],
    },
    "security_warning": {
        "simple": "Sistem melihat tanda umum bahwa kondisi keamanan perangkat atau sesi tidak ideal.",
        "why": "Ini bisa muncul dari kombinasi indikator yang tidak cukup spesifik untuk jadi satu jenis pelanggaran tunggal, tetapi tetap patut dicatat.",
        "analogy": "Seperti alarm pengawas berbunyi karena ada gerak mencurigakan, meski belum jelas persis peserta melakukan apa.",
        "guide": [
            "Gunakan ini sebagai alarm awal, bukan kesimpulan akhir.",
            "Buka log detail untuk membaca konteks dan waktu kejadiannya.",
            "Kalau muncul bersama pelanggaran spesifik lain, prioritaskan pemeriksaan peserta itu.",
        ],
    },
}


VIOLATION_TYPE_ALIASES: Dict[str, str] = {
    "violation_tab_switch": "tab_switch",
    "tab_switch": "tab_switch",
    "tabswitch": "tab_switch",
    "window_blur": "focus_lost",
    "violation_window_blur": "focus_lost",
    "focus_lost": "focus_lost",
    "violation_focus_lost": "focus_lost",
    "browser_minimize": "browser_minimize",
    "violation_browser_minimize": "browser_minimize",
    "copy": "copy",
    "violation_copy": "copy",
    "paste": "paste",
    "violation_paste": "paste",
    "cut": "cut",
    "violation_cut": "cut",
    "copy_paste_attempt": "clipboard_violation",
    "violation_copy_paste_attempt": "clipboard_violation",
    "clipboard_violation": "clipboard_violation",
    "violation_clipboard_violation": "clipboard_violation",
    "right_click": "right_click",
    "violation_right_click": "right_click",
    "devtools_attempt": "devtools_open",
    "violation_devtools_attempt": "devtools_open",
    "devtools_open": "devtools_open",
    "violation_devtools_open": "devtools_open",
    "screenshot": "screenshot_attempt",
    "violation_screenshot": "screenshot_attempt",
    "screenshot_attempt": "screenshot_attempt",
    "violation_screenshot_attempt": "screenshot_attempt",
    "overlay_app": "overlay_app",
    "violation_overlay_app": "overlay_app",
    "overlay_apps": "overlay_app",
    "screen_recording": "screen_recording",
    "violation_screen_recording": "screen_recording",
    "external_display": "external_display",
    "violation_external_display": "external_display",
    "accessibility_risk": "accessibility_risk",
    "violation_accessibility_risk": "accessibility_risk",
    "apk_tampering": "apk_tampering",
    "violation_apk_tampering": "apk_tampering",
    "security_warning": "security_warning",
    "violation_security_warning": "security_warning",
}

KNOWN_VIOLATION_EVENT_TYPES = tuple(
    sorted(
        set(VIOLATION_TYPE_METADATA)
        | {f"violation_{key}" for key in VIOLATION_TYPE_METADATA}
        | set(VIOLATION_TYPE_ALIASES)
    )
)


def strip_violation_prefix(event_type: Optional[str]) -> str:
    if not event_type:
        return ""
    return event_type.removeprefix("violation_")


def canonical_violation_key(
    event_type: Optional[str],
    event_data: Optional[Dict[str, Any]] = None,
    *,
    assume_violation: bool = False,
) -> Optional[str]:
    if not event_type:
        return None

    normalized = str(event_type).strip().lower().replace(" ", "_")
    if not normalized:
        return None

    alias = VIOLATION_TYPE_ALIASES.get(normalized)
    if alias:
        key = alias
    elif normalized.startswith("keyboard_ctrl_"):
        shortcut = normalized.rsplit("_", 1)[-1]
        key = {"c": "copy", "v": "paste", "x": "cut"}.get(shortcut, "clipboard_violation")
    elif normalized.startswith("violation_") and strip_violation_prefix(normalized) in VIOLATION_TYPE_METADATA:
        key = strip_violation_prefix(normalized)
    elif assume_violation:
        key = normalized.removeprefix("violation_")
    else:
        key = None

    if key == "clipboard_violation" and isinstance(event_data, dict):
        action = str(event_data.get("action") or "").strip().lower()
        key = {
            "copy": "copy",
            "paste": "paste",
            "cut": "cut",
            "keyboard_ctrl_c": "copy",
            "keyboard_ctrl_v": "paste",
            "keyboard_ctrl_x": "cut",
            "devtools_attempt": "devtools_open",
        }.get(action, key)

    return key


def canonical_violation_event_type(
    event_type: Optional[str],
    event_data: Optional[Dict[str, Any]] = None,
    *,
    assume_violation: bool = False,
) -> Optional[str]:
    key = canonical_violation_key(
        event_type,
        event_data,
        assume_violation=assume_violation,
    )
    if not key:
        return None
    return f"violation_{key}"


def get_violation_metadata(
    event_type: Optional[str],
    event_data: Optional[Dict[str, Any]] = None,
    *,
    assume_violation: bool = False,
) -> Dict[str, str]:
    key = canonical_violation_key(
        event_type,
        event_data,
        assume_violation=assume_violation,
    )
    if not key:
        return {
            "key": "",
            "label": "Pelanggaran",
            "severity": "medium",
            "category": "other",
            "description": "Pelanggaran terdeteksi.",
        }

    base = VIOLATION_TYPE_METADATA.get(
        key,
        {
            "label": key.replace("_", " ").title(),
            "severity": "medium",
            "category": "other",
            "description": "Pelanggaran terdeteksi.",
        },
    )
    return {"key": key, **base}


def get_violation_explanation(
    event_type: Optional[str],
    event_data: Optional[Dict[str, Any]] = None,
    *,
    assume_violation: bool = False,
) -> Dict[str, Any]:
    key = canonical_violation_key(
        event_type,
        event_data,
        assume_violation=assume_violation,
    )
    if not key:
        return {
            "simple": "Sistem melihat aktivitas yang dianggap tidak wajar selama ujian.",
            "why": "Aktivitas ini berada di luar pola normal peserta yang fokus mengerjakan ujian.",
            "analogy": "Bayangkan pengawas melihat gerakan yang tidak biasa di ruang ujian. Belum tentu langsung curang, tetapi tetap penting untuk dicatat.",
            "guide": [
                "Lihat jumlah kejadian dan siapa yang paling sering melakukannya.",
                "Buka log detail untuk membaca konteks waktunya.",
                "Gunakan bersama pelanggaran lain agar kesimpulannya lebih akurat.",
            ],
        }
    return VIOLATION_EXPLANATIONS.get(
        key,
        {
            "simple": f"Sistem melihat aktivitas {key.replace('_', ' ')} yang dianggap tidak wajar selama ujian.",
            "why": "Aktivitas ini berada di luar pola normal peserta yang fokus mengerjakan ujian.",
            "analogy": "Bayangkan pengawas melihat gerakan yang tidak biasa di ruang ujian. Belum tentu langsung curang, tetapi tetap penting untuk dicatat.",
            "guide": [
                "Lihat jumlah kejadian dan siapa yang paling sering melakukannya.",
                "Buka log detail untuk membaca konteks waktunya.",
                "Gunakan bersama pelanggaran lain agar kesimpulannya lebih akurat.",
            ],
        },
    )


def is_violation_event(
    event_type: Optional[str],
    event_data: Optional[Dict[str, Any]] = None,
) -> bool:
    return canonical_violation_key(event_type, event_data, assume_violation=False) is not None


def get_violation_warning_message(violation_count: int) -> Optional[str]:
    """
    Return the canonical warning message for the current violation count.

    Auto-submit happens on the threshold violation itself. Count one below the
    threshold is treated as the final warning state.
    """
    if violation_count >= AUTO_SUBMIT_VIOLATION_THRESHOLD:
        return "Batas pelanggaran tercapai. Ujian akan dikumpulkan otomatis."
    if violation_count == AUTO_SUBMIT_VIOLATION_THRESHOLD - 1:
        return "PERINGATAN TERAKHIR! Ujian akan dikumpulkan otomatis pada pelanggaran berikutnya."
    if violation_count >= 3:
        return f"Peringatan: Anda sudah melakukan {violation_count} pelanggaran."
    return None
