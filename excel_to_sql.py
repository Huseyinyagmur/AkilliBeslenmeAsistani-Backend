from pathlib import Path
import urllib

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError


excel_dosyasi = Path(__file__).resolve().parent / "foods_final_v2_final.xlsx"
df = pd.read_excel(excel_dosyasi)
df = df.rename(columns={
    kolon: "Yemek_Ad\u0131"
    for kolon in df.columns
    if str(kolon).strip().startswith("Yemek_Ad") and str(kolon).strip() != "Yemek_Ad\u0131"
})

server_adi = "LAPTOP-V013QBHO"
veritabani_adi = "DiyetAppDB"

print("MSSQL'e baglaniliyor...")

son_hata = None
for driver in ["ODBC Driver 17 for SQL Server", "SQL Server"]:
    params = urllib.parse.quote_plus(
        f"DRIVER={{{driver}}};"
        f"SERVER={server_adi};"
        f"DATABASE={veritabani_adi};"
        f"Trusted_Connection=yes;"
        f"Encrypt=no;"
        f"TrustServerCertificate=yes;"
    )
    try:
        print(f"Driver deneniyor: {driver}")
        engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
        df.to_sql("Yemekler", con=engine, if_exists="replace", index=False)
        son_hata = None
        break
    except OperationalError as e:
        son_hata = e
        print(f"{driver} ile baglanti kurulamadi.")

if son_hata:
    raise son_hata

print(f"Hedef tamamlandi! {len(df)} satirlik foods_final veri seti MSSQL 'Yemekler' tablosuna basariyla aktarildi!")
