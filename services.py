import pulp
from sqlalchemy import create_engine, text
import urllib

# Veritabanı Bağlantısı
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
    # 1. Yemekleri ve Makroları Çek
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
    prob += toplam_protein >= hedef_protein_g - 20, "Min_Protein"
    prob += toplam_protein <= hedef_protein_g + 20, "Max_Protein"

    toplam_karb = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["karb"] for y in yemekler])
    prob += toplam_karb >= hedef_karb_g - 20, "Min_Karb"
    prob += toplam_karb <= hedef_karb_g + 20, "Max_Karb"

    toplam_yag = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["yag"] for y in yemekler])
    prob += toplam_yag >= hedef_yag_g - 15, "Min_Yag"
    prob += toplam_yag <= hedef_yag_g + 15, "Max_Yag"

    # --- YENİ: ÖĞÜN KATEGORİLEMESİ VE KISITLARI ---
    # Not: Excel'deki yazım hatalarına karşı Türkçe karakterli/karaktersiz varyasyonları ekledik
    sabah_kat = ["Kahvalti", "Kahvaltı", "Hamur İsi", "Hamur İşi"]
    ana_ogun_kat = ["Ana Yemek", "Çorba", "Corba", "Fast Food", "Salata", "Meze"]
    ara_ogun_kat = ["Tatlı", "Tatli", "Meyve", "Atıştırmalık", "Atistirmalik", "İcecek", "İçecek"]

    # 1. Sabah için tam 1 çeşit seç
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in sabah_kat]) == 1, "Sabah_Kurali"

    # 2. Öğle ve Akşam için toplam 2 veya 3 çeşit seç (Örn: 2 ana yemek, veya 1 ana yemek + 1 çorba)
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ana_ogun_kat]) >= 2, "Min_Ana_Ogun"
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ana_ogun_kat]) <= 3, "Max_Ana_Ogun"

    # 3. Ara öğün için 1 veya 2 çeşit seç (Tatlı, içecek vs.)
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat]) >= 1, "Min_Ara_Ogun"
    prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] in ara_ogun_kat]) <= 2, "Max_Ara_Ogun"

    # 4. Kategori çeşitliliği (Her kategoriden maksimum 1 tane, 2 çorba vermesin)
    kategoriler = set([y["kategori"] for y in yemekler])
    for kat in kategoriler:
        prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] == kat]) <= 1, f"Max_1_{kat}"

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    # --- YENİ: SONUCU ÖĞÜNLERE BÖLEREK FORMATLAMA ---
    ogunler = {
        "Sabah": [],
        "Öğle_ve_Akşam": [],
        "Ara_Öğün": []
    }
    hesaplanan_kalori, hesaplanan_protein, hesaplanan_karb, hesaplanan_yag = 0.0, 0.0, 0.0, 0.0
    
    if pulp.LpStatus[prob.status] == 'Optimal':
        for y in yemekler:
            if yemek_degiskenleri[y["id"]].varValue == 1.0:
                # Yemeği ait olduğu öğüne yerleştir
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
            "ogunler": ogunler # Artık "menu" yerine düzenli "ogunler" dönüyor
        }
    else:
        return {"durum": "Başarısız", "mesaj": "Bu hedeflere uygun menü bulunamadı."}