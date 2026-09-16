# Spesifikasi Promptchived v1

Promptchived adalah aplikasi web satu pengguna yang berjalan pada `127.0.0.1`. Aplikasi mengarsipkan ekspor ChatGPT dan Gemini ke PostgreSQL 18, mempertahankan pesan, cabang alternatif, metadata sumber, revisi, dan referensi lampiran.

## Perilaku utama

1. Folder sumber didaftarkan sebagai `chatgpt` atau `gemini`.
2. Tombol **Pindai ulang** membuat pekerjaan `pending`; `promptchived worker` mengambil pekerjaan dengan row lock `SKIP LOCKED`.
3. Setiap file dihitung SHA-256. File `imported` dengan hash sama tidak diproses ulang.
4. Percakapan dan pesan di-upsert memakai ID provider serta fingerprint stabil sebagai fallback. Isi lama dicatat sebagai revisi saat berubah.
5. Teks langsung dibuat menjadi chunk dan `tsvector`, sehingga full-text search tersedia sebelum embedding selesai.
6. Worker mengunduh `intfloat/multilingual-e5-small` ke cache lokal, lalu menyimpan embedding 384 dimensi yang dinormalisasi.

## Parser sumber

- ChatGPT membaca shard `conversations*.json`, `mapping`, hubungan `parent`, `current_node`, bagian teks/multimodal, dan pemetaan nama aset. Semua cabang disimpan dan jalur `current_node` ke root ditandai aktif.
- Gemini membaca setiap `div.outer-cell` pada `MyActivity*.html`, lalu memisahkan prompt, jawaban, dan waktu. Tautan `/app/{id}` menjadi ID percakapan; entri tanpa ID menjadi percakapan tersendiri.
- Tautan media relatif diselesaikan terhadap file ekspor dan wajib berada di dalam root sumber.

## Pencarian

- Full-text: `pg_catalog.simple`, GIN, `websearch_to_tsquery`, `ts_rank_cd`, judul berbobot A dan isi B.
- Semantic: prefix E5 `query:` dan `passage:`, cosine distance exact pada `vector(384)`.
- Hybrid: maksimal 100 kandidat per jalur digabung per pesan dengan Reciprocal Rank Fusion `k=60`.
- Filter sumber, provider, peran, dan tanggal diterapkan sebelum pemeringkatan.
- Pesan panjang dipotong sekitar 400 token dengan overlap 50; teks asli tetap utuh.

## Keamanan dan batasan

- HTML/Markdown disanitasi dan skrip dari ekspor tidak dijalankan.
- Endpoint lampiran hanya melayani path di bawah folder sumber terdaftar.
- Tidak ada OCR, transkripsi baru, ekstraksi isi dokumen, upload ZIP, login, sinkronisasi otomatis, atau jawaban generatif pada v1.
- Waktu ditampilkan untuk `Asia/Jakarta` dan disimpan sebagai `timestamptz` UTC.

## Struktur kode

- `src/promptchived/importers`: normalisasi format ekspor.
- `src/promptchived/services/import_jobs.py`: antrean, deduplikasi, upsert, dan embedding.
- `src/promptchived/services/search.py`: full-text, semantic, dan RRF.
- `src/promptchived/main.py`: halaman Jinja serta API FastAPI.
- `migrations`: skema PostgreSQL dan ekstensi pgvector.
- `tests`: fixture anonim dan regresi perilaku penting.
