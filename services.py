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
    # --- YARDIMCI KATEGORİ FONKSİYONLARI ---
    def ana_yemek_mi(y):
        k, i = y["kategori"].lower(), y["isim"].lower()
        if k in ["ana yemek", "fast food"]: return True
        return any(w in i for w in ["et ", "etli", "tavuk", "balık", "somon", "köfte", "kofte", "kıyma", "kavurma", "tantuni", "kebap", "döner", "pizza", "burger", "hamburger", "şiş", "hamsi", "levrek", "şnitzel", "kokoreç", "ciğer", "kuzu", "dana"])

    def yumurta_mi(y): return any(w in y["isim"].lower() for w in ["yumurta", "omlet", "menemen", "çılbır", "sahanda"])
    def hamur_isi_mi(y): return any(w in y["isim"].lower() for w in ["ekmek", "ekmeg", "börek", "borek", "böreg", "boreg", "pide", "simit", "açma", "poğaça", "tost", "lavaş", "bazlama", "yulaf", "gevrek"])
    
    # 🌟 İÇECEK KALKANI (Süt, Maden Suyu, Şişe, Bardak, Kutu eklendi!) 🌟
    def icecek_mi(y): 
        k, i = y["kategori"].lower(), y["isim"].lower()
        if "içecek" in k or "icecek" in k: return True
        return any(w in i for w in [
            "su", "shake", "nektar", "ayran", "kahve", "çay", "cay", 
            "soda", "kola", "fanta", "gazoz", "milkshake", "meyve suyu", 
            "kefir", "limonata", "şalgam", "ice tea", "süt", "maden suyu",
            "şişe", "bardak", "kutu", "kupa", "fincan", "shaker"
        ])

    # 🌟 MEYVE/KURUYEMİŞ KALKANI (İçecekse anında reddeder) 🌟
    def meyve_kuruyemis_mi(y): 
        if icecek_mi(y): return False # Şişe, Kutu veya Sıvı olan HİÇBİR ŞEY meyve sayılamaz!
        
        k, i = y["kategori"].lower(), y["isim"].lower()
        if k in ["meyve", "kuruyemiş", "kuruyemis"]: return True
        return any(w in i for w in ["fıstık", "badem", "ceviz", "elma", "muz", "kuru", "hurma", "incir", "kayısı", "leblebi", "meyve", "fındık", "mandalina", "portakal", "çilek", "kavun", "karpuz"])
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
    # 🌟 1. RASTGELELİK EKLENDİ (Hep aynı yemeği verme sorununu çözer!) 🌟
    # prob += 0, "Amac"  <-- Eski sıfır amacını SİL, yerine alttakini yaz:
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * random.uniform(0.1, 1.0) for y in yemekler]), "Amac_Rastgele_Cesitlilik"
    # ... (Yukarıdaki kısımlar aynı) ...

    # Makro kısıtlamaları (prob += pulp.lpSum...) bittikten sonraki kısım:

    sabah_kat = ["Kahvalti", "Kahvaltı", "Hamur İsi", "Hamur İşi", "Kahvaltılık"]
    ara_ogun_kat = ["Tatlı", "Tatli", "Meyve", "Atıştırmalık", "Atistirmalik", "İcecek", "İçecek", "Kuruyemis", "Kuruyemiş"]

    # 🌟 BURASI YENİ YERİMİZ: Kategoriler tanımlandıktan SONRA bu 3 kuralı koyuyoruz! 🌟
    
    # 1. RASTGELELİK EKLENDİ
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * random.uniform(0.1, 1.0) for y in yemekler]), "Amac_Rastgele_Cesitlilik"

    # 2. ARA ÖĞÜN KALORİ FRENİ (Artık ara_ogun_kat listesini tanıyor!)
    ara_ogun_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] in ara_ogun_kat])
    prob += ara_ogun_kalori <= hedef_kalori * 0.15, "Max_Ara_Ogun_Kalori"

    # 3. ÇİFTE BALIK YASAĞI
    baliklar = [yemek_degiskenleri[y["id"]] for y in yemekler if any(k in y["isim"].lower() for k in ["somon", "balık", "hamsi", "levrek"])]
    if baliklar: prob += pulp.lpSum(baliklar) <= 1, "Max_1_Balik_Gunluk"

    # 🌟 ÖĞÜN KALORİ DAĞILIMI (Bunlar zaten vardı, altında durmaya devam etsin) 🌟
    sabah_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] in sabah_kat])
    prob += sabah_kalori >= hedef_kalori * 0.15, "Min_Sabah_Kalori"
    prob += sabah_kalori <= hedef_kalori * 0.35, "Max_Sabah_Kalori"
    
    # ... (Kodun geri kalanı aynı şekilde devam ediyor) ...
    # 🌟 2. ARA ÖĞÜN KALORİ FRENİ (Katmer faciasını önler) 🌟
    ara_ogun_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] in ara_ogun_kat])
    prob += ara_ogun_kalori <= hedef_kalori * 0.15, "Max_Ara_Ogun_Kalori"

    # 🌟 3. ÇİFTE BALIK YASAĞI (Öğlen Somon, Akşam Hamsi yasak!) 🌟
    baliklar = [yemek_degiskenleri[y["id"]] for y in yemekler if any(k in y["isim"].lower() for k in ["somon", "balık", "hamsi", "levrek"])]
    if baliklar: prob += pulp.lpSum(baliklar) <= 1, "Max_1_Balik_Gunluk"    
    # Kalori ve Makro Kısıtları
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler]) >= hedef_kalori - 250
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler]) <= hedef_kalori + 250

    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["protein"] for y in yemekler]) >= hedef_protein_g - 40
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["protein"] for y in yemekler]) <= hedef_protein_g + 40

    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["karb"] for y in yemekler]) >= hedef_karb_g - 40
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["karb"] for y in yemekler]) <= hedef_karb_g + 40

    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["yag"] for y in yemekler]) >= hedef_yag_g - 25
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["yag"] for y in yemekler]) <= hedef_yag_g + 25

    sabah_kat = ["Kahvalti", "Kahvaltı", "Hamur İsi", "Hamur İşi", "Kahvaltılık"]
    ara_ogun_kat = ["Tatlı", "Tatli", "Meyve", "Atıştırmalık", "Atistirmalik", "İcecek", "İçecek", "Kuruyemis", "Kuruyemiş"]

    # 🌟 ÖĞÜN KALORİ DAĞILIMI (Geri Geldi!) 🌟
    # Bu kural sayesinde yapay zeka kahvaltıyı 1000 kalori yapıp diğer öğünleri aç bırakamaz!
    sabah_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] in sabah_kat])
    prob += sabah_kalori >= hedef_kalori * 0.15, "Min_Sabah_Kalori"
    prob += sabah_kalori <= hedef_kalori * 0.35, "Max_Sabah_Kalori"

    ogle_aksam_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat])
    prob += ogle_aksam_kalori >= hedef_kalori * 0.45, "Min_OgleAksam_Kalori"
    prob += ogle_aksam_kalori <= hedef_kalori * 0.75, "Max_OgleAksam_Kalori"

    # --- 1. KAHVALTI ZORUNLULUKLARI VE KISITLAMALARI ---
    sabah_degiskenleri = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat]
    sabah_yumurtalar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and yumurta_mi(y)]
    sabah_hamur = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and hamur_isi_mi(y)]
    sabah_peynirler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and "peynir" in y["isim"].lower()]
    sabah_tatlilar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and any(k in y["isim"].lower() for k in ["bal", "reçel", "recel", "pekmez", "çikolata"])]
    
    # Demir Yumruk Kuralları:
    if sabah_yumurtalar: prob += pulp.lpSum(sabah_yumurtalar) >= 1, "Kesin_Min_1_Yumurta"
    if sabah_hamur: prob += pulp.lpSum(sabah_hamur) == 1, "Kesin_1_Cesit_Ekmek_Borek" # SADECE 1 çeşit hamur işi (Ekmek veya Börek)
    if sabah_peynirler: prob += pulp.lpSum(sabah_peynirler) <= 1, "Max_1_Cesit_Peynir" # 2 Çeşit peynir yasak
    if sabah_tatlilar: prob += pulp.lpSum(sabah_tatlilar) <= 1, "Max_1_Cesit_Tatli" # Reçel ve Bal aynı anda yasak
    if sabah_degiskenleri: prob += pulp.lpSum(sabah_degiskenleri) <= 5, "Max_5_Kalem_Kahvalti" # Menü kalabalık olmasın

    # Kahvaltıda "Duble Porsiyon (2x)" Yasağı (Sadece Ekmek 2 dilim olabilir, menemen/reçel olamaz)
    for y in yemekler:
        if y["kategori"] in sabah_kat and "ekmek" not in y["isim"].lower():
            prob += yemek_degiskenleri[y["id"]] <= 1, f"Sabah_Duble_Yasak_{y['id']}"

    # --- 2. ÖĞLE VE AKŞAM (Tam 2 Ana Yemek, Tam 2 Yan Yemek Kesin Kuralı) ---
    ogle_aksam_ana = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat and ana_yemek_mi(y)]
    ogle_aksam_yan = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat and not ana_yemek_mi(y)]
    
    if ogle_aksam_ana: prob += pulp.lpSum(ogle_aksam_ana) == 2, "Kesin_2_Ana_Yemek"
    if ogle_aksam_yan: prob += pulp.lpSum(ogle_aksam_yan) == 2, "Kesin_2_Yan_Yemek"

    # Öğle ve Akşam Yemeklerinde Duble Porsiyon (2x) Kesinlikle Yasak!
    for y in yemekler:
        if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat:
            prob += yemek_degiskenleri[y["id"]] <= 1, f"OgleAksam_Duble_Yasak_{y['id']}"

    # --- 3. ARA ÖĞÜN ZORUNLULUKLARI (Meyve/Kuruyemiş Şart, Sadece Sıvı Yasak) ---
    ara_meyveler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat and meyve_kuruyemis_mi(y)]
    ara_icecekler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat and icecek_mi(y)]
    ara_tumu = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat]

    if ara_meyveler: prob += pulp.lpSum(ara_meyveler) >= 1, "Kesin_Min_1_Meyve_Kuruyemis"
    if ara_icecekler: prob += pulp.lpSum(ara_icecekler) <= 1, "Max_1_Icecek"
    if ara_tumu: prob += pulp.lpSum(ara_tumu) <= 2, "Max_2_Ara_Ogun_Parca"

    # --- 4. AĞIRLIK FRENLERİ (Sıkıcı diyet kuralları) ---
    kirmizi_etler = [yemek_degiskenleri[y["id"]] for y in yemekler if any(k in y["isim"].lower() for k in ["köfte", "et", "kıyma", "kebap", "döner", "kavurma", "tantuni", "dürüm", "kokoreç"])]
    if kirmizi_etler: prob += pulp.lpSum(kirmizi_etler) <= 1, "Max_1_Kirmizi_Et"
    
    agir_karblar = [yemek_degiskenleri[y["id"]] for y in yemekler if any(kelime in y["isim"].lower() for kelime in ["makarna", "pilav", "mantı", "manti", "patates"])]
    if agir_karblar: prob += pulp.lpSum(agir_karblar) <= 1, "Max_1_Agir_Karb"

    fast_food = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ["Fast Food"] or any(k in y["isim"].lower() for k in ["pizza", "burger", "tantuni", "kokoreç", "dürüm"])]
    if fast_food: prob += pulp.lpSum(fast_food) <= 1, "Max_1_FastFood" # Günde sadece 1 defa kaçamak!

    corbalar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ["Çorba", "Corba"]]
    if corbalar: prob += pulp.lpSum(corbalar) <= 1, "Max_1_Corba"

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

                if y_kopya["kategori"] in sabah_kat: ogunler["Sabah"].append(y_kopya)
                elif y_kopya["kategori"] in ara_ogun_kat: ogunler["Ara_Öğün"].append(y_kopya)
                else:
                    if ana_yemek_mi(y_kopya): ogle_aksam_ana_secilen.append(y_kopya)
                    else: ogle_aksam_yan_secilen.append(y_kopya)

                hesaplanan_kalori += y_kopya["kalori"]
                hesaplanan_protein += y_kopya["protein"]
                hesaplanan_karb += y_kopya["karb"]
                hesaplanan_yag += y_kopya["yag"]
                
        # FERMUAR(ZIPPER) SİSTEMİ 
        ogle_aksam_birlestirilmis = []
        max_len = max(len(ogle_aksam_ana_secilen), len(ogle_aksam_yan_secilen))
        for i in range(max_len):
            if i < len(ogle_aksam_ana_secilen): ogle_aksam_birlestirilmis.append(ogle_aksam_ana_secilen[i])
            if i < len(ogle_aksam_yan_secilen): ogle_aksam_birlestirilmis.append(ogle_aksam_yan_secilen[i])
            
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