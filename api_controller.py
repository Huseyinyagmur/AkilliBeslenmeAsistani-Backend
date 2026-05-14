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
        cikarilacak_yemekler = llm_karari.get("exclude_foods", [])
        
        if not cikarilacak_yemekler:
            return {"status": "success", "reply": "Hangi yemeği değiştirmek istediğini tam anlayamadım, tekrar söyler misin?"}
            
        # 1. Kullanıcının aktif menüsünü veritabanından çekiyoruz
        aktif_menu = aktif_menuyu_getir(user_email)
        if not aktif_menu:
             return {"status": "error", "reply": "Şu an aktif bir menün bulunmuyor. Önce yeni bir menü oluşturalım mı?"}

        hedef_yemek_id = None
        hedef_kategori = None
        aranan_kelime = None

        # 2. Menüde tur atıp kullanıcının sevmediği o yemeği (örneğin pırasayı) buluyoruz
        for gun, detay in aktif_menu.get("haftalik_plan", {}).items():
            if detay.get("durum") == "Başarılı":
                for ogun, yemek_listesi in detay.get("ogunler", {}).items():
                    for yemek in yemek_listesi:
                        for istenmeyen_yemek in cikarilacak_yemekler:
                            if istenmeyen_yemek.lower() in yemek["isim"].lower():
                                hedef_yemek_id = yemek["id"]
                                hedef_kategori = yemek["kategori"]
                                aranan_kelime = istenmeyen_yemek
                                break # İstenmeyen yemeği bulduk, iç döngüden çık
                        if hedef_yemek_id:
                            break # Yemekler döngüsünden çık
                    if hedef_yemek_id:
                        break # Öğünler döngüsünden çık
            if hedef_yemek_id:
                break # Günler döngüsünden çık

        # 3. Eğer yemek menüde yoksa halüsinasyonu engelliyoruz
        if not hedef_yemek_id:
             arananlar_str = ", ".join(cikarilacak_yemekler)
             return {"status": "success", "reply": f"Menünde '{arananlar_str}' bulamadım. Başka bir yemeği değiştirmek ister misin?"}

        # 4. İŞTE BÜYÜK AN: Senin yazdığın Makine Öğrenmesi (KNN) motoru çalışıyor!
        alerjiler = llm_karari.get("allergens", [])
        yeni_yemek_sonucu = alternatif_yemek_bul_ml(
            eski_yemek_id=hedef_yemek_id, 
            kategori=hedef_kategori, 
            alerjiler=alerjiler, 
            sevilmeyenler=cikarilacak_yemekler
        )

        if yeni_yemek_sonucu["durum"] == "Başarılı":
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
        
        if sonuc["durum"] == "Başarılı":
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
    elif intent == "alakasiz_soru":
        return {
            "status": "success",
            "action_taken": "none",
            "reply": "Ben DocuMind'ın beslenme ve yaşam tarzı asistanıyım. Bu konuda uzman değilim ama sağlıklı beslenme hedeflerin hakkında konuşmaktan mutluluk duyarım!"
        }

    # ==========================================
    # 🎯 DİĞER DURUMLAR (Fallback)
    # ==========================================
    else:
        return {
            "status": "success",
            "reply": "Menün üzerinde çalışmaya devam ediyorum. Bugün su içmeyi unutma!"
        }
