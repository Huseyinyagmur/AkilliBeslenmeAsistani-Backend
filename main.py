from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from services import diyet_olustur
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
server_adi = 'LAPTOP-V013QBHO' # <--- BURAYA KENDİ SQL SERVER ADINI YAZ
veritabani_adi = 'DiyetAppDB'

params = urllib.parse.quote_plus(
    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
    f'SERVER={server_adi};'
    f'DATABASE={veritabani_adi};'
    f'Trusted_Connection=yes;'
)
engine = create_engine(f'mssql+pyodbc:///?odbc_connect={params}')
# -----------------------------

@app.get("/")
def root():
    return {"mesaj": "Diyet Asistanı API'si başarıyla çalışıyor! 🚀"}

# YENİ EKLENEN KISIM: Veritabanından Yemekleri Çeken Endpoint
@app.get("/api/yemekler")
def yemekleri_getir():
    try:
        # Veritabanına bağlan ve ilk 5 yemeği test için çek
        with engine.connect() as connection:
            sorgu = text("SELECT Yemek_Id, Yemek_Adı,Kalori_Kcal, Kategori FROM Yemekler")
            sonuc = connection.execute(sorgu)
            
            # Gelen veriyi JSON formatına (sözlük yapısına) çevir
            yemek_listesi = [
                {"id": satir.Yemek_Id, "isim": satir.Yemek_Adı, "kalori": satir.Kalori_Kcal, "kategori": satir.Kategori} 
                for satir in sonuc
            ]
            return {"basari": True, "veri": yemek_listesi}
            
    except Exception as e:
        # Eğer veritabanı bağlantısında hata olursa uygulamayı çökertme, ekrana hatayı bas
        raise HTTPException(status_code=500, detail=f"Veritabanı hatası: {str(e)}")
    
# 🧠 YENİ: YAPAY ZEKA (OPTİMİZASYON) UÇ NOKTASI
@app.get("/api/diyet-hazirla/{hedef_kalori}")
def akilli_diyet_olustur(hedef_kalori: int):
    sonuc = diyet_olustur(hedef_kalori)
    
    if sonuc["durum"] == "Başarılı":
        return sonuc
    else:
        raise HTTPException(status_code=400, detail=sonuc["mesaj"])