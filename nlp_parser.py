# nlp_parser.py
import ollama
import json
from prompts import SYSTEM_PROMPT

def profil_baglam_mesaji(profile: dict | None) -> str:
    if not profile:
        return ""
    profile_text = json.dumps(profile, ensure_ascii=False, indent=2)
    return (
        "Sen uzman bir diyetisyensin. Karşındaki kullanıcının güncel profil bilgileri şunlardır: "
        f"{profile_text}\n"
        "Kullanıcı sana bir şey sorduğunda veya menü oluşturmanı istediğinde ASLA profil bilgilerini tekrar sorma, "
        "çünkü bu bilgiler zaten sistemde kayıtlı. Doğrudan bu profil verilerine ve kısıtlamalara uygun, "
        "empatik ve profesyonel cevaplar ver."
    )

def parse_user_intent(user_message: str, profile: dict | None = None) -> dict:
    """
    Kullanıcının mesajını alır, lokal LLM'e gönderir ve sadece JSON döndürmesini sağlar.
    (Entity Extraction & Intent Detection Modülü)
    """
    try:
        # Lokal modelimize (örneğin llama3) istek atıyoruz.
        # format="json" parametresi, modelin JSON dışında bir şey üretmesini donanımsal olarak engeller!
        router_prompt = (
            SYSTEM_PROMPT
            + "\n\nKATI ROUTING KURALI: Sen bir asistansın ama menü üreticisi değilsin. "
            "Eğer kullanıcı diyet listesi, haftalık menü, beslenme planı veya menü oluşturmanı isterse "
            "ASLA kendi kafandan menü verisi, gün isimleri, öğünler veya JSON menü üretme. "
            "Sadece niyet ayrıştırması yap ve JSON içinde intent alanını kesinlikle 'yeni_menu_olustur' yap. "
            "İstersen target_service alanına 'INTENT_GENERATE_MENU' yaz. Menü üretimini yalnızca backend PuLP motoru yapacaktır."
        )

        response = ollama.chat(
            model='llama3', 
            messages=[
                {'role': 'system', 'content': router_prompt},
                {'role': 'system', 'content': profil_baglam_mesaji(profile) or "Kullanıcının profil bilgileri bu istekte yoksa profil eksik kabul edilebilir."},
                {'role': 'user', 'content': user_message}
            ],
            format='json' # EN KRİTİK NOKTA!
        )
        
        # Modelden dönen metni gerçek bir Python sözlüğüne (Dict) çeviriyoruz.
        raw_json_str = response['message']['content']
        parsed_data = json.loads(raw_json_str)
        
        return parsed_data

    except json.JSONDecodeError:
        # Eğer model inat edip JSON formatını bozarsa sistem çökmesin diye Fallback (Güvenlik ağı)
        return {
            "intent": "alakasiz_soru",
            "confidence": 0.0,
            "target_service": "fallback",
            "operation": "none",
            "error": "Model gecerli bir JSON uretemedi."
        }

# --- TEST EDELİM ---
if __name__ == "__main__":
    test_mesaji = "Yarın öğle yemeğinde makarna yemek istemiyorum, bana bol proteinli bir şeyler ver."
    sonuc = parse_user_intent(test_mesaji)
    
    print("--- LLM'DEN DÖNEN YAPILANDIRILMIŞ KARAR PAKETİ ---")
    print(json.dumps(sonuc, indent=4, ensure_ascii=False))
