"""
KUIS PEMROGRAMAN KOMPUTER - PANDAS (10 Tantangan)
Jalankan:  streamlit run app.py
Dosen   :  pilih mode "Dosen" di sidebar (password default: dosen123,
           ubah lewat environment variable DOSEN_PASSWORD).

Fitur
- Peserta login dengan Nama + NIM.
- Dataset di-generate dari NIM -> setiap peserta punya data & jawaban benar
  yang BERBEDA, jadi kode/jawaban tidak bisa sekadar disalin teman.
- Setiap soal = 7 poin (ketepatan) + 3 poin (bonus inovasi) = 10 poin.
- Semua percobaan tersimpan di SQLite (kuis_pandas.db): nama, NIM, kode, skor.
- Dashboard dosen: papan nilai real-time, progres, kode tiap peserta,
  nilai manual (override), unduh CSV.
"""
import os
import re
import sqlite3
import tempfile
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import streamlit as st

def _db_path():
    p = os.environ.get("KUIS_DB", "kuis_pandas.db")
    try:
        if os.access(os.path.dirname(os.path.abspath(p)), os.W_OK):
            return p
    except Exception:
        pass
    return os.path.join(tempfile.gettempdir(), "kuis_pandas.db")


def _password_dosen():
    pw = os.environ.get("DOSEN_PASSWORD")
    if not pw:
        try:
            pw = st.secrets["DOSEN_PASSWORD"]
        except Exception:
            pw = "dosen123"
    return str(pw).strip()


DB = _db_path()
DOSEN_PASSWORD = _password_dosen()
KOTA = ["Surabaya", "Malang", "Kediri", "Jakarta", "Bandung"]
PRODUK = {
    "Elektronik": [("Headset", 250000), ("Powerbank", 180000), ("Mouse", 95000)],
    "Fashion": [("Kemeja", 160000), ("Sepatu", 320000), ("Topi", 60000)],
    "Makanan": [("Kopi", 45000), ("Snack Box", 30000), ("Madu", 85000)],
    "Buku": [("Novel", 75000), ("Buku Python", 140000)],
    "Olahraga": [("Raket", 210000), ("Matras", 120000)],
}


# ----------------------------------------------------------------- DATABASE
def koneksi():
    return sqlite3.connect(DB, timeout=30, check_same_thread=False)


def init_db():
    con = koneksi()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS siswa(nim TEXT PRIMARY KEY, nama TEXT, mulai TEXT);
        CREATE TABLE IF NOT EXISTS attempts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, nim TEXT, nama TEXT, soal INTEGER,
            kode TEXT, dasar REAL, bonus REAL, skor REAL, pesan TEXT, waktu TEXT);
        CREATE TABLE IF NOT EXISTS manual(
            nim TEXT, soal INTEGER, skor REAL, catatan TEXT, PRIMARY KEY(nim, soal));
        """
    )
    con.commit()
    con.close()


def daftar_siswa(nim, nama):
    con = koneksi()
    con.execute("INSERT OR IGNORE INTO siswa VALUES(?,?,?)", (nim, nama, datetime.now().isoformat(" ", "seconds")))
    con.execute("UPDATE siswa SET nama=? WHERE nim=?", (nama, nim))
    con.commit()
    con.close()


def simpan_attempt(nim, nama, no, kode, r):
    con = koneksi()
    con.execute(
        "INSERT INTO attempts(nim,nama,soal,kode,dasar,bonus,skor,pesan,waktu) VALUES(?,?,?,?,?,?,?,?,?)",
        (nim, nama, no, kode, r["dasar"], r["bonus"], r["skor"], " | ".join(r["pesan"]),
         datetime.now().isoformat(" ", "seconds")),
    )
    con.commit()
    con.close()


def skor_peserta(nim):
    con = koneksi()
    d = dict(con.execute("SELECT soal,MAX(skor) FROM attempts WHERE nim=? GROUP BY soal", (nim,)).fetchall())
    for soal, skor in con.execute("SELECT soal,skor FROM manual WHERE nim=?", (nim,)):
        d[soal] = skor
    con.close()
    return d


def kode_terakhir(nim, no):
    con = koneksi()
    row = con.execute("SELECT kode FROM attempts WHERE nim=? AND soal=? ORDER BY id DESC LIMIT 1", (nim, no)).fetchone()
    con.close()
    return row[0] if row else None


def papan_nilai():
    con = koneksi()
    s = pd.read_sql("SELECT nim,nama,mulai FROM siswa", con)
    a = pd.read_sql("SELECT nim,soal,MAX(skor) AS skor FROM attempts GROUP BY nim,soal", con)
    m = pd.read_sql("SELECT nim,soal,skor FROM manual", con)
    t = pd.read_sql("SELECT nim,MAX(waktu) AS terakhir_aktif,COUNT(*) AS percobaan FROM attempts GROUP BY nim", con)
    con.close()
    if s.empty:
        return s
    nilai = pd.concat([a, m]).drop_duplicates(["nim", "soal"], keep="last")  # manual menimpa otomatis
    wide = nilai.pivot(index="nim", columns="soal", values="skor").reindex(columns=range(1, 11))
    wide.columns = [f"S{i}" for i in wide.columns]
    wide["Dikerjakan"] = wide.notna().sum(axis=1)
    wide["Total"] = wide[[f"S{i}" for i in range(1, 11)]].sum(axis=1)
    out = s.set_index("nim").join(wide).join(t.set_index("nim"))
    out["Dikerjakan"] = out["Dikerjakan"].fillna(0).astype(int)
    out["Total"] = out["Total"].fillna(0)
    out["percobaan"] = out["percobaan"].fillna(0).astype(int)
    return out.reset_index().sort_values("Total", ascending=False)


# --------------------------------------------------------------- DATA UNIK
@st.cache_data(max_entries=300, show_spinner=False)
def buat_data(nim):
    """Dataset toko online, unik per NIM (seed dari NIM)."""
    rng = np.random.default_rng(int(re.sub(r"\D", "", nim) or 0) % (2**32))
    n_pel, n = 60, 400
    pelanggan = pd.DataFrame({
        "pelanggan_id": [f"P{i:03d}" for i in range(1, n_pel + 1)],
        "nama": [f"Pelanggan {i:02d}" for i in range(1, n_pel + 1)],
        "umur": rng.integers(17, 60, n_pel),
        "kota_asal": rng.choice(KOTA, n_pel),
        "member": rng.choice(["Basic", "Silver", "Gold"], n_pel, p=[0.5, 0.3, 0.2]),
    })
    base = pd.Timestamp("2025-01-01")
    rows = []
    for _ in range(n):
        kat = str(rng.choice(list(PRODUK)))
        nama, harga = PRODUK[kat][int(rng.integers(len(PRODUK[kat])))]
        rows.append({
            "tanggal": base + pd.Timedelta(days=int(rng.integers(0, 180))),
            "kota": str(rng.choice(KOTA)), "kategori": kat, "produk": nama,
            "qty": int(rng.integers(1, 6)), "harga": harga,
            "diskon": float(rng.choice([0, 0.05, 0.1, 0.15, 0.2])),
            "pelanggan_id": str(rng.choice(pelanggan["pelanggan_id"])),
        })
    dfb = pd.DataFrame(rows).sort_values("tanggal").reset_index(drop=True)
    dfb.insert(0, "id_transaksi", [f"T{i:04d}" for i in range(1, n + 1)])

    dfm = dfb.copy()
    dfm["total"] = dfm["qty"] * dfm["harga"] * (1 - dfm["diskon"])
    dfm["bulan"] = dfm["tanggal"].dt.month

    k = dfb.copy()
    k["tanggal"] = k["tanggal"].dt.strftime("%Y-%m-%d")
    k["qty"] = k["qty"].astype(float)
    k.loc[rng.choice(n, 12, replace=False), "qty"] = np.nan
    k.loc[rng.choice(n, 15, replace=False), "diskon"] = np.nan
    ik = rng.choice(n, 16, replace=False)
    k.loc[ik[:8], "kota"] = k.loc[ik[:8], "kota"].str.lower()
    k.loc[ik[8:], "kota"] = " " + k.loc[ik[8:], "kota"].str.upper() + " "
    dup = k.loc[rng.choice(n, 8, replace=False)]
    kotor = pd.concat([k, dup]).sample(frac=1, random_state=int(rng.integers(1_000_000))).reset_index(drop=True)
    return SimpleNamespace(kotor=kotor, dfb=dfb, dfm=dfm, pelanggan=pelanggan)


# ------------------------------------------------------- PENILAIAN OTOMATIS
def nilai(kondisi):
    """7 poin dibagi rata ke semua kondisi. Return (poin, daftar pesan salah)."""
    benar = sum(1 for b, _ in kondisi if b)
    return round(7 * benar / len(kondisi), 1), [m for b, m in kondisi if not b]


def dekat(a, b):
    try:
        return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), rtol=1e-6, atol=1e-6))
    except Exception:
        return False


def c1(h, ns, D, kode):
    if not isinstance(h, dict):
        return 0, ["`hasil` harus berupa dict."]
    k = D.kotor
    miss = k.isna().sum()
    teratas = set(miss[miss == miss.max()].index)
    return nilai([
        (h.get("baris") == len(k), "'baris' belum tepat"),
        (h.get("kolom") == k.shape[1], "'kolom' belum tepat"),
        (h.get("duplikat") == int(k.duplicated().sum()), "'duplikat' belum tepat (hitung baris yang identik penuh)"),
        (h.get("kolom_missing_terbanyak") in teratas, "'kolom_missing_terbanyak' belum tepat"),
    ])


def b1(h, ns, D, kode):
    return len(set(h) - {"baris", "kolom", "duplikat", "kolom_missing_terbanyak"}) >= 2


def c2(h, ns, D, kode):
    if not isinstance(h, pd.DataFrame):
        return 0, ["`hasil` harus DataFrame."]
    return nilai([
        (h.duplicated().sum() == 0, "masih ada baris duplikat"),
        (len(h) == len(D.dfb), f"jumlah baris harus {len(D.dfb)} setelah duplikat dibuang (sekarang {len(h)})"),
        ("qty" in h and h["qty"].notna().all() and "diskon" in h and h["diskon"].notna().all(),
         "kolom qty/diskon masih memiliki NaN"),
        ("tanggal" in h and pd.api.types.is_datetime64_any_dtype(h["tanggal"]), "kolom tanggal belum bertipe datetime"),
        ("kota" in h and set(h["kota"].unique()) <= set(KOTA), "penulisan kota belum seragam (spasi/huruf besar-kecil)"),
    ])


def b2(h, ns, D, kode):
    return bool(re.search(r"^\s*def\s+\w+", kode, re.M)) and bool(re.search(r"groupby|transform|median|interpolate", kode))


def c3(h, ns, D, kode):
    if not isinstance(h, pd.DataFrame):
        return 0, ["`hasil` harus DataFrame."]
    b = D.dfb
    return nilai([
        (len(h) == len(b), "jumlah baris berubah"),
        ("total" in h and dekat(h["total"], b.qty * b.harga * (1 - b.diskon)), "kolom 'total' belum sesuai rumus"),
        ("bulan" in h and dekat(h["bulan"], b.tanggal.dt.month), "kolom 'bulan' belum sesuai"),
    ])


def b3(h, ns, D, kode):
    return len(set(h.columns) - set(D.dfb.columns) - {"total", "bulan"}) >= 2


def c4(h, ns, D, kode):
    if not isinstance(h, pd.DataFrame) or "id_transaksi" not in h:
        return 0, ["`hasil` harus DataFrame dengan kolom 'id_transaksi'."]
    m = D.dfm
    thr = m.groupby("kota")["total"].transform(lambda s: s.quantile(0.9))
    ge, gt = set(m.id_transaksi[m.total >= thr]), set(m.id_transaksi[m.total > thr])
    got = set(h["id_transaksi"])
    return nilai([
        (h["id_transaksi"].is_unique, "ada id_transaksi ganda"),
        (got == ge or got == gt, f"transaksi terpilih belum tepat (harusnya {len(gt)} transaksi, Anda {len(got)})"),
    ])


def b4(h, ns, D, kode):
    return len(set(h.columns) - set(D.dfm.columns)) >= 1


def c5(h, ns, D, kode):
    if not isinstance(h, pd.DataFrame) or not {"kota", "kategori"} <= set(h.columns):
        return 0, ["`hasil` harus DataFrame dengan kolom 'kota' & 'kategori'."]
    g = D.dfm.groupby(["kota", "kategori"])["total"].sum().reset_index()
    top = g.sort_values("total", ascending=False).groupby("kota").head(3)
    exp = set(zip(top.kota, top.kategori))
    got = set(zip(h.kota, h.kategori))
    return nilai([
        (h.groupby("kota").size().eq(3).all() and h["kota"].nunique() == len(KOTA), "tiap kota harus tepat 3 baris"),
        (got == exp, "kategori top-3 belum tepat (urut berdasarkan SUM total)"),
    ])


def b5(h, ns, D, kode):
    return h.shape[1] >= 4


def c6(h, ns, D, kode):
    if not isinstance(h, pd.DataFrame):
        return 0, ["`hasil` harus DataFrame (pivot)."]
    exp = D.dfm.pivot_table(index="kota", columns="bulan", values="total", aggfunc="sum", fill_value=0)
    ada = set(exp.index) <= set(h.index) and set(exp.columns) <= set(h.columns)
    sama = ada and dekat(h.reindex(index=exp.index, columns=exp.columns).fillna(0), exp)
    return nilai([
        (set(exp.index) <= set(h.index), "baris harus berisi semua kota"),
        (set(exp.columns) <= set(h.columns), "kolom harus bulan (angka 1-6)"),
        (sama, "isi pivot (jumlah total) belum tepat"),
    ])


def b6(h, ns, D, kode):
    return h.shape[0] > 5 or h.shape[1] > 6


def c7(h, ns, D, kode):
    if not isinstance(h, pd.DataFrame):
        return 0, ["`hasil` harus DataFrame."]
    h = h.reset_index() if "member" not in h.columns else h
    m = D.dfm.merge(D.pelanggan, on="pelanggan_id").groupby("member")["total"].mean()
    if "member" not in h or "rata_total" not in h:
        return 0, ["butuh kolom 'member' dan 'rata_total'."]
    got = h.set_index("member")["rata_total"]
    return nilai([
        (set(got.index) == set(m.index), "harus ada 3 level member"),
        (dekat(got.reindex(m.index), m), "rata_total per member belum tepat"),
    ])


def b7(h, ns, D, kode):
    return h.shape[1] >= 3


def c8(h, ns, D, kode):
    if isinstance(h, pd.DataFrame) and h.shape[1] == 1:
        h = h.iloc[:, 0]
    if not isinstance(h, pd.Series):
        return 0, ["`hasil` harus Series moving average."]
    daily = D.dfm.groupby("tanggal")["total"].sum().asfreq("D", fill_value=0)
    exp = daily.rolling(7).mean().dropna()
    hv = h.dropna()
    return nilai([
        (len(hv) == len(exp), f"panjang data harus {len(exp)} (hari tanpa transaksi diisi 0, window=7)"),
        (len(hv) == len(exp) and dekat(hv.values, exp.values), "nilai rata-rata bergerak belum tepat"),
    ])


def b8(h, ns, D, kode):
    daily = D.dfm.groupby("tanggal")["total"].sum()
    try:
        return pd.Timestamp(ns.get("hari_puncak")) == daily.idxmax()
    except Exception:
        return False


def c9(h, ns, D, kode):
    if not isinstance(h, pd.DataFrame):
        return 0, ["`hasil` harus DataFrame."]
    h = h.set_index("pelanggan_id") if "pelanggan_id" in h.columns else h
    m = D.dfm
    ref = m.tanggal.max() + pd.Timedelta(days=1)
    g = m.groupby("pelanggan_id")
    rec = (ref - g["tanggal"].max()).dt.days
    freq, mon = g["id_transaksi"].count(), g["total"].sum()
    if not {"recency", "frequency", "monetary"} <= set(h.columns):
        return 0, ["butuh kolom recency, frequency, monetary."]
    r = h.reindex(rec.index)
    return nilai([
        (set(h.index) == set(rec.index), "satu baris per pelanggan yang bertransaksi"),
        (dekat(r["recency"], rec) or dekat(r["recency"], rec - 1), "recency belum tepat"),
        (dekat(r["frequency"], freq), "frequency belum tepat"),
        (dekat(r["monetary"], mon), "monetary belum tepat"),
    ])


def b9(h, ns, D, kode):
    return "segmen" in h.columns and h["segmen"].nunique() >= 3


OPS = ["groupby", "pivot_table", "merge", "apply", "transform", "rolling", "qcut", "cut", "agg",
       "value_counts", "sort_values", "resample", "crosstab", "map", "assign", "nlargest"]


def c10(h, ns, D, kode):
    if not isinstance(h, dict):
        return 0, ["`hasil` harus dict berisi 'temuan' dan 'tabel'."]
    pakai = {o for o in OPS if re.search(rf"\b{o}\b", kode)}
    t, f = h.get("tabel"), h.get("temuan")
    return nilai([
        (isinstance(t, pd.DataFrame) and len(t) >= 3, "'tabel' harus DataFrame minimal 3 baris"),
        (isinstance(f, str) and len(f) >= 40, "'temuan' minimal 40 karakter"),
        (isinstance(f, str) and bool(re.search(r"\d", f)), "'temuan' harus memuat angka sebagai bukti"),
        (len(pakai) >= 3, f"pakai minimal 3 operasi pandas berbeda (terdeteksi {len(pakai)})"),
    ])


def b10(h, ns, D, kode):
    pakai = {o for o in OPS if re.search(rf"\b{o}\b", kode)}
    r = h.get("rekomendasi")
    return len(pakai) >= 5 and isinstance(r, str) and len(r) >= 20


TANTANGAN = [
    dict(judul="Detektif Data", cek=c1, bonus=b1,
         soal="Dataset **`kotor`** adalah data transaksi mentah yang berantakan. Buat dict `hasil` dengan kunci: "
              "`baris`, `kolom`, `duplikat` (jumlah baris identik penuh), dan `kolom_missing_terbanyak` (nama kolom).",
         bonus_txt="Tambahkan minimal 2 kunci temuan buatan Anda sendiri (mis. rentang tanggal, jumlah kota unik, kolom paling janggal).",
         starter="# Tersedia: kotor, pelanggan, pd, np\nhasil = {}\n"),
    dict(judul="Operasi Pembersihan", cek=c2, bonus=b2,
         soal="Bersihkan **`kotor`** menjadi DataFrame bersih `hasil`: buang duplikat, isi NaN pada `qty` dan `diskon` "
              "dengan strategi yang masuk akal (jelaskan lewat komentar), ubah `tanggal` ke datetime, "
              "dan seragamkan penulisan `kota` (huruf & spasi).",
         bonus_txt="Bungkus logika pembersihan dalam sebuah **fungsi** `def` yang reusable, dan isi NaN memakai statistik per kelompok (groupby/transform/median).",
         starter="# Tersedia: kotor, pelanggan, pd, np\nhasil = kotor.copy()\n"),
    dict(judul="Feature Engineering", cek=c3, bonus=b3,
         soal="`df` adalah data bersih. Tambahkan kolom `total` (= qty x harga x (1 - diskon)) dan `bulan` (angka bulan) "
              "lalu simpan ke `hasil`.",
         bonus_txt="Buat minimal 2 kolom baru ciptaan Anda yang berguna untuk analisis (mis. `hari`, `kategori_harga`, `is_weekend`).",
         starter="# Tersedia: df, pelanggan, pd, np\nhasil = df.copy()\n"),
    dict(judul="Filter Cerdas", cek=c4, bonus=b4,
         soal="Pada `df` (sudah ada `total`), temukan transaksi **bernilai tinggi**: `total` berada di atas **persentil ke-90 "
              "pada kotanya sendiri** (bukan persentil seluruh data). Simpan DataFrame hasil di `hasil` (harus ada kolom `id_transaksi`).",
         bonus_txt="Tambahkan kolom penjelas buatan Anda di `hasil` (mis. `ambang_kota`, `selisih_dari_ambang`).",
         starter="# Tersedia: df (ada total & bulan), pelanggan, pd, np\nhasil = df\n"),
    dict(judul="Juara per Kota", cek=c5, bonus=b5,
         soal="Untuk **setiap kota**, cari **3 kategori dengan omzet (sum total) tertinggi**. `hasil` berupa DataFrame "
              "dengan kolom minimal `kota` dan `kategori` (tepat 3 baris per kota).",
         bonus_txt="Sertakan minimal 4 kolom: mis. `omzet`, `peringkat`, `persen_dari_kota`.",
         starter="# Tersedia: df (ada total & bulan), pelanggan, pd, np\nhasil = None\n"),
    dict(judul="Peta Omzet (Pivot)", cek=c6, bonus=b6,
         soal="Buat tabel pivot: **baris = kota, kolom = bulan, isi = total omzet** (kosong diisi 0). Simpan ke `hasil`.",
         bonus_txt="Tambahkan total baris/kolom (margins) atau ubah hasil menjadi tabel yang lebih informatif dari sekadar pivot dasar.",
         starter="# Tersedia: df (ada total & bulan), pelanggan, pd, np\nhasil = None\n"),
    dict(judul="Gabung Dua Dunia (Merge)", cek=c7, bonus=b7,
         soal="Gabungkan `df` dengan `pelanggan` (kunci `pelanggan_id`). Hitung **rata-rata `total` per transaksi** untuk "
              "setiap level `member`. `hasil` DataFrame berkolom `member` dan `rata_total`.",
         bonus_txt="Tambahkan minimal 1 metrik lain (mis. `jumlah_transaksi`, `umur_rata2`) sehingga ada >= 3 kolom.",
         starter="# Tersedia: df (ada total & bulan), pelanggan, pd, np\nhasil = None\n"),
    dict(judul="Detak Waktu (Time Series)", cek=c8, bonus=b8,
         soal="Hitung omzet **harian** (hari tanpa transaksi dihitung 0, pastikan tanggal kontinu), lalu **rata-rata bergerak 7 hari**. "
              "Simpan Series-nya di `hasil`.",
         bonus_txt="Buat juga variabel `hari_puncak` berisi tanggal dengan omzet harian tertinggi.",
         starter="# Tersedia: df (ada total & bulan), pelanggan, pd, np\nhasil = None\n"),
    dict(judul="Segmentasi Pelanggan (RFM)", cek=c9, bonus=b9,
         soal="Untuk tiap pelanggan hitung **recency** (hari sejak transaksi terakhir, acuan = tanggal terakhir data), "
              "**frequency** (jumlah transaksi), **monetary** (jumlah total). `hasil` DataFrame ber-index `pelanggan_id` "
              "dengan kolom `recency`, `frequency`, `monetary`.",
         bonus_txt="Tambahkan kolom `segmen` dengan >= 3 label ciptaan Anda (mis. VIP / Setia / Berisiko pergi).",
         starter="# Tersedia: df (ada total & bulan), pelanggan, pd, np\nhasil = None\n"),
    dict(judul="Tantangan Bebas: Konsultan Data", cek=c10, bonus=b10,
         soal="Anda konsultan toko online ini. Temukan **satu insight bisnis** yang menurut Anda paling berharga dari `df` + `pelanggan`. "
              "`hasil` = dict dengan kunci `temuan` (kalimat, >= 40 karakter, memuat angka bukti) dan `tabel` (DataFrame pendukung, >= 3 baris). "
              "Gunakan minimal 3 operasi pandas berbeda. *Soal ini bebas: dosen dapat meninjau & mengubah nilai.*",
         bonus_txt="Tambahkan kunci `rekomendasi` (>= 20 karakter) dan gunakan >= 5 operasi pandas berbeda.",
         starter="# Tersedia: df (ada total & bulan), pelanggan, pd, np\nhasil = {'temuan': '', 'tabel': None}\n"),
]

BLOK = re.compile(
    r"(\bimport\s+(os|sys|subprocess|socket|shutil|requests|pathlib|ctypes|builtins)\b|"
    r"\bfrom\s+(os|sys|subprocess|socket|shutil|pathlib|ctypes)\b|__\w+__|\bopen\s*\(|"
    r"\beval\s*\(|\bexec\s*\(|\bcompile\s*\(|\binput\s*\(|\bto_(csv|pickle|excel|sql)\s*\()"
)


def buat_ns(no, D, buf):
    ns = {"pd": pd, "np": np, "pelanggan": D.pelanggan.copy(),
          "print": lambda *a, sep=" ", end="\n", **k: buf.append(sep.join(map(str, a)) + end)}
    if no <= 2:
        ns["kotor"] = D.kotor.copy()
    elif no == 3:
        ns["df"] = D.dfb.copy()
    else:
        ns["df"] = D.dfm.copy()
    return ns


def evaluasi(no, kode, D):
    t = TANTANGAN[no - 1]
    buf = []
    res = dict(skor=0.0, dasar=0.0, bonus=0.0, pesan=[], output="", hasil=None)
    if BLOK.search(kode):
        res["pesan"] = ["Kode memakai perintah yang tidak diizinkan (file/sistem/eval/input/to_csv)."]
        return res
    ns = buat_ns(no, D, buf)
    try:
        exec(kode, ns)
    except Exception as e:
        res["pesan"] = [f"Error saat menjalankan kode: {type(e).__name__}: {e}"]
        res["output"] = "".join(buf)[:3000]
        return res
    res["output"] = "".join(buf)[:3000]
    if "hasil" not in ns or ns["hasil"] is None:
        res["pesan"] = ["Variabel `hasil` belum diisi."]
        return res
    h = ns["hasil"]
    res["hasil"] = h
    try:
        dasar, salah = t["cek"](h, ns, D, kode)
    except Exception as e:
        res.update(pesan=[f"Format `hasil` tidak sesuai: {type(e).__name__}: {e}"])
        return res
    bonus = 0.0
    if dasar >= 7:
        try:
            bonus = 3.0 if t["bonus"](h, ns, D, kode) else 0.0
        except Exception:
            bonus = 0.0
    res.update(dasar=dasar, bonus=bonus, skor=dasar + bonus, pesan=salah)
    return res


# ---------------------------------------------------------------- HALAMAN

IKON = ["🔍", "🧹", "🛠️", "🎯", "🏆", "🗺️", "🔗", "⏱️", "👥", "💡"]
MELAYANG = ["🐼", "📊", "📈", "🐍", "💻", "🧮", "✨", "🔍", "📁", "🏆", "📉", "🚀", "🧠", "⭐"]

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;600&family=Poppins:wght@400;600;700&display=swap');
@keyframes bgmove{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
@keyframes naik{0%{transform:translateY(0) rotate(0deg);opacity:0}10%{opacity:.75}90%{opacity:.75}100%{transform:translateY(-115vh) rotate(360deg);opacity:0}}
@keyframes goyang{0%,100%{transform:rotate(-8deg) scale(1)}50%{transform:rotate(8deg) scale(1.12)}}
.stApp{background:linear-gradient(-45deg,#0f172a,#312e81,#0e7490,#6d28d9,#be185d);background-size:400% 400%;animation:bgmove 20s ease infinite;font-family:'Poppins',sans-serif;}
header[data-testid="stHeader"]{background:transparent;}
[data-testid="stSidebar"]{background:rgba(15,23,42,.62);backdrop-filter:blur(14px);border-right:1px solid rgba(255,255,255,.14);}
[data-testid="stMetric"]{background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.2);border-radius:18px;padding:14px 18px;backdrop-filter:blur(10px);box-shadow:0 8px 24px rgba(0,0,0,.28);transition:transform .2s;}
[data-testid="stMetric"]:hover{transform:translateY(-4px);}
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button{border-radius:14px;font-weight:700;border:1px solid rgba(255,255,255,.25);transition:transform .15s,box-shadow .15s;}
.stButton>button:hover,.stDownloadButton>button:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(0,0,0,.35);}
.stButton>button[kind="primary"],[data-testid="stFormSubmitButton"]>button{background:linear-gradient(90deg,#f59e0b,#ef4444,#ec4899);color:#fff;border:0;}
textarea{font-family:'Fira Code',monospace !important;font-size:14px !important;}
[data-testid="stAlert"]{border-radius:14px;backdrop-filter:blur(8px);}
[data-testid="stExpander"]{background:rgba(255,255,255,.06);border-radius:14px;border:1px solid rgba(255,255,255,.14);}
[data-testid="stDataFrame"]{border-radius:14px;overflow:hidden;}
.hero{display:flex;align-items:center;gap:18px;padding:18px 26px;margin-bottom:18px;border-radius:22px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.22);backdrop-filter:blur(12px);box-shadow:0 10px 30px rgba(0,0,0,.3);}
.hero-ico{font-size:56px;animation:goyang 3s ease-in-out infinite;}
.hero h1{margin:0;padding:0;font-size:2.2rem;font-weight:700;background:linear-gradient(90deg,#fde68a,#f9a8d4,#93c5fd);-webkit-background-clip:text;background-clip:text;color:transparent;}
.hero p{margin:2px 0 0;opacity:.85;}
.floaty{position:fixed;bottom:-60px;z-index:0;pointer-events:none;animation:naik linear infinite;}
</style>
"""


def pasang_tema():
    bola = "".join(
        f'<div class="floaty" style="left:{(i * 7 + 3) % 96}%;font-size:{22 + (i * 5) % 26}px;'
        f'animation-duration:{14 + (i * 3) % 14}s;animation-delay:-{(i * 4) % 20}s">{e}</div>'
        for i, e in enumerate(MELAYANG)
    )
    st.markdown(CSS + bola, unsafe_allow_html=True)


def hero(ikon, judul, sub):
    st.markdown(
        f'<div class="hero"><div class="hero-ico">{ikon}</div><div><h1>{judul}</h1><p>{sub}</p></div></div>',
        unsafe_allow_html=True,
    )

def tampil_hasil(h):
    if isinstance(h, (pd.DataFrame, pd.Series)):
        st.dataframe(h.head(30) if len(h) > 30 else h, width="stretch")
    elif isinstance(h, dict):
        for k, v in h.items():
            st.markdown(f"**{k}**")
            if isinstance(v, (pd.DataFrame, pd.Series)):
                tampil_hasil(v)
            else:
                st.write(v)
    else:
        st.write(h)


def halaman_peserta():
    if "nim" not in st.session_state:
        hero("🐼", "Kuis Pandas", "10 tantangan coding data. Datamu unik berdasarkan NIM, jadi jawabanmu berbeda dari teman! 🚀")
        with st.form("login"):
            nama = st.text_input("👤 Nama lengkap")
            nim = st.text_input("🪪 NIM")
            if st.form_submit_button("🚀 Mulai Kuis"):
                if nama.strip() and re.fullmatch(r"\d{5,}", nim.strip()):
                    st.session_state.update(nama=nama.strip(), nim=nim.strip())
                    daftar_siswa(nim.strip(), nama.strip())
                    st.rerun()
                else:
                    st.error("Nama wajib diisi dan NIM harus angka (min. 5 digit).")
        return

    nim, nama = st.session_state["nim"], st.session_state["nama"]
    D = buat_data(nim)
    skor = skor_peserta(nim)

    with st.sidebar:
        st.markdown(f"### 🎓 {nama}  \nNIM {nim}")
        if st.button("🚪 Keluar"):
            st.session_state.clear()
            st.rerun()
        def label(i):
            v = skor.get(i)
            tanda = "⚪" if v is None else ("✅" if v >= 10 else "🟡")
            return f"{tanda} {IKON[i-1]} {i}. {TANTANGAN[i-1]['judul']} ({'-' if v is None else '%.1f' % v}/10)"

        no = st.radio("📚 Pilih soal", range(1, 11), format_func=label)

    total = sum(skor.values())
    hero("🐼", "Kuis Pandas", f"Semangat, {nama}! Kerjakan tantangan satu per satu. 💪")
    c1_, c2_, c3_ = st.columns(3)
    c1_.metric("🏅 Nilai saat ini", f"{total:.1f} / 100")
    c2_.metric("📝 Soal dikerjakan", f"{len(skor)} / 10")
    c3_.metric("🎯 Soal ini", f"{skor.get(no, 0):.1f} / 10")
    st.progress(len(skor) / 10)

    t = TANTANGAN[no - 1]
    st.header(f"{IKON[no-1]} Tantangan {no}: {t['judul']}")
    st.markdown(t["soal"])
    st.info(f"⭐ **Bonus inovasi (+3):** {t['bonus_txt']}")

    with st.expander("📂 Lihat data yang tersedia"):
        if no <= 2:
            st.write("`kotor`"); st.dataframe(D.kotor.head(15), width="stretch")
        else:
            st.write("`df`"); st.dataframe((D.dfb if no == 3 else D.dfm).head(15), width="stretch")
        st.write("`pelanggan`"); st.dataframe(D.pelanggan.head(10), width="stretch")

    key = f"kode_{nim}_{no}"
    if key not in st.session_state:
        st.session_state[key] = kode_terakhir(nim, no) or t["starter"]
    kode = st.text_area("Tulis kode pandas Anda (hasil akhir wajib disimpan di variabel `hasil`)",
                        key=key, height=300)

    if st.button("▶️ Jalankan & Nilai", type="primary"):
        r = evaluasi(no, kode, D)
        simpan_attempt(nim, nama, no, kode, r)
        st.session_state[f"res_{nim}_{no}"] = r
        if r["skor"] >= 10:
            st.session_state["balon"] = True
        st.rerun()

    r = st.session_state.get(f"res_{nim}_{no}")
    if r:
        st.subheader(f"Skor percobaan ini: {r['skor']:.1f} / 10 (ketepatan {r['dasar']:.1f}/7, bonus {r['bonus']:.0f}/3)")
        for p in r["pesan"]:
            st.warning(p)
        if r["skor"] >= 10:
            st.success("🎉 Sempurna! Skor penuh!")
            if st.session_state.pop("balon", False):
                st.balloons()
        if r["output"]:
            st.code(r["output"])
        if r["hasil"] is not None:
            with st.expander("Isi `hasil` Anda", expanded=True):
                tampil_hasil(r["hasil"])
    st.caption("Boleh dicoba berulang kali; nilai yang dihitung adalah skor terbaik tiap soal.")


@st.fragment(run_every=10)
def tampil_papan():
    df = papan_nilai()
    if df.empty:
        st.info("Belum ada peserta.")
        return
    a, b, c, d = st.columns(4)
    a.metric("👥 Peserta", len(df))
    b.metric("📈 Rata-rata nilai", f"{df['Total'].mean():.1f}")
    c.metric("🏆 Tertinggi", f"{df['Total'].max():.1f}")
    d.metric("✅ Selesai 10 soal", int((df["Dikerjakan"] == 10).sum()))
    st.caption(f"Auto-refresh tiap 10 detik. Terakhir: {datetime.now():%H:%M:%S}")
    st.dataframe(df.rename(columns={"nim": "NIM", "nama": "Nama", "mulai": "Mulai",
                                    "terakhir_aktif": "Terakhir aktif", "percobaan": "Percobaan"}),
                 width="stretch", hide_index=True)
    st.download_button("⬇️ Unduh CSV", df.to_csv(index=False).encode("utf-8"), "nilai_kuis_pandas.csv", "text/csv")
    st.markdown("**📊 Rata-rata skor per soal**")
    st.bar_chart(df[[f"S{i}" for i in range(1, 11)]].mean())


def halaman_dosen():
    hero("📊", "Dashboard Dosen", "Pantau progres dan hasil pekerjaan mahasiswa secara real-time.")
    if not st.session_state.get("dosen_ok"):
        pw = st.text_input("🔑 Password dosen", type="password")
        if st.button("🔓 Masuk"):
            if pw.strip() == DOSEN_PASSWORD:
                st.session_state["dosen_ok"] = True
                st.rerun()
            else:
                st.error("Password salah.")
        return
    tampil_papan()
    st.divider()
    st.subheader("🔎 Periksa pekerjaan peserta")
    df = papan_nilai()
    if df.empty:
        return
    pilih = st.selectbox("Peserta", df["nim"], format_func=lambda n: f"{n} - {df.set_index('nim').loc[n, 'nama']}")
    no = st.selectbox("Soal", range(1, 11), format_func=lambda i: f"{i}. {TANTANGAN[i-1]['judul']}")
    con = koneksi()
    att = pd.read_sql("SELECT id,waktu,dasar,bonus,skor,pesan,kode FROM attempts WHERE nim=? AND soal=? ORDER BY id DESC",
                      con, params=(pilih, no))
    con.close()
    if att.empty:
        st.info("Peserta belum mengerjakan soal ini.")
    for _, row in att.iterrows():
        with st.expander(f"{row['waktu']} - skor {row['skor']:.1f} ({row['dasar']:.1f}+{row['bonus']:.0f})"):
            if row["pesan"]:
                st.warning(row["pesan"])
            st.code(row["kode"], language="python")
    with st.form("manual"):
        st.markdown("**Nilai manual (menimpa nilai otomatis untuk soal ini)**")
        sk = st.number_input("Skor (0-10)", 0.0, 10.0, step=0.5)
        cat = st.text_input("Catatan")
        if st.form_submit_button("Simpan nilai manual"):
            con = koneksi()
            con.execute("INSERT OR REPLACE INTO manual VALUES(?,?,?,?)", (pilih, no, sk, cat))
            con.commit()
            con.close()
            st.success("Tersimpan.")


def main():
    st.set_page_config(page_title="Kuis Pandas", page_icon="🐼", layout="wide")
    init_db()
    pasang_tema()
    mode = st.sidebar.radio("Mode", ["🎓 Peserta", "🧑‍🏫 Dosen"])
    if mode.endswith("Peserta"):
        halaman_peserta()
    else:
        halaman_dosen()


if __name__ == "__main__":
    main()