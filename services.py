import pulp
from sqlalchemy import create_engine, text
import urllib

server_adi = 'LAPTOP-V013QBHO' 
veritabani_adi = 'DiyetAppDB' 

params = urllib.parse.quote_plus(
    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
    f'SERVER={server_adi};'
    f'DATABASE={veritabani_adi};'
    f'Trusted_Connection=yes;'
)
engine = create_engine(f'mssql+pyodbc:///?odbc_connect={params}')

def diyet_olustur(hedef_kalori: int):
    yemekler = []
    with engine.connect() as conn:
        # 1. Sütun adını Olcu_Birimi olarak güncelledik
        sorgu = text("""
            SELECT Yemek_Id, Yemek_Adı, Olcu_Birimi, Kalori_Kcal, Kategori, 
                   Protein_g, Karbonhidrat_g, Yag_g 
            FROM Yemekler 
            WHERE Kalori_Kcal IS NOT NULL 
              AND Protein_g IS NOT NULL 
              AND Karbonhidrat_g IS NOT NULL 
              AND Yag_g IS NOT NULL
        """)
        sonuc = conn.execute(sorgu)
        for row in sonuc:
            # 2. Burada da row.Olcu_Birimi olarak çekiyoruz
            porsiyon = row.Olcu_Birimi if row.Olcu_Birimi else ""
            
            # Porsiyon ile ismi birleştir (Örn: "1 Dilim" + " " + "Kaşarlı Tost")
            tam_isim = f"{porsiyon} {row.Yemek_Adı}".strip()

            yemekler.append({
                "id": row.Yemek_Id,
                "isim": tam_isim,
                "kalori": float(row.Kalori_Kcal),
                "kategori": row.Kategori,
                "protein": float(row.Protein_g),
                "karb": float(row.Karbonhidrat_g),
                "yag": float(row.Yag_g)
            })
        
    # Makro Hedefleri (Standart %30 Protein, %40 Karb, %30 Yağ dağılımı)
    hedef_protein_g = (hedef_kalori * 0.30) / 4
    hedef_karb_g = (hedef_kalori * 0.40) / 4
    hedef_yag_g = (hedef_kalori * 0.30) / 9

    prob = pulp.LpProblem("Ogunlu_Makro_Dengeli_Diyet", pulp.LpMinimize)
    yemek_degiskenleri = pulp.LpVariable.dicts("Yemek", [y["id"] for y in yemekler], cat='Binary')
    prob += 0, "Amac"
    
    # 1. ESNEK KALORİ VE MAKRO KISITLARI (Çeşitlilik arttığı için esnekliği açtık)
    toplam_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler])
    prob += toplam_kalori >= hedef_kalori - 250, "Min_Kalori"
    prob += toplam_kalori <= hedef_kalori + 250, "Max_Kalori"

    toplam_protein = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["protein"] for y in yemekler])
    prob += toplam_protein >= hedef_protein_g - 40, "Min_Protein"
    prob += toplam_protein <= hedef_protein_g + 40, "Max_Protein"

    toplam_karb = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["karb"] for y in yemekler])
    prob += toplam_karb >= hedef_karb_g - 40, "Min_Karb"
    prob += toplam_karb <= hedef_karb_g + 40, "Max_Karb"

    toplam_yag = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["yag"] for y in yemekler])
    prob += toplam_yag >= hedef_yag_g - 25, "Min_Yag"
    prob += toplam_yag <= hedef_yag_g + 25, "Max_Yag"

    # 2. KATEGORİ LİSTELERİ (Genişletildi)
    sabah_kat = ["Kahvalti", "Kahvaltı", "Hamur İsi", "Hamur İşi", "Kahvaltılık"]
    ana_ogun_kat = ["Ana Yemek", "Çorba", "Corba", "Fast Food", "Salata", "Meze", "ZeytinYagli", "Zeytinyağlı"]
    ara_ogun_kat = ["Tatlı", "Tatli", "Meyve", "Atıştırmalık", "Atistirmalik", "İcecek", "İçecek", "Kuruyemis", "Kuruyemiş"]

    # Değişkenleri Öğünlere Göre Filtreleme
    sabah_degiskenleri = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat]
    ana_ogun_degiskenleri = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ana_ogun_kat]
    ara_ogun_degiskenleri = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat]

    # 3. YENİ NESİL ÖĞÜN KURALLARI (Mükemmel Tabak Tasarımı)
    
    # KAHVALTI: Serpme mantığı (En az 3, en fazla 5 parça - Örn: Yumurta, Peynir, Zeytin, Ekmek)
    if sabah_degiskenleri:
        prob += pulp.lpSum(sabah_degiskenleri) >= 3, "Min_Sabah_Cesit"
        prob += pulp.lpSum(sabah_degiskenleri) <= 5, "Max_Sabah_Cesit"

    # ÖĞLE VE AKŞAM (Birlikte): Toplamda en az 3, en fazla 6 çeşit (Örn: 2 Ana Yemek, 1 Çorba, 1 Salata vb.)
    if ana_ogun_degiskenleri:
        prob += pulp.lpSum(ana_ogun_degiskenleri) >= 3, "Min_Ana_Ogun_Cesit"
        prob += pulp.lpSum(ana_ogun_degiskenleri) <= 6, "Max_Ana_Ogun_Cesit"

    # ARA ÖĞÜN: En az 1, en fazla 2 parça (Örn: Elma + Kuruyemiş)
    if ara_ogun_degiskenleri:
        prob += pulp.lpSum(ara_ogun_degiskenleri) >= 1, "Min_Ara_Ogun_Cesit"
        prob += pulp.lpSum(ara_ogun_degiskenleri) <= 2, "Max_Ara_Ogun_Cesit"

    # AĞIR YEMEK KONTROLÜ: Günü 1 Ana Yemekle geçiştirmesin, Öğle ve Akşam için toplam 1-2 ağır yemek seçebilsin
    agir_yemekler = [y["id"] for y in yemekler if y["kategori"] in ["Ana Yemek", "Fast Food"]]
    if agir_yemekler:
        prob += pulp.lpSum([yemek_degiskenleri[y_id] for y_id in agir_yemekler]) >= 1, "Min_Bir_Agir_Yemek"
        prob += pulp.lpSum([yemek_degiskenleri[y_id] for y_id in agir_yemekler]) <= 2, "Max_Iki_Agir_Yemek"


    # ----- İNSANİ MANTIK KURALLARI (Saçmalıkları Önleme) -----

    # 1. Günde en fazla 1 Çorba içilsin
    corbalar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ["Çorba", "Corba"]]
    if corbalar:
        prob += pulp.lpSum(corbalar) <= 1, "Max_1_Corba"

    # 2. Ara öğünde 2 tane içecek üst üste verilmesin (Günde max 1 içecek)
    icecekler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ["İcecek", "İçecek"]]
    if icecekler:
        prob += pulp.lpSum(icecekler) <= 1, "Max_1_Icecek"

    # 3. Günde en fazla 1 Tatlı yensin (Şeker komasına girmesin)
    tatlilar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ["Tatlı", "Tatli"]]
    if tatlilar:
        prob += pulp.lpSum(tatlilar) <= 1, "Max_1_Tatli"

    # 4. Ana Yemek yığılmasını önle (Maksimum 2 ağır ana yemek seçilsin - Öğle 1, Akşam 1 gibi)
    ana_yemekler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] == "Ana Yemek"]
    if ana_yemekler:
        prob += pulp.lpSum(ana_yemekler) <= 2, "Max_2_AnaYemek"
        
    # 5. Makarna / Pilav (Karbonhidrat) yığılmasını önle (Öğlen makarna, akşam pilav vermesin)
    # Not: Veritabanında pilav/makarna "Ana Yemek" veya başka kategorideyken, isimden yakalayabiliriz:
    karb_bombalari = [yemek_degiskenleri[y["id"]] for y in yemekler if "Makarna" in y["isim"] or "Pilav" in y["isim"]]
    if karb_bombalari:
        prob += pulp.lpSum(karb_bombalari) <= 1, "Max_1_Pilav_Veya_Makarna"
# 6. Kahvaltıda Hamur İşi / Ekmek Yığılmasını Önle (GELİŞMİŞ TÜRKÇE KONTROLÜ)
    kahvalti_karb = [
        yemek_degiskenleri[y["id"]] for y in yemekler 
        if any(kelime in y["isim"].lower() for kelime in [
            "tost", "börek", "borek", "böreg", "boreg", 
            "pide", "simit", "ekmek", "ekmeg", 
            "açma", "acma", "poğaça", "pogaca", "gözleme"
        ])
    ]
    if kahvalti_karb:
        prob += pulp.lpSum(kahvalti_karb) <= 1, "Max_1_Kahvalti_Hamur_Isi"

    # 7. Yoğurt Türevi Yığılmasını Önle (Öğlen hem Cacık hem Yoğurt vermesin)
    sut_urunleri = [yemek_degiskenleri[y["id"]] for y in yemekler if any(kelime in y["isim"] for kelime in ["Yoğurt", "Yogurt", "Cacık", "Cacik", "Ayran"])]
    if sut_urunleri:
        prob += pulp.lpSum(sut_urunleri) <= 1, "Max_1_Sut_Urunu"

    # 8. Çift Salata Saçmalığını Önle (Ton balıklı salata + Tavuklu salata yan yana gelmesin)
    salatalar = [yemek_degiskenleri[y["id"]] for y in yemekler if "Salata" in y["isim"] or y["kategori"] == "Salata"]
    if salatalar:
        prob += pulp.lpSum(salatalar) <= 1, "Max_1_Salata"
        
    # 9. Peynir Yığılmasını Önle (Kaşar Peyniri + Beyaz Peynir + Tulum Peyniri doldurmasın)
    peynirler = [yemek_degiskenleri[y["id"]] for y in yemekler if "Peynir" in y["isim"]]
    if peynirler:
        prob += pulp.lpSum(peynirler) <= 1, "Max_1_Peynir"
    # ----------------------------------------------------------
    # Modeli Çöz
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    ogunler = {
        "Sabah": [],
        "Öğle_ve_Akşam": [],
        "Ara_Öğün": []
    }
    hesaplanan_kalori, hesaplanan_protein, hesaplanan_karb, hesaplanan_yag = 0.0, 0.0, 0.0, 0.0
    
    if pulp.LpStatus[prob.status] == 'Optimal':
        for y in yemekler:
            if yemek_degiskenleri[y["id"]].varValue == 1.0:
                if y["kategori"] in sabah_kat:
                    ogunler["Sabah"].append(y)
                elif y["kategori"] in ara_ogun_kat:
                    ogunler["Ara_Öğün"].append(y)
                else:
                    ogunler["Öğle_ve_Akşam"].append(y)

                hesaplanan_kalori += y["kalori"]
                hesaplanan_protein += y["protein"]
                hesaplanan_karb += y["karb"]
                hesaplanan_yag += y["yag"]
                
        return {
            "durum": "Başarılı",
            "hedef_kalori": hedef_kalori,
            "gerceklesen": {
                "kalori": round(hesaplanan_kalori, 1),
                "protein_g": round(hesaplanan_protein, 1),
                "karb_g": round(hesaplanan_karb, 1),
                "yag_g": round(hesaplanan_yag, 1)
            },
            "ogunler": ogunler
        }
    else:
        return {"durum": "Başarısız", "mesaj": "Bu kaloriye ve makro hedeflerine uygun mantıklı bir menü bulunamadı."}

def bmr_ve_kalori_hesapla(cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float, hedef: str):
    # Mifflin-St Jeor Formülü
    if cinsiyet.lower() == "erkek":
        bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) + 5
    else:
        bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) - 161
    
    # TDEE (Günlük Harcanan Toplam Kalori)
    gunluk_harcanan_kalori = bmr * hareket_katsayisi
    
    # HEDEFE GÖRE KALORİ MANİPÜLASYONU
    if hedef == "Kilo Ver":
        hedef_kalori = gunluk_harcanan_kalori - 500  # Zayıflamak için 500 kcal açık
    elif hedef == "Kas Yap":
        hedef_kalori = gunluk_harcanan_kalori + 300  # Büyümek için 300 kcal fazlalık
    else:
        hedef_kalori = gunluk_harcanan_kalori # "Kilomu Koru" ise aynı kalır

    return int(hedef_kalori)

# Kullanıcı kaydet fonksiyonuna da 'hedef' parametresini ekliyoruz
def kullanici_kaydet(ad: str, cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float, hedef: str):
    hedef_kalori = bmr_ve_kalori_hesapla(cinsiyet, yas, boy_cm, kilo_kg, hareket_katsayisi, hedef)
    
    # ... (Geri kalan veritabanı kayıt işlemleri aynı kalacak) ...
    
    with engine.begin() as conn: 
        conn.execute(text("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Kullanicilar' and xtype='U')
            CREATE TABLE Kullanicilar (
                Kullanici_Id INT IDENTITY(1,1) PRIMARY KEY,
                Ad NVARCHAR(100),
                Cinsiyet NVARCHAR(10),
                Yas INT,
                Boy_cm FLOAT,
                Kilo_kg FLOAT,
                Hareket_Katsayisi FLOAT,
                Hedef_Kalori INT
            )
        """))
        
        sorgu = text("""
            INSERT INTO Kullanicilar (Ad, Cinsiyet, Yas, Boy_cm, Kilo_kg, Hareket_Katsayisi, Hedef_Kalori)
            VALUES (:ad, :cinsiyet, :yas, :boy, :kilo, :hareket, :hedef)
        """)
        conn.execute(sorgu, {
            "ad": ad, "cinsiyet": cinsiyet, "yas": yas, "boy": boy_cm, 
            "kilo": kilo_kg, "hareket": hareket_katsayisi, "hedef": hedef_kalori
        })
        
    return {
        "mesaj": f"Hoş geldin {ad}! Profilin oluşturuldu.", 
        "hesaplanan_hedef_kalori": hedef_kalori,
        "detay": "Senin için oluşturulan bu kalori hedefini /api/diyet-hazirla uç noktasında kullanabilirsin."
    }