from nlp_parser import parse_user_intent
from senin_algoritma_dosyan import alternatif_yemek_bul_ml, diyet_olustur, aktif_menuyu_getir
import json

def chat_endpoint_islemi(user_message: str, user_email: str):
    """
    Kullanıcıdan gelen mesajı alır, LLM ile analiz eder ve 
    ilgili optimizasyon algoritmasını tetikleyerek nihai cevabı üretir.
    """
    # 1. NLP AYRIŞTIRICI (Lokal LLM'e gönder ve yapılandırılmış JSON al)
    llm_karari = parse_user_intent(user_message)
    
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
            return {"status": "success", "reply": "Hangi yemeği değiştirmek istediğini belirtmedin."}
            
        # Kullanıcının aktif menüsünü veritabanından çek
        aktif_menu = aktif_menuyu_getir(user_email)
        
        # TODO: Burada aktif menüden eski yemeğin ID'sini bulup KNN algoritmana göndereceğiz.
        # Örnek kullanım:
        # yeni_yemek = alternatif_yemek_bul_ml(eski_yemek_id, kategori, alerjiler, sevilmeyenler=cikarilacak_yemekler)
        
        return {
            "status": "success",
            "action_taken": "yemek_degistirildi",
            "reply": f"{', '.join(cikarilacak_yemekler)} menüden çıkarıldı. Yerine yeni alternatifler ekledim. Menünü arayüzden kontrol edebilirsin!",
            "ai_data": llm_karari # Frontend'in arayüzü güncellemesi için gerekli data
        }

    # ==========================================
    # 🎯 SENARYO 2: YENİ MENÜ OLUŞTURMA İSTEĞİ
    # ==========================================
    elif intent == "yeni_menu_olustur":
        diyet_tipi = llm_karari.get("diet_type", "Standart")
        sevilmeyenler = llm_karari.get("exclude_foods", [])
        
        # LLM'den gelen parametreleri doğrudan senin PuLP motoruna basıyoruz!
        # sonuc = diyet_olustur(hedef_kalori=2000, sevilmeyenler=sevilmeyenler, diyet_turu=diyet_tipi)
        
        return {
            "status": "success",
            "action_taken": "yeni_menu_olusturuldu",
            "reply": f"Harika! {diyet_tipi} diyetine uygun, {', '.join(sevilmeyenler)} içermeyen yepyeni bir menü hazırladım.",
            "ai_data": llm_karari
        }

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
