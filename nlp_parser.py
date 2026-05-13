# nlp_parser.py
import ollama
import json
from prompts import SYSTEM_PROMPT

def parse_user_intent(user_message: str) -> dict:
    """
    Kullanıcının mesajını alır, lokal LLM'e gönderir ve sadece JSON döndürmesini sağlar.
    (Entity Extraction & Intent Detection Modülü)
    """
    try:
        # Lokal modelimize (örneğin llama3) istek atıyoruz.
        # format="json" parametresi, modelin JSON dışında bir şey üretmesini donanımsal olarak engeller!
        response = ollama.chat(
            model='llama3', 
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
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