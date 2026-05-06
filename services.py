import pulp
from sqlalchemy import create_engine, text
import urllib
import random
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.neighbors import NearestNeighbors

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

def diyet_olustur(hedef_kalori: int, alerjiler: list = None, sevilmeyenler: list = None, saglik_sorunlari: list = None, diyet_turu: str = "Standart", sevilenler: list = None):
    
    # Gelen verileri küçük harfe çevirerek standardize ediyoruz
    alerjiler = [a.lower() for a in (alerjiler or [])]
    sevilmeyenler = [s.lower() for s in (sevilmeyenler or [])]
    sevilenler = [f.lower() for f in (sevilenler or [])]
    saglik_sorunlari = saglik_sorunlari or []
    
    diyabet_var_mi = "Diyabet" in saglik_sorunlari or "İnsülin Direnci" in saglik_sorunlari

    # --- YARDIMCI KATEGORİ FONKSİYONLARI ---
    def ana_yemek_mi(y):
        k, i = y["kategori"].lower(), y["isim"].lower()
        if k in ["ana yemek", "fast food"]: return True
        return any(w in i for w in ["et ", "etli", "tavuk", "balık", "somon", "köfte", "kofte", "kıyma", "kavurma", "tantuni", "kebap", "döner", "pizza", "burger", "hamburger", "şiş", "hamsi", "levrek", "şnitzel", "kokoreç", "ciğer", "kuzu", "dana", "iskender", "biftek", "antrikot", "beğendi"])

    def yumurta_mi(y): return any(w in y["isim"].lower() for w in ["yumurta", "omlet", "menemen", "çılbır", "sahanda"])
    def hamur_isi_mi(y): return any(w in y["isim"].lower() for w in ["ekmek", "ekmeg", "börek", "borek", "simit", "açma", "poğaça", "tost", "lavaş", "bazlama", "yulaf", "gevrek"])
    
    def icecek_mi(y): 
        k, i = y["kategori"].lower(), y["isim"].lower()
        if "içecek" in k or "icecek" in k: return True
        return any(w in i for w in ["su", "shake", "nektar", "ayran", "kahve", "çay", "cay", "soda", "kola", "fanta", "gazoz", "milkshake", "meyve suyu", "kefir", "limonata", "şalgam", "ice tea", "süt", "maden suyu", "şişe", "bardak", "kutu", "kupa", "fincan", "shaker"])

    def meyve_kuruyemis_mi(y): 
        if icecek_mi(y): return False 
        k, i = y["kategori"].lower(), y["isim"].lower()
        if k in ["tatlı", "tatli"] or any(w in i for w in ["dondurma", "tatlı", "pasta", "kek", "çikolata"]): return False
        if k in ["meyve", "kuruyemiş", "kuruyemis"]: return True
        return any(w in i for w in ["fıstık", "badem", "ceviz", "elma", "muz", "kuru", "hurma", "incir", "kayısı", "leblebi", "meyve", "fındık", "mandalina", "portakal", "çilek", "kavun", "karpuz"])

    def hafif_yan_mi(y):
        k, i = y["kategori"].lower(), y["isim"].lower()
        if k in ["çorba", "corba", "salata", "meze"]: return True
        return any(w in i for w in ["çorba", "corba", "salata", "yoğurt", "yogurt", "cacık", "ayran", "yeşillik", "piyaz", "tarator"])

    yemekler = []
    with engine.connect() as conn:
        sorgu = text("""
            SELECT Yemek_Id, Yemek_Adı, Olcu_Birimi, Kalori_Kcal, Kategori, 
                   Protein_g, Karbonhidrat_g, Yag_g, Baskin_Malzemeler, Alerjen_Bilgisi
            FROM Yemekler 
            WHERE Kalori_Kcal IS NOT NULL AND Protein_g IS NOT NULL AND Karbonhidrat_g IS NOT NULL AND Yag_g IS NOT NULL
        """)
        sonuc = conn.execute(sorgu)
        for row in sonuc:
            isim_lower = str(row.Yemek_Adı).lower()
            kat_lower = str(row.Kategori).lower()
            malzemeler_db = str(row.Baskin_Malzemeler).lower() if row.Baskin_Malzemeler else ""
            alerjen_db = str(row.Alerjen_Bilgisi).lower() if row.Alerjen_Bilgisi else ""

            # 🛑 DİYET TÜRÜ FİLTRESİ
            if diyet_turu == "Vegan" and any(w in isim_lower or w in kat_lower or w in malzemeler_db for w in ["et", "tavuk", "balık", "süt", "peynir", "yoğurt", "yumurta", "kefir", "ayran", "sucuk", "kavurma", "kuzu", "dana", "köfte", "kıyma"]):
                continue
            if diyet_turu == "Vejetaryen" and any(w in isim_lower or w in kat_lower or w in malzemeler_db for w in ["et", "tavuk", "balık", "sucuk", "kavurma", "kuzu", "dana", "köfte", "hamsi", "somon", "kıyma"]):
                continue

            # 🛑 ALERJEN VE SEVİLMEYENLER (Veritabanı Sütunlarından Süzme)
            if any(a in alerjen_db for a in alerjiler): continue
            
            yasakli_kelimeler = []
            if "gluten" in alerjiler: yasakli_kelimeler.extend(["ekmek", "ekmeg", "börek", "borek", "simit", "makarna", "erişte", "eriste", "pide", "lavaş", "lavas", "un", "mantı", "manti", "şehriye", "sehriye", "bulgur", "tarhana", "irmik", "bazlama", "yufka", "galeta", "kraker", "pasta", "kek", "çerkez", "cerkez"])
            if "laktoz" in alerjiler: yasakli_kelimeler.extend(["süt", "sut", "peynir", "yoğurt", "yogurt", "kefir", "ayran", "krem", "tereyağ", "tereyag", "cacık", "cacik"])
            if "yer fıstığı" in alerjiler: yasakli_kelimeler.extend(["fıstık", "fistik"])
            if "yumurta" in alerjiler: yasakli_kelimeler.extend(["yumurta", "omlet", "menemen", "çılbır", "cilbir"])
            if "deniz ürünleri" in alerjiler: yasakli_kelimeler.extend(["balık", "balik", "somon", "hamsi", "levrek", "karides", "kalamar"])
            if "kuruyemiş" in alerjiler: yasakli_kelimeler.extend(["ceviz", "fındık", "findik", "badem", "fıstık", "fistik"])
            
            if any(y in isim_lower or y in malzemeler_db for y in yasakli_kelimeler): continue
            if any(s in isim_lower or s in malzemeler_db for s in sevilmeyenler): continue

            # 🛑 SAĞLIK (Diyabet)
            if diyabet_var_mi and (kat_lower in ["tatlı", "tatli"] or any(k in isim_lower or k in malzemeler_db for k in ["çikolata", "cikolata", "pasta", "kek", "bal", "reçel", "recel", "pekmez", "şeker"])):
                continue

            # 🌟 ÖDÜL PUANI HESAPLAMA (Sevilen Yiyecekler)
            # Minimize ettiğimiz için sevilen yemeğin skorunu çok düşürüyoruz ki algoritma ona "atlasın"
            skor = random.uniform(1, 100)
            if any(f in isim_lower or f in malzemeler_db for f in sevilenler):
                skor -= 10000 

            porsiyon = row.Olcu_Birimi if row.Olcu_Birimi else ""
            y_isim = f"{porsiyon} {row.Yemek_Adı}".strip()
            
            # 🌟 Akıllı Yulaf Notu
            if "yulaf" in y_isim.lower() and "lapa" in y_isim.lower() and "laktoz" in alerjiler:
                y_isim += " (Su veya Bitkisel Süt ile)"

            yemekler.append({
                "id": row.Yemek_Id,
                "isim": y_isim,
                "kalori": float(row.Kalori_Kcal),
                "kategori": row.Kategori,
                "protein": float(row.Protein_g),
                "karb": float(row.Karbonhidrat_g),
                "yag": float(row.Yag_g),
                "skor": skor
            })
    
    if len(yemekler) < 15:
        return {"durum": "Başarısız", "mesaj": "Kısıtlamalara uygun yeterli yemek kalmadı."}

    # --- PuLP OPTİMİZASYONU ---
    prob = pulp.LpProblem("Ogunlu_Diyet_Plani", pulp.LpMinimize)
    yemek_degiskenleri = pulp.LpVariable.dicts("Yemek", [y["id"] for y in yemekler], 0, 1, cat='Integer')
    
    # AMAÇ: Skoru minimize et (Sevilenleri seç, geri kalanı rastgele çeşitlendir)
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["skor"] for y in yemekler])

    # Makro Hedefleri
    hedef_protein_g = (hedef_kalori * 0.30) / 4
    hedef_karb_g = (hedef_kalori * 0.40) / 4
    hedef_yag_g = (hedef_kalori * 0.30) / 9

    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler]) >= hedef_kalori - 200
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler]) <= hedef_kalori + 200
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["protein"] for y in yemekler]) >= hedef_protein_g - 40
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["karb"] for y in yemekler]) >= hedef_karb_g - 40
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["yag"] for y in yemekler]) >= hedef_yag_g - 25

    # Öğün Kalori Dağılımları
    sabah_kat = ["Kahvalti", "Kahvaltı", "Hamur İsi", "Hamur İşi", "Kahvaltılık"]
    ara_ogun_kat = ["Tatlı", "Tatli", "Meyve", "Atıştırmalık", "Atistirmalik", "İcecek", "İçecek", "Kuruyemis", "Kuruyemiş"]

    sabah_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] in sabah_kat])
    prob += sabah_kalori >= hedef_kalori * 0.20
    prob += sabah_kalori <= hedef_kalori * 0.35

    ara_ogun_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] in ara_ogun_kat])
    prob += ara_ogun_kalori <= hedef_kalori * 0.15

    # 🌟 ÖĞÜN KURALLARI VE ÇORBA SINIRI
    # Günde max 2 çorba
    tum_corbalar = [yemek_degiskenleri[y["id"]] for y in yemekler if any(k in y["isim"].lower() for k in ["çorba", "corba"])]
    if tum_corbalar: prob += pulp.lpSum(tum_corbalar) <= 2

    # Kahvaltı Standartları
    sabah_yumurtalar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and yumurta_mi(y)]
    if sabah_yumurtalar and "yumurta" not in alerjiler: prob += pulp.lpSum(sabah_yumurtalar) >= 1

    # Öğle ve Akşam Ana Yemekleri
    ogle_aksam_ana = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat and ana_yemek_mi(y)]
    if ogle_aksam_ana: prob += pulp.lpSum(ogle_aksam_ana) == 2

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    # --- SONUÇLARI PAKETLEME ---
    ogunler = { "Sabah": [], "Öğle_ve_Akşam": [], "Ara_Öğün": [] }
    hesap_kal, hesap_prot, hesap_karb, hesap_yag = 0, 0, 0, 0
    
    if pulp.LpStatus[prob.status] == 'Optimal':
        ana_secilen = []
        yan_secilen = []

        for y in yemekler:
            if yemek_degiskenleri[y["id"]].varValue > 0:
                if y["kategori"] in sabah_kat: ogunler["Sabah"].append(y)
                elif y["kategori"] in ara_ogun_kat: ogunler["Ara_Öğün"].append(y)
                else:
                    if ana_yemek_mi(y): ana_secilen.append(y)
                    else: yan_secilen.append(y)
                
                hesap_kal += y["kalori"]; hesap_prot += y["protein"]
                hesap_karb += y["karb"]; hesap_yag += y["yag"]

        # Yan yemekleri (çorba, salata vb.) öğünlere dağıt
        if len(ana_secilen) >= 2:
            ogunler["Öğle_ve_Akşam"].append(ana_secilen[0])
            if yan_secilen: ogunler["Öğle_ve_Akşam"].append(yan_secilen.pop(0))
            if yan_secilen: ogunler["Öğle_ve_Akşam"].append(yan_secilen.pop(0))
            
            ogunler["Öğle_ve_Akşam"].append(ana_secilen[1])
            while yan_secilen: ogunler["Öğle_ve_Akşam"].append(yan_secilen.pop(0))

        return {
            "durum": "Başarılı",
            "hedef_kalori": hedef_kalori,
            "gerceklesen": {"kalori": round(hesap_kal), "protein_g": round(hesap_prot), "karb_g": round(hesap_karb), "yag_g": round(hesap_yag)},
            "ogunler": ogunler
        }
    return {"durum": "Başarısız", "mesaj": "Kısıtlamalara uygun menü bulunamadı."}

# ... (bmr_ve_kalori_hesapla ve kullanici_kaydet fonksiyonları aynı kalıyor) ...

def bmr_ve_kalori_hesapla(cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float, hedef: str):
    if cinsiyet.lower() == "erkek": bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) + 5
    else: bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) - 161
    
    gunluk_harcanan_kalori = bmr * hareket_katsayisi
    if hedef == "Kilo Ver": hedef_kalori = gunluk_harcanan_kalori - 500
    elif hedef == "Kas Yap": hedef_kalori = gunluk_harcanan_kalori + 300
    else: hedef_kalori = gunluk_harcanan_kalori
    return int(hedef_kalori)

def kullanici_kaydet(email: str, ad: str, cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float, hedef: str):
    # Kalori hesabını yapan fonksiyonunun adının bmr_ve_kalori_hesapla olduğunu varsayıyorum (mevcut kodunla aynı)
    hedef_kalori = bmr_ve_kalori_hesapla(cinsiyet, yas, boy_cm, kilo_kg, hareket_katsayisi, hedef)
    
    with engine.begin() as conn: 
        # Tablo yoksa oluştur
        conn.execute(text("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Kullanicilar' and xtype='U')
            CREATE TABLE Kullanicilar (
                Kullanici_Id INT IDENTITY(1,1) PRIMARY KEY,
                Email NVARCHAR(255) UNIQUE, 
                Ad NVARCHAR(100), Cinsiyet NVARCHAR(10), Yas INT, Boy_cm FLOAT,
                Kilo_kg FLOAT, Hareket_Katsayisi FLOAT, Hedef_Kalori INT
            )
        """))
        
        # 🌟 İŞTE HAYAT KURTARAN UPSERT (Güncelle veya Ekle) MANTIĞI
        sorgu = text("""
            IF EXISTS (SELECT 1 FROM Kullanicilar WHERE Email = :email)
            BEGIN
                -- Kullanıcı varsa, yeni girdiği boy/kilo verileriyle GÜNCELLE
                UPDATE Kullanicilar 
                SET Ad = :ad, Cinsiyet = :cinsiyet, Yas = :yas, Boy_cm = :boy, 
                    Kilo_kg = :kilo, Hareket_Katsayisi = :hareket, Hedef_Kalori = :hedef_kalori
                WHERE Email = :email
            END
            ELSE
            BEGIN
                -- Kullanıcı yoksa, SIFIRDAN EKLE
                INSERT INTO Kullanicilar (Email, Ad, Cinsiyet, Yas, Boy_cm, Kilo_kg, Hareket_Katsayisi, Hedef_Kalori)
                VALUES (:email, :ad, :cinsiyet, :yas, :boy, :kilo, :hareket, :hedef_kalori)
            END
        """)
        
        conn.execute(sorgu, {
            "email": email, "ad": ad, "cinsiyet": cinsiyet, "yas": yas, "boy": boy_cm, 
            "kilo": kilo_kg, "hareket": hareket_katsayisi, "hedef_kalori": hedef_kalori
        })
        
    return {
        "mesaj": "Profil başarıyla oluşturuldu veya güncellendi.", 
        "hesaplanan_hedef_kalori": hedef_kalori
    }
def alternatif_yemek_bul_ml(eski_yemek_id: int, kategori: str, alerjiler: list, sevilmeyenler: list):
    with engine.connect() as conn:
        # 1. ADIM: İlgili kategorideki tüm yemekleri çek
        # DİKKAT: Veritabanındaki tablo adının "Yemekler" ve "kategori" sütununun adının doğru olduğundan emin ol.
        sorgu = text("SELECT * FROM Yemekler WHERE Kategori = :kategori")
        sonuc = conn.execute(sorgu, {"kategori": kategori})
        yemekler_db = sonuc.fetchall()
        
        if not yemekler_db:
            return {"durum": "Hata", "mesaj": "Bu kategoride uygun alternatif bulunamadı."}

        # 2. ADIM: Pandas DataFrame'e çevir
        sutun_isimleri = sonuc.keys()
        df = pd.DataFrame(yemekler_db, columns=sutun_isimleri)

        # NLP & Filtreleme: Yasaklıları çıkar
        yasaklilar = alerjiler + sevilmeyenler
        for yasakli in yasaklilar:
            # Sütun adı DB'de 'isim' ise 'isim', 'Isim' ise 'Isim' olmalı!
            df = df[~df['Yemek_Adı'].str.contains(yasakli, case=False, na=False)]

        if df.empty:
            return {"durum": "Hata", "mesaj": "Kısıtlamalara uyan alternatif kalmadı."}

        # Eski yemeği bul (Sütun adı 'id' ise küçük harfle)
        eski_yemek_satiri = df[df['Yemek_Id'] == eski_yemek_id]
        if eski_yemek_satiri.empty:
            return {"durum": "Hata", "mesaj": "Orijinal yemek filtreye takıldı veya bulunamadı."}
            
        eski_yemek_index = eski_yemek_satiri.index[0]

        # 3. ADIM: FEATURE EXTRACTION (Özellik Çıkarımı)
        # Sütun isimleri veritabanındaki ile BİREBİR aynı olmalı
        features = df[['Kalori_Kcal', 'Protein_g', 'Karbonhidrat_g', 'Yag_g']].fillna(0)

        # 4. ADIM: NORMALİZASYON
        # Makine öğrenmesi algoritmasının makroları doğru algılaması için ölçeklendirme
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(features)

        # 5. ADIM: MAKİNE ÖĞRENMESİ - KNN (K-Nearest Neighbors) MODELİ
        # Uzaklık metriği olarak 'cosine' (Kosinüs Benzerliği) kullanıyoruz.
        knn_model = NearestNeighbors(n_neighbors=2, metric='cosine', algorithm='brute')
        
        # MODELİ EĞİT (Fit): Yemeklerin uzaydaki yerlerini modele öğret
        knn_model.fit(scaled_features)

        # TAHMİN ET (Predict): Hedef yemeğe uzayda en yakın komşuyu bul
        matris_indeksi = df.index.get_loc(eski_yemek_index)
        hedef_vektor = scaled_features[matris_indeksi].reshape(1, -1)
        mesafeler, indeksler = knn_model.kneighbors(hedef_vektor)

        # indeksler[0][0] yemeğin kendisidir, indeksler[0][1] en iyi alternatiftir
        en_iyi_index_df = indeksler[0][1]
        gercek_index = df.index[en_iyi_index_df]

        # 6. ADIM: Frontend'e Gönderim Formatı
        yeni_yemek = df.loc[gercek_index]

        # Porsiyon birleştirme (İsim ve Birim sütunlarına göre)
        formatli_isim = f"{yeni_yemek['Olcu_Birimi']} {yeni_yemek['Yemek_Adı']}"

        return {
            "durum": "Başarılı",
            "yeni_yemek": {
                "id": int(yeni_yemek["Yemek_Id"]),
                "isim": formatli_isim,
                "kalori": float(yeni_yemek["Kalori_Kcal"]),
                "protein": float(yeni_yemek["Protein_g"]),
                "karb": float(yeni_yemek["Karbonhidrat_g"]),
                "yag": float(yeni_yemek["Yag_g"]),
                "kategori": str(yeni_yemek["Kategori"])
            }
        }
# services.py içine ekle
def aktif_menuyu_kaydet(email: str, diyet_plani: dict):
    import json
    with engine.begin() as conn:
        # Tablo yoksa oluştur
        conn.execute(text("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DiyetKayitlari' and xtype='U')
            CREATE TABLE DiyetKayitlari (
                Id INT IDENTITY(1,1) PRIMARY KEY,
                Email NVARCHAR(255),
                DiyetJSON NVARCHAR(MAX),
                KayitTarihi DATETIME DEFAULT GETDATE()
            )
        """))
        
        # Kullanıcının eski aktif menüsünü temizle (Sadece en güncelini tutmak için)
        conn.execute(text("DELETE FROM DiyetKayitlari WHERE Email = :email"), {"email": email})
        
        # Yeni menüyü JSON olarak kaydet
        conn.execute(text("""
            INSERT INTO DiyetKayitlari (Email, DiyetJSON) 
            VALUES (:email, :json_veri)
        """), {"email": email, "json_veri": json.dumps(diyet_plani)})
    return {"durum": "kaydedildi"}

def aktif_menuyu_getir(email: str):
    import json
    with engine.connect() as conn:
        try:
            # ÖNCE KONTROL: Tablo veritabanında mevcut mu?
            tablo_var_mi = conn.execute(text("SELECT count(*) FROM sysobjects WHERE name='DiyetKayitlari' and xtype='U'")).scalar()
            if tablo_var_mi == 0:
                return None
            
            sorgu = text("SELECT TOP 1 DiyetJSON FROM DiyetKayitlari WHERE Email = :email ORDER BY KayitTarihi DESC")
            sonuc = conn.execute(sorgu, {"email": email}).fetchone()
            if sonuc:
                return json.loads(sonuc[0])
            return None
        except Exception as e:
            print(f"Veri çekme hatası: {e}")
            return None

def kullanici_kontrol_et(email: str):
    with engine.connect() as conn:
        try:
            tablo_var_mi = conn.execute(text("SELECT count(*) FROM sysobjects WHERE name='Kullanicilar' and xtype='U'")).scalar()
            if tablo_var_mi == 0:
                return {"kayitli_mi": False, "durum": "kayitsiz"}
            
            sorgu = text("SELECT Ad, Cinsiyet, Yas, Boy_cm, Kilo_kg, Hareket_Katsayisi, Hedef_Kalori FROM Kullanicilar WHERE Email = :email")
            sonuc = conn.execute(sorgu, {"email": email}).fetchone()
            
            if sonuc:
                return {
                    "kayitli_mi": True,
                    "durum": "kayitli",
                    "ad": sonuc.Ad,
                    "cinsiyet": sonuc.Cinsiyet,
                    "yas": sonuc.Yas,
                    "boy_cm": sonuc.Boy_cm,
                    "kilo_kg": sonuc.Kilo_kg,
                    "hareket_katsayisi": sonuc.Hareket_Katsayisi,
                    "hedef_kalori": sonuc.Hedef_Kalori
                }
            
            return {"kayitli_mi": False, "durum": "kayitsiz"}
        except Exception as e:
            print(f"Kullanici kontrol hatası: {e}")
            return {"kayitli_mi": False, "durum": "hata", "mesaj": str(e)}