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
    # 1. Yemekleri SQL'den Çek
    yemekler = []
    with engine.connect() as conn:
        sorgu = text("SELECT Yemek_Id, Yemek_Adı, Kalori_Kcal, Kategori FROM Yemekler WHERE Kalori_Kcal IS NOT NULL")
        sonuc = conn.execute(sorgu)
        for row in sonuc:
            yemekler.append({
                "id": row.Yemek_Id,
                "isim": row.Yemek_Adı,
                "kalori": float(row.Kalori_Kcal),
                "kategori": row.Kategori
            })
    
    # 2. PuLP Matematiksel Modeli Başlat
    prob = pulp.LpProblem("Diyet_Optimizasyonu", pulp.LpMinimize)
    
    # Karar Değişkenleri
    yemek_degiskenleri = pulp.LpVariable.dicts("Yemek", [y["id"] for y in yemekler], cat='Binary')
    
    prob += 0, "Amac"
    
    # KISIT 1: Kalori Hedefi (+- 100 kcal esneklik)
    toplam_kalori = pulp.lpSum([yemek_degiskenleri[y["id"]] * y["kalori"] for y in yemekler])
    prob += toplam_kalori >= hedef_kalori - 100, "Min_Kalori"
    prob += toplam_kalori <= hedef_kalori + 100, "Max_Kalori"
    
    # KISIT 2: Çeşit Sayısı (Günlük 3 ile 5 farklı yemek/atıştırmalık)
    toplam_secilen_yemek = pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler])
    prob += toplam_secilen_yemek >= 3, "Min_Cesit"
    prob += toplam_secilen_yemek <= 5, "Max_Cesit"

    # --- MANTIKLI KATEGORİ DAĞILIMI (YENİ) ---
    kategoriler = set([y["kategori"] for y in yemekler])
    
    for kat in kategoriler:
        # Kural: Aynı kategoriden birden fazla yemek seçilemez (Örn: 2 tatlı veya 2 çorba yok)
        prob += pulp.lpSum([yemek_degiskenleri[y["id"]] for y in yemekler if y["kategori"] == kat]) <= 1, f"Max_1_{kat}"

    # --- ZORUNLU KATEGORİLER (YENİ) ---
    # Diyetin doyurucu olması için 1 adet 'Ana Yemek' seçilmesini zorunlu kılıyoruz
    ana_yemekler = [y["id"] for y in yemekler if y["kategori"] == "Ana Yemek"]
    if ana_yemekler:
        prob += pulp.lpSum([yemek_degiskenleri[y_id] for y_id in ana_yemekler]) == 1, "Zorunlu_Ana_Yemek"

    # 3. Modeli Çöz
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    # 4. Sonucu Formatla ve Döndür
    secilen_menu = []
    hesaplanan_kalori = 0.0
    
    if pulp.LpStatus[prob.status] == 'Optimal':
        for y in yemekler:
            if yemek_degiskenleri[y["id"]].varValue == 1.0:
                secilen_menu.append(y)
                hesaplanan_kalori += y["kalori"]
                
        return {
            "durum": "Başarılı",
            "hedef_kalori": hedef_kalori,
            "ulasilan_kalori": round(hesaplanan_kalori, 2),
            "menu": secilen_menu
        }
    else:
        return {"durum": "Başarısız", "mesaj": "Belirlenen kriterlere ve kaloriye uygun bir menü oluşturulamadı."}