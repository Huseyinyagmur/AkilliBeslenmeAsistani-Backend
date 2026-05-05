from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from pydantic import BaseModel
from typing import List
from services import diyet_olustur, kullanici_kaydet, alternatif_yemek_bul, kullanici_kontrol_et
import urllib

# FastAPI uygulamasını başlat
app = FastAPI(title="Akıllı Beslenme Asistanı API")

# CORS Ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- VERİTABANI BAĞLANTISI ---
server_adi = 'LAPTOP-V013QBHO' 
veritabani_adi = 'DiyetAppDB'

params = urllib.parse.quote_plus(
    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
    f'SERVER={server_adi};'
    f'DATABASE={veritabani_adi};'
    f'Trusted_Connection=yes;'
)
engine = create_engine(f'mssql+pyodbc:///?odbc_connect={params}')
# -----------------------------

class KullaniciBilgileri(BaseModel):
    email:str
    ad: str
    cinsiyet: str
    yas: int
    boy_cm: float
    kilo_kg: float
    hareket_katsayisi: float
    hedef: str

# 🌟 GÜNCELLENDİ: sevilenler parametresi eklendi
class DiyetIstegi(BaseModel):
    hedef_kalori: int
    alerjiler: List[str] = []
    sevilmeyenler: List[str] = []
    sevilenler: List[str] = [] # YENİ EKLENDİ
    saglik_sorunlari: List[str] = []
    diyet_turu: str = "Standart"

# 🌟 YENİ: Alternatif Bulma İstek Modeli
class AlternatifIstegi(BaseModel):
    eski_yemek_id: int
    eski_yemek_kategorisi: str
    eski_yemek_kalorisi: float
    alerjiler: List[str] = []
    sevilmeyenler: List[str] = []
    sevilenler: List[str] = []
    saglik_sorunlari: List[str] = []
    diyet_turu: str = "Standart"

@app.get("/")
def root():
    return {"mesaj": "Diyet Asistanı API'si başarıyla çalışıyor! 🚀"}

@app.get("/api/yemekler")
def yemekleri_getir():
    try:
        with engine.connect() as connection:
            sorgu = text("SELECT Yemek_Id, Yemek_Adı, Kalori_Kcal, Kategori FROM Yemekler")
            sonuc = connection.execute(sorgu)
            
            yemek_listesi = [
                {"id": satir.Yemek_Id, "isim": satir.Yemek_Adı, "kalori": satir.Kalori_Kcal, "kategori": satir.Kategori} 
                for satir in sonuc
            ]
            return {"basari": True, "veri": yemek_listesi}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Veritabanı hatası: {str(e)}")
    
@app.post("/api/diyet-hazirla")
def akilli_diyet_olustur(istek: DiyetIstegi):
    # 🌟 GÜNCELLENDİ: sevilenler backend'e iletiliyor
    sonuc = diyet_olustur(
        hedef_kalori=istek.hedef_kalori,
        alerjiler=istek.alerjiler,
        sevilmeyenler=istek.sevilmeyenler,
        sevilenler=istek.sevilenler, # YENİ EKLENDİ
        saglik_sorunlari=istek.saglik_sorunlari,
        diyet_turu=istek.diyet_turu
    )
    
    if sonuc["durum"] == "Başarılı":
        return sonuc
    else:
        raise HTTPException(status_code=400, detail=sonuc["mesaj"])

# 🌟 YENİ: Alternatif Bul Endpoint'i (Şimdilik taslak)
@app.post("/api/alternatif-bul")
def alternatif_yemek_bul_api(istek: AlternatifIstegi):
    sonuc = alternatif_yemek_bul(
        eski_yemek_id=istek.eski_yemek_id,
        kategori=istek.eski_yemek_kategorisi,
        eski_kalori=istek.eski_yemek_kalorisi,
        alerjiler=istek.alerjiler,
        sevilmeyenler=istek.sevilmeyenler,
        sevilenler=istek.sevilenler,
        saglik_sorunlari=istek.saglik_sorunlari,
        diyet_turu=istek.diyet_turu
    )
    
    if sonuc["durum"] == "Başarılı":
        return sonuc
    else:
        raise HTTPException(status_code=404, detail=sonuc["mesaj"])

@app.post("/api/kullanici-olustur")
def yeni_kullanici_olustur(kullanici: KullaniciBilgileri):
    try:
        sonuc = kullanici_kaydet(
            email=kullanici.email,
            ad=kullanici.ad,
            cinsiyet=kullanici.cinsiyet,
            yas=kullanici.yas,
            boy_cm=kullanici.boy_cm,
            kilo_kg=kullanici.kilo_kg,
            hareket_katsayisi=kullanici.hareket_katsayisi,
            hedef=kullanici.hedef
        )
        return sonuc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kullanıcı kaydedilirken hata: {str(e)}")

# YENİ EKLENEN ENDPOINT
@app.get("/api/kullanici-kontrol/{email}")
def kullanici_var_mi(email: str):
    try:
        return kullanici_kontrol_et(email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kontrol hatası: {str(e)}")

# Sınıf tanımlamalarının (class ... BaseModel) olduğu yere ekle
class DiyetKayitIstegi(BaseModel):
    email: str
    diyet_plani: dict

# Endpoint'lerin olduğu yere ekle
@app.post("/api/diyet-kaydet")
def diyet_kaydet(istek: DiyetKayitIstegi):
    from services import aktif_menuyu_kaydet
    return aktif_menuyu_kaydet(istek.email, istek.diyet_plani)

@app.get("/api/aktif-diyet/{email}")
def diyet_getir(email: str):
    from services import aktif_menuyu_getir
    return aktif_menuyu_getir(email)