content = '''
        tdee = bmr * activity_multipliers.get(activity_level, 1.2)

        if goal in ['kilo_verme', 'kilo ver', 'Kilo Ver', 'lose_weight']:
            hedef_kalori = int(tdee - 400)
        elif goal in ['kilo_alma', 'kilo al', 'Kas Yap', 'gain_weight']:
            hedef_kalori = int(tdee + 400)
        else:
            hedef_kalori = int(tdee)
            
    if hedef_kalori < 1200:
        hedef_kalori = 1200
        
    alerjiler = [a.lower() for a in (alerjiler or [])]
    sevilmeyenler = [s.lower() for s in (sevilmeyenler or [])]
    sevilenler = [f.lower() for f in (sevilenler or [])]
    
    alerjiler_norm = [normalize_tr(a) for a in alerjiler]
    sevilmeyenler_norm = [normalize_tr(s) for s in sevilmeyenler]
    
    saglik_sorunlari = saglik_sorunlari or []
    if ai_data and ai_data.get('health_conditions'):
        saglik_sorunlari.extend(ai_data.get('health_conditions'))
    saglik_sorunlari_lower = [str(s).lower() for s in saglik_sorunlari]
'''
with open('c:/AkıllıBeslenmeAsistanı/Backend/services.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    
lines = lines[:89] + [content] + lines[110:]

with open('c:/AkıllıBeslenmeAsistanı/Backend/services.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
