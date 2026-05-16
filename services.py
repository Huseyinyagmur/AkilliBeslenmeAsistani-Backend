import pulp
from sqlalchemy import create_engine, text
import urllib
import random
import pandas as pd
from pathlib import Path
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
    f'Encrypt=no;'
    f'TrustServerCertificate=yes;'
)
engine = create_engine(f'mssql+pyodbc:///?odbc_connect={params}')

BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR / "dataset_fixed.xlsx"
DB_KULLANILABILIR = True


class AttrDict(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc


def yemekleri_kaynaktan_getir(sorgu, haric_tutulacak_idler):
    global DB_KULLANILABILIR
    if DB_KULLANILABILIR:
        try:
            with engine.connect() as conn:
                sonuc = conn.execute(sorgu)
                return [AttrDict(row._mapping) for row in sonuc]
        except Exception as e:
            DB_KULLANILABILIR = False
            print(f"Veritabanına bağlanılamadı, Excel veri seti kullanılacak: {e}")

    df = pd.read_excel(DATASET_PATH)
    df = df[
        df["Kalori_Kcal"].notna()
        & df["Protein_g"].notna()
        & df["Karbonhidrat_g"].notna()
        & df["Yag_g"].notna()
    ]
    if haric_tutulacak_idler:
        df = df[~df["Yemek_Id"].isin(haric_tutulacak_idler)]
    return [AttrDict(record) for record in df.to_dict(orient="records")]


def normalize_tr(metin: str) -> str:
    if not metin: return ""
    return str(metin).lower().replace('ı', 'i').replace('ö', 'o').replace('ü', 'u').replace('ç', 'c').replace('ş', 's').replace('ğ', 'g')


def diyet_olustur(hedef_kalori: int, alerjiler: list = None, sevilmeyenler: list = None, saglik_sorunlari: list = None, diyet_turu: str = "Standart", sevilenler: list = None, haric_tutulacak_idler: list = None, yasakli_kategoriler: list = None, ai_data: dict = None, yasakli_ozel_kategoriler: list = None):
    
    goal = ai_data.get('goal', 'koruma') if ai_data else 'koruma'
    yasakli_ozel_kategoriler = yasakli_ozel_kategoriler or []
    
    if ai_data and ai_data.get('age') and ai_data.get('weight') and ai_data.get('height') and ai_data.get('gender'):
        age = ai_data['age']
        weight = ai_data['weight']
        height = ai_data['height']
        gender = ai_data['gender']
        activity_level = ai_data.get('activity_level') or 'hareketsiz'
        goal = ai_data.get('goal') or 'koruma'

        if gender.lower() == 'erkek':
            bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
        else:
            bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161

        activity_multipliers = {
            'hareketsiz': 1.2,
            'az_hareketli': 1.375,
            'orta': 1.55,
            'cok_hareketli': 1.725
        }
        tdee = bmr * activity_multipliers.get(activity_level, 1.2)

        if goal == 'kilo_verme':
            hedef_kalori = int(tdee - 500)
        elif goal == 'kilo_alma':
            hedef_kalori = int(tdee + 500)
        else:
            hedef_kalori = int(tdee)
    
    alerjiler = [a.lower() for a in (alerjiler or [])]
    sevilmeyenler = [s.lower() for s in (sevilmeyenler or [])]
    sevilenler = [f.lower() for f in (sevilenler or [])]
    
    alerjiler_norm = [normalize_tr(a) for a in alerjiler]
    sevilmeyenler_norm = [normalize_tr(s) for s in sevilmeyenler]
    
    saglik_sorunlari = saglik_sorunlari or []
    if ai_data and ai_data.get('health_conditions'):
        saglik_sorunlari.extend(ai_data.get('health_conditions'))
    saglik_sorunlari_lower = [str(s).lower() for s in saglik_sorunlari]
    diyabet_var_mi = any(w in s for s in saglik_sorunlari_lower for w in ["diyabet", "diabetic", "insülin", "insulin"])

    haric_tutulacak_idler = haric_tutulacak_idler or []
    haric_str = ", ".join(map(str, haric_tutulacak_idler)) if haric_tutulacak_idler else "-1"

    yasakli_kategoriler = yasakli_kategoriler or []
    kategori_sart = ""
    if yasakli_kategoriler:
        yasakli_str = ", ".join([f"'{k}'" for k in yasakli_kategoriler])
        kategori_sart = f"AND Kategori NOT IN ({yasakli_str})"

    sorgu = text(f"""
        SELECT Yemek_Id, Yemek_Adı, Olcu_Birimi, Kalori_Kcal, Kategori, 
               Protein_g, Karbonhidrat_g, Yag_g, Baskin_Malzemeler, Alerjen_Bilgisi, Diyet_Turu
        FROM Yemekler 
        WHERE Kalori_Kcal IS NOT NULL AND Protein_g IS NOT NULL AND Karbonhidrat_g IS NOT NULL AND Yag_g IS NOT NULL
        AND Yemek_Id NOT IN ({haric_str})
        {kategori_sart}
    """)

    yemekler = []
    for row in yemekleri_kaynaktan_getir(sorgu, haric_tutulacak_idler):
        if True:
            isim_lower = str(row.Yemek_Adı).lower()
            kat_lower = str(row.Kategori).lower().strip() if row.Kategori else ""
            malzemeler_db = str(row.Baskin_Malzemeler).lower() if row.Baskin_Malzemeler else ""
            alerjen_db = str(row.Alerjen_Bilgisi).lower() if row.Alerjen_Bilgisi else ""
            diyet_turu_db = str(row.Diyet_Turu).lower() if hasattr(row, 'Diyet_Turu') and row.Diyet_Turu else ""

            isim_norm = normalize_tr(isim_lower)
            malz_norm = normalize_tr(malzemeler_db)

            # 🛑 1. DİYET TÜRÜ FİLTRESİ (Veritabanı Odaklı)
            if diyet_turu.lower() == "vegan" and diyet_turu_db != "vegan": continue
            if diyet_turu.lower() == "vejetaryen" and diyet_turu_db not in ["vegan", "vejetaryen"]: continue
            
            # 🛑 2. ALERJİ FİLTRESİ (Genişletilmiş Alt Metin Araması)
            if any(a in isim_norm or a in malz_norm for a in alerjiler_norm): continue
            
            # 🛑 3. ÖZEL SAKATAT FİLTRESİ
            if "sakatat" in sevilmeyenler:
                if "sakatat" in kat_lower or any(k in malzemeler_db or k in isim_lower for k in ["işkembe", "kelle", "paça", "ciğer", "yürek", "dil","kokoreç"]):
                    continue

            # Sevilmeyenler
            if any(s in isim_norm or s in malz_norm for s in sevilmeyenler_norm): continue

            skor = random.uniform(1, 100)
            if any(f in isim_lower or f in malzemeler_db for f in sevilenler): skor -= 1000

            porsiyon = row.Olcu_Birimi if row.Olcu_Birimi else ""
            y_isim = f"{porsiyon} {row.Yemek_Adı}".strip()
            
            # 🌟 VERİ ODAKLI HARİTALAMA
            ozel_kat = "diger"
            if kat_lower in ["hamur_i̇si", "hamur_isi"]: ozel_kat = "hamur_isi"
            elif kat_lower == "peynir": ozel_kat = "peynir"
            elif kat_lower == "kahvalti_ana": ozel_kat = "kahvalti_ana"
            elif kat_lower in ["kahvalti_yan", "kahvalti_yan "]: ozel_kat = "kahvalti_yan"
            elif kat_lower == "kahvalti": 
                if any(w in isim_lower for w in ["krep", "pankek", "lapa", "gevrek"]): ozel_kat = "hamur_isi"
                elif any(w in isim_lower for w in ["ezme", "reçel", "kaymak", "tahin", "pekmez", "zeytin"]): ozel_kat = "kahvalti_yan"
                else: ozel_kat = "kahvalti_ana"
            elif kat_lower in ["ana_yemek", "fast food"]: ozel_kat = "ana_yemek"
            elif kat_lower == "corba": ozel_kat = "corba"
            elif kat_lower == "karb_yan": ozel_kat = "karb_yan"
            elif "salata_meze" in kat_lower: ozel_kat = "salata_meze"
            elif kat_lower in ["tatlı", "tatli"]: ozel_kat = "snack_tatli"
            elif kat_lower in ["snack_meyve", "meyve"]: ozel_kat = "snack_meyve"
            elif kat_lower == "snack_kuruyemis": ozel_kat = "snack_kuruyemis"
            elif kat_lower in ["i̇cecek", "icecek"]:
                if any(w in isim_lower for w in ["çay", "cay", "kahve", "espresso", "latte", "mocha", "macchiato", "ıhlamur", "adaçayı"]): ozel_kat = "cay_kahve"
                else: ozel_kat = "snack_icecek"
            elif kat_lower in ["atıştırmalık", "atistirmalik"]:
                if "bar" in isim_lower or "kestane" in isim_lower: ozel_kat = "snack_tatli"
                else: ozel_kat = "snack_kuruyemis"

            # 🚨 AŞAMA 1: KATEGORİK FİLTRELEME (PRE-FILTERING / KATEGORİ DUVARI)
            if ozel_kat in yasakli_ozel_kategoriler:
                continue

            if diyabet_var_mi:
                if kat_lower in ["tatlı", "tatli"] or ozel_kat == "snack_tatli": continue
                if any(x in malzemeler_db for x in ["şeker", "çikolata", "şurup", "bal"]): continue
                
            # hedef_kalori < 2200 ise goal verisinden bağımsız tüm zararlılar droplanır
            if goal == "kilo_verme" or (hedef_kalori is not None and hedef_kalori < 2200):
                kat_clean = str(row.Kategori).strip().lower()
                if kat_clean == "tatlı" or kat_clean == "fast food" or ozel_kat == "snack_tatli" or "fast food" in kat_lower or "kola" in isim_lower or "milkshake" in isim_lower:
                    continue

            yemekler.append({
                "id": row.Yemek_Id,
                "isim": y_isim,
                "kalori": float(row.Kalori_Kcal),
                "kategori": row.Kategori,
                "ozel_kategori": ozel_kat,
                "protein": float(row.Protein_g),
                "karb": float(row.Karbonhidrat_g),
                "yag": float(row.Yag_g),
                "malzemeler": malzemeler_db,
                "skor": skor
            })
    
    if len(yemekler) < 15: return {"durum": "Başarısız", "mesaj": "Kısıtlamalara uygun yeterli yemek kalmadı."}

    prob = pulp.LpProblem("Ogunlu_Diyet_Plani", pulp.LpMinimize)
    yemek_degiskenleri = pulp.LpVariable.dicts("Yemek", [y["id"] for y in yemekler], 0, 1, cat='Integer')
    
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["skor"] for y in yemekler])

    # 1. MAKRO VE KALORİ KISITLARI (Esnek Toleranslar)
    hedef_protein_g = (hedef_kalori * 0.30) / 4
    hedef_karb_g = (hedef_kalori * 0.40) / 4
    hedef_yag_g = (hedef_kalori * 0.30) / 9

    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler]) >= hedef_kalori * 0.90
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler]) <= hedef_kalori * 1.10
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["protein"] for y in yemekler]) >= hedef_protein_g - 60
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["karb"] for y in yemekler]) >= hedef_karb_g - 60
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] * y["yag"] for y in yemekler]) >= hedef_yag_g - 40

    # 2. ÇÖP KATEGORİ KISITI
    v_diger = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "diger"]
    if v_diger: prob += pulp.lpSum(v_diger) == 0

    # 1. KAHVALTI (Esnek Korumalı Şablon)
    v_k_ana = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "kahvalti_ana"]
    v_k_yan = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] in ["kahvalti_yan", "peynir"]]
    v_hamur = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "hamur_isi"]
    v_cay = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "cay_kahve"]

    prob += pulp.lpSum(v_k_ana) <= 1 # 1 olmak zorunda değil, 0 da olabilir
    prob += pulp.lpSum(v_hamur) <= 1 
    prob += pulp.lpSum(v_cay) <= 1
    
    # Toplam kahvaltı çeşidi (ana + yan ürünler) en az 2, en fazla 4 olacak
    v_tum_kahvalti = v_k_ana + v_k_yan + v_hamur + v_cay
    prob += pulp.lpSum(v_tum_kahvalti) >= 2
    prob += pulp.lpSum(v_tum_kahvalti) <= 4

    # 4. ÖĞLE VE AKŞAM YEMEĞİ ŞABLONU (Kati Kurallar)
    v_ana_yemek = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "ana_yemek"]
    v_yan_urun = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] in ["corba", "salata_meze", "karb_yan"]]
    
    # Toplam: Öğle(1 Ana, 1 Yan) + Akşam(1 Ana, 2 Yan)
    prob += pulp.lpSum(v_ana_yemek) == 2 # 1 Öğle, 1 Akşam
    prob += pulp.lpSum(v_yan_urun) == 3  # 1 Öğle, 2 Akşam

    # Ekstra Sınırlar (Çorba ve Karbonhidrat Patlamasını Engellemek İçin)
    v_corba = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "corba"]
    v_salata = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "salata_meze"]
    v_karb_yan = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] == "karb_yan"]
    
    # Akşam Yemeği Çeşitliliği: Seçilen yan ürünler KESİNLİKLE farklı kategorilerden olmalı
    prob += pulp.lpSum(v_corba) <= 1
    prob += pulp.lpSum(v_salata) <= 1
    prob += pulp.lpSum(v_karb_yan) <= 1

    # 5. ARA ÖĞÜN ŞABLONU (Kati Kurallar)
    v_ara_ogun_tum = [yemek_degiskenleri[y["id"]] for y in yemekler if y["ozel_kategori"] in ["snack_icecek", "snack_meyve", "snack_kuruyemis", "snack_tatli"]]
    prob += pulp.lpSum(v_ara_ogun_tum) >= 1
    prob += pulp.lpSum(v_ara_ogun_tum) <= 2

    # 6. ÖĞÜN KALORİ DENGE KURALLARI (Kalori Uçurumunu Engelleme)
    sabah_kat_listesi = ["hamur_isi", "peynir", "cay_kahve", "kahvalti_ana", "kahvalti_yan"]
    ara_kat_listesi = ["snack_icecek", "snack_meyve", "snack_kuruyemis", "snack_tatli"]
    ogle_aksam_listesi = ["ana_yemek", "corba", "karb_yan", "salata_meze"]

    sabah_kalorisi = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["ozel_kategori"] in sabah_kat_listesi])
    ara_ogun_kalorisi = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["ozel_kategori"] in ara_kat_listesi])
    ogle_aksam_kalorisi = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler if y["ozel_kategori"] in ogle_aksam_listesi])

    prob += sabah_kalorisi <= hedef_kalori * 0.40 # Sabah max 40%
    prob += ara_ogun_kalorisi <= hedef_kalori * 0.15 # Ara öğün limit
    prob += ogle_aksam_kalorisi <= hedef_kalori * 0.90 # Toplam Öğle ve Akşam limiti (0.45 * 2 = 0.90)

    # ========================================================
    # 🚨 7. ANTİ-SPAM VE ÇEŞİTLİLİK KURALLARI (Data-Driven)
    # ========================================================
    # İçinde "makarna", "erişte" vb. geçenleri malzeme sütunundan bul
    v_makarnalar = [yemek_degiskenleri[y["id"]] for y in yemekler if "makarna" in y["malzemeler"] or "erişte" in y["malzemeler"]]
    # İçinde "pirinç", "bulgur", "pilav" vb. geçenleri malzeme sütunundan bul
    v_pilavlar = [yemek_degiskenleri[y["id"]] for y in yemekler if "pirinç" in y["malzemeler"] or "pilav" in y["malzemeler"] or "bulgur" in y["malzemeler"]]
    
    # Protein Anti-Spam: Aynı protein kaynağından üst üste verilmesini engelle
    v_tavuklar = [yemek_degiskenleri[y["id"]] for y in yemekler if "tavuk" in y["malzemeler"]]
    v_kirmizietler = [yemek_degiskenleri[y["id"]] for y in yemekler if "kırmızı et" in y["malzemeler"] or "kıyma" in y["malzemeler"]]
    v_baliklar = [yemek_degiskenleri[y["id"]] for y in yemekler if "balık" in y["malzemeler"] or "somon" in y["malzemeler"] or "balık" in y["isim"].lower() or "somon" in y["isim"].lower()]

    if v_makarnalar: prob += pulp.lpSum(v_makarnalar) <= 1
    if v_pilavlar: prob += pulp.lpSum(v_pilavlar) <= 1
    if v_tavuklar: prob += pulp.lpSum(v_tavuklar) <= 1
    if v_kirmizietler: prob += pulp.lpSum(v_kirmizietler) <= 1
    if v_baliklar: prob += pulp.lpSum(v_baliklar) <= 1

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    # 🚨 AŞAMA 3: ÇÖZÜM KONTROLÜ (INFEASIBLE HANDLING)
    if pulp.LpStatus[prob.status] != 'Optimal':
        return {"durum": "Başarısız", "mesaj": "Bu kısıtlamalara ve kalori hedefine uygun, kuralları ihlal etmeyen bir menü bulunamadı."}
    
    # --- SONUÇLARI PAKETLEME
    ogunler = { "Sabah": [], "Öğle": [], "Akşam": [], "Ara_Öğün": [] }
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

        # Kati Şablon Dağılımı: Öğle (1 Ana, 1 Yan), Akşam (1 Ana, 2 Yan)
        if len(ana_secilen) >= 2:
            ogunler["Öğle"].append(ana_secilen[0])
            ogunler["Akşam"].append(ana_secilen[1])
        else: # Güvenlik yedeği
            for y in ana_secilen:
                if len(ogunler["Öğle"]) == 0: ogunler["Öğle"].append(y)
                else: ogunler["Akşam"].append(y)

        for y in yan_secilen:
            if len(ogunler["Öğle"]) < 2: # 1 ana zaten eklendi, 1 yan daha eklenince toplam 2 olur
                ogunler["Öğle"].append(y)
            else:
                ogunler["Akşam"].append(y)

        return {
            "durum": "Başarılı",
            "hedef_kalori": hedef_kalori,
            "gerceklesen": {"kalori": round(hesap_kal), "protein_g": round(hesap_prot), "karb_g": round(hesap_karb), "yag_g": round(hesap_yag)},
            "ogunler": ogunler
        }
    return {"durum": "Başarısız", "mesaj": "Kısıtlamalara uygun menü bulunamadı."}

def haftalik_diyet_olustur(hedef_kalori: int, alerjiler: list = None, sevilmeyenler: list = None, saglik_sorunlari: list = None, diyet_turu: str = "Standart", sevilenler: list = None, ai_data: dict = None):
    gunler = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    haftalik_plan = {}
    kullanilan_ana_yemekler = []
    karb_sayaci = 0
    hamur_isi_sayaci = 0

    saglik_sorunlari_lower = [str(s).lower() for s in (saglik_sorunlari or [])]
    if ai_data and ai_data.get('health_conditions'):
        saglik_sorunlari_lower.extend([str(s).lower() for s in ai_data.get('health_conditions')])
    diyabet_var_mi = any(w in s for s in saglik_sorunlari_lower for w in ["diyabet", "diabetic", "insülin", "insulin"])

    for gun in gunler:
        basarili = False
        deneme_sayisi = 0
        
        yasakli_kat = []
        yasakli_ozel_kat = []
        if karb_sayaci >= 2:
            yasakli_kat = ["Karb_Yan", "karb_yan"]
            
        if diyabet_var_mi and hamur_isi_sayaci >= 2:
            yasakli_ozel_kat.append("hamur_isi")

        while not basarili and deneme_sayisi < 2:
            sonuc = diyet_olustur(hedef_kalori, alerjiler, sevilmeyenler, saglik_sorunlari, diyet_turu, sevilenler, haric_tutulacak_idler=kullanilan_ana_yemekler, yasakli_kategoriler=yasakli_kat, ai_data=ai_data, yasakli_ozel_kategoriler=yasakli_ozel_kat)
            
            if sonuc["durum"] == "Başarılı":
                haftalik_plan[gun] = {
                    "ogunler": sonuc["ogunler"],
                    "gerceklesen": sonuc["gerceklesen"]
                }
                
                gun_icinde_karb_var = False

                for ogun_adi, ogun_yemekleri in sonuc["ogunler"].items():
                    for y in ogun_yemekleri:
                        kat = y.get("ozel_kategori", "")
                        isim = y.get("isim", "").lower()
                        is_su = isim == "su" or isim.endswith(" su")
                        is_cay_kahve = kat == "cay_kahve"
                        
                        if not is_cay_kahve and not is_su:
                            kullanilan_ana_yemekler.append(y["id"])
                        
                        if kat == "karb_yan":
                            gun_icinde_karb_var = True
                            
                        if kat == "hamur_isi":
                            hamur_isi_sayaci += 1
                
                if gun_icinde_karb_var:
                    karb_sayaci += 1
                
                basarili = True
            else:
                kullanilan_ana_yemekler = []
                deneme_sayisi += 1
                
        if not basarili:
            return {"durum": "Başarısız", "mesaj": "Kısıtlamalarınıza uygun 7 günlük menü kombinasyonu bulunamadı. Lütfen kısıtlamaları biraz esnetin."}

    return {"durum": "Başarılı", "haftalik_plan": haftalik_plan}
def haftalik_diyet_olustur(hedef_kalori: int, alerjiler: list = None, sevilmeyenler: list = None, saglik_sorunlari: list = None, diyet_turu: str = "Standart", sevilenler: list = None, ai_data: dict = None):
    basarisiz_cevap = {
        "durum": "Başarısız",
        "mesaj": "Mevcut veri havuzu ile belirttiğiniz sağlık koşulları ve alerjiler birleştirildiğinde haftalık menü oluşturulamadı. Lütfen kısıtlamalarınızı azaltın."
    }

    gunler = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    slot_to_ogun = {
        "kahvalti": "Sabah",
        "ogle_ana": "Öğle",
        "ogle_yan": "Öğle",
        "aksam_ana": "Akşam",
        "aksam_yan": "Akşam",
        "ara": "Ara_Öğün",
    }
    slotlar = list(slot_to_ogun.keys())

    def norm(value):
        text = str(value or "").lower()
        return (
            text.replace("ı", "i").replace("ö", "o").replace("ü", "u").replace("ç", "c").replace("ş", "s").replace("ğ", "g")
            .replace("İ", "i").replace("Ö", "o").replace("Ü", "u").replace("Ç", "c").replace("Ş", "s").replace("Ğ", "g")
            .replace("�", "i").replace("i̇", "i")
        )

    def kolon_bul(df, adaylar):
        kolon_haritasi = {norm(k): k for k in df.columns}
        for aday in adaylar:
            bulunan = kolon_haritasi.get(norm(aday))
            if bulunan:
                return bulunan
        return adaylar[0]

    def ozel_kategori_bul(kategori, isim):
        kat = norm(kategori).strip()
        ad = norm(isim)
        if kat in ["hamur_isi", "hamur isi", "hamurisi"]:
            return "hamur_isi"
        if kat == "peynir":
            return "peynir"
        if kat == "kahvalti_ana":
            return "kahvalti_ana"
        if kat in ["kahvalti_yan", "kahvalti yan"]:
            return "kahvalti_yan"
        if kat == "kahvalti":
            if any(w in ad for w in ["krep", "pankek", "lapa", "gevrek"]):
                return "hamur_isi"
            if any(w in ad for w in ["ezme", "recel", "kaymak", "tahin", "pekmez", "zeytin"]):
                return "kahvalti_yan"
            return "kahvalti_ana"
        if kat in ["ana_yemek", "ana yemek"]:
            return "ana_yemek"
        if kat == "fast food":
            return "fast_food"
        if kat == "corba":
            return "corba"
        if kat == "karb_yan":
            return "karb_yan"
        if "salata_meze" in kat:
            return "salata_meze"
        if kat == "tatli":
            return "snack_tatli"
        if kat in ["snack_meyve", "meyve"]:
            return "meyve"
        if kat == "snack_kuruyemis":
            return "snack_kuruyemis"
        if kat in ["icecek", "içecek"]:
            return "icecek"
        if kat in ["atistirmalik", "atıştırmalık"]:
            return "snack_tatli" if any(w in ad for w in ["bar", "kestane"]) else "snack_kuruyemis"
        return "diger"

    def deger(row, kolon, varsayilan=""):
        value = row.get(kolon, varsayilan)
        if pd.isna(value):
            return varsayilan
        return value

    goal = ai_data.get("goal", "koruma") if ai_data else "koruma"
    if ai_data and ai_data.get("age") and ai_data.get("weight") and ai_data.get("height") and ai_data.get("gender"):
        age = ai_data["age"]
        weight = ai_data["weight"]
        height = ai_data["height"]
        gender = ai_data["gender"]
        activity_level = ai_data.get("activity_level") or "hareketsiz"
        goal = ai_data.get("goal") or "koruma"

        if str(gender).lower() == "erkek":
            bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
        else:
            bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161

        activity_multipliers = {
            "hareketsiz": 1.2,
            "az_hareketli": 1.375,
            "orta": 1.55,
            "cok_hareketli": 1.725,
            "çok_hareketli": 1.725,
        }
        tdee = bmr * activity_multipliers.get(activity_level, 1.2)
        if goal == "kilo_verme":
            hedef_kalori = int(tdee - 500)
        elif goal == "kilo_alma":
            hedef_kalori = int(tdee + 500)
        else:
            hedef_kalori = int(tdee)

    if hedef_kalori < 1200:
        hedef_kalori = 1200

    alerjiler = [norm(a) for a in (alerjiler or []) if str(a).strip()]
    sevilmeyenler = [norm(s) for s in (sevilmeyenler or []) if str(s).strip()]
    sevilenler = [norm(s) for s in (sevilenler or []) if str(s).strip()]
    exclude_es_anlamlilar = {
        "balik": ["balik", "somon", "hamsi", "ton baligi", "levrek", "cipura", "uskumru", "deniz urunleri"],
        "deniz urunleri": ["deniz urunleri", "balik", "somon", "hamsi", "karides", "midye", "kalamar"],
        "tavuk": ["tavuk", "pilic", "hindi"],
        "et": ["et", "kirmizi et", "kebap", "sarkuteri", "sakatat", "kiyma", "kavurma", "sucuk", "sosis", "pastirma", "ciger", "doner", "dana", "kuzu", "burger", "hamburger", "cheeseburger", "kofte", "tantuni", "lahmacun", "manti"],
        "kirmizi et": ["et", "kirmizi et", "kebap", "sarkuteri", "sakatat", "kiyma", "kavurma", "sucuk", "sosis", "pastirma", "ciger", "doner", "dana", "kuzu", "burger", "hamburger", "cheeseburger", "kofte", "tantuni", "lahmacun", "manti"],
        "sakatat": ["sakatat", "iskembe", "kelle", "paca", "ciger", "yurek", "dil", "kokorec"],
    }
    genisletilmis_sevilmeyenler = []
    for kelime in sevilmeyenler:
        genisletilmis_sevilmeyenler.extend(exclude_es_anlamlilar.get(kelime, [kelime]))
    sevilmeyenler = list(dict.fromkeys(genisletilmis_sevilmeyenler))
    saglik_sorunlari = list(saglik_sorunlari or [])
    if ai_data and ai_data.get("health_conditions"):
        saglik_sorunlari.extend(ai_data.get("health_conditions"))
    saglik_norm = [norm(s) for s in saglik_sorunlari]
    diyabet_var_mi = any(w in s for s in saglik_norm for w in ["diyabet", "diabetic", "insulin", "insulin direnci"])

    sorgu = text("""
        SELECT Yemek_Id, Yemek_Adı, Olcu_Birimi, Kalori_Kcal, Kategori,
               Protein_g, Karbonhidrat_g, Yag_g, Baskin_Malzemeler, Alerjen_Bilgisi, Diyet_Turu
        FROM Yemekler
        WHERE Kalori_Kcal IS NOT NULL AND Protein_g IS NOT NULL AND Karbonhidrat_g IS NOT NULL AND Yag_g IS NOT NULL
    """)
    satirlar = yemekleri_kaynaktan_getir(sorgu, [])
    if not satirlar:
        return basarisiz_cevap

    df = pd.DataFrame([dict(row) for row in satirlar])
    yemek_id_col = kolon_bul(df, ["Yemek_Id"])
    isim_col = kolon_bul(df, ["Yemek_Adı", "Yemek_Adi"])
    olcu_col = kolon_bul(df, ["Olcu_Birimi", "Ölçü_Birimi"])
    kalori_col = kolon_bul(df, ["Kalori_Kcal"])
    kategori_col = kolon_bul(df, ["Kategori"])
    protein_col = kolon_bul(df, ["Protein_g"])
    karb_col = kolon_bul(df, ["Karbonhidrat_g"])
    yag_col = kolon_bul(df, ["Yag_g", "Yağ_g"])
    malzeme_col = kolon_bul(df, ["Baskin_Malzemeler", "Baskın_Malzemeler"])
    alerjen_col = kolon_bul(df, ["Alerjen_Bilgisi"])
    diyet_col = kolon_bul(df, ["Diyet_Turu", "Diyet_Türü"])

    for col in [kalori_col, protein_col, karb_col, yag_col]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=[yemek_id_col, isim_col, kalori_col, protein_col, karb_col, yag_col]).copy()
    if df.empty:
        return basarisiz_cevap

    df["isim_norm"] = df[isim_col].map(norm)
    df["kategori_norm"] = df[kategori_col].map(norm)
    df["malzeme_norm"] = df[malzeme_col].fillna("").map(norm)
    df["alerjen_norm"] = df[alerjen_col].fillna("").map(norm)
    df["diyet_norm"] = df[diyet_col].fillna("").map(norm)
    df["ozel_kategori"] = df.apply(lambda row: ozel_kategori_bul(row[kategori_col], row[isim_col]), axis=1)
    df["ozel_kategori_norm"] = df["ozel_kategori"].map(norm)

    if norm(diyet_turu) == "vegan":
        df = df[df["diyet_norm"] == "vegan"].copy()
    elif norm(diyet_turu) == "vejetaryen":
        df = df[df["diyet_norm"].isin(["vegan", "vejetaryen"])].copy()

    hard_drop_kelimeleri = alerjiler + sevilmeyenler
    if hard_drop_kelimeleri:
        maske = pd.Series(False, index=df.index)
        for kelime in hard_drop_kelimeleri:
            maske = maske | df["isim_norm"].str.contains(kelime, regex=False, na=False)
            maske = maske | df["malzeme_norm"].str.contains(kelime, regex=False, na=False)
            maske = maske | df["kategori_norm"].str.contains(kelime, regex=False, na=False)
            maske = maske | df["ozel_kategori_norm"].str.contains(kelime, regex=False, na=False)
            maske = maske | df["alerjen_norm"].str.contains(kelime, regex=False, na=False)
        df = df[~maske].copy()

    if goal == "kilo_verme":
        agir_ana_yemek = (df["ozel_kategori"] == "ana_yemek") & (df[kalori_col] > 550)
        df = df[~agir_ana_yemek].copy()

    if diyabet_var_mi:
        diyabet_tatli = (
            df["kategori_norm"].str.contains("tatli", regex=False, na=False)
            | df["ozel_kategori_norm"].str.contains("tatli", regex=False, na=False)
            | df["ozel_kategori"].isin(["snack_tatli"])
        )
        diyabet_gizli_seker_kelimeleri = ["recel", "pekmez", "bal", "cikolata", "sprite", "kola", "gazoz", "meyve suyu", "surup", "nektar", "nektari", "hazir", "kizartma", "kizartmasi"]
        for kelime in diyabet_gizli_seker_kelimeleri:
            diyabet_tatli = diyabet_tatli | df["isim_norm"].str.contains(kelime, regex=False, na=False)
        df = df[~diyabet_tatli].copy()

    if goal == "kilo_verme" or (hedef_kalori is not None and hedef_kalori < 2200):
        zararli = (
            df["kategori_norm"].str.contains("tatli", regex=False, na=False)
            | df["kategori_norm"].str.contains("fast food", regex=False, na=False)
            | df["ozel_kategori"].isin(["snack_tatli", "fast_food"])
            | df["isim_norm"].str.contains("kola", regex=False, na=False)
            | df["isim_norm"].str.contains("milkshake", regex=False, na=False)
        )
        df = df[~zararli].copy()

    if df.empty:
        return basarisiz_cevap

    df["sevilen_odul"] = 0
    for kelime in sevilenler:
        df.loc[
            df["isim_norm"].str.contains(kelime, regex=False, na=False)
            | df["malzeme_norm"].str.contains(kelime, regex=False, na=False),
            "sevilen_odul"
        ] += 100

    yemekler = []
    for _, row in df.iterrows():
        porsiyon = str(deger(row, olcu_col, "")).strip()
        isim = str(deger(row, isim_col, "")).strip()
        yemekler.append({
            "id": int(row[yemek_id_col]),
            "isim": f"{porsiyon} {isim}".strip(),
            "kalori": float(row[kalori_col]),
            "kategori": str(deger(row, kategori_col, "")),
            "ozel_kategori": row["ozel_kategori"],
            "protein": float(row[protein_col]),
            "karb": float(row[karb_col]),
            "yag": float(row[yag_col]),
            "malzemeler": str(deger(row, malzeme_col, "")),
            "sevilen_odul": float(row["sevilen_odul"]),
            "rastgele_odul": random.uniform(0, 1),
        })

    kahvalti_kat = ["kahvalti_ana", "kahvalti_yan", "peynir", "hamur_isi"]
    ana_kat = ["ana_yemek"]
    yan_kat = ["corba", "salata_meze", "karb_yan"]
    ara_kat = ["snack_tatli", "snack_kuruyemis", "icecek", "meyve"]
    uygun_katlar = set(kahvalti_kat + ana_kat + yan_kat + ara_kat)
    yemekler = [y for y in yemekler if y["ozel_kategori"] in uygun_katlar]

    def kategori_var(kategoriler, minimum):
        return sum(1 for y in yemekler if y["ozel_kategori"] in kategoriler) >= minimum

    if (
        not kategori_var(kahvalti_kat, 2)
        or not kategori_var(ana_kat, 1)
        or not kategori_var(yan_kat, 1)
        or not kategori_var(ara_kat, 1)
    ):
        return basarisiz_cevap

    yemek_by_id = {y["id"]: y for y in yemekler}
    prob = pulp.LpProblem("Haftalik_Diyet_Plani", pulp.LpMaximize)
    x = {}

    def slot_icin_uygun(slot, yemek):
        kat = yemek["ozel_kategori"]
        if slot == "kahvalti":
            return kat in kahvalti_kat
        if slot in ["ogle_ana", "aksam_ana"]:
            return kat in ana_kat
        if slot in ["ogle_yan", "aksam_yan"]:
            return kat in yan_kat
        if slot == "ara":
            return kat in ara_kat
        return False

    for gun in gunler:
        for slot in slotlar:
            for yemek in yemekler:
                if slot_icin_uygun(slot, yemek):
                    x[(gun, slot, yemek["id"])] = pulp.LpVariable(f"x_{gun}_{slot}_{yemek['id']}", 0, 1, cat="Binary")

    if not x:
        return basarisiz_cevap

    prob += pulp.lpSum(
        x[key] * (yemek_by_id[key[2]]["sevilen_odul"] + yemek_by_id[key[2]]["rastgele_odul"] - 0.01)
        for key in x
    )

    for gun in gunler:
        kalori_toplam = pulp.lpSum(var * yemek_by_id[yid]["kalori"] for (g, _, yid), var in x.items() if g == gun)
        prob += kalori_toplam >= hedef_kalori * 0.85
        prob += kalori_toplam <= hedef_kalori * 1.15

        kahvalti_vars = [var for (g, slot, _), var in x.items() if g == gun and slot == "kahvalti"]
        prob += pulp.lpSum(kahvalti_vars) >= 2
        prob += pulp.lpSum(kahvalti_vars) <= 4

        kahvalti_agir_vars = [
            var for (g, slot, yid), var in x.items()
            if g == gun and slot == "kahvalti" and yemek_by_id[yid]["ozel_kategori"] in ["kahvalti_ana", "hamur_isi"]
        ]
        prob += pulp.lpSum(kahvalti_agir_vars) <= 1

        kahvalti_tatli_surulebilir_vars = [
            var for (g, slot, yid), var in x.items()
            if g == gun
            and slot == "kahvalti"
            and any(
                kelime in norm(
                    f"{yemek_by_id[yid]['isim']} {yemek_by_id[yid]['malzemeler']} {yemek_by_id[yid]['kategori']}"
                )
                for kelime in ["recel", "bal", "pekmez", "krem cikolata", "cikolata krem", "nutella", "fistik ezmesi"]
            )
        ]
        prob += pulp.lpSum(kahvalti_tatli_surulebilir_vars) <= 1

        kahvalti_doyurucu_vars = [
            var for (g, slot, yid), var in x.items()
            if g == gun
            and slot == "kahvalti"
            and (
                yemek_by_id[yid]["ozel_kategori"] == "peynir"
                or any(
                    kelime in norm(
                        f"{yemek_by_id[yid]['isim']} {yemek_by_id[yid]['malzemeler']} {yemek_by_id[yid]['kategori']}"
                    )
                    for kelime in ["yumurta", "zeytin", "ekmek", "tost", "bazlama"]
                )
            )
        ]
        prob += pulp.lpSum(kahvalti_doyurucu_vars) + pulp.lpSum(kahvalti_agir_vars) >= 1

        prob += pulp.lpSum(var for (g, slot, _), var in x.items() if g == gun and slot == "ogle_ana") == 1
        prob += pulp.lpSum(var for (g, slot, _), var in x.items() if g == gun and slot == "ogle_yan") == 1
        prob += pulp.lpSum(var for (g, slot, _), var in x.items() if g == gun and slot == "aksam_ana") == 1
        prob += pulp.lpSum(var for (g, slot, _), var in x.items() if g == gun and slot == "aksam_yan") == 2
        prob += pulp.lpSum(var for (g, slot, _), var in x.items() if g == gun and slot == "ara") >= 1
        prob += pulp.lpSum(var for (g, slot, _), var in x.items() if g == gun and slot == "ara") <= 2

        for yan_turu in yan_kat:
            prob += pulp.lpSum(
                var for (g, slot, yid), var in x.items()
                if g == gun and slot == "aksam_yan" and yemek_by_id[yid]["ozel_kategori"] == yan_turu
            ) <= 1

        for yemek in yemekler:
            ayni_gun_ayni_yemek = [var for (g, _, yid), var in x.items() if g == gun and yid == yemek["id"]]
            if ayni_gun_ayni_yemek:
                prob += pulp.lpSum(ayni_gun_ayni_yemek) <= 1

    if diyabet_var_mi:
        prob += pulp.lpSum(
            var for (_, _, yid), var in x.items()
            if yemek_by_id[yid]["ozel_kategori"] == "hamur_isi"
        ) <= 2

    for yemek in yemekler:
        haftalik_tekrar = [var for (_, _, yid), var in x.items() if yid == yemek["id"]]
        if haftalik_tekrar:
            prob += pulp.lpSum(haftalik_tekrar) <= 2

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[prob.status] != "Optimal":
        return basarisiz_cevap

    haftalik_plan = {}
    for gun in gunler:
        ogunler = {"Sabah": [], "Öğle": [], "Akşam": [], "Ara_Öğün": []}
        hesap_kal, hesap_prot, hesap_karb, hesap_yag = 0, 0, 0, 0

        for slot in slotlar:
            secilenler = []
            for (g, s, yid), var in x.items():
                if g == gun and s == slot and var.varValue and var.varValue > 0.5:
                    secilenler.append(yemek_by_id[yid])

            secilenler.sort(key=lambda y: (y["ozel_kategori"], y["isim"]))
            for yemek in secilenler:
                ogunler[slot_to_ogun[slot]].append(yemek)
                hesap_kal += yemek["kalori"]
                hesap_prot += yemek["protein"]
                hesap_karb += yemek["karb"]
                hesap_yag += yemek["yag"]

        haftalik_plan[gun] = {
            "ogunler": ogunler,
            "gerceklesen": {
                "kalori": round(hesap_kal),
                "protein_g": round(hesap_prot),
                "karb_g": round(hesap_karb),
                "yag_g": round(hesap_yag),
            }
        }

    return {"durum": "Başarılı", "haftalik_plan": haftalik_plan}

def bmr_ve_kalori_hesapla(cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float, hedef: str):
    if cinsiyet.lower() == "erkek": bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) + 5
    else: bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) - 161
    
    gunluk_harcanan_kalori = bmr * hareket_katsayisi
    if hedef == "Kilo Ver": hedef_kalori = gunluk_harcanan_kalori - 500
    elif hedef == "Kas Yap": hedef_kalori = gunluk_harcanan_kalori + 300
    else: hedef_kalori = gunluk_harcanan_kalori
    if hedef_kalori < 1200:
        hedef_kalori = 1200
    return int(hedef_kalori)

def kullanici_kaydet(email: str, ad: str, cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float, hedef: str):
    hedef_kalori = bmr_ve_kalori_hesapla(cinsiyet, yas, boy_cm, kilo_kg, hareket_katsayisi, hedef)
    
    try:
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
    except Exception as e:
        print(f"Profil veritabanına kaydedilemedi, hesaplanan kaloriyle devam ediliyor: {e}")
        return {
            "mesaj": "Profil veritabanına kaydedilemedi; menü oluşturma için kalori hesabı yapıldı.",
            "hesaplanan_hedef_kalori": hedef_kalori,
            "db_kayit": "atlanmis"
        }

def kilo_guncelle(email: str, yeni_kilo: float):
    with engine.begin() as conn:
        sorgu = text("SELECT Kilo_kg, Hareket_Katsayisi, Hedef_Kalori FROM Kullanicilar WHERE Email = :email")
        kullanici = conn.execute(sorgu, {"email": email}).fetchone()
        
        if not kullanici:
            return {"durum": "Hata", "mesaj": "Kullanıcı bulunamadı"}
            
        eski_kilo = kullanici.Kilo_kg
        hareket = kullanici.Hareket_Katsayisi
        eski_hedef_kalori = kullanici.Hedef_Kalori
        
        # BMR değişimi: (10 * yeni_kilo) - (10 * eski_kilo) = 10 * (yeni_kilo - eski_kilo)
        delta_kalori = 10 * (yeni_kilo - eski_kilo) * hareket
        yeni_hedef_kalori = int(eski_hedef_kalori + delta_kalori)
        
        guncelle_sorgu = text("""
            UPDATE Kullanicilar 
            SET Kilo_kg = :yeni_kilo, Hedef_Kalori = :yeni_hedef_kalori
            WHERE Email = :email
        """)
        conn.execute(guncelle_sorgu, {
            "yeni_kilo": yeni_kilo,
            "yeni_hedef_kalori": yeni_hedef_kalori,
            "email": email
        })
        
    return {"durum": "Başarılı", "mesaj": "Kilonuz güncellendi", "yeni_hedef_kalori": yeni_hedef_kalori}

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
    from sqlalchemy import text
    
    try:
        # ensure_ascii=False: Türkçe karakterlerin bozulmadan (ç, ş, ğ olarak) veritabanına yazılmasını sağlar!
        json_verisi = json.dumps(diyet_plani, ensure_ascii=False)
        
        with engine.begin() as conn:
            # 1. Tablo yoksa oluştur
            conn.execute(text("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DiyetKayitlari' and xtype='U')
                CREATE TABLE DiyetKayitlari (
                    Id INT IDENTITY(1,1) PRIMARY KEY,
                    Email NVARCHAR(255),
                    DiyetJSON NVARCHAR(MAX),
                    KayitTarihi DATETIME DEFAULT GETDATE()
                )
            """))
            
            # 2. Eski menüyü sil
            conn.execute(text("DELETE FROM DiyetKayitlari WHERE Email = :email"), {"email": email})
            
            # 3. Yeni menüyü kaydet
            conn.execute(text("""
                INSERT INTO DiyetKayitlari (Email, DiyetJSON) 
                VALUES (:email, :json_veri)
            """), {"email": email, "json_veri": json_verisi})
            
        print(f"BAŞARILI: {email} için menü veritabanına kaydedildi.")
        return {"durum": "kaydedildi"}
        
    except Exception as e:
        print(f"KRİTİK HATA - aktif_menuyu_kaydet başarısız: {str(e)}")
        return {"durum": "hata", "hata_mesaji": str(e)}

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

def genel_bilgi_sorusunu_cevapla(user_message: str, profile: dict | None = None) -> str:
    import ollama
    import json
    
    system_prompt = "Sen NexText'in profesyonel, samimi ve motive edici diyetisyen asistanısın. Kullanıcının beslenme, diyet veya sağlıklı yaşam ile ilgili sorusuna kısa, öz (maksimum 3-4 cümle) ve bilimsel olarak doğru bir cevap ver. JSON üretme, normal metin olarak konuş. KESİNLİKLE VE SADECE TÜRKÇE DİLİNDE CEVAP VER. İNGİLİZCE VEYA BAŞKA BİR DİL KULLANMA."
    if profile:
        profile_text = json.dumps(profile, ensure_ascii=False, indent=2)
        system_prompt += (
            "\n\nSen uzman bir diyetisyensin. Karşındaki kullanıcının güncel profil bilgileri şunlardır: "
            f"{profile_text}\n"
            "Kullanıcı sana bir şey sorduğunda veya menü oluşturmanı istediğinde ASLA profil bilgilerini tekrar sorma, "
            "çünkü bu bilgiler zaten sistemde kayıtlı. Doğrudan bu profil verilerine ve kısıtlamalara uygun, "
            "empatik ve profesyonel cevaplar ver."
        )
    else:
        system_prompt += "\n\nBu istekte profil verisi yoksa, yalnızca kişiselleştirme için gerçekten gerekliyse profili doldurmasını isteyebilirsin."
    
    try:
        response = ollama.chat(
            model='llama3',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_message}
            ]
        )
        return response['message']['content']
    except Exception as e:
        print(f"Ollama bilgi_ver hatası: {e}")
        return "Şu an bilgi sistemlerimde kısa süreli bir yoğunluk var, bana birazdan tekrar sorabilir misin?"

def sohbeti_kaydet(email: str, user_message: str, ai_reply: str):
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='SohbetKayitlari' and xtype='U')
                CREATE TABLE SohbetKayitlari (
                    Id INT IDENTITY(1,1) PRIMARY KEY,
                    Email NVARCHAR(255),
                    UserMessage NVARCHAR(MAX),
                    AIMessage NVARCHAR(MAX),
                    Tarih DATETIME DEFAULT GETDATE()
                )
            """))
            
            conn.execute(text("""
                INSERT INTO SohbetKayitlari (Email, UserMessage, AIMessage)
                VALUES (:email, :user_message, :ai_reply)
            """), {"email": email, "user_message": user_message, "ai_reply": ai_reply})
            
    except Exception as e:
        print(f"Sohbet kaydetme hatası: {e}")
