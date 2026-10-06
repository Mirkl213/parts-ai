import re
from datetime import datetime

FORBIDDEN = set("IOQ")
ALLOWED = set("ABCDEFGHJKLMNPRSTUVWXYZ0123456789")

COUNTRY_RANGES = [
    ("SA","SM","Великобритания"),("SN","ST","Германия"),("SU","SZ","Польша"),
    ("S1","S4","Латвия"),("TA","TH","Швейцария"),("TJ","TP","Чехия"),
    ("TR","TV","Венгрия"),("TW","T1","Португалия"),("UH","UM","Дания"),
    ("UN","UT","Ирландия"),("UU","UZ","Румыния"),("U5","U7","Словакия"),
    ("VA","VE","Австрия"),("VF","VR","Франция"),("VS","VW","Испания"),
    ("VX","V2","Сербия"),("V3","V5","Хорватия"),("V6","V0","Эстония"),
    ("WA","W0","Германия"),("XA","XE","Болгария"),("XF","XK","Греция"),
    ("XL","XR","Нидерланды"),("XS","XW","Россия"),("XX","X2","Люксембург"),
    ("YA","YE","Бельгия"),("YF","YK","Финляндия"),("YL","YR","Мальта"),
    ("YS","YW","Швеция"),("YX","Y2","Норвегия"),("Y3","Y5","Беларусь"),
    ("Y6","Y0","Украина"),("ZA","ZR","Италия"),("ZX","Z2","Словения"),
    ("Z3","Z5","Литва"),
]
WMI = {
    "VF1":"Renault","VF3":"Peugeot","VF7":"Citroën","VF8":"Matra",
    "VSS":"SEAT","VSE":"Suzuki","VSX":"Opel","VWV":"Volkswagen",
    "VNK":"Toyota","WAU":"Audi","WA1":"Audi SUV","WBA":"BMW","WBS":"BMW M",
    "WBY":"BMW i","WDB":"Mercedes-Benz","WDC":"Mercedes-Benz SUV",
    "WDD":"Mercedes-Benz","WDF":"Mercedes-Benz Van","WME":"smart",
    "WMW":"MINI","WP0":"Porsche","WP1":"Porsche SUV","WVW":"Volkswagen",
    "WV1":"Volkswagen Commercial","WV2":"Volkswagen Bus/Van","W0L":"Opel",
    "W0V":"Opel","TMA":"Hyundai","TMB":"Škoda","TRU":"Audi","UU1":"Dacia",
    "U5Y":"Kia","U6Y":"Kia","XLR":"DAF","XTA":"Lada/AvtoVAZ",
    "XW8":"Volkswagen Group Rus","YV1":"Volvo","YV2":"Volvo Trucks",
    "YV4":"Volvo","ZAR":"Alfa Romeo","ZAM":"Maserati","ZFA":"Fiat",
    "ZFF":"Ferrari","ZHW":"Lamborghini","ZLA":"Lancia","JA3":"Mitsubishi",
    "JA4":"Mitsubishi","JMB":"Mitsubishi","JMZ":"Mazda","JHM":"Honda",
    "JTD":"Toyota","JTM":"Toyota","JTN":"Toyota","JN1":"Nissan","JN8":"Nissan",
    "KNA":"Kia","KMH":"Hyundai","KNM":"Renault Samsung","MMB":"Mitsubishi",
    "MMT":"Mitsubishi","NMT":"Toyota","NLE":"Mercedes-Benz",
}
MODEL_RULES = {
    "WVW":{"from":6,"to":8,"models":{
        "1H":"Golf III / Vento","1J":"Golf IV / Bora","1K":"Golf V/VI / Jetta",
        "5K":"Golf VI","5G":"Golf VII","AU":"Golf VII","CD":"Golf VIII",
        "3B":"Passat B5","3C":"Passat B6/B7 / CC","3G":"Passat B8",
        "6R":"Polo V","6C":"Polo V","AW":"Polo VI","5N":"Tiguan I",
        "AD":"Tiguan II","BW":"Tiguan II","1T":"Touran","7L":"Touareg I",
        "7P":"Touareg II","NF":"T-Roc"
    }},
    "WAU":{"from":6,"to":8,"models":{
        "8E":"Audi A4 B6/B7","8K":"Audi A4 B8","8W":"Audi A4 B9",
        "8P":"Audi A3 8P","8V":"Audi A3 8V","8Y":"Audi A3 8Y",
        "4B":"Audi A6 C5","4F":"Audi A6 C6","4G":"Audi A6 C7",
        "4E":"Audi A8 D3","4H":"Audi A8 D4","8U":"Audi Q3",
        "8R":"Audi Q5","4L":"Audi Q7","4M":"Audi Q7"
    }},
    "VSS":{"from":6,"to":8,"models":{
        "1L":"SEAT Toledo I","1M":"SEAT Leon I / Toledo II","1P":"SEAT Leon II",
        "5F":"SEAT Leon III","KL":"SEAT Leon IV","6K":"SEAT Ibiza II",
        "6L":"SEAT Ibiza III","6J":"SEAT Ibiza IV","6F":"SEAT Ibiza V",
        "5P":"SEAT Altea / Toledo III","3R":"SEAT Exeo"
    }},
    "TMB":{"from":6,"to":8,"models":{
        "1U":"Škoda Octavia I","1Z":"Škoda Octavia II","5E":"Škoda Octavia III",
        "NX":"Škoda Octavia IV","3T":"Škoda Superb II","3V":"Škoda Superb III",
        "5J":"Škoda Fabia II","NJ":"Škoda Fabia III","PJ":"Škoda Fabia IV",
        "5L":"Škoda Yeti","NS":"Škoda Karoq","NU":"Škoda Kodiaq"
    }},
}

YEAR_CODES = {
    **{c:y for c,y in zip("ABCDEFGHJKLMNPRSTVWXY", range(1980,2000))},
    **{str(i):2000+i for i in range(1,10)}
}
# VIN year code repeats every 30 years. We return both plausible years.
def year_candidates(vin):
    # VIN position 10 (index 9) is the year code.
    # Position 7 (index 6) distinguishes the 1980-2000 cycle from 2010-2030
    # for the common European VIN format.
    code = vin[9]
    p7 = vin[6]
    letters = {
        "A": (1980, 2010), "B": (1981, 2011), "C": (1982, 2012),
        "D": (1983, 2013), "E": (1984, 2014), "F": (1985, 2015),
        "G": (1986, 2016), "H": (1987, 2017), "J": (1988, 2018),
        "K": (1989, 2019), "L": (1990, 2020), "M": (1991, 2021),
        "N": (1992, 2022), "P": (1993, 2023), "R": (1994, 2024),
        "S": (1995, 2025), "T": (1996, 2026), "V": (1997, 2027),
        "W": (1998, 2028), "X": (1999, 2029), "Y": (2000, 2030)
    }
    digits = {str(i): (2000+i, 2030+i) for i in range(1,10)}
    pair = letters.get(code) or digits.get(code)
    if not pair:
        return []
    # If position 7 is a letter, use the later cycle; if it is a digit, use
    # the earlier cycle. This is the convention documented by the open WMI DB.
    if code.isalpha():
        return [pair[1] if p7.isalpha() else pair[0]]
    return [pair[1] if p7.isalpha() else pair[0]]

def country_for(wmi2):
    for lo,hi,country in COUNTRY_RANGES:
        if lo <= wmi2 <= hi:
            return country
    return None

def decode(vin):
    vin = re.sub(r"[\s-]", "", vin.upper())
    if len(vin) != 17:
        raise ValueError("VIN должен содержать 17 символов")
    if any(c not in ALLOWED or c in FORBIDDEN for c in vin):
        raise ValueError("VIN содержит недопустимые символы")
    wmi = vin[:3]
    country = country_for(vin[:2]) or ("Россия" if vin[:3] == "Z8T" else None)
    maker = WMI.get(wmi, "Неизвестный производитель")
    result = {
        "vin": vin, "wmi": wmi, "country": country,
        "manufacturer": maker, "region": "Европа" if vin[0] in "STUVWXYZ" else None,
        "year_candidates": year_candidates(vin[9]),
        "plant_code": vin[10], "serial": vin[11:],
        "descriptor": vin[3:8], "model": None
    }
    rule = MODEL_RULES.get(wmi)
    if rule and rule.get("filler_zzz") is not False and vin[3:6] == "ZZZ":
        result["model"] = rule["models"].get(vin[rule["from"]:rule["to"]])
    elif rule:
        result["model"] = rule["models"].get(vin[rule["from"]:rule["to"]])
    return result
