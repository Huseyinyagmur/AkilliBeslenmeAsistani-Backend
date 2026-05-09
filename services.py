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
    
    alerjiler = [a.lower() for a in (alerjiler or [])]
    sevilmeyenler = [s.lower() for s in (sevilmeyenler or [])]
    sevilenler = [f.lower() for f in (sevilenler or [])]
    saglik_sorunlari = saglik_sorunlari or []
    diyabet_var_mi = "Diyabet" in saglik_sorunlari or "İnsülin Direnci" in saglik_sorunlari

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
            kat_lower = str(row.Kategori).lower().strip() if row.Kategori else ""
            malzemeler_db = str(row.Baskin_Malzemeler).lower() if row.Baskin_Malzemeler else ""
            alerjen_db = str(row.Alerjen_Bilgisi).lower() if row.Alerjen_Bilgisi else ""

            # 🛑 FİLTRELER (Vegan, Alerjen, Diyabet)
            if diyet_turu == "Vegan" and any(w in isim_lower or w in kat_lower or w in malzemeler_db for w in ["et", "tavuk", "balık", "süt", "peynir", "yoğurt", "yumurta", "kefir", "ayran", "sucuk", "kavurma", "kuzu", "dana", "köfte", "kıyma", "bal", "tereyağ", "tereyag", "krem", "hamsi", "levrek", "somon"]): continue
            if diyet_turu == "Vejetaryen" and any(w in isim_lower or w in kat_lower or w in malzemeler_db for w in ["et", "tavuk", "balık", "sucuk", "kavurma", "kuzu", "dana", "köfte", "hamsi", "somon", "kıyma", "levrek"]): continue
            
            if any(a in alerjen_db for a in alerjiler): continue
            
            yasakli_kelimeler = []
            if "gluten" in alerjiler: yasakli_kelimeler.extend(["ekmek", "ekmeg", "börek", "borek", "simit", "makarna", "erişte", "eriste", "pide", "lavaş", "lavas", "un", "mantı", "manti", "şehriye", "sehriye", "bulgur", "tarhana", "irmik", "bazlama", "yufka", "galeta", "kraker", "pasta", "kek", "krep", "pankek"])
            if "laktoz" in alerjiler: yasakli_kelimeler.extend(["süt", "sut", "peynir", "yoğurt", "yogurt", "kefir", "ayran", "krem", "tereyağ", "tereyag", "cacık", "cacik"])
            if "yer fıstığı" in alerjiler: yasakli_kelimeler.extend(["fıstık", "fistik"])
            if "yumurta" in alerjiler: yasakli_kelimeler.extend(["yumurta", "omlet", "menemen", "çılbır", "cilbir", "krep"])
            if "deniz ürünleri" in alerjiler: yasakli_kelimeler.extend(["balık", "balik", "somon", "hamsi", "levrek", "karides", "kalamar"])
            if "kuruyemiş" in alerjiler: yasakli_kelimeler.extend(["ceviz", "fındık", "findik", "badem", "fıstık", "fistik", "kaju"])
            
            if any(y in isim_lower or y in malzemeler_db for y in yasakli_kelimeler): continue
            if any(s in isim_lower or s in malzemeler_db for s in sevilmeyenler): continue

            if diyabet_var_mi and (kat_lower in ["tatlı", "tatli"] or any(k in isim_lower or k in malzemeler_db for k in ["çikolata", "cikolata", "pasta", "kek", "bal", "reçel", "recel", "pekmez", "şeker", "milkshake", "meyve suyu", "gazoz", "fanta", "kola", "şurup", "surup", "nektar", "tatlısı", "tatlisi"])):
                continue

            skor = random.uniform(1, 100)
            if any(f in isim_lower or f in malzemeler_db for f in sevilenler): skor -= 10000 

            porsiyon = row.Olcu_Birimi if row.Olcu_Birimi else ""
            y_isim = f"{porsiyon} {row.Yemek_Adı}".strip()
            
            # ==========================================
            # 🌟 VERİ ODAKLI HARİTALAMA (Kusursuz)
            # ==========================================
            ozel_kat = "diger"

            # KAHVALTI
            if kat_lower in ["hamur_i̇si", "hamur_isi"]: ozel_kat = "hamur_isi"
            elif kat_lower == "peynir": ozel_kat = "peynir"
            elif kat_lower == "kahvalti_ana": ozel_kat = "kahvalti_ana"
            elif kat_lower in ["kahvalti_yan", "kahvalti_yan "]: ozel_kat = "kahvalti_yan"
            elif kat_lower == "kahvalti": # Geriye kalan tanımlanmamış kahvaltılıklar için cankurtaran
                if any(w in isim_lower for w in ["krep", "pankek", "lapa", "gevrek"]): ozel_kat = "hamur_isi"
                elif any(w in isim_lower for w in ["ezme", "reçel", "kaymak", "tahin", "pekmez", "zeytin"]): ozel_kat = "kahvalti_yan"
                else: ozel_kat = "kahvalti_ana"

            # ÖĞLE / AKŞAM
            elif kat_lower in ["ana_yemek", "fast food"]: ozel_kat = "ana_yemek"
            elif kat_lower == "corba": ozel_kat = "corba"
            elif kat_lower == "karb_yan": ozel_kat = "karb_yan"
            elif "salata_meze" in kat_lower: ozel_kat = "salata_meze"

            # ARA ÖĞÜN VE İÇECEK
            elif kat_lower in ["tatlı", "tatli"]: ozel_kat = "snack_tatli"
            elif kat_lower in ["snack_meyve", "meyve"]: ozel_kat = "snack_meyve"
            elif kat_lower == "snack_kuruyemis": ozel_kat = "snack_kuruyemis"
            elif kat_lower in ["i̇cecek", "icecek"]:
                # İçecek çay/kahve mi yoksa ara öğün soğuk içeceği mi?
                if any(w in isim_lower for w in ["çay", "cay", "kahve", "espresso", "latte", "mocha", "macchiato", "ıhlamur", "adaçayı"]):
                    ozel_kat = "cay_kahve"
                else:
                    ozel_kat = "snack_icecek"
            elif kat_lower in ["atıştırmalık", "atistirmalik"]:
                if "bar" in isim_lower or "kestane" in isim_lower: ozel_kat = "snack_tatli"
                else: ozel_kat = "snack_kuruyemis"

            yemekler.append({
                "id": row.Yemek_Id,
                "isim": y_isim,
                "kalori": float(row.Kalori_Kcal),
                "kategori": row.Kategori,
                "ozel_kategori": ozel_kat,
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
    
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["skor"] for y in yemekler])

    hedef_protein_g = (hedef_kalori * 0.30) / 4
    hedef_karb_g = (hedef_kalori * 0.40) / 4
    hedef_yag_g = (hedef_kalori * 0.30) / 9

    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler]) >= hedef_kalori - 400
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler]) <= hedef_kalori + 400
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["protein"] for y in yemekler]) >= hedef_protein_g - 60
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["karb"] for y in yemekler]) >= hedef_karb_g - 60
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["yag"] for y in yemekler]) >= hedef_yag_g - 40

    # 🚨 DİĞER (ÇÖP) TORBASINI YOK ETME KURALI (Sistem Artık Hata Yapamaz)
    v_diger = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "diger"]
    if v_diger: prob += pulp.lpSum(v_diger) == 0

    # 1. KAHVALTI KURALLARI
    v_hamur = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "hamur_isi"]
    v_peynir = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "peynir"]
    v_cay = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "cay_kahve"]
    v_k_ana = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "kahvalti_ana"]
    v_k_yan = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "kahvalti_yan"]

    prob += pulp.lpSum(v_hamur) <= 1
    prob += pulp.lpSum(v_peynir) <= 1
    prob += pulp.lpSum(v_cay) <= 1
    prob += pulp.lpSum(v_k_ana) <= 2
    prob += pulp.lpSum(v_k_yan) <= 3
    
    prob += pulp.lpSum(v_hamur) + pulp.lpSum(v_peynir) + pulp.lpSum(v_k_ana) + pulp.lpSum(v_k_yan) >= 2
    prob += pulp.lpSum(v_hamur) + pulp.lpSum(v_peynir) + pulp.lpSum(v_k_ana) + pulp.lpSum(v_k_yan) <= 4

    # 2. ÖĞLE VE AKŞAM KURALLARI
    v_ana = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "ana_yemek"]
    v_corba = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "corba"]
    v_karb = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "karb_yan"]
    v_salata = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "salata_meze"]

    prob += pulp.lpSum(v_ana) >= 1
    prob += pulp.lpSum(v_ana) <= 2

    is_high_cal = hedef_kalori >= 2100 
    if is_high_cal:
        prob += pulp.lpSum(v_corba) + pulp.lpSum(v_karb) + pulp.lpSum(v_salata) >= 2
        prob += pulp.lpSum(v_corba) + pulp.lpSum(v_karb) + pulp.lpSum(v_salata) <= 4
        prob += pulp.lpSum(v_corba) <= 2
        prob += pulp.lpSum(v_karb) <= 2
        prob += pulp.lpSum(v_salata) <= 2
    else:
        prob += pulp.lpSum(v_corba) + pulp.lpSum(v_karb) + pulp.lpSum(v_salata) >= 1
        prob += pulp.lpSum(v_corba) + pulp.lpSum(v_karb) + pulp.lpSum(v_salata) <= 3
        prob += pulp.lpSum(v_corba) <= 1
        prob += pulp.lpSum(v_karb) <= 1
        prob += pulp.lpSum(v_salata) <= 2

    # 3. ARA ÖĞÜN KURALLARI
    v_s_icecek = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "snack_icecek"]
    v_s_meyve = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "snack_meyve"]
    v_s_kuru = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "snack_kuruyemis"]
    v_s_tatli = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "snack_tatli"]

    prob += pulp.lpSum(v_s_icecek) + pulp.lpSum(v_s_meyve) + pulp.lpSum(v_s_kuru) + pulp.lpSum(v_s_tatli) >= 1
    prob += pulp.lpSum(v_s_icecek) + pulp.lpSum(v_s_meyve) + pulp.lpSum(v_s_kuru) + pulp.lpSum(v_s_tatli) <= 3
    prob += pulp.lpSum(v_s_icecek) <= 1
    prob += pulp.lpSum(v_s_meyve) <= 2
    prob += pulp.lpSum(v_s_kuru) <= 1
    prob += pulp.lpSum(v_s_tatli) <= 1

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    # --- SONUÇLARI PAKETLEME
    ogunler = { "Sabah": [], "Öğle_ve_Akşam": [], "Ara_Öğün": [] }
    hesap_kal, hesap_prot, hesap_karb, hesap_yag = 0, 0, 0, 0
    
    if pulp.LpStatus[prob.status] == 'Optimal':
        ana_secilen = []
        yan_secilen = []

        sabah_grup = ["hamur_isi", "peynir", "cay_kahve", "kahvalti_ana", "kahvalti_yan"]
        ara_grup = ["snack_icecek", "snack_meyve", "snack_kuruyemis", "snack_tatli"]
        yan_grup = ["corba", "karb_yan", "salata_meze"]

        for y in yemekler:
            if yemek_degiskenleri[y["id"]].varValue > 0:
                kat = y["ozel_kategori"]
                if kat in sabah_grup: ogunler["Sabah"].append(y)
                elif kat in ara_grup: ogunler["Ara_Öğün"].append(y)
                elif kat == "ana_yemek": ana_secilen.append(y)
                elif kat in yan_grup: yan_secilen.append(y)
                
                hesap_kal += y["kalori"]; hesap_prot += y["protein"]
                hesap_karb += y["karb"]; hesap_yag += y["yag"]

        for ana in ana_secilen:
            ogunler["Öğle_ve_Akşam"].append(ana)
            if yan_secilen:
                ogunler["Öğle_ve_Akşam"].append(yan_secilen.pop(0))
            if is_high_cal and yan_secilen:
                ogunler["Öğle_ve_Akşam"].append(yan_secilen.pop(0))
        
        while yan_secilen:
            ogunler["Öğle_ve_Akşam"].append(yan_secilen.pop(0))

        return {
            "durum": "Başarılı",
            "hedef_kalori": hedef_kalori,
            "gerceklesen": {"kalori": round(hesap_kal), "protein_g": round(hesap_prot), "karb_g": round(hesap_karb), "yag_g": round(hesap_yag)},
            "ogunler": ogunler
        }
    return {"durum": "Başarısız", "mesaj": "Kısıtlamalara uygun menü bulunamadı."}

def bmr_ve_kalori_hesapla(cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float, hedef: str):
    if cinsiyet.lower() == "erkek": bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) + 5
    else: bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) - 161
    
    gunluk_harcanan_kalori = bmr * hareket_katsayisi
    if hedef == "Kilo Ver": hedef_kalori = gunluk_harcanan_kalori - 500
    elif hedef == "Kas Yap": hedef_kalori = gunluk_harcanan_kalori + 300
    else: hedef_kalori = gunluk_harcanan_kalori
    return int(hedef_kalori)

def kullanici_kaydet(email: str, ad: str, cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float, hedef: str):
    hedef_kalori = bmr_ve_kalori_hesapla(cinsiyet, yas, boy_cm, kilo_kg, hareket_katsayisi, hedef)
    
    with engine.begin() as conn: 
        conn.execute(text("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Kullanicilar' and xtype='U')
            CREATE TABLE Kullanicilar (
                Kullanici_Id INT IDENTITY(1,1) PRIMARY KEY,
                Email NVARCHAR(255) UNIQUE, 
                Ad NVARCHAR(100), Cinsiyet NVARCHAR(10), Yas INT, Boy_cm FLOAT,
                Kilo_kg FLOAT, Hareket_Katsayisi FLOAT, Hedef_Kalori INT
            )
        """))
        
        sorgu = text("""
            IF EXISTS (SELECT 1 FROM Kullanicilar WHERE Email = :email)
            BEGIN
                UPDATE Kullanicilar 
                SET Ad = :ad, Cinsiyet = :cinsiyet, Yas = :yas, Boy_cm = :boy, 
                    Kilo_kg = :kilo, Hareket_Katsayisi = :hareket, Hedef_Kalori = :hedef_kalori
                WHERE Email = :email
            END
            ELSE
            BEGIN
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
        sorgu = text("SELECT * FROM Yemekler WHERE Kategori = :kategori")
        sonuc = conn.execute(sorgu, {"kategori": kategori})
        yemekler_db = sonuc.fetchall()
        
        if not yemekler_db:
            return {"durum": "Hata", "mesaj": "Bu kategoride uygun alternatif bulunamadı."}

        sutun_isimleri = sonuc.keys()
        df = pd.DataFrame(yemekler_db, columns=sutun_isimleri)

        yasaklilar = alerjiler + sevilmeyenler
        for yasakli in yasaklilar:
            df = df[~df['Yemek_Adı'].str.contains(yasakli, case=False, na=False)]

        if df.empty:
            return {"durum": "Hata", "mesaj": "Kısıtlamalara uyan alternatif kalmadı."}

        eski_yemek_satiri = df[df['Yemek_Id'] == eski_yemek_id]
        if eski_yemek_satiri.empty:
            return {"durum": "Hata", "mesaj": "Orijinal yemek filtreye takıldı veya bulunamadı."}
            
        eski_yemek_index = eski_yemek_satiri.index[0]

        features = df[['Kalori_Kcal', 'Protein_g', 'Karbonhidrat_g', 'Yag_g']].fillna(0)

        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(features)

        knn_model = NearestNeighbors(n_neighbors=2, metric='cosine', algorithm='brute')
        knn_model.fit(scaled_features)

        matris_indeksi = df.index.get_loc(eski_yemek_index)
        hedef_vektor = scaled_features[matris_indeksi].reshape(1, -1)
        mesafeler, indeksler = knn_model.kneighbors(hedef_vektor)

        en_iyi_index_df = indeksler[0][1]
        gercek_index = df.index[en_iyi_index_df]

        yeni_yemek = df.loc[gercek_index]

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

def aktif_menuyu_kaydet(email: str, diyet_plani: dict):
    import json
    with engine.begin() as conn:
        conn.execute(text("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DiyetKayitlari' and xtype='U')
            CREATE TABLE DiyetKayitlari (
                Id INT IDENTITY(1,1) PRIMARY KEY,
                Email NVARCHAR(255),
                DiyetJSON NVARCHAR(MAX),
                KayitTarihi DATETIME DEFAULT GETDATE()
            )
        """))
        
        conn.execute(text("DELETE FROM DiyetKayitlari WHERE Email = :email"), {"email": email})
        
        conn.execute(text("""
            INSERT INTO DiyetKayitlari (Email, DiyetJSON) 
            VALUES (:email, :json_veri)
        """), {"email": email, "json_veri": json.dumps(diyet_plani)})
    return {"durum": "kaydedildi"}

def aktif_menuyu_getir(email: str):
    import json
    with engine.connect() as conn:
        try:
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