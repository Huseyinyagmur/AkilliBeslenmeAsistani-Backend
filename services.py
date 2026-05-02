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
            SELECT Yemek_Id, Yemek_Adı, Kalori_Kcal, Kategori, 
                   Protein_g, Karbonhidrat_g, Yag_g 
            FROM Yemekler 
            WHERE Kalori_Kcal IS NOT NULL 
              AND Protein_g IS NOT NULL 
              AND Karbonhidrat_g IS NOT NULL 
              AND Yag_g IS NOT NULL
        """)
        sonuc = conn.execute(sorgu)
        for row in sonuc:
            yemekler.append({
                "id": row.Yemek_Id,
                "isim": row.Yemek_Adı,
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
    yemek_degiskenleri = pulp.LpVariable.dicts("Yemek", [y["id"] for y in yemekler], cat='Binary')
    prob += 0, "Amac"
    
    # Kalori ve Makro Kısıtları
    toplam_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler])
    prob += toplam_kalori >= hedef_kalori - 100, "Min_Kalori"
    prob += toplam_kalori <= hedef_kalori + 100, "Max_Kalori"

    toplam_protein = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["protein"] for y in yemekler])
    prob += toplam_protein >= hedef_protein_g - 25, "Min_Protein"
    prob += toplam_protein <= hedef_protein_g + 25, "Max_Protein"

    toplam_karb = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["karb"] for y in yemekler])
    prob += toplam_karb >= hedef_karb_g - 25, "Min_Karb"
    prob += toplam_karb <= hedef_karb_g + 25, "Max_Karb"

    toplam_yag = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["yag"] for y in yemekler])
    prob += toplam_yag >= hedef_yag_g - 20, "Min_Yag"
    prob += toplam_yag <= hedef_yag_g + 20, "Max_Yag"

    # Çeşit Sayısı
    toplam_secilen_yemek = pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler])
    prob += toplam_secilen_yemek >= 3, "Min_Cesit"
    prob += toplam_secilen_yemek <= 5, "Max_Cesit"

    # Kategori Listeleri
    sabah_kat = ["Kahvalti", "Kahvaltı", "Hamur İsi", "Hamur İşi"]
    ana_ogun_kat = ["Ana Yemek", "Çorba", "Corba", "Fast Food", "Salata", "Meze", "ZeytinYagli", "Zeytinyağlı"]
    ara_ogun_kat = ["Tatlı", "Tatli", "Meyve", "Atıştırmalık", "Atistirmalik", "İcecek", "İçecek", "Kuruyemis", "Kuruyemiş"]

    # Öğün Kuralları
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat]) == 1, "Sabah_1_Cesit"
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ana_ogun_kat]) >= 1, "Min_Ana_Ogun"
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ana_ogun_kat]) <= 3, "Max_Ana_Ogun"
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat]) <= 2, "Max_Ara_Ogun"

    kategoriler = set([y["kategori"] for y in yemekler])
    for kat in kategoriler:
        prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] == kat]) <= 1, f"Max_1_{kat}"

    agir_yemekler = [y["id"] for y in yemekler if y["kategori"] in ["Ana Yemek", "Fast Food"]]
    if agir_yemekler:
        prob += pulp.lpSum([yemek_degiskenleri[y_id] for y_id in agir_yemekler]) == 1, "Sadece_Bir_Agir_Yemek"

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

def bmr_ve_kalori_hesapla(cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float):
    # Mifflin-St Jeor Formülü
    if cinsiyet.lower() == "erkek":
        bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) + 5
    else:
        bmr = (10 * kilo_kg) + (6.25 * boy_cm) - (5 * yas) - 161
    
    hedef_kalori = bmr * hareket_katsayisi
    return int(hedef_kalori)

def kullanici_kaydet(ad: str, cinsiyet: str, yas: int, boy_cm: float, kilo_kg: float, hareket_katsayisi: float):
    hedef_kalori = bmr_ve_kalori_hesapla(cinsiyet, yas, boy_cm, kilo_kg, hareket_katsayisi)
    
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