from nlp_parser import parse_user_intent
from services import alternatif_yemek_bul_ml, diyet_olustur, aktif_menuyu_getir
import json

def metni_normalize_et(metin: str) -> str:
    return (
        str(metin or "")
        .lower()
        .replace("ı", "i").replace("ö", "o").replace("ü", "u").replace("ç", "c").replace("ş", "s").replace("ğ", "g")
        .replace("İ", "i").replace("Ö", "o").replace("Ü", "u").replace("Ç", "c").replace("Ş", "s").replace("Ğ", "g")
        .replace("�", "i").replace("i̇", "i")
    )

def menu_olusturma_istegi_mi(user_message: str) -> bool:
    metin = metni_normalize_et(user_message)
    guncelleme_kelimeleri = ["degistir", "cikar", "çıkar", "sevmedim", "istemiyorum", "yerine", "alternatif"]
    if any(kelime in metin for kelime in guncelleme_kelimeleri):
        return False

    menu_kelimeleri = [
        "menu olustur", "menu hazirla", "menu yap", "menü oluştur", "menü hazırla",
        "diyet listesi", "liste yap", "beslenme plani", "beslenme planı",
        "haftalik menu", "haftalik liste", "7 gunluk menu", "7 gunluk liste"
    ]
    return any(kelime in metin for kelime in menu_kelimeleri)

def profil_var_mi(profile: dict | None) -> bool:
    return isinstance(profile, dict) and bool(profile)

def profil_kisitlarini_cikar(profile: dict | None) -> dict:
    if not profil_var_mi(profile):
        return {}

    secimler = profile.get("secimler") or {}
    fiziksel = profile.get("kullaniciFiziksel") or {}

    return {
        "hedef_kalori": profile.get("yapayZekaHedefKalori") or fiziksel.get("hedef_kalori") or 2000,
        "alerjiler": secimler.get("allergies") or secimler.get("alerjiler") or [],
        "sevilmeyenler": secimler.get("dislikedFoods") or secimler.get("sevilmeyenler") or [],
        "sevilenler": secimler.get("likedFoods") or secimler.get("sevilenler") or [],
        "saglik_sorunlari": secimler.get("healthIssues") or secimler.get("saglik_sorunlari") or [],
        "diyet_turu": secimler.get("dietType") or secimler.get("diyet_turu") or "Standart",
    }

def chat_endpoint_islemi(user_message: str, user_email: str, profile: dict | None = None):
    if menu_olusturma_istegi_mi(user_message):
        llm_karari = {
            "intent": "yeni_menu_olustur",
            "confidence": 1.0,
            "target_service": "INTENT_GENERATE_MENU",
            "operation": "generate",
            "allergens": [],
            "exclude_foods": [],
            "include_foods": [],
            "health_conditions": [],
            "diet_type": None,
        }
    else:
        llm_karari = parse_user_intent(user_message, profile)
    
    # Llama-3'ün ürettiği ham JSON'ı terminale yazdıralım:
    print("--- LLM KARARI ---")
    print(llm_karari)
    
    intent = llm_karari.get("intent")
    target_service = llm_karari.get("target_service")
    confidence = llm_karari.get("confidence", 0)
    if target_service == "INTENT_GENERATE_MENU":
        intent = "yeni_menu_olustur"
    if intent == "ogun_degistir" and "confidence" not in llm_karari:
        confidence = 1.0
    
    # Güvenlik Ağı: Model emin değilse saçmalamasını engelle
    if confidence < 0.6:
        return {
            "status": "error",
            "reply": "Ne demek istediğini tam anlayamadım, biraz daha detaylı yazar mısın?"
        }

    if intent == "ogun_degistir":
        from services import kullanici_kontrol_et, haftalik_diyet_olustur, aktif_menuyu_kaydet

        profil_kisitlari = profil_kisitlarini_cikar(profile)
        kullanici = {"kayitli_mi": True, "hedef_kalori": profil_kisitlari.get("hedef_kalori", 2000)}

        if not profil_kisitlari:
            kullanici = kullanici_kontrol_et(user_email)

        if not kullanici.get("kayitli_mi"):
            return {
                "status": "error",
                "reply": "Lutfen once profil bilgilerini doldur, ardindan menundeki ogunleri guncelleyebilirim."
            }

        istenmeyen_yemek = llm_karari.get("istenmeyen_yemek")
        if not istenmeyen_yemek:
            exclude_foods = llm_karari.get("exclude_foods") or []
            istenmeyen_yemek = exclude_foods[0] if exclude_foods else None

        if not istenmeyen_yemek:
            return {
                "status": "success",
                "reply": "Hangi yemegi degistirecegimi anlayamadim. Gun, ogun ve yemek adini birlikte yazar misin?"
            }

        mevcut_sevilmeyenler = profil_kisitlari.get("sevilmeyenler") or []
        llm_sevilmeyenler = llm_karari.get("exclude_foods") or []
        sevilmeyenler = list(dict.fromkeys(mevcut_sevilmeyenler + llm_sevilmeyenler + [istenmeyen_yemek]))

        hedef_kalori = kullanici.get("hedef_kalori", 2000)
        alerjiler = list(dict.fromkeys((profil_kisitlari.get("alerjiler") or []) + (llm_karari.get("allergens", []) or [])))
        sevilenler = list(dict.fromkeys((profil_kisitlari.get("sevilenler") or []) + (llm_karari.get("include_foods", []) or [])))
        saglik_sorunlari = list(dict.fromkeys((profil_kisitlari.get("saglik_sorunlari") or []) + (llm_karari.get("health_conditions", []) or [])))
        diyet_turu = llm_karari.get("diet_type") or profil_kisitlari.get("diyet_turu") or "Standart"

        sonuc = haftalik_diyet_olustur(
            hedef_kalori=hedef_kalori,
            alerjiler=alerjiler,
            sevilmeyenler=sevilmeyenler,
            sevilenler=sevilenler,
            saglik_sorunlari=saglik_sorunlari,
            diyet_turu=diyet_turu,
            ai_data=llm_karari,
        )

        if sonuc.get("haftalik_plan"):
            aktif_menuyu_kaydet(user_email, sonuc)
            hedef_gun = llm_karari.get("hedef_gun")
            hedef_ogun = llm_karari.get("hedef_ogun") or llm_karari.get("meal_type")
            hedef_metni = " ".join(str(parca) for parca in [hedef_gun, hedef_ogun] if parca)
            if hedef_metni:
                reply = f"{hedef_metni} ogununu senin icin guncelliyorum. {istenmeyen_yemek} yeni planda disarida birakildi."
            else:
                reply = f"Menunu senin icin guncelledim. {istenmeyen_yemek} yeni planda disarida birakildi."

            return {
                "status": "success",
                "action": "menu_updated",
                "action_taken": "ogun_degistirildi",
                "reply": reply,
                "ai_data": llm_karari,
                "menuData": sonuc,
                "yeni_menu_verisi": sonuc
            }

        return {
            "status": "error",
            "reply": "Bu degisiklikle tam ve dengeli bir haftalik menu olusturamadim. Kisitlari biraz azaltabilir miyiz?"
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
        
        profil_kisitlari = profil_kisitlarini_cikar(profile)
        kullanici = {"kayitli_mi": True, "hedef_kalori": profil_kisitlari.get("hedef_kalori", 2000)}

        if not profil_kisitlari:
            kullanici = kullanici_kontrol_et(user_email)

        if not kullanici.get("kayitli_mi"):
            return {"status": "error", "reply": "Lütfen önce profil bilgilerini doldur, ardından sana özel bir menü oluşturabilirim."}
        
        hedef_kalori = kullanici.get("hedef_kalori", 2000)
        alerjiler = list(dict.fromkeys((profil_kisitlari.get("alerjiler") or []) + (llm_karari.get("allergens", []) or [])))
        sevilmeyenler = list(dict.fromkeys((profil_kisitlari.get("sevilmeyenler") or []) + (llm_karari.get("exclude_foods", []) or [])))
        sevilenler = list(dict.fromkeys((profil_kisitlari.get("sevilenler") or []) + (llm_karari.get("include_foods", []) or [])))
        diyet_turu = llm_karari.get("diet_type") or profil_kisitlari.get("diyet_turu") or "Standart"
        if not diyet_turu:
             diyet_turu = "Standart"
        saglik_sorunlari = list(dict.fromkeys((profil_kisitlari.get("saglik_sorunlari") or []) + (llm_karari.get("health_conditions", []) or [])))
        
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
                "action": "menu_created",
                "action_taken": "yeni_menu_olusturuldu",
                "reply": "Harika! Profiline ve kısıtlamalarına uygun 7 günlük menünü başarıyla oluşturdum. Menü sekmesinden veya ekrandan inceleyebilirsin.",
                "ai_data": llm_karari,
                "menuData": sonuc,
                "yeni_menu_verisi": sonuc
            }
        else:
            return {"status": "error", "reply": "Bu kısıtlamalara uygun tam bir menü oluşturamadım, biraz daha esnek olabilir miyiz?"}

    # ==========================================
    # 🎯 SENARYO 3: ALAKASIZ SORU / GÜVENLİK DUVARI
    # ==========================================
    elif intent == "bilgi_ver":
        from services import genel_bilgi_sorusunu_cevapla, sohbeti_kaydet
        
        # Kullanıcının sorusunu doğrudan Llama-3'e normal bir sohbet gibi soruyoruz
        llm_cevabi = genel_bilgi_sorusunu_cevapla(user_message, profile)
        
        # Sohbet geçmişini kaydet
        sohbeti_kaydet(user_email, user_message, llm_cevabi)
        
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
