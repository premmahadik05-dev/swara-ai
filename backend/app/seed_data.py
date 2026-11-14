"""Synthetic demo catalogue for a Gujarati kirana store.

All data here is invented for demonstration: product names are generic (no brands),
prices are plausible-but-fictional, and no customer data is involved.
Gujarati / Hindi names should be reviewed by a native speaker before production use.
"""
from __future__ import annotations

from typing import Any

# keys: sku, en, gu, hi, cat, unit, price (INR per unit), stock, reorder, aliases, default_for,
#       pack_size, pack_size_unit


def _p(sku, en, gu, hi, cat, unit, price, stock, reorder, aliases, default_for=None, pack=None, pack_unit=None):
    return {
        "sku": sku, "name_en": en, "name_gu": gu, "name_hi": hi, "category": cat, "unit": unit,
        "price": price, "stock": stock, "reorder_level": reorder,
        "aliases": aliases, "default_for": default_for or [],
        "pack_size": pack, "pack_size_unit": pack_unit,
    }


_DAL = ["dal", "daal", "દાળ", "दाल"]
_OIL = ["oil", "tel", "તેલ", "तेल"]
_BISC = ["biscuit", "biscuits", "biscut", "બિસ્કિટ", "બિસ્કીટ", "बिस्कुट", "बिस्किट"]
_SOAP = ["soap", "sabun", "sabu", "સાબુ", "साबुन"]

CATALOG: list[dict[str, Any]] = [
    # ---- grains & flour
    _p("RICE-REGULAR", "Rice", "ચોખા", "चावल", "Grains & Flour", "kg", 58, 120, 25,
       ["rice", "chawal", "chaval", "chokha", "chokhaa", "ચોખા", "ચાવલ", "चावल"]),
    _p("RICE-BASMATI", "Basmati Rice", "બાસમતી ચોખા", "बासमती चावल", "Grains & Flour", "kg", 120, 60, 15,
       ["basmati rice", "basmati", "basmati chawal", "basmati chokha", "બાસમતી", "બાસમતી ચોખા", "बासमती", "बासमती चावल"]),
    _p("ATTA", "Wheat Flour (Atta)", "ઘઉંનો લોટ", "गेहूं का आटा", "Grains & Flour", "kg", 44, 150, 30,
       ["atta", "aata", "wheat flour", "wheat atta", "flour", "ghau no lot", "ghau nolot", "gehu ka atta", "lot",
        "ઘઉંનો લોટ", "ઘઉંનો", "ઘઉં", "લોટ", "આટો", "आटा", "गेहूं का आटा", "गेहूं", "ghau", "gehu"]),
    _p("MAIDA", "Maida (Refined Flour)", "મેંદો", "मैदा", "Grains & Flour", "kg", 40, 40, 10,
       ["maida", "meda", "mendo", "refined flour", "મેંદો", "મેંદા", "मैदा"]),
    _p("BESAN", "Besan (Gram Flour)", "ચણાનો લોટ", "बेसन", "Grains & Flour", "kg", 95, 35, 10,
       ["besan", "gram flour", "chana no lot", "chanano lot", "ચણાનો લોટ", "બેસન", "बेसन"]),
    _p("SUJI", "Semolina (Suji)", "રવો", "सूजी", "Grains & Flour", "kg", 52, 30, 8,
       ["suji", "sooji", "rava", "rawa", "ravo", "semolina", "સોજી", "રવો", "સુજી", "सूजी", "रवा"]),
    _p("POHA", "Poha (Flattened Rice)", "પૌંઆ", "पोहा", "Grains & Flour", "kg", 62, 45, 10,
       ["poha", "pauva", "pava", "flattened rice", "પૌંઆ", "પૌવા", "પોહા", "पोहा"]),
    _p("MAMRA", "Puffed Rice (Mamra)", "મમરા", "मुरमुरे", "Grains & Flour", "kg", 70, 20, 6,
       ["mamra", "murmura", "puffed rice", "મમરા", "मुरमुरे", "मुरमुरा"]),
    _p("SABUDANA", "Sabudana", "સાબુદાણા", "साबूदाना", "Grains & Flour", "kg", 85, 0, 8,
       ["sabudana", "sago", "સાબુદાણા", "साबूदाना"]),
    # ---- pulses
    _p("DAL-TOOR", "Toor Dal", "તુવેરની દાળ", "तूर दाल", "Pulses", "kg", 160, 70, 15,
       ["toor dal", "tuvar dal", "tur dal", "arhar dal", "toor", "tuver", "tuvar", "તુવેર દાળ", "તુવેરની દાળ", "તુવેર",
        "तूर दाल", "अरहर दाल", "तूर", *_DAL]),
    _p("DAL-MOONG", "Moong Dal", "મગની દાળ", "मूंग दाल", "Pulses", "kg", 120, 40, 10,
       ["moong dal", "mung dal", "moong", "mung", "મગની દાળ", "મગ દાળ", "મગ", "मूंग दाल", "मूंग", *_DAL]),
    _p("DAL-CHANA", "Chana Dal", "ચણાની દાળ", "चना दाल", "Pulses", "kg", 90, 40, 10,
       ["chana dal", "chane ki dal", "ચણાની દાળ", "ચણા દાળ", "चना दाल", "chana", "ચણા", "चना", *_DAL]),
    _p("DAL-URAD", "Urad Dal", "અડદની દાળ", "उड़द दाल", "Pulses", "kg", 130, 30, 8,
       ["urad dal", "udad dal", "urad", "અડદની દાળ", "અડદ દાળ", "અડદ", "उड़द दाल", "उड़द", *_DAL]),
    _p("KABULI", "Kabuli Chana (Chickpeas)", "કાબુલી ચણા", "काबुली चना", "Pulses", "kg", 110, 30, 8,
       ["kabuli chana", "chole", "chhole", "chickpeas", "કાબુલી ચણા", "છોલે", "काबुली चना", "छोले", "chana", "ચણા", "चना"]),
    _p("RAJMA", "Rajma", "રાજમા", "राजमा", "Pulses", "kg", 140, 5, 6,
       ["rajma", "kidney beans", "રાજમા", "राजमा"]),
    # ---- sugar, salt, tea
    _p("SUGAR", "Sugar", "ખાંડ", "चीनी", "Sugar, Salt & Tea", "kg", 46, 100, 25,
       ["sugar", "chini", "cheeni", "shakkar", "khand", "khaand", "ખાંડ", "સાકર", "चीनी", "शक्कर"]),
    _p("JAGGERY", "Jaggery", "ગોળ", "गुड़", "Sugar, Salt & Tea", "kg", 60, 40, 10,
       ["jaggery", "gud", "gur", "gol", "ગોળ", "गुड़"]),
    _p("SALT", "Salt", "મીઠું", "नमक", "Sugar, Salt & Tea", "kg", 22, 80, 20,
       ["salt", "namak", "mithu", "meethu", "મીઠું", "नमक"]),
    _p("TEA", "Tea Leaves (250 g pack)", "ચા પત્તી", "चायपत्ती", "Sugar, Salt & Tea", "pack", 120, 60, 15,
       ["tea", "chai", "chai patti", "chaipatti", "tea powder", "tea leaves", "ચા", "ચા પત્તી", "ચાની પત્તી",
        "चाय", "चायपत्ती", "चाय पत्ती"], pack="0.25", pack_unit="kg"),
    _p("COFFEE", "Instant Coffee (50 g jar)", "કોફી", "कॉफी", "Sugar, Salt & Tea", "pack", 165, 25, 6,
       ["coffee", "કોફી", "કૉફી", "कॉफी"]),
    # ---- oils & ghee
    _p("OIL-GROUNDNUT", "Groundnut Oil", "સીંગતેલ", "मूंगफली का तेल", "Oil & Ghee", "l", 185, 60, 15,
       ["groundnut oil", "peanut oil", "singtel", "sing tel", "સીંગતેલ", "સિંગતેલ", "मूंगफली का तेल", "मूंगफली तेल", *_OIL],
       default_for=["oil", "tel", "તેલ", "तेल", "edible oil"]),
    _p("OIL-SUNFLOWER", "Sunflower Oil", "સનફ્લાવર તેલ", "सूरजमुखी तेल", "Oil & Ghee", "l", 140, 40, 10,
       ["sunflower oil", "refined oil", "સનફ્લાવર તેલ", "રિફાઇન્ડ તેલ", "सनफ्लावर तेल", "सूरजमुखी का तेल", "सूरजमुखी तेल", *_OIL]),
    _p("OIL-MUSTARD", "Mustard Oil", "સરસવનું તેલ", "सरसों का तेल", "Oil & Ghee", "l", 165, 20, 6,
       ["mustard oil", "sarson oil", "sarson tel", "sarso ka tel", "સરસવનું તેલ", "સરસવ તેલ", "सरसों का तेल", "सरसों तेल", *_OIL]),
    _p("GHEE", "Ghee", "ઘી", "घी", "Oil & Ghee", "kg", 620, 25, 6, ["ghee", "ghi", "ઘી", "घी"]),
    _p("BUTTER", "Butter (100 g pack)", "માખણ", "मक्खन", "Oil & Ghee", "pack", 58, 40, 10,
       ["butter", "makhan", "makkhan", "માખણ", "બટર", "मक्खन", "बटर"]),
    # ---- dairy, eggs, bread
    _p("MILK", "Milk", "દૂધ", "दूध", "Dairy & Bakery", "l", 56, 90, 30, ["milk", "doodh", "dudh", "dood", "દૂધ", "दूध"]),
    _p("CURD", "Curd (Dahi)", "દહીં", "दही", "Dairy & Bakery", "kg", 70, 40, 10,
       ["curd", "dahi", "yogurt", "yoghurt", "દહીં", "दही"]),
    _p("PANEER", "Paneer", "પનીર", "पनीर", "Dairy & Bakery", "kg", 380, 3, 4, ["paneer", "cottage cheese", "પનીર", "पनीर"]),
    _p("EGGS", "Eggs", "ઈંડા", "अंडे", "Dairy & Bakery", "pc", 7, 180, 48,
       ["egg", "eggs", "anda", "ande", "ઈંડા", "ઈંડું", "ઇંડા", "अंडा", "अंडे"]),
    _p("BREAD", "Bread", "બ્રેડ", "ब्रेड", "Dairy & Bakery", "pack", 45, 35, 10,
       ["bread", "double roti", "બ્રેડ", "ब्रेड", "डबल रोटी"]),
    # ---- vegetables
    _p("ONION", "Onion", "ડુંગળી", "प्याज", "Vegetables", "kg", 32, 100, 25,
       ["onion", "onions", "pyaz", "pyaaj", "kanda", "dungli", "dungri", "ડુંગળી", "ડુંગરી", "प्याज", "कांदा"]),
    _p("POTATO", "Potato", "બટાકા", "आलू", "Vegetables", "kg", 28, 120, 30,
       ["potato", "potatoes", "aloo", "aalu", "batata", "bataka", "બટાકા", "બટાટા", "आलू"]),
    _p("TOMATO", "Tomato", "ટામેટા", "टमाटर", "Vegetables", "kg", 40, 60, 15,
       ["tomato", "tomatoes", "tamatar", "tameta", "ટામેટા", "ટમેટા", "टमाटर"]),
    _p("GARLIC", "Garlic", "લસણ", "लहसुन", "Vegetables", "kg", 180, 3.5, 4,
       ["garlic", "lehsun", "lahsun", "lasan", "લસણ", "लहसुन"]),
    _p("GINGER", "Ginger", "આદુ", "अदरक", "Vegetables", "kg", 120, 12, 4,
       ["ginger", "adrak", "adu", "aadu", "આદુ", "अदरक"]),
    _p("LEMON", "Lemon", "લીંબુ", "नींबू", "Vegetables", "kg", 90, 2, 3,
       ["lemon", "nimbu", "limbu", "લીંબુ", "नींबू"]),
    _p("BRINJAL", "Brinjal (Eggplant)", "રીંગણ", "बैंगन", "Vegetables", "kg", 50, 20, 6,
       ["brinjal", "eggplant", "baingan", "ringan", "રીંગણ", "बैंगन"]),
    _p("OKRA", "Okra (Bhindi)", "ભીંડા", "भिंडी", "Vegetables", "kg", 60, 20, 6,
       ["okra", "ladyfinger", "bhindi", "bhinda", "ભીંડા", "ભીંડી", "भिंडी"]),
    _p("CAULIFLOWER", "Cauliflower", "ફૂલકોબી", "फूलगोभी", "Vegetables", "kg", 40, 0, 5,
       ["cauliflower", "gobi", "phool gobi", "fulkobi", "ફૂલકોબી", "ફ્લાવર", "फूलगोभी", "गोभी"]),
    _p("GREEN-CHILLI", "Green Chillies", "લીલા મરચાં", "हरी मिर्च", "Vegetables", "kg", 80, 2.5, 3,
       ["green chilli", "green chillies", "green chili", "hari mirch", "lila marcha", "લીલા મરચાં", "લીલા મરચા", "हरी मिर्च"]),
    # ---- spices
    _p("TURMERIC", "Turmeric Powder", "હળદર", "हल्दी", "Spices", "kg", 240, 15, 4,
       ["turmeric", "haldi", "haldar", "હળદર", "हल्दी"]),
    _p("CHILLI-POWDER", "Red Chilli Powder", "લાલ મરચું", "लाल मिर्च", "Spices", "kg", 320, 15, 4,
       ["red chilli powder", "chilli powder", "chili powder", "lal mirch", "lal marcha", "mirch", "marcha",
        "લાલ મરચું", "મરચું", "लाल मिर्च", "मिर्च पाउडर", "मिर्च"]),
    _p("DHANA-JEERA", "Dhana Jeera Powder", "ધાણાજીરું", "धनिया जीरा पाउडर", "Spices", "kg", 180, 12, 4,
       ["dhana jeera", "dhanajiru", "dhanajeera", "coriander powder", "ધાણાજીરું", "ધાણા જીરું", "धनिया पाउडर", "धनिया जीरा"]),
    _p("CUMIN", "Cumin Seeds (Jeera)", "જીરું", "जीरा", "Spices", "kg", 420, 10, 3,
       ["jeera", "jira", "cumin", "cumin seeds", "જીરું", "जीरा"]),
    _p("MUSTARD-SEEDS", "Mustard Seeds (Rai)", "રાઈ", "राई", "Spices", "kg", 110, 1.5, 2,
       ["rai", "mustard seeds", "mustard seed", "રાઈ", "राई"]),
    _p("GARAM-MASALA", "Garam Masala (50 g pack)", "ગરમ મસાલો", "गरम मसाला", "Spices", "pack", 55, 30, 8,
       ["garam masala", "garam masala powder", "ગરમ મસાલો", "ગરમ મસાલા", "गरम मसाला", "masala", "મસાલો", "मसाला"]),
    # ---- snacks & biscuits
    _p("BISC-GLUCOSE", "Glucose Biscuits", "ગ્લુકોઝ બિસ્કિટ", "ग्लूकोज़ बिस्कुट", "Snacks", "pack", 10, 150, 40,
       ["glucose biscuit", "glucose biscuits", "ગ્લુકોઝ બિસ્કિટ", "ग्लूकोज बिस्कुट", *_BISC], default_for=list(_BISC)),
    _p("BISC-MARIE", "Marie Biscuits", "મેરી બિસ્કિટ", "मैरी बिस्कुट", "Snacks", "pack", 25, 70, 20,
       ["marie biscuit", "marie biscuits", "marie", "મેરી બિસ્કિટ", "મેરી", "मैरी बिस्कुट", *_BISC]),
    _p("BISC-CREAM", "Cream Biscuits", "ક્રીમ બિસ્કિટ", "क्रीम बिस्कुट", "Snacks", "pack", 30, 60, 15,
       ["cream biscuit", "cream biscuits", "ક્રીમ બિસ્કિટ", "क्रीम बिस्कुट", *_BISC]),
    _p("NOODLES", "Instant Noodles", "ઇન્સ્ટન્ટ નૂડલ્સ", "इंस्टेंट नूडल्स", "Snacks", "pack", 14, 120, 30,
       ["noodles", "instant noodles", "maggi", "નૂડલ્સ", "મેગી", "नूडल्स", "मैगी"]),
    _p("CHIPS", "Potato Chips", "વેફર્સ", "चिप्स", "Snacks", "pack", 20, 90, 25,
       ["chips", "wafers", "potato chips", "ચિપ્સ", "વેફર્સ", "चिप्स"]),
    _p("GATHIYA", "Gathiya", "ગાંઠિયા", "गाठिया", "Snacks", "kg", 320, 15, 4,
       ["gathiya", "ganthia", "gathia", "ગાંઠિયા", "ગાઠિયા", "गाठिया"]),
    _p("KHAKHRA", "Khakhra (pack)", "ખાખરા", "खाखरा", "Snacks", "pack", 40, 40, 10,
       ["khakhra", "khakhara", "ખાખરા", "खाखरा"]),
    _p("PAPAD", "Papad (pack)", "પાપડ", "पापड़", "Snacks", "pack", 45, 35, 10,
       ["papad", "papadam", "પાપડ", "पापड़"]),
    # ---- beverages
    _p("COLD-DRINK", "Cold Drink (750 ml bottle)", "કોલ્ડ ડ્રિંક", "कोल्ड ड्रिंक", "Beverages", "pc", 40, 60, 15,
       ["cold drink", "colddrink", "soft drink", "soda", "કોલ્ડ ડ્રિંક", "કોલ્ડડ્રિંક", "कोल्ड ड्रिंक"]),
    _p("WATER", "Packaged Water (1 L bottle)", "પાણીની બોટલ", "पानी की बोतल", "Beverages", "pc", 20, 80, 20,
       ["water bottle", "packaged water", "mineral water", "paani bottle", "પાણીની બોટલ", "પાણી બોટલ", "पानी की बोतल", "पानी बोतल"]),
    # ---- dry fruits & nuts
    _p("ALMOND", "Almonds", "બદામ", "बादाम", "Dry Fruits", "kg", 950, 2, 2, ["almond", "almonds", "badam", "બદામ", "बादाम"]),
    _p("RAISINS", "Raisins", "કિસમિસ", "किशमिश", "Dry Fruits", "kg", 420, 8, 2,
       ["raisins", "kishmish", "kismis", "કિસમિસ", "किशमिश"]),
    _p("PEANUTS", "Peanuts", "સીંગદાણા", "मूंगफली दाना", "Dry Fruits", "kg", 140, 30, 8,
       ["peanuts", "peanut", "singdana", "sing dana", "moongfali", "mungfali", "સીંગદાણા", "સિંગદાણા", "मूंगफली", "मूंगफली दाना"]),
    # ---- household
    _p("SOAP-BATH", "Bath Soap", "નહાવાનો સાબુ", "नहाने का साबुन", "Household", "pc", 38, 100, 25,
       ["bath soap", "nahane ka sabun", "નહાવાનો સાબુ", "नहाने का साबुन", *_SOAP], default_for=list(_SOAP)),
    _p("SOAP-DISH", "Dishwash Bar", "વાસણ ધોવાનો સાબુ", "बर्तन धोने का साबुन", "Household", "pc", 10, 90, 25,
       ["dishwash bar", "dishwash", "vasan sabun", "વાસણ ધોવાનો સાબુ", "बर्तन धोने का साबुन", *_SOAP]),
    _p("DETERGENT", "Detergent Powder", "ડિટર્જન્ટ પાવડર", "डिटर्जेंट पाउडर", "Household", "kg", 110, 50, 12,
       ["detergent", "detergent powder", "washing powder", "kapda powder", "ડિટર્જન્ટ", "ડિટર્જન્ટ પાવડર", "વોશિંગ પાવડર",
        "डिटर्जेंट", "वाशिंग पाउडर"]),
    _p("TOOTHPASTE", "Toothpaste", "ટૂથપેસ્ટ", "टूथपेस्ट", "Household", "pc", 95, 40, 10,
       ["toothpaste", "paste", "ટૂથપેસ્ટ", "टूथपेस्ट"]),
    _p("AGARBATTI", "Incense Sticks (pack)", "અગરબત્તી", "अगरबत्ती", "Household", "pack", 20, 50, 12,
       ["agarbatti", "incense", "incense sticks", "અગરબત્તી", "अगरबत्ती"]),
    _p("MATCHBOX", "Matchbox", "માચીસ", "माचिस", "Household", "pc", 2, 200, 60,
       ["matchbox", "matches", "machis", "માચીસ", "माचिस"]),
]

# Synthetic first names used only for demo orders (not real customers)
SYNTHETIC_CUSTOMERS = [
    "Demo Customer A", "Demo Customer B", "Demo Customer C", "Demo Customer D",
    "Demo Customer E", "Demo Customer F", "Demo Customer G", "Demo Customer H",
]
