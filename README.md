# Promptchived

Promptchived adalah aplikasi web pribadi lokal untuk membaca dan mencari ekspor ChatGPT dan Gemini. Data disimpan di PostgreSQL, pencarian kata kunci memakai Full Text Search, dan pencarian makna memakai embedding lokal `intfloat/multilingual-e5-small` dengan pgvector.

## Persyaratan

- Windows 10/11 dan Python 3.12 x64
- PostgreSQL 18 yang berjalan lokal
- Visual Studio Build Tools dengan komponen **Desktop development with C++** untuk membangun pgvector
- Ruang kosong untuk model embedding (diunduh satu kali ke `.models`)

## 1. Pasang pgvector pada PostgreSQL 18

Buka **x64 Native Tools Command Prompt for VS** sebagai Administrator, lalu jalankan:

```bat
set "PGROOT=C:\Program Files\PostgreSQL\18"
cd %TEMP%
git clone --branch v0.8.6 https://github.com/pgvector/pgvector.git
cd pgvector
nmake /F Makefile.win
nmake /F Makefile.win install
```

Perintah terakhir menulis ke instalasi PostgreSQL sehingga memerlukan hak Administrator. Panduan resminya tersedia di <https://github.com/pgvector/pgvector#windows>.

## 2. Buat database dan environment

Masuk menggunakan akun administrator PostgreSQL. Ganti password pada contoh berikut:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -U postgres -d postgres
```

```sql
CREATE ROLE promptchived LOGIN PASSWORD 'ganti-password-ini';
CREATE DATABASE promptchived OWNER promptchived;
\c promptchived
CREATE EXTENSION vector;
```

Lalu siapkan aplikasi:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env`, terutama password `PROMPTCHIVED_DATABASE_URL`, kemudian jalankan `promptchived migrate`.

## 3. Daftarkan dan impor ekspor

`1.txt` serta `2.txt` pada repository ini adalah daftar lokasi file. Jadikan keduanya sumber awal, lalu antrekan pemindaian:

```powershell
promptchived bootstrap
promptchived scan-all
```

Anda juga dapat mendaftarkan folder langsung dari halaman utama. Provider ChatGPT mencari `conversations*.json`; provider Gemini mencari `MyActivity*.html`. File yang hash-nya tidak berubah dilewati.

Jalankan worker dalam terminal terpisah:

```powershell
promptchived worker
```

Impor teks disimpan lebih dahulu. Jika unduhan model gagal, full-text search tetap dapat dipakai dan pekerjaan ditandai `partial`; pindai ulang setelah model tersedia untuk melanjutkan embedding.

## 4. Jalankan web

```powershell
promptchived serve --reload
```

Buka <http://127.0.0.1:8765>. Aplikasi hanya bind ke loopback dan tidak memiliki login karena ditujukan untuk satu pengguna di komputer lokal. Dokumentasi API berada di <http://127.0.0.1:8765/docs>.

## Pengujian

```powershell
pytest
```

Untuk tes idempotensi dengan PostgreSQL sungguhan, buat database pengujian terpisah yang namanya mengandung `test`, set `PROMPTCHIVED_TEST_DATABASE_URL`, lalu jalankan `pytest`. Tes memiliki guard agar tidak dapat diarahkan ke database aplikasi biasa.

## Pencadangan

Teks, metadata, indeks, dan referensi lampiran berada di database; file lampiran tetap di folder ekspor asal. Cadangkan keduanya:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe' -U promptchived -Fc promptchived -f promptchived.dump
```

Jika folder ekspor dipindahkan atau dihapus, teks tetap dapat dicari tetapi preview lampiran tidak tersedia.
