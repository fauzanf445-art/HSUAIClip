import re

def sanitize_filename(name: str) -> str:
    """
    Membersihkan string untuk digunakan sebagai nama file atau folder yang aman.
    - Menghapus karakter yang tidak valid.
    - Mengganti spasi berlebih dengan satu spasi.
    """
    # Hapus semua karakter yang bukan alfanumerik, spasi, strip, atau underscore
    raw_safe = re.sub(r'[^\w\s\-_]', '', name).strip()
    # Ganti beberapa spasi atau karakter whitespace lainnya menjadi satu spasi tunggal
    safe_name = re.sub(r'\s+', ' ', raw_safe)
    return safe_name