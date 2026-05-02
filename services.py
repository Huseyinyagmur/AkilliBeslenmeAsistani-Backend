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
    # 1. Yemekleri ve MAKROLARI SQL'den Çek
    yemekler = []
    with engine.connect() as conn:
        # Sütun isimlerini kendi veritabanına göre ayarladığından emin ol!
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
    
    # 2. Makro Hedeflerini Hesapla (Dengeli Diyet: %30 P, %40 C, %30 Y)
    hedef_protein_g = (hedef_kalori * 0.30) / 4
    hedef_karb_g = (hedef_kalori * 0.40) / 4
    hedef_yag_g = (hedef_kalori * 0.30) / 9

    # 3. PuLP Modelini Başlat
    prob = pulp.LpProblem("Makro_Dengeli_Diyet_Optimizasyonu", pulp.LpMinimize)
    yemek_degiskenleri = pulp.LpVariable.dicts("Yemek", [y["id"] for y in yemekler], cat='Binary')
    prob += 0, "Amac"
    
    # KISIT 1: Kalori Hedefi (+- 100 kcal esneklik)
    toplam_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler])
    prob += toplam_kalori >= hedef_kalori - 100, "Min_Kalori"
    prob += toplam_kalori <= hedef_kalori + 100, "Max_Kalori"

    # --- YENİ: MAKRO KISITLARI (+- 20 gram esneklik veriyoruz ki model tıkanmasın) ---
    toplam_protein = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["protein"] for y in yemekler])
    prob += toplam_protein >= hedef_protein_g - 20, "Min_Protein"
    prob += toplam_protein <= hedef_protein_g + 20, "Max_Protein"

    toplam_karb = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["karb"] for y in yemekler])
    prob += toplam_karb >= hedef_karb_g - 20, "Min_Karb"
    prob += toplam_karb <= hedef_karb_g + 20, "Max_Karb"

    toplam_yag = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["yag"] for y in yemekler])
    prob += toplam_yag >= hedef_yag_g - 15, "Min_Yag"
    prob += toplam_yag <= hedef_yag_g + 15, "Max_Yag"

    # KISIT 2: Çeşit Sayısı ve Kategori Mantığı
    toplam_secilen_yemek = pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler])
    prob += toplam_secilen_yemek >= 3, "Min_Cesit"
    prob += toplam_secilen_yemek <= 5, "Max_Cesit"

    kategoriler = set([y["kategori"] for y in yemekler])
    for kat in kategoriler:
        prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] == kat]) <= 1, f"Max_1_{kat}"

    ana_yemekler = [y["id"] for y in yemekler if y["kategori"] == "Ana Yemek"]
    if ana_yemekler:
        prob += pulp.lpSum([yemek_degiskenleri[y_id] for y_id in ana_yemekler]) == 1, "Zorunlu_Ana_Yemek"

    # 4. Modeli Çöz
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    # 5. Sonucu Formatla ve Döndür
    secilen_menu = []
    hesaplanan_kalori, hesaplanan_protein, hesaplanan_karb, hesaplanan_yag = 0.0, 0.0, 0.0, 0.0
    
    if pulp.LpStatus[prob.status] == 'Optimal':
        for y in yemekler:
            if yemek_degiskenleri[y["id"]].varValue == 1.0:
                secilen_menu.append(y)
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
            "menu": secilen_menu
        }
    else:
        return {"durum": "Başarısız", "mesaj": "Bu kalori ve makro dengesine tam uygun bir menü bulunamadı. Lütfen kaloriyi değiştirin."}