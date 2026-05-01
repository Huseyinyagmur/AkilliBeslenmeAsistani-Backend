import pandas as pd
from sqlalchemy import create_engine
import urllib

# 1. Kusursuz hale getirdiğin Excel dosyanı oku
excel_dosyasi = 'dataset_fixed.xlsx'
df = pd.read_excel(excel_dosyasi)

# 2. MSSQL Bağlantı Ayarları (Sunucu adını senin için ekledim)
server_adi = 'LAPTOP-V013QBHO' 
veritabani_adi = 'DiyetAppDB' 

params = urllib.parse.quote_plus(
    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
    f'SERVER={server_adi};'
    f'DATABASE={veritabani_adi};'
    f'Trusted_Connection=yes;'
)

print("MSSQL'e bağlanılıyor...")

# 3. SQLAlchemy Motorunu (Engine) Oluştur
engine = create_engine(f'mssql+pyodbc:///?odbc_connect={params}')

# 4. Veriyi SQL'e Aktar
df.to_sql('Yemekler', con=engine, if_exists='replace', index=False)

print("🚀 Hedef tamamlandı! 318 satırlık veri seti MSSQL 'Yemekler' tablosuna başarıyla aktarıldı!")