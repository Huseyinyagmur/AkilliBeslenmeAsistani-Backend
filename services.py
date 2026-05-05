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

def diyet_olustur(hedef_kalori: int, alerjiler: list = None, sevilmeyenler: list = None, saglik_sorunlari: list = None, diyet_turu: str = "Standart"):
    
    alerjiler = [a.lower() for a in (alerjiler or [])]
    sevilmeyenler = [s.lower() for s in (sevilmeyenler or [])]
    saglik_sorunlari = saglik_sorunlari or []
    
    diyabet_var_mi = "Diyabet" in saglik_sorunlari or "İnsülin Direnci" in saglik_sorunlari

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
        # 🌟 YENİ: SQL Sorgusuna "Baskin_Malzemeler" ve "Alerjen_Bilgisi" eklendi!
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
            
            # 🌟 YENİ: Veritabanı sütunlarımızı çekip küçük harfe çeviriyoruz
            malzemeler_db = str(row.Baskin_Malzemeler).lower() if row.Baskin_Malzemeler else ""
            alerjen_db = str(row.Alerjen_Bilgisi).lower() if row.Alerjen_Bilgisi else ""

            if diyet_turu == "Vegan" and any(w in isim_lower or w in kat_lower or w in malzemeler_db for w in ["et", "tavuk", "balık", "süt", "peynir", "yoğurt", "yumurta", "kefir", "ayran", "sucuk", "kavurma", "kuzu", "dana", "köfte", "kıyma"]):
                continue
            if diyet_turu == "Vejetaryen" and any(w in isim_lower or w in kat_lower or w in malzemeler_db for w in ["et", "tavuk", "balık", "sucuk", "kavurma", "kuzu", "dana", "köfte", "hamsi", "somon", "kıyma"]):
                continue

            # 🌟 YENİ ALERJİ SÜZGECİ (Önce Alerjen_Bilgisi sütununa bakar)
            alerji_tespit_edildi = False
            for secilen_alerji in alerjiler:
                if secilen_alerji in alerjen_db:  # Direkt veritabanı sütunundan yakalarsa
                    alerji_tespit_edildi = True
                    break
            if alerji_tespit_edildi: continue

            # Alerjiler için kelime bazlı "Çifte Güvenlik" Ağı (Eğer veritabanına girilmemişse diye)
            yasakli_kelimeler = []
            if "gluten" in alerjiler: 
                yasakli_kelimeler.extend(["ekmek", "ekmeg", "börek", "borek", "simit", "makarna", "erişte", "eriste", "pide", "lavaş", "lavas", "un", "mantı", "manti", "şehriye", "sehriye", "bulgur", "tarhana", "irmik", "bazlama", "yufka", "galeta", "kraker", "pasta", "kek", "çerkez", "cerkez"])
            if "laktoz" in alerjiler: 
                yasakli_kelimeler.extend(["süt", "sut", "peynir", "yoğurt", "yogurt", "kefir", "ayran", "krem", "tereyağ", "tereyag", "cacık", "cacik"])
            if "yer fıstığı" in alerjiler: yasakli_kelimeler.extend(["fıstık", "fistik"])
            if "yumurta" in alerjiler: yasakli_kelimeler.extend(["yumurta", "omlet", "menemen", "çılbır", "cilbir"])
            if "deniz ürünleri" in alerjiler: yasakli_kelimeler.extend(["balık", "balik", "somon", "hamsi", "levrek", "karides", "kalamar"])
            if "kuruyemiş" in alerjiler: yasakli_kelimeler.extend(["ceviz", "fındık", "findik", "badem", "fıstık", "fistik"])
            
            # Hem isminde hem de Baskın Malzemeler sütununda bu yasaklı kelimelerden var mı?
            if any(y in isim_lower or y in malzemeler_db for y in yasakli_kelimeler): continue
            
            # 🌟 YENİ SEVİLMEYENLER SÜZGECİ: Direkt Baskın Malzemeler'de arıyor (Örn: Karnıyarık -> Patlıcan)
            if any(s in isim_lower or s in malzemeler_db for s in sevilmeyenler): continue

            # Hastalıklar (Diyabet)
            if diyabet_var_mi and (kat_lower in ["tatlı", "tatli"] or any(k in isim_lower or k in malzemeler_db for k in ["çikolata", "cikolata", "pasta", "kek", "bal", "reçel", "recel", "pekmez", "şeker"])):
                continue

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
    
    if len(yemekler) < 15:
        return {"durum": "Başarısız", "mesaj": "Seçtiğiniz kısıtlamalara uygun veritabanında yeterli yemek kalmadı!"}

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

    sabah_degiskenleri = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat]
    sabah_yumurtalar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and yumurta_mi(y)]
    sabah_hamur = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and hamur_isi_mi(y)]
    sabah_klasikler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and any(k in y["isim"].lower() for k in ["peynir", "zeytin", "domates", "salatalık", "söğüş"])]
    
    sabah_cay = [yemek_degiskenleri[y["id"]] for y in yemekler if "çay" in y["isim"].lower() or "cay" in y["isim"].lower()]
    if sabah_cay: prob += pulp.lpSum(sabah_cay) >= 1

    sabah_yasaklilar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and any(k in y["isim"].lower() for k in ["pide", "lahmacun", "pizza", "hamburger", "döner", "mantı", "manti"])]
    if sabah_yasaklilar: prob += pulp.lpSum(sabah_yasaklilar) == 0

    if sabah_yumurtalar: prob += pulp.lpSum(sabah_yumurtalar) >= 1
    if sabah_hamur: prob += pulp.lpSum(sabah_hamur) == 1
    if sabah_klasikler: prob += pulp.lpSum(sabah_klasikler) >= 1
    
    sabah_peynirler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and "peynir" in y["isim"].lower()]
    sabah_tatlilar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat and any(k in y["isim"].lower() for k in ["bal", "reçel", "recel", "pekmez", "çikolata", "cikolata"])]
    if sabah_peynirler: prob += pulp.lpSum(sabah_peynirler) <= 1
    if sabah_tatlilar: prob += pulp.lpSum(sabah_tatlilar) <= 1
    if sabah_degiskenleri: prob += pulp.lpSum(sabah_degiskenleri) <= 5

    for y in yemekler:
        if y["kategori"] in sabah_kat and "ekmek" not in y["isim"].lower():
            prob += yemek_degiskenleri[y["id"]] <= 1

    ogle_aksam_ana = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat and ana_yemek_mi(y)]
    ogle_aksam_yan_tumu = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat and not ana_yemek_mi(y)]
    
    ogle_aksam_hafif_yan = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat and not ana_yemek_mi(y) and hafif_yan_mi(y)]
    ogle_aksam_agir_karb = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat and not ana_yemek_mi(y) and any(k in y["isim"].lower() for k in ["pilav", "makarna", "patates", "barbunya", "mantı", "manti", "börek", "borek", "erişte", "eriste"])]

    if ogle_aksam_ana: prob += pulp.lpSum(ogle_aksam_ana) == 2
    if ogle_aksam_yan_tumu: prob += pulp.lpSum(ogle_aksam_yan_tumu) == 4 
    if ogle_aksam_hafif_yan: prob += pulp.lpSum(ogle_aksam_hafif_yan) >= 2
    if ogle_aksam_agir_karb: prob += pulp.lpSum(ogle_aksam_agir_karb) <= 2

    tum_makarnalar_mantilar = [yemek_degiskenleri[y["id"]] for y in yemekler if any(k in y["isim"].lower() for k in ["makarna", "mantı", "manti", "erişte", "eriste", "noodle"])]
    if tum_makarnalar_mantilar: prob += pulp.lpSum(tum_makarnalar_mantilar) <= 1
    
    tum_pilavlar = [yemek_degiskenleri[y["id"]] for y in yemekler if "pilav" in y["isim"].lower()]
    if tum_pilavlar: prob += pulp.lpSum(tum_pilavlar) <= 1

    tum_corbalar = [yemek_degiskenleri[y["id"]] for y in yemekler if any(k in y["isim"].lower() for k in ["çorba", "corba"])]
    if tum_corbalar: prob += pulp.lpSum(tum_corbalar) <= 2

    for y in yemekler:
        if y["kategori"] not in sabah_kat and y["kategori"] not in ara_ogun_kat:
            prob += yemek_degiskenleri[y["id"]] <= 1

    ara_meyveler = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat and meyve_kuruyemis_mi(y)]
    ara_icecekler_cay_haric = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat and icecek_mi(y) and "çay" not in y["isim"].lower() and "cay" not in y["isim"].lower()]
    ara_tumu_cay_haric = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat and "çay" not in y["isim"].lower() and "cay" not in y["isim"].lower()]

    tum_tatlilar = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"].lower() in ["tatlı", "tatli"] or any(k in y["isim"].lower() for k in ["dondurma", "tatlı", "tatli", "pasta", "kek", "çikolata", "cikolata", "gofret"])]
    
    if tum_tatlilar: prob += pulp.lpSum(tum_tatlilar) <= 1
    if ara_meyveler: prob += pulp.lpSum(ara_meyveler) >= 1
    if ara_icecekler_cay_haric: prob += pulp.lpSum(ara_icecekler_cay_haric) <= 1
    
    if ara_tumu_cay_haric: prob += pulp.lpSum(ara_tumu_cay_haric) == 2

    baliklar = [yemek_degiskenleri[y["id"]] for y in yemekler if any(k in y["isim"].lower() for k in ["somon", "balık", "balik", "hamsi", "levrek"])]
    if baliklar: prob += pulp.lpSum(baliklar) <= 1

    kirmizi_etler = [yemek_degiskenleri[y["id"]] for y in yemekler if any(k in y["isim"].lower() for k in ["köfte", "kofte", "et", "kıyma", "kiyma", "kebap", "döner", "doner", "kavurma", "tantuni", "dürüm", "durum", "kokoreç", "kokorec", "iskender", "kuzu", "beyti", "biftek", "antrikot"])]
    if kirmizi_etler: prob += pulp.lpSum(kirmizi_etler) <= 1

    fast_food = [yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ["Fast Food"] or any(k in y["isim"].lower() for k in ["pizza", "burger", "tantuni", "kokoreç", "kokorec", "dürüm", "durum", "iskender"])]
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
                
                if "yulaf" in y_kopya["isim"].lower() and "lapa" in y_kopya["isim"].lower():
                    if "laktoz" in alerjiler:
                        y_kopya["isim"] = f"{y_kopya['isim']} (Su veya Bitkisel Süt ile)"
                    else:
                        y_kopya["isim"] = f"{y_kopya['isim']} (Süt ile)"

                y_kopya["kalori"] *= secilen_miktar
                y_kopya["protein"] *= secilen_miktar
                y_kopya["karb"] *= secilen_miktar
                y_kopya["yag"] *= secilen_miktar

                if y_kopya["kategori"] in sabah_kat: 
                    ogunler["Sabah"].append(y_kopya)
                elif "çay" in y_kopya["isim"].lower() or "cay" in y_kopya["isim"].lower():
                    if not any("çay" in s["isim"].lower() or "cay" in s["isim"].lower() for s in ogunler["Sabah"]):
                        ogunler["Sabah"].append(y_kopya) 
                    else:
                        ogunler["Ara_Öğün"].append(y_kopya) 
                elif y_kopya["kategori"] in ara_ogun_kat: 
                    ogunler["Ara_Öğün"].append(y_kopya)
                else:
                    if ana_yemek_mi(y_kopya): ogle_aksam_ana_secilen.append(y_kopya)
                    else: ogle_aksam_yan_secilen.append(y_kopya)

                hesaplanan_kalori += y_kopya["kalori"]
                hesaplanan_protein += y_kopya["protein"]
                hesaplanan_karb += y_kopya["karb"]
                hesaplanan_yag += y_kopya["yag"]
                
        hafif_yanlar = [y for y in ogle_aksam_yan_secilen if hafif_yan_mi(y)]
        diger_yanlar = [y for y in ogle_aksam_yan_secilen if not hafif_yan_mi(y)]

        ogle_yanlari = []
        aksam_yanlari = []

        if hafif_yanlar: ogle_yanlari.append(hafif_yanlar.pop(0))
        if hafif_yanlar: aksam_yanlari.append(hafif_yanlar.pop(0))

        kalan_yanlar = diger_yanlar + hafif_yanlar
        if kalan_yanlar: ogle_yanlari.append(kalan_yanlar.pop(0))
        if kalan_yanlar: aksam_yanlari.append(kalan_yanlar.pop(0))

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
        return {"durum": "Başarısız", "mesaj": "Bu hedeflere uygun menü bulunamadı. Lütfen kısıtlamalarınızı azaltın veya veritabanına yeni yemekler ekleyin."}

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