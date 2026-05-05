from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from pydantic import BaseModel
from typing import List  # YENİ EKLENDİ: Listeleri tanımlamak için
from services import diyet_olustur, kullanici_kaydet
import urllib

# FastAPI uygulamasını başlat
app = FastAPI(title="Akıllı Beslenme Asistanı API")

# CORS Ayarları (Frontend'in bağlanabilmesi için)
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

# API'nin kabul edeceği kullanıcı şablonu (Pydantic Modeli)
class KullaniciBilgileri(BaseModel):
    ad: str
    cinsiyet: str  # "erkek" veya "kadin"
    yas: int
    boy_cm: float
    kilo_kg: float
    hareket_katsayisi: float
    hedef: str

# YENİ: Diyet algoritmasının beklediği detaylı veri şablonu
class DiyetIstegi(BaseModel):
    hedef_kalori: int
    alerjiler: List[str] = []
    sevilmeyenler: List[str] = []
    saglik_sorunlari: List[str] = []
    diyet_turu: str = "Standart"

@app.get("/")
def root():
    return {"mesaj": "Diyet Asistanı API'si başarıyla çalışıyor! 🚀"}

# Veritabanından Yemekleri Çeken Endpoint
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
    
# 🧠 YAPAY ZEKA (OPTİMİZASYON) UÇ NOKTASI (GÜNCELLENDİ: Artık POST isteği)
@app.post("/api/diyet-hazirla")
def akilli_diyet_olustur(istek: DiyetIstegi):
    # Gelen listeleri ve hedef kaloriyi services.py'a gönderiyoruz
    sonuc = diyet_olustur(
        hedef_kalori=istek.hedef_kalori,
        alerjiler=istek.alerjiler,
        sevilmeyenler=istek.sevilmeyenler,
        saglik_sorunlari=istek.saglik_sorunlari,
        diyet_turu=istek.diyet_turu
    )
    
    if sonuc["durum"] == "Başarılı":
        return sonuc
    else:
        raise HTTPException(status_code=400, detail=sonuc["mesaj"])

# 👤 YENİ: KULLANICI OLUŞTURMA VE BMR HESAPLAMA UÇ NOKTASI
@app.post("/api/kullanici-olustur")
def yeni_kullanici_olustur(kullanici: KullaniciBilgileri):
    try:
        sonuc = kullanici_kaydet(
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
        raise HTTPException(status_code=500, detail=f"Kullanıcı kaydedilirken bir hata oluştu: {str(e)}")