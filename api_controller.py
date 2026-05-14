from nlp_parser import parse_user_intent
from services import alternatif_yemek_bul_ml, diyet_olustur, aktif_menuyu_getir
import json

def chat_endpoint_islemi(user_message: str, user_email: str):
    llm_karari = parse_user_intent(user_message)
    
    # Llama-3'ün ürettiği ham JSON'ı terminale yazdıralım:
    print("--- LLM KARARI ---")
    print(llm_karari)
    
    intent = llm_karari.get("intent")
    confidence = llm_karari.get("confidence", 0)
    
    # Güvenlik Ağı: Model emin değilse saçmalamasını engelle
    if confidence < 0.6:
        return {
            "status": "error",
            "reply": "Ne demek istediğini tam anlayamadım, biraz daha detaylı yazar mısın?"
        }

    # ==========================================
    # 🎯 SENARYO 1: KULLANICI MENÜYÜ GÜNCELLEMEK / YEMEK DEĞİŞTİRMEK İSTİYOR
    # ==========================================
    if intent == "menuyu_guncelle":
        aktif_menu = aktif_menuyu_getir(user_email)
        if not aktif_menu:
             return {"status": "success", "reply": "Şu an aktif bir menün bulunmuyor. Önce yeni bir menü oluşturalım mı?"}

        istenmeyen_yemek_listesi = llm_karari.get("exclude_foods", [])
        if not istenmeyen_yemek_listesi:
            return {"status": "success", "reply": "Hangi yemeği değiştireceğimi anlayamadım."}
            
        def metin_temizle(metin):
            if not metin: return ""
            metin = metin.lower()
            degisimler = {"ç": "c", "ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "i̇": "i"}
            for eski, yeni in degisimler.items():
                metin = metin.replace(eski, yeni)
            return metin

        aranan_kelime = istenmeyen_yemek_listesi[0]
        aranan_kelimeler = metin_temizle(aranan_kelime).split()
        
        bulunan_yemek_id = None
        bulunan_kategori = None
        
        # 2. Veritabanından gelen aktif menüyü 4 katman derine inerek tara
        haftalik_plan = aktif_menu.get("haftalik_plan", {})
        
        for gun, gun_verisi in haftalik_plan.items():
            ogunler = gun_verisi.get("ogunler", {})
            for ogun_adi, yemek_listesi in ogunler.items():
                for yemek in yemek_listesi:
                    # Esnek ve Türkçe karakter duyarsız arama
                    temiz_yemek_ismi = metin_temizle(yemek.get("isim", ""))
                    
                    eslesme_bulundu = False
                    for kelime in aranan_kelimeler:
                        if len(kelime) > 3 and kelime in temiz_yemek_ismi:
                            eslesme_bulundu = True
                            break
                            
                    if eslesme_bulundu:
                        bulunan_yemek_id = yemek.get("id")
                        bulunan_kategori = yemek.get("kategori", "Ana_Yemek") # Varsayılan kategori
                        print(f"BULDUM! {gun} {ogun_adi} menüsündeki {yemek.get('isim')} (ID: {bulunan_yemek_id}) değiştirilecek.")
                        break # Yemeği bulduk, en iç döngüden çık
                if bulunan_yemek_id: break # Orta döngüden çık
            if bulunan_yemek_id: break # Dış döngüden çık

        # 3. Eğer yemek menüde yoksa halüsinasyonu engelliyoruz
        if not bulunan_yemek_id:
            return {"status": "success", "reply": f"Menünde '{aranan_kelime}' bulamadım. Lütfen tam adını söyler misin?"}

        # 4. İŞTE BÜYÜK AN: Senin yazdığın Makine Öğrenmesi (KNN) motoru çalışıyor!
        alerjiler = llm_karari.get("allergens", [])
        try:
            yeni_yemek_sonucu = alternatif_yemek_bul_ml(
                eski_yemek_id=bulunan_yemek_id, 
                kategori=bulunan_kategori, 
                alerjiler=alerjiler,
                sevilmeyenler=istenmeyen_yemek_listesi
            )

            if yeni_yemek_sonucu.get("durum") == "Başarılı":
                yeni_isim = yeni_yemek_sonucu['yeni_yemek']['isim']
                return {
                    "status": "success",
                    "action_taken": "yemek_degistirildi",
                    "reply": f"Harika haber! {aranan_kelime} menüden çıkarıldı. Yerine aynı besin değerlerinde nefis bir {yeni_isim} ekledim.",
                    "ai_data": llm_karari,
                    "yeni_menu_verisi": yeni_yemek_sonucu['yeni_yemek'] # Frontend bu veriyi alıp arayüzü güncelleyecek
                }
            else:
                 return {"status": "error", "reply": "Bu kısıtlamalara uygun bir alternatif bulamadım, biraz daha esnek olabilir miyiz?"}
                 
        except Exception as e:
            print("KNN Hatası:", str(e))
            return {"status": "error", "reply": "Alternatif yemek ararken matematiksel bir hata oluştu."}

    # ==========================================
    # 🎯 SENARYO 2: YENİ MENÜ OLUŞTURMA İSTEĞİ
    # ==========================================
    elif intent == "yeni_menu_olustur":
        from services import kullanici_kontrol_et, haftalik_diyet_olustur, aktif_menuyu_kaydet
        
        kullanici = kullanici_kontrol_et(user_email)
        if not kullanici.get("kayitli_mi"):
            return {"status": "error", "reply": "Lütfen önce profil bilgilerini doldur, ardından sana özel bir menü oluşturabilirim."}
        
        hedef_kalori = kullanici.get("hedef_kalori", 2000)
        alerjiler = llm_karari.get("allergens", [])
        sevilmeyenler = llm_karari.get("exclude_foods", [])
        sevilenler = llm_karari.get("include_foods", [])
        diyet_turu = llm_karari.get("diet_type", "Standart")
        if not diyet_turu:
             diyet_turu = "Standart"
        saglik_sorunlari = llm_karari.get("health_conditions", [])
        
        sonuc = haftalik_diyet_olustur(
            hedef_kalori=hedef_kalori,
            alerjiler=alerjiler,
            sevilmeyenler=sevilmeyenler,
            sevilenler=sevilenler,
            saglik_sorunlari=saglik_sorunlari,
            diyet_turu=diyet_turu
        )
        
        if sonuc.get("durum") == "Başarılı":
            aktif_menuyu_kaydet(user_email, sonuc)
            return {
                "status": "success",
                "action_taken": "yeni_menu_olusturuldu",
                "reply": "Harika! Belirttiğin özelliklere ve hedeflerine uygun, tamamen sana özel yepyeni bir haftalık menü hazırladım.",
                "ai_data": llm_karari,
                "yeni_menu_verisi": sonuc
            }
        else:
            return {"status": "error", "reply": "Bu kısıtlamalara uygun tam bir menü oluşturamadım, biraz daha esnek olabilir miyiz?"}

    # ==========================================
    # 🎯 SENARYO 3: ALAKASIZ SORU / GÜVENLİK DUVARI
    # ==========================================
    elif intent == "bilgi_ver":
        from services import genel_bilgi_sorusunu_cevapla
        
        # Kullanıcının sorusunu doğrudan Llama-3'e normal bir sohbet gibi soruyoruz
        llm_cevabi = genel_bilgi_sorusunu_cevapla(user_message)
        
        return {
            "status": "success",
            "action_taken": "bilgi_verildi",
            "reply": llm_cevabi
        }
    # ==========================================
    # 🎯 DİĞER DURUMLAR (Fallback)
    # ==========================================
    else:
        return {
            "status": "success",
            "reply": "Menün üzerinde çalışmaya devam ediyorum. Bugün su içmeyi unutma!"
        }