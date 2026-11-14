"""Reply templates for every language the app speaks: ``gu`` (Gujarati), ``hi`` (Hindi), ``hinglish`` (romanised), ``en``,
and (2.3.0) ``mr``, ``bn``, ``ta``, ``te``, ``kn``, ``ml``, ``pa`` from ``nlu/langpacks``.

Replies are plain text that is shown on screen *and* sent to Gnani Timbre for speech.
Numbers/currency are left as digits and ₹ because Timbre normalises them when the
language is set explicitly (docs: "Text Normalization Guide").
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .units import fmt_qty


_UNIT = {
    "en": {"kg": ("kg", "kg"), "g": ("g", "g"), "l": ("litre", "litres"), "ml": ("ml", "ml"),
           "pack": ("packet", "packets"), "pc": ("piece", "pieces")},
    "hinglish": {"kg": ("kilo", "kilo"), "g": ("gram", "gram"), "l": ("litre", "litre"), "ml": ("ml", "ml"),
                 "pack": ("packet", "packet"), "pc": ("piece", "piece")},
    "hi": {"kg": ("किलो", "किलो"), "g": ("ग्राम", "ग्राम"), "l": ("लीटर", "लीटर"), "ml": ("एमएल", "एमएल"),
           "pack": ("पैकेट", "पैकेट"), "pc": ("पीस", "पीस")},
    "gu": {"kg": ("કિલો", "કિલો"), "g": ("ગ્રામ", "ગ્રામ"), "l": ("લીટર", "લીટર"), "ml": ("એમએલ", "એમએલ"),
           "pack": ("પેકેટ", "પેકેટ"), "pc": ("નંગ", "નંગ")},
}
_AND = {"en": " and ", "hinglish": " aur ", "hi": " और ", "gu": " અને "}

T: dict[str, dict[str, str]] = {
    "greeting": {
        "en": "Namaste! What would you like to order?",
        "hinglish": "Namaste! Boliye, aapko kya chahiye?",
        "hi": "नमस्ते! बताइए, आपको क्या चाहिए?",
        "gu": "નમસ્તે! બોલો, તમને શું જોઈએ છે?",
    },
    "added": {
        "en": "Added {items}. Total so far {total}. Anything else?",
        "hinglish": "{items} add kar diya. Abhi tak ka total {total}. Aur kuch chahiye?",
        "hi": "{items} जोड़ दिया। अभी तक का कुल {total}। और कुछ चाहिए?",
        "gu": "{items} ઉમેર્યું. અત્યાર સુધીનું કુલ {total}. બીજું કંઈ જોઈએ છે?",
    },
    "added_only": {
        "en": "Added {items}.",
        "hinglish": "{items} add kar diya.",
        "hi": "{items} जोड़ दिया।",
        "gu": "{items} ઉમેર્યું.",
    },
    "updated": {
        "en": "Updated {items}.",
        "hinglish": "{items} update kar diya.",
        "hi": "{items} अपडेट कर दिया।",
        "gu": "{items} અપડેટ કર્યું.",
    },
    "assumed": {
        "en": "I took {product}; say another name to change it.",
        "hinglish": "Maine {product} liya hai; badalna ho to dusra naam boliye.",
        "hi": "मैंने {product} लिया है; बदलना हो तो दूसरा नाम बोलिए।",
        "gu": "મેં {product} લીધું છે; બદલવું હોય તો બીજું નામ બોલો.",
    },
    "confirm_summary": {
        "en": "Your order: {items}. Total {total}. Shall I confirm?",
        "hinglish": "Aapka order: {items}. Total {total}. Confirm kar doon?",
        "hi": "आपका ऑर्डर: {items}। कुल {total}। कन्फर्म कर दूँ?",
        "gu": "તમારો ઓર્ડર: {items}. કુલ {total}. કન્ફર્મ કરું?",
    },
    "confirmed": {
        "en": "Order number {num} is confirmed. Total {total}. Thank you!",
        "hinglish": "Order number {num} confirm ho gaya. Total {total}. Dhanyavaad!",
        "hi": "ऑर्डर नंबर {num} कन्फर्म हो गया। कुल {total}। धन्यवाद!",
        "gu": "ઓર્ડર નંબર {num} કન્ફર્મ થઈ ગયો. કુલ {total}. આભાર!",
    },
    "cancelled": {
        "en": "Okay, I have cancelled this order.",
        "hinglish": "Theek hai, order cancel kar diya.",
        "hi": "ठीक है, ऑर्डर रद्द कर दिया।",
        "gu": "ઠીક છે, ઓર્ડર રદ કર્યો.",
    },
    "need_qty": {
        "en": "How much {product} would you like?",
        "hinglish": "{product} kitna chahiye?",
        "hi": "{product} कितना चाहिए?",
        "gu": "{product} કેટલું જોઈએ છે?",
    },
    "need_unit": {
        "en": "How many {unit} of {product}?",
        "hinglish": "{product} kitne {unit} chahiye?",
        "hi": "{product} कितने {unit} चाहिए?",
        "gu": "{product} કેટલા {unit} જોઈએ?",
    },
    "confirm_unit": {
        "en": "{product} is sold per {unit}. Did you mean {qty} {unit}?",
        "hinglish": "{product} {unit} mein milta hai. {qty} {unit} chalega?",
        "hi": "{product} {unit} में मिलता है। क्या {qty} {unit} चलेगा?",
        "gu": "{product} {unit} માં મળે છે. {qty} {unit} ચાલશે?",
    },
    "unit_wrong": {
        "en": "{product} is sold per {unit}. How many {unit}?",
        "hinglish": "{product} {unit} mein milta hai. Kitne {unit} chahiye?",
        "hi": "{product} {unit} में मिलता है। कितने {unit} चाहिए?",
        "gu": "{product} {unit} માં મળે છે. કેટલા {unit} જોઈએ?",
    },
    "need_pack_count": {
        "en": "{product} comes in packs of {pack}. How many packs?",
        "hinglish": "{product} {pack} ke packet mein aata hai. Kitne packet chahiye?",
        "hi": "{product} {pack} के पैकेट में आता है। कितने पैकेट चाहिए?",
        "gu": "{product} {pack} ના પેકેટમાં આવે છે. કેટલા પેકેટ જોઈએ?",
    },
    "need_whole": {
        "en": "How many whole {unit} of {product}?",
        "hinglish": "{product} ke kitne poore {unit} chahiye?",
        "hi": "{product} के कितने पूरे {unit} चाहिए?",
        "gu": "{product} ના કેટલા આખા {unit} જોઈએ?",
    },
    "choose_product": {
        "en": "Which {generic}: {options}?",
        "hinglish": "Kaunsa {generic}: {options}?",
        "hi": "कौन सा {generic}: {options}?",
        "gu": "કયું {generic}: {options}?",
    },
    "out_of_stock": {
        "en": "Sorry, {product} is out of stock.",
        "hinglish": "Maaf kijiye, {product} khatam ho gaya hai.",
        "hi": "माफ़ कीजिए, {product} खत्म हो गया है।",
        "gu": "માફ કરશો, {product} ખતમ થઈ ગયું છે.",
    },
    "no_more_stock": {
        "en": "Sorry, no more {product} is available beyond what is in your cart.",
        "hinglish": "Maaf kijiye, {product} cart ke alawa aur nahi bacha.",
        "hi": "माफ़ कीजिए, {product} कार्ट के अलावा और नहीं बचा।",
        "gu": "માફ કરશો, {product} કાર્ટ સિવાય વધુ બાકી નથી.",
    },
    "confirm_partial": {
        "en": "We have only {avail} of {product}. Shall I add that much?",
        "hinglish": "{product} sirf {avail} bacha hai. Utna add kar doon?",
        "hi": "{product} सिर्फ़ {avail} बचा है। उतना जोड़ दूँ?",
        "gu": "{product} માત્ર {avail} બાકી છે. એટલું ઉમેરું?",
    },
    "unknown": {
        "en": "Sorry, I couldn't find '{term}' in our store.",
        "hinglish": "Maaf kijiye, '{term}' humare paas nahi mila.",
        "hi": "माफ़ कीजिए, '{term}' हमारे यहाँ नहीं मिला।",
        "gu": "માફ કરશો, '{term}' અમારી પાસે મળ્યું નથી.",
    },
    "confirm_suggestion": {
        "en": "I couldn't find '{term}'. Did you mean {product}?",
        "hinglish": "'{term}' nahi mila. Kya aapka matlab {product} hai?",
        "hi": "'{term}' नहीं मिला। क्या आपका मतलब {product} है?",
        "gu": "'{term}' મળ્યું નથી. શું તમારો મતલબ {product} છે?",
    },
    "removed": {
        "en": "Removed {items}.",
        "hinglish": "{items} hata diya.",
        "hi": "{items} हटा दिया।",
        "gu": "{items} કાઢી નાખ્યું.",
    },
    "not_in_cart": {
        "en": "{product} is not in your cart.",
        "hinglish": "{product} aapke cart mein nahi hai.",
        "hi": "{product} आपके कार्ट में नहीं है।",
        "gu": "{product} તમારા કાર્ટમાં નથી.",
    },
    "cart_empty": {
        "en": "Your cart is empty. What would you like?",
        "hinglish": "Aapka cart khali hai. Boliye, kya chahiye?",
        "hi": "आपका कार्ट खाली है। बताइए, क्या चाहिए?",
        "gu": "તમારું કાર્ટ ખાલી છે. બોલો, શું જોઈએ?",
    },
    "what_else": {
        "en": "Sure, what else would you like?",
        "hinglish": "Haan, aur kya chahiye?",
        "hi": "जी, और क्या चाहिए?",
        "gu": "હા, બીજું શું જોઈએ?",
    },
    "no_problem_change": {
        "en": "No problem. What would you like to change?",
        "hinglish": "Koi baat nahi. Kya badalna hai?",
        "hi": "कोई बात नहीं। क्या बदलना है?",
        "gu": "કંઈ વાંધો નહીં. શું બદલવું છે?",
    },
    "price_one": {
        "en": "{product} is {price} per {unit}.",
        "hinglish": "{product} {price} per {unit} hai.",
        "hi": "{product} {price} प्रति {unit} है।",
        "gu": "{product} {price} પ્રતિ {unit} છે.",
    },
    "price_qty": {
        "en": "{items} comes to {total}.",
        "hinglish": "{items} ka {total} hoga.",
        "hi": "{items} का {total} होगा।",
        "gu": "{items} ના {total} થશે.",
    },
    "price_oos": {
        "en": "It is currently out of stock.",
        "hinglish": "Abhi stock mein nahi hai.",
        "hi": "अभी स्टॉक में नहीं है।",
        "gu": "હાલમાં સ્ટોકમાં નથી.",
    },
    "didnt_understand": {
        "en": "Sorry, I didn't catch that. Please say the item and quantity, for example two kilo rice.",
        "hinglish": "Maaf kijiye, samajh nahi aaya. Item aur quantity boliye, jaise do kilo chawal.",
        "hi": "माफ़ कीजिए, समझ नहीं आया। आइटम और मात्रा बोलिए, जैसे दो किलो चावल।",
        "gu": "માફ કરશો, સમજાયું નહીં. વસ્તુ અને જથ્થો બોલો, જેમ કે બે કિલો ચોખા.",
    },
    "no_speech": {
        "en": "I couldn't hear anything. Please try again.",
        "hinglish": "Kuch sunai nahi diya. Phir se boliye.",
        "hi": "कुछ सुनाई नहीं दिया। फिर से बोलिए।",
        "gu": "કંઈ સંભળાયું નહીં. ફરી બોલો.",
    },
    "skipped": {
        "en": "Okay, skipped that.",
        "hinglish": "Theek hai, chhod diya.",
        "hi": "ठीक है, छोड़ दिया।",
        "gu": "ઠીક છે, છોડી દીધું.",
    },
    "stock_changed": {
        "en": "Sorry, stock changed while confirming. I adjusted your cart: {items}.",
        "hinglish": "Maaf kijiye, confirm karte waqt stock badal gaya. Cart adjust kiya: {items}.",
        "hi": "माफ़ कीजिए, कन्फर्म करते समय स्टॉक बदल गया। कार्ट ठीक किया: {items}।",
        "gu": "માફ કરશો, કન્ફર્મ કરતી વખતે સ્ટોક બદલાયો. કાર્ટ સુધાર્યું: {items}.",
    },
}


# ---- languages added in 2.3.0: templates, unit words and the "and" join come from the packs
from .langpacks import load_all as _load_packs  # noqa: E402

for _key, _pack in _load_packs().items():
    _UNIT[_key] = dict(_pack.unit_labels)
    _AND[_key] = _pack.and_join
    for _tk, _text in _pack.templates.items():
        T[_tk][_key] = _text
LANGS = ("gu", "hi", "hinglish", "en", *_load_packs())


def unit_label(lang: str, unit: str, qty: Decimal | None = None) -> str:
    sing, plur = _UNIT.get(lang, _UNIT["en"]).get(unit, (unit, unit))
    return plur if (qty is not None and qty != 1) else sing


def money(paise: int) -> str:
    rupees, p = divmod(paise, 100)
    return f"₹{rupees}" if p == 0 else f"₹{rupees}.{p:02d}"


def item_text(lang: str, name: str, qty: Decimal, unit: str) -> str:
    return f"{fmt_qty(qty)} {unit_label(lang, unit, qty)} {name}"


def join_items(lang: str, items: Iterable[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + _AND.get(lang, " and ") + items[-1]


def render(key: str, lang: str, **kw: object) -> str:
    tpl = T[key].get(lang) or T[key]["en"]
    return tpl.format(**kw)
