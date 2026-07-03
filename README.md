# Web Resize Gambar

Aplikasi web sederhana untuk resize banyak gambar menjadi JPG maksimal 250 KB.

## Deploy ke Vercel

1. Push folder project ini ke GitHub.
2. Buka Vercel, pilih **Add New Project**, lalu import repository ini.
3. Framework Preset biarkan **Other**.
4. Build Command kosongkan.
5. Output Directory kosongkan.
6. Klik **Deploy**.

Vercel akan menyajikan `index.html` sebagai halaman utama dan menjalankan
`api/resize.py` sebagai Python Function. Entrypoint Python dikunci lewat
`pyproject.toml` supaya Vercel membaca `api.resize:handler` dan memasang
dependency `Pillow`.

> Catatan: Vercel Function punya batas payload, jadi web ini membatasi upload
> menjadi maksimal 12 gambar atau total 4 MB per proses.

## Menjalankan

```powershell
python -m pip install -r requirements.txt
python local_server.py
```

Buka `http://127.0.0.1:8000` di browser.

## Catatan

- Tidak memakai login.
- Tidak memakai database.
- Gambar diproses sementara dan hasilnya diunduh sebagai ZIP.
