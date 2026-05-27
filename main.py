from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from services import diyet_olustur, kullanici_kaydet, alternatif_yemek_bul_ml, kullanici_kontrol_et
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
    f'Encrypt=no;'
    f'TrustServerCertificate=yes;'
)
engine = create_engine(f'mssql+pyodbc:///?odbc_connect={params}')
# -----------------------------
class AlternatifIstegi(BaseModel):
    eski_yemek_id: int
    eski_yemek_kategorisi: str
    eski_yemek_kalorisi: float
    alerjiler: List[str]
    sevilmeyenler: List[str]
    sevilenler: List[str]
    saglik_sorunlari: List[str]
    diyet_turu: str

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
    plan_turu: str = "Haftalik"

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
    # 🌟 GÜNCELLENDİ: haftalik_diyet_olustur kullanılıyor
    plan_turu = (
        str(istek.plan_turu or "").lower()
        .replace("ı", "i").replace("ö", "o").replace("ü", "u")
        .replace("ç", "c").replace("ş", "s").replace("ğ", "g")
        .replace("Ä±", "i").replace("Ã¶", "o").replace("Ã¼", "u")
        .replace("Ã§", "c").replace("ÅŸ", "s").replace("ÄŸ", "g")
        .replace("�", "i")
    )
    if "gunluk" in plan_turu:
        sonuc = diyet_olustur(
            hedef_kalori=istek.hedef_kalori,
            alerjiler=istek.alerjiler,
            sevilmeyenler=istek.sevilmeyenler,
            sevilenler=istek.sevilenler,
            saglik_sorunlari=istek.saglik_sorunlari,
            diyet_turu=istek.diyet_turu
        )
    else:
        from services import haftalik_diyet_olustur
        sonuc = haftalik_diyet_olustur(
            hedef_kalori=istek.hedef_kalori,
            alerjiler=istek.alerjiler,
            sevilmeyenler=istek.sevilmeyenler,
            sevilenler=istek.sevilenler,
            saglik_sorunlari=istek.saglik_sorunlari,
            diyet_turu=istek.diyet_turu
        )
    
    if sonuc["durum"] == "Başarılı":
        return sonuc
    else:
        raise HTTPException(status_code=400, detail=sonuc["mesaj"])
@app.post("/api/alternatif-bul")
def alternatif_bul(istek: AlternatifIstegi):
    from services import alternatif_yemek_bul_ml
    
    # İstekteki verileri Python fonksiyonumuza gönderiyoruz
    sonuc = alternatif_yemek_bul_ml(
        eski_yemek_id=istek.eski_yemek_id,
        kategori=istek.eski_yemek_kategorisi,
        alerjiler=istek.alerjiler,
        sevilmeyenler=istek.sevilmeyenler
    )
    return sonuc
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

class KiloGuncelleIstegi(BaseModel):
    email: str
    weight: float

@app.post("/api/update_weight")
def update_weight(istek: KiloGuncelleIstegi):
    from services import kilo_guncelle
    try:
        sonuc = kilo_guncelle(istek.email, istek.weight)
        if sonuc["durum"] == "Başarılı":
            return sonuc
        else:
            raise HTTPException(status_code=404, detail=sonuc["mesaj"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ProfilGuncelleIstegi(BaseModel):
    email: str
    goal: Optional[str] = None
    dietType: Optional[str] = None
    alerjiler: List[str] = []
    sevilmeyenler: List[str] = []
    sevilenler: List[str] = []
    saglik_sorunlari: List[str] = []

@app.put("/api/profil-guncelle")
def profil_guncelle(istek: ProfilGuncelleIstegi):
    """
    1. Profil tercihlerini (goal, dietType, kısıtlamalar) kaydeder.
    2. Hemen ardından yeni profil verisiyle haftalık menüyü OTOMATİK yeniler.
    3. Menü oluşturulamadıysa (Infeasible) uyarıyla birlikte başarılı döner.
    """
    from services import (
        haftalik_diyet_olustur,
        aktif_menuyu_kaydet,
        kullanici_kontrol_et,
        bmr_ve_kalori_hesapla,
    )

    # ── ADIM 1: Profil tercihlerini kaydet (fonksiyon yoksa atla) ────────
    try:
        kullanici = kullanici_kontrol_et(istek.email)
        if not kullanici.get("kayitli_mi"):
            raise HTTPException(status_code=404, detail="Kalori hesaplamak için kayıtlı kullanıcı fiziksel bilgileri bulunamadı.")

        yeni_hesaplanan_kalori = bmr_ve_kalori_hesapla(
            kullanici.get("cinsiyet"),
            kullanici.get("yas"),
            kullanici.get("boy_cm"),
            kullanici.get("kilo_kg"),
            kullanici.get("hareket_katsayisi"),
            istek.goal,
        )
        profil_data = {
            "email": istek.email,
            "goal": istek.goal,
            "diet_type": istek.dietType,
            "alerjiler": istek.alerjiler,
            "sevilmeyenler": istek.sevilmeyenler,
            "sevilenler": istek.sevilenler,
            "saglik_sorunlari": istek.saglik_sorunlari,
        }
        profil_data["hedef_kalori"] = yeni_hesaplanan_kalori

        from services import profil_kaydet
        profil_kaydet(
            email=istek.email,
            goal=istek.goal,
            diet_type=istek.dietType,
            alerjiler=istek.alerjiler,
            sevilmeyenler=istek.sevilmeyenler,
            sevilenler=istek.sevilenler,
            saglik_sorunlari=istek.saglik_sorunlari,
            hedef_kalori=profil_data["hedef_kalori"],
        )
    except (ImportError, AttributeError) as e:
        raise HTTPException(status_code=500, detail=f"Profil kaydetme servisi bulunamadı: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Profil kaydedilemedi: {str(e)}")

    # ── ADIM 2: Kullanıcının kalori hedefini bul ─────────────────────────
    hedef_kalori = profil_data["hedef_kalori"]

    goal_normalized = str(istek.goal or "koruma").lower().strip()

    # ── ADIM 3: Yeni profil verisiyle haftalık menüyü yeniden üret ───────
    try:
        ai_data = {
            "goal": goal_normalized,
            "diet_type": istek.dietType or "Standart",
            "allergens": istek.alerjiler,
            "exclude_foods": istek.sevilmeyenler,
            "include_foods": istek.sevilenler,
            "health_conditions": istek.saglik_sorunlari,
        }

        menu_sonuc = haftalik_diyet_olustur(
            hedef_kalori=hedef_kalori,
            alerjiler=istek.alerjiler,
            sevilmeyenler=istek.sevilmeyenler,
            sevilenler=istek.sevilenler,
            saglik_sorunlari=istek.saglik_sorunlari,
            diyet_turu=istek.dietType or "Standart",
            ai_data=ai_data,
        )

        if menu_sonuc.get("durum") == "Başarılı" and menu_sonuc.get("haftalik_plan"):
            aktif_menuyu_kaydet(istek.email, menu_sonuc)
            return {
                "durum": "Başarılı",
                "mesaj": "Profil güncellendi ve yeni menünüz oluşturuldu.",
                "menu_updated": True,
            }
        else:
            # Menü oluşturulamadı (Infeasible) — profil kaydedildi ama menü değişmedi
            return {
                "durum": "Başarılı",
                "mesaj": "Profil güncellendi.",
                "menu_updated": False,
                "uyari": (
                    menu_sonuc.get("mesaj")
                    or "Bu kısıtlamalarla yeni menü oluşturulamadı. "
                       "Lütfen diyet ayarlarınızı esnetin."
                ),
            }

    except Exception as e:
        # Menü üretimi çöktü — profil zaten kaydedildi, sadece uyarı ver
        print(f"[profil-guncelle] Menü oluşturma hatası: {e}")
        return {
            "durum": "Başarılı",
            "mesaj": "Profil güncellendi.",
            "menu_updated": False,
            "uyari": "Profil güncellendi ancak bu kısıtlamalarla yeni menü oluşturulamadı. Lütfen diyet ayarlarınızı esnetin.",
        }


class ChatRequest(BaseModel):
    user_message: str
    user_email: str
    profile: Optional[Dict[str, Any]] = None

@app.post("/api/chat")
async def chat_with_assistant(request: ChatRequest):
    from api_controller import chat_endpoint_islemi
    try:
        response = chat_endpoint_islemi(request.user_message, request.user_email, request.profile)
        return response
    except Exception as e:
        print(f"Chatbot Hatası: {str(e)}")
        raise HTTPException(status_code=500, detail="Asistan şu an biraz yoğun, lütfen tekrar dene.")

