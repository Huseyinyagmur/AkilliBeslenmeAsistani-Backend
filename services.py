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
            porsiyon = row.Olcu_Birimi if row.Olcu_Birimi else ""
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
    
    hedef_protein_g = (hedef_kalori * 0.30) / 4
    hedef_karb_g = (hedef_kalori * 0.40) / 4
    hedef_yag_g = (hedef_kalori * 0.30) / 9

    prob = pulp.LpProblem("Ogunlu_Makro_Dengeli_Diyet", pulp.LpMinimize)
    
    # 🌟 YAPAY ZEKANIN SINIF ATLADIĞI YER: Artık Binary değil, Integer! (Max 2 porsiyon)
    yemek_degiskenleri = pulp.LpVariable.dicts("Yemek", [y["id"] for y in yemekler], lowBound=0, upBound=2, cat='Integer')
    prob += 0, "Amac"
    
    # Kalori ve Makro Kısıtları
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

    # 🌟 KATEGORİ KAÇAĞINI ÖNLEYEN YENİ MANTIK
    sabah_kat = ["Kahvalti", "Kahvaltı", "Hamur İsi", "Hamur İşi", "Kahvaltılık"]
    ara_ogun_kat = ["Tatlı", "Tatli", "Meyve", "Atıştırmalık", "Atistirmalik", "İcecek", "İçecek", "Kuruyemis", "Kuruyemiş"]

    sabah_degiskenleri = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat]
    ara_ogun_degiskenleri = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat]
    # Geri kalan HER ŞEY ana öğündür (Çorba, Zeytinyağlı, Ev Yemeği vs. kaçamaz)
    ana_ogun_degiskenleri = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat]

    # --- YENİ KURAL 1: ÖĞÜN KALORİ LİMİTLERİ (Dengeli Dağılım) ---
    sabah_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] in sabah_kat])
    # Kahvaltı günlük kalorinin %20'si ile %35'i arasında olmalı
    prob += sabah_kalori >= hedef_kalori * 0.20, "Min_Sabah_Kalori"
    prob += sabah_kalori <= hedef_kalori * 0.35, "Max_Sabah_Kalori"

    ogle_aksam_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat])
    # Öğle ve Akşam toplamı günlük kalorinin %40'ı ile %60'ı arasında olmalı
    prob += ogle_aksam_kalori >= hedef_kalori * 0.40, "Min_OgleAksam_Kalori"
    prob += ogle_aksam_kalori <= hedef_kalori * 0.60, "Max_OgleAksam_Kalori"

# --- YENİ KURAL 2: AĞIR YEMEKLERDE PORSİYON FRENİ (GÜNCELLENDİ) ---
    for y in yemekler:
        isim_kucuk = y["isim"].lower()
        kategori_kucuk = y["kategori"].lower()
        # Makarna, pilav, patates gibi şeyleri DUBLE (2x) porsiyon yapması KESİNLİKLE yasak!
        if kategori_kucuk in ["fast food", "hamur işi", "hamur isi", "tatlı", "tatli"] or any(k in isim_kucuk for k in ["tost", "pizza", "börek", "pide", "hamburger", "makarna", "pilav", "patates", "mantı"]):
            prob += yemek_degiskenleri[y["id"]] <= 1, f"Max_1_Porsiyon_{y['id']}"

    # --- PORSİYON VE ÇEŞİT KISITLAMALARI ---
    if sabah_degiskenleri:
        prob += pulp.lpSum(sabah_degiskenleri) >= 3, "Min_Sabah_Porsiyon"
        prob += pulp.lpSum(sabah_degiskenleri) <= 5, "Max_Sabah_Porsiyon"

    if ana_ogun_degiskenleri:
        # Porsiyonlar büyüdüğü için çeşitliliği iyice kıstık! (Öğle + Akşam toplamı max 4 parça)
        prob += pulp.lpSum(ana_ogun_degiskenleri) >= 2, "Min_Ana_Ogun_Porsiyon"
        prob += pulp.lpSum(ana_ogun_degiskenleri) <= 4, "Max_Ana_Ogun_Porsiyon"

    if ara_ogun_degiskenleri:
        prob += pulp.lpSum(ara_ogun_degiskenleri) >= 1, "Min_Ara_Ogun_Porsiyon"
        prob += pulp.lpSum(ara_ogun_degiskenleri) <= 2, "Max_Ara_Ogun_Porsiyon"

# --- İNSANİ MANTIK KURALLARI (TİTANYUM YUMRUK) ---
    corbalar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ["Çorba", "Corba"]]
    if corbalar: prob += pulp.lpSum(corbalar) <= 1, "Max_1_Corba"

    tatlilar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ["Tatlı", "Tatli"]]
    if tatlilar: prob += pulp.lpSum(tatlilar) <= 1, "Max_1_Tatli"

    # 1. KAHVALTIDA KALP KRİZİNE SON (Börek, Tost, Pide ve Kızartma aynı anda seçilemez)
    kahvalti_agir = [yemek_degiskenleri[y["id"]] for y in yemekler if any(kelime in y["isim"].lower() for kelime in ["tost", "börek", "borek", "pide", "simit", "açma", "kızartma", "kizartma", "patates"])]
    if kahvalti_agir: prob += pulp.lpSum(kahvalti_agir) <= 1, "Max_1_Kahvalti_Agir"

    # 2. KARBONHİDRAT KOMASINA SON (Aynı gün makarna, pilav, mantı 1'den fazla olamaz)
    agir_karblar = [yemek_degiskenleri[y["id"]] for y in yemekler if any(kelime in y["isim"].lower() for kelime in ["makarna", "pilav", "mantı", "manti"])]
    if agir_karblar: prob += pulp.lpSum(agir_karblar) <= 1, "Max_1_Agir_Karb"
    
    # 3. KASAP ENGELLEYİCİ - GÜNCELLENDİ (Kavurma, Tantuni ve Dürüm kaçakları kapatıldı!)
    kirmizi_etler = [yemek_degiskenleri[y["id"]] for y in yemekler if any(kelime in y["isim"].lower() for kelime in ["köfte", "kofte", "et", "kıyma", "kebap", "döner", "kavurma", "tantuni", "dürüm", "durum"])]
    if kirmizi_etler: prob += pulp.lpSum(kirmizi_etler) <= 1, "Max_1_Kirmizi_Et"

    # 4. GIDAKLAMA ENGELLEYİCİ
    tavuklu_yemekler = [yemek_degiskenleri[y["id"]] for y in yemekler if "tavuk" in y["isim"].lower()]
    if tavuklu_yemekler: prob += pulp.lpSum(tavuklu_yemekler) <= 1, "Max_1_Tavuklu_Yemek"

    # 5. PROTEİN TOZU BAĞIMLILIĞI ÇÖZÜMÜ (Shake ve Barlar sadece 1 porsiyon olabilir)
    ek_gidalar = [yemek_degiskenleri[y["id"]] for y in yemekler if any(k in y["isim"].lower() for k in ["shake", "bar", "tozu"])]
    if ek_gidalar: prob += pulp.lpSum(ek_gidalar) <= 1, "Max_1_Ek_Gida"

    # 6. KÜLTÜREL ÇATIŞMAYI ÖNLE (Bamya ile Pizza, Fast Food ile Sulu Yemek yan yana gelemez!)
    fast_foodlar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ["Fast Food"] or any(k in y["isim"].lower() for k in ["pizza", "burger", "hamburger", "tantuni", "dürüm"])]
    sulu_yemekler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ["Zeytinyağlı", "Sebze Yemeği", "Ev Yemeği"] or any(k in y["isim"].lower() for k in ["bamya", "fasulye", "nohut", "kapuska", "pırasa"])]
    
    # Fast Food'lardan biri seçildiyse, sulu yemeklerin hiçbiri seçilemez (Mutually Exclusive)
    for f in fast_foodlar:
        for s in sulu_yemekler:
            prob += f + s <= 1, f"Uyumsuzluk_{f}_{s}"

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    ogunler = { "Sabah": [], "Öğle_ve_Akşam": [], "Ara_Öğün": [] }
    hesaplanan_kalori, hesaplanan_protein, hesaplanan_karb, hesaplanan_yag = 0.0, 0.0, 0.0, 0.0
    
    if pulp.LpStatus[prob.status] == 'Optimal':
        for y in yemekler:
            secilen_miktar = int(yemek_degiskenleri[y["id"]].varValue) # 0, 1 veya 2 dönecek
            
            if secilen_miktar > 0:
                y_kopya = y.copy() # Referans hatası olmasın diye kopyalıyoruz
                
                # Eğer 2 porsiyon seçtiyse ismin başına "2 x" ekle ve makroları çarp
                if secilen_miktar > 1:
                    y_kopya["isim"] = f"{secilen_miktar} x {y['isim']}"
                
                y_kopya["kalori"] *= secilen_miktar
                y_kopya["protein"] *= secilen_miktar
                y_kopya["karb"] *= secilen_miktar
                y_kopya["yag"] *= secilen_miktar

                # Çoğaltılmış veya tekil yemeği ilgili öğüne ekle
                if y_kopya["kategori"] in sabah_kat:
                    ogunler["Sabah"].append(y_kopya)
                elif y_kopya["kategori"] in ara_ogun_kat:
                    ogunler["Ara_Öğün"].append(y_kopya)
                else:
                    ogunler["Öğle_ve_Akşam"].append(y_kopya)

                hesaplanan_kalori += y_kopya["kalori"]
                hesaplanan_protein += y_kopya["protein"]
                hesaplanan_karb += y_kopya["karb"]
                hesaplanan_yag += y_kopya["yag"]
                
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
        return {"durum": "Başarısız", "mesaj": "Bu hedeflere uygun menü bulunamadı. Lütfen veritabanına daha fazla yemek ekleyin."}

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
            VALUES (:ad, :cinsiyet, :yas, :boy, :kilo, :hareket, :hedef_kalori)
        """)
        conn.execute(sorgu, {
            "ad": ad, "cinsiyet": cinsiyet, "yas": yas, "boy": boy_cm, 
            "kilo": kilo_kg, "hareket": hareket_katsayisi, "hedef_kalori": hedef_kalori
        })
        
    return {
        "mesaj": f"Hoş geldin {ad}! Profilin oluşturuldu.", 
        "hesaplanan_hedef_kalori": hedef_kalori,
        "detay": "Senin için oluşturulan bu kalori hedefini /api/diyet-hazirla uç noktasında kullanabilirsin."
    }