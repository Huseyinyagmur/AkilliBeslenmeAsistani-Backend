import pulp
from sqlalchemy import create_engine, text
import urllib
import random

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
    alerjiler = [a.lower() for a in (alerjiler or [])]
    sevilmeyenler = [s.lower() for s in (sevilmeyenler or [])]
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
        # Sebze ve zeytinyağlıları da buraya alabilir veya ayrı tutabiliriz. Çorba/Salata/Yoğurt odaklı bırakıyoruz.
        return any(w in i for w in ["çorba", "corba", "salata", "yoğurt", "yogurt", "cacık", "ayran", "yeşillik", "piyaz", "tarator"])

    yemekler = []
    with engine.connect() as conn:
        # SORGUMUZA ALERJEN VE MALZEME SÜTUNLARINI DA EKLİYORUZ
        sorgu = text("""
            SELECT Yemek_Id, Yemek_Adı, Olcu_Birimi, Kalori_Kcal, Kategori, 
                   Protein_g, Karbonhidrat_g, Yag_g, Alerjen_Bilgisi, Baskin_Malzemeler, Diyet_Turu 
            FROM Yemekler 
            WHERE Kalori_Kcal IS NOT NULL AND Protein_g IS NOT NULL AND Karbonhidrat_g IS NOT NULL AND Yag_g IS NOT NULL
        """)
        sonuc = conn.execute(sorgu)
        for row in sonuc:
            isim_lower = str(row.Yemek_Adı).lower()
            alerjenler_db = str(row.Alerjen_Bilgisi).lower() if row.Alerjen_Bilgisi else ""
            malzemeler_db = str(row.Baskin_Malzemeler).lower() if row.Baskin_Malzemeler else ""
            diyet_db = str(row.Diyet_Turu).lower() if row.Diyet_Turu else ""

            # 🛑 1. DİYET TÜRÜ FİLTRESİ
            if diyet_turu == "Vegan" and "vegan" not in diyet_db: continue
            if diyet_turu == "Vejetaryen" and diyet_db not in ["vegan", "vejetaryen"]: continue
            
            # 🛑 2. ALERJİ FİLTRESİ (Alerjen listesinde veya isminde geçiyorsa YASAKLA)
            if any(a in alerjenler_db or a in isim_lower or a in malzemeler_db for a in alerjiler): continue
            
            # 🛑 3. SEVİLMEYENLER FİLTRESİ (Malzemelerde veya isminde varsa YASAKLA)
            if any(s in isim_lower or s in malzemeler_db for s in sevilmeyenler): continue

            # 🛑 4. SAĞLIK SORUNU (Örn: Diyabet varsa Tatlı kategorisini komple çöpe at)
            if diyabet_var_mi and row.Kategori in ["Tatlı", "Tatli"]: continue

            # Eğer tüm güvenlik filtrelerinden geçtiyse, yapay zekanın havuzuna ekle:
            porsiyon = row.Olcu_Birimi if row.Olcu_Birimi else ""
            yemekler.append({
                "id": row.Yemek_Id,
                "isim": f"{porsiyon} {row.Yemek_Adı}".strip(),
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
    yemek_degiskenleri = pulp.LpVariable.dicts("Yemek", [y["id"] for y in yemekler], lowBound=0, upBound=2, cat='Integer')
    
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * random.uniform(1, 100) for y in yemekler]), "Amac_Rastgele_Cesitlilik"

    sabah_kat = ["Kahvalti", "Kahvaltı", "Hamur İsi", "Hamur İşi", "Kahvaltılık"]
    ara_ogun_kat = ["Tatlı", "Tatli", "Meyve", "Atıştırmalık", "Atistirmalik", "İcecek", "İçecek", "Kuruyemis", "Kuruyemiş"]

    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler]) >= hedef_kalori - 250
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler]) <= hedef_kalori + 250
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["protein"] for y in yemekler]) >= hedef_protein_g - 60
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["protein"] for y in yemekler]) <= hedef_protein_g + 60
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["karb"] for y in yemekler]) >= hedef_karb_g - 60
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["karb"] for y in yemekler]) <= hedef_karb_g + 60
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["yag"] for y in yemekler]) >= hedef_yag_g - 35
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["yag"] for y in yemekler]) <= hedef_yag_g + 35

    sabah_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] in sabah_kat])
    prob += sabah_kalori >= hedef_kalori * 0.15
    prob += sabah_kalori <= hedef_kalori * 0.35

    ogle_aksam_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat])
    prob += ogle_aksam_kalori >= hedef_kalori * 0.45
    prob += ogle_aksam_kalori <= hedef_kalori * 0.75

    ara_ogun_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] in ara_ogun_kat])
    prob += ara_ogun_kalori <= hedef_kalori * 0.15

    # --- TÜRK KAHVALTISI STANDARDI ---
    sabah_degiskenleri = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat]
    sabah_yumurtalar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and yumurta_mi(y)]
    sabah_hamur = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and hamur_isi_mi(y)]
    sabah_klasikler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and any(k in y["isim"].lower() for k in ["peynir", "zeytin", "domates", "salatalık", "söğüş"])]
    
    sabah_cay = [yemek_degiskenleri[y["id"]] for y in yemekler if "çay" in y["isim"].lower()]
    if sabah_cay: prob += pulp.lpSum(sabah_cay) >= 1

    sabah_yasaklilar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and any(k in y["isim"].lower() for k in ["pide", "lahmacun", "pizza", "hamburger", "döner", "mantı"])]
    if sabah_yasaklilar: prob += pulp.lpSum(sabah_yasaklilar) == 0

    if sabah_yumurtalar: prob += pulp.lpSum(sabah_yumurtalar) >= 1
    if sabah_hamur: prob += pulp.lpSum(sabah_hamur) == 1
    if sabah_klasikler: prob += pulp.lpSum(sabah_klasikler) >= 1
    
    sabah_peynirler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and "peynir" in y["isim"].lower()]
    sabah_tatlilar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and any(k in y["isim"].lower() for k in ["bal", "reçel", "recel", "pekmez", "çikolata"])]
    if sabah_peynirler: prob += pulp.lpSum(sabah_peynirler) <= 1
    if sabah_tatlilar: prob += pulp.lpSum(sabah_tatlilar) <= 1
    if sabah_degiskenleri: prob += pulp.lpSum(sabah_degiskenleri) <= 5

    for y in yemekler:
        if y["kategori"] in sabah_kat and "ekmek" not in y["isim"].lower():
            prob += yemek_degiskenleri[y["id"]] <= 1

    # 🌟 KUSURSUZ LOKANTA/TABLDOT STANDARDI (Öğle & Akşam 3'er Çeşit) 🌟
    ogle_aksam_ana = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat and ana_yemek_mi(y)]
    ogle_aksam_yan_tumu = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat and not ana_yemek_mi(y)]
    
    # Hafif Yan Yemekler: Çorba, Salata, Yoğurt, Meze havuzu
    ogle_aksam_hafif_yan = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat and not ana_yemek_mi(y) and hafif_yan_mi(y)]
    
    # Ağır Karbonhidratlar havuzu
    ogle_aksam_agir_karb = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat and not ana_yemek_mi(y) and any(k in y["isim"].lower() for k in ["pilav", "makarna", "patates", "barbunya", "mantı", "börek", "erişte"])]

    # Kesin Kurallar: Tam 2 Ana Yemek, Tam 4 Yan Yemek ve EN AZ 2 Hafif Yan!
    if ogle_aksam_ana: prob += pulp.lpSum(ogle_aksam_ana) == 2, "Kesin_2_Ana_Yemek"
    if ogle_aksam_yan_tumu: prob += pulp.lpSum(ogle_aksam_yan_tumu) == 4, "Kesin_4_Yan_Yemek" 
    if ogle_aksam_hafif_yan: prob += pulp.lpSum(ogle_aksam_hafif_yan) >= 2, "Kesin_Min_2_Corba_Salata"
    if ogle_aksam_agir_karb: prob += pulp.lpSum(ogle_aksam_agir_karb) <= 2, "Max_2_Agir_Karb"

    # Çifte Makarna / Çifte Pilav Rezaletine Son!
    tum_makarnalar = [yemek_degiskenleri[y["id"]] for y in yemekler if "makarna" in y["isim"].lower()]
    if tum_makarnalar: prob += pulp.lpSum(tum_makarnalar) <= 1, "Max_1_Makarna"
    tum_pilavlar = [yemek_degiskenleri[y["id"]] for y in yemekler if "pilav" in y["isim"].lower()]
    if tum_pilavlar: prob += pulp.lpSum(tum_pilavlar) <= 1, "Max_1_Pilav"

    for y in yemekler:
        if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat:
            prob += yemek_degiskenleri[y["id"]] <= 1

    # --- ARA ÖĞÜN VE DONDURMA KISITLAMASI ---
    ara_meyveler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat and meyve_kuruyemis_mi(y)]
    ara_icecekler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat and icecek_mi(y)]
    ara_tumu = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat]

    tum_tatlilar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"].lower() in ["tatlı", "tatli"] or any(k in y["isim"].lower() for k in ["dondurma", "tatlı", "pasta", "kek", "çikolata", "gofret"])]
    if tum_tatlilar: prob += pulp.lpSum(tum_tatlilar) <= 1
    if ara_meyveler: prob += pulp.lpSum(ara_meyveler) >= 1
    if ara_icecekler: prob += pulp.lpSum(ara_icecekler) <= 1
    if ara_tumu: prob += pulp.lpSum(ara_tumu) == 2

    # --- AĞIRLIK FRENLERİ ---
    baliklar = [yemek_degiskenleri[y["id"]] for y in yemekler if any(k in y["isim"].lower() for k in ["somon", "balık", "hamsi", "levrek"])]
    if baliklar: prob += pulp.lpSum(baliklar) <= 1

    kirmizi_etler = [yemek_degiskenleri[y["id"]] for y in yemekler if any(k in y["isim"].lower() for k in ["köfte", "et", "kıyma", "kebap", "döner", "kavurma", "tantuni", "dürüm", "kokoreç", "iskender", "kuzu", "beyti", "biftek", "antrikot"])]
    if kirmizi_etler: prob += pulp.lpSum(kirmizi_etler) <= 1

    fast_food = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ["Fast Food"] or any(k in y["isim"].lower() for k in ["pizza", "burger", "tantuni", "kokoreç", "dürüm", "iskender"])]
    if fast_food: prob += pulp.lpSum(fast_food) <= 1

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    ogunler = { "Sabah": [], "Öğle_ve_Akşam": [], "Ara_Öğün": [] }
    hesaplanan_kalori, hesaplanan_protein, hesaplanan_karb, hesaplanan_yag = 0.0, 0.0, 0.0, 0.0
    
    if pulp.LpStatus[prob.status] == 'Optimal':
        ogle_aksam_ana_secilen = []
        ogle_aksam_yan_secilen = []

        for y in yemekler:
            secilen_miktar = int(yemek_degiskenleri[y["id"]].varValue)
            if secilen_miktar > 0:
                y_kopya = y.copy()
                if secilen_miktar > 1: y_kopya["isim"] = f"{secilen_miktar} x {y['isim']}"
                y_kopya["kalori"] *= secilen_miktar
                y_kopya["protein"] *= secilen_miktar
                y_kopya["karb"] *= secilen_miktar
                y_kopya["yag"] *= secilen_miktar

                if y_kopya["kategori"] in sabah_kat or "çay" in y_kopya["isim"].lower(): 
                    ogunler["Sabah"].append(y_kopya)
                elif y_kopya["kategori"] in ara_ogun_kat: 
                    ogunler["Ara_Öğün"].append(y_kopya)
                else:
                    if ana_yemek_mi(y_kopya): ogle_aksam_ana_secilen.append(y_kopya)
                    else: ogle_aksam_yan_secilen.append(y_kopya)

                hesaplanan_kalori += y_kopya["kalori"]
                hesaplanan_protein += y_kopya["protein"]
                hesaplanan_karb += y_kopya["karb"]
                hesaplanan_yag += y_kopya["yag"]
                
        # 🌟 ZEKİ DAĞITICI: Her Öğüne Kesinlikle 1 Hafif (Çorba/Salata) + 1 Ekstra (Makarna/Pilav/Zeytinyağlı) 🌟
        hafif_yanlar = [y for y in ogle_aksam_yan_secilen if hafif_yan_mi(y)]
        diger_yanlar = [y for y in ogle_aksam_yan_secilen if not hafif_yan_mi(y)]

        ogle_yanlari = []
        aksam_yanlari = []

        # 1. Aşama: Her öğüne banko 1 Hafif Yan koy
        if hafif_yanlar: ogle_yanlari.append(hafif_yanlar.pop(0))
        if hafif_yanlar: aksam_yanlari.append(hafif_yanlar.pop(0))

        # 2. Aşama: Kalan 2 yan yemeği öğünlere paylaştır
        kalan_yanlar = diger_yanlar + hafif_yanlar
        if kalan_yanlar: ogle_yanlari.append(kalan_yanlar.pop(0))
        if kalan_yanlar: aksam_yanlari.append(kalan_yanlar.pop(0))

        # 3. Aşama: Öğünleri "Ana Yemek + 1. Yan + 2. Yan" şeklinde birleştir
        ogle_aksam_birlestirilmis = []
        if len(ogle_aksam_ana_secilen) > 0:
            ogle_aksam_birlestirilmis.append(ogle_aksam_ana_secilen[0])
            ogle_aksam_birlestirilmis.extend(ogle_yanlari)
            
        if len(ogle_aksam_ana_secilen) > 1:
            ogle_aksam_birlestirilmis.append(ogle_aksam_ana_secilen[1])
            ogle_aksam_birlestirilmis.extend(aksam_yanlari)
            
        ogunler["Öğle_ve_Akşam"] = ogle_aksam_birlestirilmis

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
# ... Alt kısımdaki BMR ve Kayıt fonksiyonları olduğu gibi kalıyor.
def bmr_ve_kalori_hesapla(cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float, hedef: str):
    if cinsiyet.lower() == "erkek": bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) + 5
    else: bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) - 161
    
    gunluk_harcanan_kalori = bmr * hareket_katsayisi
    if hedef == "Kilo Ver": hedef_kalori = gunluk_harcanan_kalori - 500
    elif hedef == "Kas Yap": hedef_kalori = gunluk_harcanan_kalori + 300
    else: hedef_kalori = gunluk_harcanan_kalori
    return int(hedef_kalori)

def kullanici_kaydet(ad: str, cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float, hedef: str):
    hedef_kalori = bmr_ve_kalori_hesapla(cinsiyet, yas, boy_cm, kilo_kg, hareket_katsayisi, hedef)
    with engine.begin() as conn: 
        conn.execute(text("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Kullanicilar' and xtype='U')
            CREATE TABLE Kullanicilar (
                Kullanici_Id INT IDENTITY(1,1) PRIMARY KEY,
                Ad NVARCHAR(100), Cinsiyet NVARCHAR(10), Yas INT, Boy_cm FLOAT,
                Kilo_kg FLOAT, Hareket_Katsayisi FLOAT, Hedef_Kalori INT
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