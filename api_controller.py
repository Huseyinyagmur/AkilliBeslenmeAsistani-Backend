"""
api_controller.py — Hibrit NLP Intent Yönlendirici
====================================================
Mimari:
  Aşama 1 → Kural tabanlı Python string eşleştirme (Öğün > Gün > Tüm Menü)
  Aşama 2 → LLM fallback (yalnızca genel bilgi soruları için)
  Güvenlik → LLM çıktısı her zaman string formatına zorlanır; JSON sızıntısı engellenir
"""

import re
from nlp_parser import parse_user_intent

# ──────────────────────────────────────────────
# 1. KELIME SÖZLÜKLERİ
# ──────────────────────────────────────────────

GUNLER: dict[str, str] = {
    "pazartesi": "Pazartesi",
    "sali":      "Salı",
    "salı":      "Salı",
    "carsamba":  "Çarşamba",
    "çarşamba":  "Çarşamba",
    "persembe":  "Perşembe",
    "perşembe":  "Perşembe",
    "cuma":      "Cuma",
    "cumartesi": "Cumartesi",
    "pazar":     "Pazar",
}

OGUNLER: dict[str, str] = {
    "sabah":    "Sabah",
    "kahvalti": "Sabah",
    "kahvaltı": "Sabah",
    "ogle":     "Öğle",
    "öğle":     "Öğle",
    "aksam":    "Akşam",
    "akşam":    "Akşam",
    "ara":      "Ara_Öğün",
    "ara öğün": "Ara_Öğün",
    "ara ogun": "Ara_Öğün",
}

# Menü değiştirme niyeti tetikleyicileri
DEGISIM_KELIMELERI = [
    "değiştir", "degistir", "yenile", "başka", "baska",
    "farklı", "farkli", "çıkar", "cikar", "istemiyorum",
    "istmiyorum", "yerine", "güncelle", "guncelle",
]

# Yeni menü oluşturma tetikleyicileri
YENI_MENU_KELIMELERI_CIFT = [
    ("yeni", "menü"), ("yeni", "menu"),
    ("yeni", "diyet"), ("menü", "oluştur"),
    ("menu", "olustur"), ("diyet", "oluştur"),
    ("diyet", "olustur"), ("menü", "yap"),
    ("menu", "yap"), ("menü", "hazırla"),
    ("menu", "hazirla"), ("menü", "ver"),
    ("menu", "ver"), ("yeni", "liste"),
    ("haftalık", "oluştur"), ("haftalik", "olustur"),
]


# ──────────────────────────────────────────────
# 2. YARDIMCI FONKSİYONLAR
# ──────────────────────────────────────────────

def normalize(metin: str) -> str:
    """Türkçe karakterleri ASCII'ye indirgeyip küçük harf yapar."""
    return (
        str(metin or "").lower()
        .replace("ı", "i").replace("ö", "o").replace("ü", "u")
        .replace("ç", "c").replace("ş", "s").replace("ğ", "g")
        .replace("İ", "i").replace("Ö", "o").replace("Ü", "u")
        .replace("Ç", "c").replace("Ş", "s").replace("Ğ", "g")
    )


def gun_cikar(metin_norm: str) -> str | None:
    """Normalize edilmiş metinden gün adını çıkarır."""
    # Önce çift kelimeli eşleşmeler (örn: "çarşamba")
    for anahtar, gun in GUNLER.items():
        if normalize(anahtar) in metin_norm:
            return gun
    return None


def ogun_cikar(metin_norm: str) -> str | None:
    """Normalize edilmiş metinden öğün adını çıkarır."""
    # Çift kelimeli önce
    for anahtar in ["ara öğün", "ara ogun"]:
        if normalize(anahtar) in metin_norm:
            return "Ara_Öğün"
    for anahtar, ogun in OGUNLER.items():
        if normalize(anahtar) in metin_norm:
            return ogun
    return None


def degisim_var_mi(metin_norm: str) -> bool:
    """Mesajda değişim isteği var mı?"""
    return any(normalize(k) in metin_norm for k in DEGISIM_KELIMELERI)


def yeni_menu_istegi_var_mi(metin_norm: str) -> bool:
    """Mesajda yeni menü oluşturma isteği var mı?"""
    return any(
        normalize(a) in metin_norm and normalize(b) in metin_norm
        for a, b in YENI_MENU_KELIMELERI_CIFT
    )


def menu_json_sizintisi_mi(value) -> bool:
    """LLM çıktısında menü JSON'u var mı kontrol eder."""
    if isinstance(value, dict):
        yasakli = {"menu", "menuler", "ogunler", "gun", "haftalik_plan", "yemekler", "guncellemeler"}
        norm_keys = {normalize(k) for k in value.keys()}
        if norm_keys & yasakli:
            return True
        return any(menu_json_sizintisi_mi(v) for v in value.values())
    if isinstance(value, list):
        return any(isinstance(i, (dict, list)) or menu_json_sizintisi_mi(i) for i in value)
    return False


def guvenli_response(reply, action=None) -> dict:
    """Her zaman güvenli {reply, action} formatı döner."""
    if isinstance(reply, (dict, list)) or menu_json_sizintisi_mi(reply):
        reply = "Bunu tam anlayamadım, mevcut menünü baştan oluşturmamı ister misin?"
        action = None
    if not isinstance(reply, str):
        reply = str(reply or "")
    if action not in ("menu_created", "menu_updated", None):
        action = None
    return {"reply": reply, "action": action}


def profil_kisitlarini_cikar(profile: dict | None) -> dict:
    if not isinstance(profile, dict) or not profile:
        return {}
    secimler = profile.get("secimler") or {}
    fiziksel = profile.get("kullaniciFiziksel") or {}
    return {
        "hedef_kalori":    profile.get("yapayZekaHedefKalori") or fiziksel.get("hedef_kalori") or 2000,
        "alerjiler":       secimler.get("allergies") or secimler.get("alerjiler") or [],
        "sevilmeyenler":   secimler.get("dislikedFoods") or secimler.get("sevilmeyenler") or [],
        "sevilenler":      secimler.get("likedFoods") or secimler.get("sevilenler") or [],
        "saglik_sorunlari": secimler.get("healthIssues") or secimler.get("saglik_sorunlari") or [],
        "diyet_turu":      secimler.get("dietType") or secimler.get("diyet_turu") or "Standart",
    }


# ──────────────────────────────────────────────
# 3. BACKEND SERVİS ÇAĞRILARI
# ──────────────────────────────────────────────

def _profil_ile_haftalik_menu_uret(user_email: str, profile: dict | None, ai_data: dict | None = None) -> bool:
    """Haftalık menüyü profil kısıtlarıyla PuLP motoruna ürettirip kaydeder."""
    from services import aktif_menuyu_kaydet, haftalik_diyet_olustur, kullanici_kontrol_et

    ai_data = ai_data or {}
    kisitlar = profil_kisitlarini_cikar(profile)

    if kisitlar:
        kullanici = {"kayitli_mi": True, "hedef_kalori": kisitlar.get("hedef_kalori", 2000)}
    else:
        kullanici = kullanici_kontrol_et(user_email)

    if not kullanici.get("kayitli_mi"):
        return False

    sonuc = haftalik_diyet_olustur(
        hedef_kalori=kullanici.get("hedef_kalori", 2000),
        alerjiler=list(dict.fromkeys((kisitlar.get("alerjiler") or []) + (ai_data.get("allergens") or []))),
        sevilmeyenler=list(dict.fromkeys((kisitlar.get("sevilmeyenler") or []) + (ai_data.get("exclude_foods") or []))),
        sevilenler=list(dict.fromkeys((kisitlar.get("sevilenler") or []) + (ai_data.get("include_foods") or []))),
        saglik_sorunlari=list(dict.fromkeys((kisitlar.get("saglik_sorunlari") or []) + (ai_data.get("health_conditions") or []))),
        diyet_turu=ai_data.get("diet_type") or kisitlar.get("diyet_turu") or "Standart",
        ai_data=ai_data,
    )

    if sonuc.get("haftalik_plan"):
        aktif_menuyu_kaydet(user_email, sonuc)
        return True
    return False


def _tek_gun_menu_uret(user_email: str, profile: dict | None, hedef_gun: str) -> bool:
    """
    Mevcut haftalık menüyü DB'den çekip sadece hedef_gun'u yeniden üretir,
    sonra tüm planı geri kaydeder.
    """
    from services import (
        aktif_menuyu_getir, aktif_menuyu_kaydet,
        diyet_olustur, kullanici_kontrol_et,
    )

    kisitlar = profil_kisitlarini_cikar(profile)
    if kisitlar:
        hedef_kalori = kisitlar.get("hedef_kalori", 2000)
    else:
        kullanici = kullanici_kontrol_et(user_email)
        if not kullanici.get("kayitli_mi"):
            return False
        hedef_kalori = kullanici.get("hedef_kalori", 2000)

    mevcut = aktif_menuyu_getir(user_email)
    if not mevcut or not mevcut.get("haftalik_plan"):
        # Mevcut menü yoksa tamamen yeni üret
        return _profil_ile_haftalik_menu_uret(user_email, profile)

    yeni_gun_sonuc = diyet_olustur(
        hedef_kalori=hedef_kalori,
        alerjiler=kisitlar.get("alerjiler") or [],
        sevilmeyenler=kisitlar.get("sevilmeyenler") or [],
        saglik_sorunlari=kisitlar.get("saglik_sorunlari") or [],
        diyet_turu=kisitlar.get("diyet_turu") or "Standart",
        sevilenler=kisitlar.get("sevilenler") or [],
    )

    if yeni_gun_sonuc.get("durum") != "Başarılı":
        return False

    haftalik_plan = mevcut["haftalik_plan"]
    haftalik_plan[hedef_gun] = {
        "ogunler":    yeni_gun_sonuc["ogunler"],
        "gerceklesen": yeni_gun_sonuc["gerceklesen"],
    }
    aktif_menuyu_kaydet(user_email, {"durum": "Başarılı", "haftalik_plan": haftalik_plan})
    return True


def _tek_ogun_uret(user_email: str, profile: dict | None, hedef_gun: str, hedef_ogun: str) -> bool:
    """
    Mevcut haftalık menüden sadece hedef_gun'un hedef_ogun öğününü yeniler.
    """
    from services import (
        aktif_menuyu_getir, aktif_menuyu_kaydet,
        diyet_olustur, kullanici_kontrol_et,
    )

    kisitlar = profil_kisitlarini_cikar(profile)
    if kisitlar:
        hedef_kalori = kisitlar.get("hedef_kalori", 2000)
    else:
        kullanici = kullanici_kontrol_et(user_email)
        if not kullanici.get("kayitli_mi"):
            return False
        hedef_kalori = kullanici.get("hedef_kalori", 2000)

    mevcut = aktif_menuyu_getir(user_email)
    if not mevcut or not mevcut.get("haftalik_plan"):
        return _profil_ile_haftalik_menu_uret(user_email, profile)

    # Öğün için yeni tek günlük menü üret, sadece ilgili öğünü al
    yeni_gun_sonuc = diyet_olustur(
        hedef_kalori=hedef_kalori,
        alerjiler=kisitlar.get("alerjiler") or [],
        sevilmeyenler=kisitlar.get("sevilmeyenler") or [],
        saglik_sorunlari=kisitlar.get("saglik_sorunlari") or [],
        diyet_turu=kisitlar.get("diyet_turu") or "Standart",
        sevilenler=kisitlar.get("sevilenler") or [],
    )

    if yeni_gun_sonuc.get("durum") != "Başarılı":
        return False

    haftalik_plan = mevcut["haftalik_plan"]
    # Eğer gün yoksa boş oluştur
    if hedef_gun not in haftalik_plan:
        haftalik_plan[hedef_gun] = {"ogunler": {}, "gerceklesen": {}}

    # Sadece ilgili öğünü güncelle
    yeni_ogun_yemekleri = yeni_gun_sonuc["ogunler"].get(hedef_ogun, [])
    if not yeni_ogun_yemekleri:
        # Öğün adı eşleşmesi yoksa tüm günü yenile
        haftalik_plan[hedef_gun] = {
            "ogunler":    yeni_gun_sonuc["ogunler"],
            "gerceklesen": yeni_gun_sonuc["gerceklesen"],
        }
    else:
        haftalik_plan[hedef_gun]["ogunler"][hedef_ogun] = yeni_ogun_yemekleri

    aktif_menuyu_kaydet(user_email, {"durum": "Başarılı", "haftalik_plan": haftalik_plan})
    return True


# ──────────────────────────────────────────────
# 4. AŞAMA 1 — KURAL TABANLI INTENT TESPİTİ
# ──────────────────────────────────────────────

def kural_tabanli_intent_isle(user_message: str, user_email: str, profile: dict | None) -> dict | None:
    """
    Kademeli NLP tespiti:
      A. Selam / karşılama
      B. Yeni menü oluşturma
      C. Öğün değişimi (gün + öğün)
      D. Gün değişimi (sadece gün)
      E. Genel değişim (gün/öğün belirtilmemiş ama değiştirme niyeti var)
    Hiçbiri eşleşmezse None döner → LLM fallback'e geçilir.
    """
    metin = normalize(user_message)

    # A. KARŞILAMA
    if any(k in metin for k in ["selam", "merhaba", "nasilsin", "iyi misin"]):
        return guvenli_response("Merhaba! Ben senin beslenme asistanınım. Menün, tarifler veya sağlıklı yaşam hedeflerin hakkında yardımcı olabilirim. 😊", None)

    # B. YENİ MENÜ OLUŞTURMA
    if yeni_menu_istegi_var_mi(metin):
        basarili = _profil_ile_haftalik_menu_uret(user_email, profile, {"intent": "yeni_menu_olustur", "operation": "generate"})
        if basarili:
            return guvenli_response("Harika! 7 günlük tüm menünü yepyeni tariflerle ve profil ayarlarına göre baştan oluşturdum. Listeden kontrol edebilirsin! 🥗", "menu_created")
        return guvenli_response("Bu kısıtlamalarla yeni menü oluşturamadım. Kısıtlarını biraz azaltabilir miyiz?", None)

    # Değişim kelimesi var mı?
    if not degisim_var_mi(metin):
        return None  # → LLM fallback

    hedef_gun  = gun_cikar(metin)
    hedef_ogun = ogun_cikar(metin)

    # C. HEM GÜN HEM ÖĞÜN VAR → tek öğün güncelle
    if hedef_gun and hedef_ogun:
        basarili = _tek_ogun_uret(user_email, profile, hedef_gun, hedef_ogun)
        if basarili:
            return guvenli_response(
                f"{hedef_gun} günü {hedef_ogun} yemeğini senin için yeni alternatiflerle değiştirdim. Afiyet olsun! 🍽️",
                "menu_updated",
            )
        return guvenli_response(
            f"{hedef_gun} günü {hedef_ogun} öğününü değiştiremedim. Kısıtlarını biraz esnetebilir misin?",
            None,
        )

    # D. SADECE GÜN VAR → o günü tamamen yenile
    if hedef_gun:
        basarili = _tek_gun_menu_uret(user_email, profile, hedef_gun)
        if basarili:
            return guvenli_response(
                f"{hedef_gun} gününün tüm menüsünü baştan aşağı yeniledim. Listeden kontrol edebilirsin! ✅",
                "menu_updated",
            )
        return guvenli_response(
            f"{hedef_gun} günkü menüyü yenilemedim. Kısıtlarını biraz esnetebilir misin?",
            None,
        )

    # E. GENEL DEĞİŞİM (gün/öğün yok ama değiştirme niyeti var)
    basarili = _profil_ile_haftalik_menu_uret(user_email, profile, {"intent": "yeni_menu_olustur", "operation": "generate"})
    if basarili:
        return guvenli_response("Harika! 7 günlük tüm menünü yepyeni tariflerle baştan oluşturdum. 🥗", "menu_created")
    return guvenli_response("Bu kısıtlamalarla menüyü yenileyemedim. Kısıtlarını biraz azaltabilir miyiz?", None)


# ──────────────────────────────────────────────
# 5. AŞAMA 2 — LLM FALLBACK (SADECE BİLGİ SORULARI)
# ──────────────────────────────────────────────

def llm_fallback_cevabi(user_message: str, user_email: str, profile: dict | None) -> dict:
    """
    LLM'e yalnızca genel beslenme soruları gönderilir.
    LLM çıktısı string'e zorlanır; menü JSON'u sızarsa temizlenir.
    """
    try:
        parsed = parse_user_intent(user_message, profile)
    except Exception as exc:
        print(f"[LLM intent parser hatası]: {exc}")
        return guvenli_response("Bunu tam anlayamadım, mevcut menünü baştan oluşturmamı ister misin?", None)

    if not isinstance(parsed, dict) or menu_json_sizintisi_mi(parsed):
        return guvenli_response("Bunu tam anlayamadım, mevcut menünü baştan oluşturmamı ister misin?", None)

    intent     = parsed.get("intent")
    confidence = parsed.get("confidence", 0)

    # Güven eşiği düşükse genel yanıt
    if isinstance(confidence, (int, float)) and confidence < 0.55:
        return guvenli_response("Bunu tam anlayamadım, mevcut menünü baştan oluşturmamı ister misin?", None)

    # LLM yine de menü oluşturma intent'i döndürdüyse kural motoruna yönlendir
    if intent == "yeni_menu_olustur":
        basarili = _profil_ile_haftalik_menu_uret(user_email, profile, parsed)
        if basarili:
            return guvenli_response("Yeni menünü profil ayarlarına göre başarıyla oluşturdum!", "menu_created")
        return guvenli_response("Bu kısıtlamalarla yeni menü oluşturamadım. Kısıtları biraz azaltabilir miyiz?", None)

    if intent in ("gun_degistir", "ogun_degistir", "menuyu_guncelle"):
        hedef_gun  = parsed.get("hedef_gun")
        hedef_ogun = parsed.get("hedef_ogun")
        if hedef_gun and hedef_ogun:
            basarili = _tek_ogun_uret(user_email, profile, hedef_gun, hedef_ogun)
            msg = f"{hedef_gun} günü {hedef_ogun} yemeğini yeniden düzenledim. Afiyet olsun! 🍽️"
        elif hedef_gun:
            basarili = _tek_gun_menu_uret(user_email, profile, hedef_gun)
            msg = f"{hedef_gun} gününün tüm menüsünü yeniledim. Listeden kontrol edebilirsin! ✅"
        else:
            basarili = _profil_ile_haftalik_menu_uret(user_email, profile, parsed)
            msg = "İstediğin değişikliği menüne yaptım. Afiyet olsun! 🥗"

        if basarili:
            return guvenli_response(msg, "menu_updated")
        return guvenli_response("Bu değişiklikle menüyü güncelleyemedim. Kısıtları biraz azaltabilir miyiz?", None)

    # GENEL BİLGİ SORUSU — sadece metin yanıtı
    if intent == "bilgi_ver":
        try:
            from services import genel_bilgi_sorusunu_cevapla, sohbeti_kaydet
            llm_cevabi = genel_bilgi_sorusunu_cevapla(user_message, profile)
            if not isinstance(llm_cevabi, str) or menu_json_sizintisi_mi(llm_cevabi):
                return guvenli_response("Bunu tam anlayamadım, mevcut menünü baştan oluşturmamı ister misin?", None)
            sohbeti_kaydet(user_email, user_message, llm_cevabi)
            return guvenli_response(llm_cevabi, None)
        except Exception as exc:
            print(f"[LLM bilgi hatası]: {exc}")

    return guvenli_response("Bunu tam anlayamadım, mevcut menünü baştan oluşturmamı ister misin?", None)


# ──────────────────────────────────────────────
# 6. ANA CHAT ENDPOİNT (main.py tarafından çağrılır)
# ──────────────────────────────────────────────

def chat_endpoint_islemi(user_message: str, user_email: str, profile: dict | None = None) -> dict:
    """
    3 Aşamalı Hibrit NLP:
      1. Kural tabanlı Python tespiti (deterministik, LLM yok)
      2. LLM intent parsing (yalnızca genel sorular)
      3. Güvenli fallback
    """
    # AŞAMA 1: Kural tabanlı
    kural_sonucu = kural_tabanli_intent_isle(user_message, user_email, profile)
    if kural_sonucu is not None:
        return kural_sonucu

    # AŞAMA 2: LLM fallback (yalnızca bilgi soruları için)
    return llm_fallback_cevabi(user_message, user_email, profile)
