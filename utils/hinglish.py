"""Transliteration from Urdu (Perso-Arabic) and Hindi (Devanagari) to Roman Hinglish."""
from __future__ import annotations

import re

# Detect Perso-Arabic (Urdu) and Devanagari (Hindi) scripts
URDU_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
DEVA_RE = re.compile(r"[\u0900-\u097F]")

_STRIP_PUNCT = ".,!?;:\"\x27؟،()[]{}\u0964"

# Common Hindustani vocabulary in Urdu script mapped to standard conversational Hinglish
URDU_WORD_MAP: dict[str, str] = {
    # Modern / English Loanwords & Political terms
    'انڈین': 'Indian', 'جنزی': 'Gen-Z', 'الیکشن': 'election', 'کمیشن': 'commission',
    'کمشنر': 'commissioner', 'ریزائن': 'resign', 'پروٹسٹ': 'protest', 'پروٹیسٹ': 'protest',
    'پروٹیسٹرز': 'protesters', 'سمپل': 'simple', 'لیول': 'level', 'آفیسر': 'officer',
    'پرائم': 'prime', 'منسٹر': 'minister', 'چیف': 'chief', 'ایجوکیشن': 'education',
    'کیژولٹی': 'casualty', 'کژولٹی': 'casualty', 'اسٹوڈنٹس': 'students', 'اسٹیٹ': 'state',
    'سسٹم': 'system', 'پولیٹیکل': 'political', 'فیکٹ': 'fact', 'فیسینیٹ': 'fascinate',
    'رومنٹیسائز': 'romanticize', 'سولیوشن': 'solution', 'ہینڈل': 'handle', 'فائرنگ': 'firing',
    'رپورٹ': 'report', 'ایگزامپلز': 'examples', 'اسٹل': 'still', 'پی ٹی آئی': 'PTI',
    'ٹی ایل پی': 'TLP', 'ڈی چوک': 'D-Chowk', 'پریشر': 'pressure', 'بلڈ': 'build',
    'فیل': 'feel', 'فگر': 'figure', 'آؤٹ': 'out', 'بائیک': 'bike', 'کار': 'car',
    # Common conversational words
    'کوئی': 'koi', 'بھائی': 'bhai', 'نہیں': 'nahi', 'نکل': 'nikal', 'نکلے': 'nikle',
    'سمجھنے': 'samajhne', 'ضرورت': 'zaroorat', 'صرف': 'sirf', 'عوام': 'awaam',
    'روٹی': 'roti', 'کمانی': 'kamaani', 'گھنٹہ': 'ghanta', 'فرق': 'farq',
    'خواب': 'khwaab', 'چھوڑ': 'chhod', 'کوشش': 'koshish', 'واقعی': 'waqai',
    'نظر': 'nazar', 'ادھر': 'idhar', 'سبق': 'sabaq', 'اچھے': 'acche',
    'زندگی': 'zindagi', 'باتوں': 'baaton', 'عرش': 'arsh', 'زمین': 'zameen',

    'کچھ': 'kuch', 'ہر': 'har', 'ہم': 'hum', 'سب': 'sab', 'پہ': 'pe', 'پر': 'par',
    'جب': 'jab', 'تب': 'tab', 'کب': 'kab', 'اب': 'ab', 'سبھی': 'sabhi', 'ابھی': 'abhi',
    'تبھی': 'tabhi', 'کبھی': 'kabhi', 'ڈیزائن': 'design', 
    # Pronouns & pointers
    "یہ": "yeh", "وہ": "woh", "آپ": "aap", "تم": "tum", "تو": "tu", "میں": "main",
    "ہم": "hum", "اپنا": "apna", "اپنی": "apni", "اپنے": "apne", "اس": "is", "اسے": "ise",
    "اسکا": "iska", "اسکی": "iski", "اسکے": "iske", "ان": "in", "انہیں": "unhein",
    "انکا": "inka", "انکی": "inki", "انکے": "inke", "کون": "kaun", "کونسا": "kaunsa",
    "کونسی": "kaunsi", "کونسے": "kaunse", "کیا": "kya", "کیوں": "kyun", "کب": "kab",
    "کہاں": "kahan", "یہاں": "yahan", "وہاں": "wahan", "کیسے": "kaise", "کیسا": "kaisa",
    "کیسی": "kaisi", "کس": "kis", "کسے": "kise", "کسکا": "kiska", "کسکی": "kiski",

    # Postpositions & prepositions
    "کا": "ka", "کی": "ki", "کے": "ke", "کو": "ko", "سے": "se", "میں": "mein",
    "پر": "par", "پہ": "pe", "تک": "tak", "ساتھ": "saath", "پاس": "paas", "دور": "door",
    "اندر": "andar", "باہر": "baahar", "اوپر": "ooper", "نیچے": "neeche", "آگے": "aage",
    "پیچھے": "peeche", "سامنے": "saamne", "درمیان": "darmiyan", "بیچ": "beech",
    "بغیر": "baghair", "علاوہ": "elawa", "طرف": "taraf",

    # Conjunctions & discourse markers
    "اور": "aur", "لیکن": "lekin", "مگر": "magar", "اگر": "agar", "تو": "to",
    "بھی": "bhi", "ہی": "hi", "کہ": "ke", "کیونکہ": "kyunki", "اسلئے": "isliye",
    "اسلیے": "isliye", "یعنی": "yaani", "یا": "ya", "چاہے": "chahe",

    # Common verbs & auxiliaries
    "ہے": "hai", "ہیں": "hain", "تھا": "tha", "تھی": "thi", "تھے": "the",
    "ہو": "ho", "ہوا": "hua", "ہوئی": "hui", "ہوئے": "hue", "ہوتا": "hota",
    "ہوتی": "hoti", "ہوتے": "hote", "ہونا": "hona", "ہونے": "hone", "ہونی": "honi",
    "کرو": "karo", "کر": "kar", "کرتا": "karta", "کرتی": "karti", "کرتے": "karte",
    "کرنا": "karna", "کرنے": "karne", "کرنی": "karni", "کیا": "kiya",
    "مل": "mil", "ملتا": "milta", "ملتی": "milti", "ملتے": "milte", "ملا": "mila",
    "ملی": "mili", "ملے": "mile", "ملنا": "milna", "ملنے": "milne",
    "جاتا": "jata", "جاتی": "jati", "جاتے": "jate", "جا": "ja", "جاؤ": "jao",
    "جانا": "jaana", "جانے": "jaane", "گیا": "gaya", "گئی": "gayi", "گئے": "gaye",
    "آتا": "aata", "آتی": "aati", "آتے": "aate", "آ": "aa", "آؤ": "aao",
    "آنا": "aana", "آنے": "aane", "آیا": "aaya", "آئی": "aayi", "آئے": "aaye",
    "رہا": "raha", "رہی": "rahi", "رہے": "rahe", "رہتا": "rehta", "رہتی": "rehti",
    "رہتے": "rehte", "رہنا": "rehna", "رہنے": "rehne",
    "دیکھ": "dekh", "دیکھو": "dekho", "دیکھتے": "dekhte", "دیکھتا": "dekhta",
    "دیکھتی": "dekhti", "دیکھا": "dekha", "دیکھی": "dekhi", "دیکھے": "dekhe",
    "دیکھنا": "dekhna", "دیکھنے": "dekhne",
    "بول": "bol", "بولو": "bolo", "بولتا": "bolta", "بولتی": "bolti", "بولتے": "bolte",
    "بولا": "bola", "بولی": "boli", "بولے": "bole", "بولنا": "bolna",
    "کہہ": "keh", "کہو": "kaho", "کہتا": "kehta", "کہتی": "kehti", "کہتے": "kehte",
    "کہا": "kaha", "کہی": "kahi", "کہے": "kehe", "کہنا": "kehna",
    "بتا": "bata", "بتاؤ": "batao", "بتاتا": "batata", "بتاتی": "batati", "بتاتے": "batate",
    "بتایا": "bataya", "بتائی": "batayi", "بتائے": "bataye", "بتانا": "batana",
    "سمجھ": "samajh", "سمجھو": "samjho", "سمجھتا": "samajhta", "سمجھتے": "samajhte",
    "سمجھا": "samjha", "سمجھی": "samjhi", "سمجھے": "samjhe", "سمجھنا": "samajhna",
    "سوچ": "soch", "سوچو": "socho", "سوچتا": "sochta", "سوچتے": "sochte", "سوچا": "socha",
    "لگتا": "lagta", "لگتی": "lagti", "لگتے": "lagte", "لگا": "laga", "لگی": "lagi", "لگے": "lage",
    "سکھ": "seekh", "سیکھو": "seekho", "سیکھتا": "seekhta", "سیکھا": "seekha", "سیکھنا": "seekhna",
    "بن": "ban", "بنو": "bano", "بنتا": "banta", "بنتی": "banti", "بنتے": "bante",
    "بنا": "bana", "بنی": "bani", "بنے": "bane", "بننا": "banna",
    "بنایا": "banaya", "بنائی": "banayi", "بنائے": "banaye", "بنانا": "banana",
    "پڑتا": "padta", "پڑتی": "padti", "پڑتے": "padte", "پڑا": "pada", "پڑی": "padi", "پڑے": "pade",
    "سکتا": "sakta", "سکتی": "sakti", "سکتے": "sakte", "سکا": "saka", "سکی": "saki", "سکے": "sake",
    "چاہتا": "chahta", "چاہتی": "chahti", "چاہتے": "chahte", "چاہا": "chaha",
    "چاہئے": "chahiye", "چاہیے": "chahiye", "چاہئیں": "chahiyen",
    "بھیج": "bhej", "بھیجو": "bhejo", "بھیجتا": "bhejta", "بھیجتی": "bhejti", "بھیجتے": "bhejte",
    "بھیجا": "bheja", "بھیجی": "bheji", "بھیجے": "bheje", "بھیجنا": "bhejna",
    "لے": "le", "لو": "lo", "لیا": "liya", "لی": "li", "لیے": "liye", "لینا": "lena",
    "دے": "de", "دو": "do", "دیا": "diya", "دی": "di", "دینا": "dena",
    "رکھ": "rakh", "رکھو": "rakho", "رکھتا": "rakhta", "رکھا": "rakha", "رکھی": "rakhi", "رکھنا": "rakhna",
    "ڈال": "daal", "ڈالو": "daalo", "ڈالا": "daala", "ڈالی": "daali", "ڈالنا": "daalna",
    "نکال": "nikal", "نکالو": "nikalo", "نکالا": "nikala", "نکالنا": "nikalna",
    "اٹھا": "utha", "اٹھاؤ": "uthao", "اٹھایا": "uthaya", "اٹھالو": "uthalo",
    "چھوڑ": "chhod", "چھوڑو": "chhodo", "چھوڑا": "chhoda", "چھوڑنا": "chhodna",

    # Adjectives & Adverbs
    "اچھا": "accha", "اچھی": "acchi", "اچھے": "acche", "برا": "bura", "بری": "buri", "برے": "bure",
    "بڑا": "bada", "بڑی": "badi", "بڑے": "bade", "چھوٹا": "chhota", "چھوٹی": "chhoti", "چھوٹے": "chhote",
    "زیادہ": "zyada", "کم": "kam", "بہت": "bohot", "تھوڑا": "thoda", "تھوڑی": "thodi", "تھوڑے": "thode",
    "سارا": "saara", "ساری": "saari", "سارے": "saare", "سب": "sab", "پورا": "poora", "پوری": "poori",
    "صحیح": "sahi", "غلط": "ghalat", "ٹھیک": "theek", "آسان": "aasan", "مشکل": "mushkil",
    "جلدی": "jaldi", "آہستہ": "aahista", "تیز": "tez", "پہلے": "pehle", "بعد": "baad",
    "اب": "ab", "ابھی": "abhi", "تب": "tab", "تبھی": "tabhi", "کبھی": "kabhi", "ہمیشہ": "hamesha",
    "ضرور": "zaroor", "شاید": "shayad", "بلکل": "bilkul", "بالکل": "bilkul", "خاص": "khaas",
    "عام": "aam", "سچ": "sach", "جھوٹ": "jhooth", "تقریباً": "taqreeban", "تقریبا": "taqreeban",
    "اکیلا": "akela", "اکیلی": "akeli", "اکیلے": "akele", "خود": "khud",

    # Nouns & Common Words
    "بات": "baat", "باتیں": "baatein", "کام": "kaam", "چیز": "cheez", "چیزیں": "cheezein",
    "جگہ": "jagah", "وجہ": "wajah", "طریقہ": "tareeqa", "وقت": "waqt", "ٹائم": "time",
    "دن": "din", "رات": "raat", "سال": "saal", "مہینہ": "maheena", "گھنٹہ": "ghanta",
    "منٹ": "minute", "سیکنڈ": "second", "سیکنڈز": "seconds", "ہزار": "hazar", "ہزاروں": "hazaron",
    "لاکھ": "lakh", "کروڑ": "crore", "شہر": "shehar", "ملک": "mulk", "لوگ": "log",
    "دوست": "dost", "گھر": "ghar", "گاڑی": "gaadi", "راستہ": "raasta", "سوال": "sawaal",
    "جواب": "jawaab", "فائدہ": "faayda", "نقصان": "nuqsaan", "نام": "naam", "پتہ": "pata",
    "معلوم": "maloom", "ضرورت": "zaroorat", "امید": "umeed", "شکریہ": "shukriya",

    # Numbers
    "ایک": "ek", "دو": "do", "تین": "teen", "چار": "char", "فور": "four",
    "پانچ": "paanch", "چھ": "che", "سات": "saat", "آٹھ": "aath", "نو": "nau", "دس": "das",

    # Technology & App Terms (common in reels)
    "اوبر": "Uber", "کیاب": "cab", "کاب": "cab", "ریکویس": "request", "ریکویسٹ": "request",
    "ڈرائیور": "driver", "ڈرائیورز": "drivers", "لوکیشن": "location", "فائن": "find",
    "فائنڈ": "find", "آبویس": "obvious", "آئیڈیا": "idea", "کسٹمر": "customer",
    "ڈسٹنس": "distance", "سسٹم": "system", "ڈیٹا": "data", "ویڈیو": "video",
    "فون": "phone", "موبائل": "mobile", "انٹرنیٹ": "internet", "سرور": "server",
    "کوڈ": "code", "پروڈکٹ": "product", "سروس": "service", "چیک": "check",
    "کلک": "click", "شیئر": "share", "لائک": "like", "فالو": "follow",
    "لنک": "link", "اکاؤنٹ": "account", "میسج": "message", "پوسٹ": "post",
    "ریل": "reel", "فائل": "file", "نوٹ": "note", "ٹیکسٹ": "text",
}

URDU_CHAR_MAP: dict[str, str] = {
    'چھ': 'chh', 'کھ': 'kh', 'گھ': 'gh', 'جھ': 'jh', 'ٹھ': 'th', 'ڈھ': 'dh',
    'پھ': 'ph', 'تھ': 'th', 'دھ': 'dh', 'بھ': 'bh', 
    "آ": "aa", "ا": "a", "ب": "b", "پ": "p", "ت": "t", "ٹ": "t", "ث": "s",
    "ج": "j", "چ": "ch", "ح": "h", "خ": "kh", "د": "d", "ڈ": "d", "ذ": "z",
    "ر": "r", "ڑ": "r", "ز": "z", "ژ": "zh", "س": "s", "ش": "sh", "ص": "s",
    "ض": "z", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "q",
    "ک": "k", "گ": "g", "ل": "l", "م": "m", "ن": "n", "ں": "n", "و": "o",
    "ہ": "h", "ھ": "h", "ء": "", "ئ": "i", "ؤ": "o", "ۂ": "h", "ی": "i", "ے": "e", "ۃ": "t",
    "َ": "a", "ِ": "i", "ُ": "u", "ً": "an", "ّ": "", "ْ": ""
}

# Common Devanagari Hindi vocabulary mapped to Hinglish
DEVA_WORD_MAP: dict[str, str] = {
    "उबर": "Uber", "कैब": "cab", "रिक्वेस्ट": "request", "करो": "karo", "और": "aur",
    "कुछ": "kuch", "ही": "hi", "सेकंड": "second", "में": "mein", "ड्राइवर": "driver",
    "ड्राइवर्स": "drivers", "मिल": "mil", "जाता": "jata", "जाते": "jate", "जाती": "jati",
    "है": "hai", "हैं": "hain", "लेकिन": "lekin", "शहर": "shehar", "हज़ारों": "hazaron",
    "हजारों": "hazaron", "हर": "har", "तकरीबन": "taqreeban", "बाद": "baad", "अपनी": "apni",
    "अपना": "apna", "अपने": "apne", "लोकेशन": "location", "भेज": "bhej", "रहा": "raha",
    "رہی": "rahi", "रहे": "rahe", "होता": "hota", "होती": "hoti", "होते": "hote",
    "तो": "to", "सही": "sahi", "इतनी": "itni", "इतना": "itna", "इतने": "itne",
    "जल्दी": "jaldi", "करता": "karta", "करती": "karti", "करते": "karte", "कैसे": "kaise",
    "कैसा": "kaisa", "कैसी": "kaisi", "चलो": "chalo", "देखते": "dekhte", "देखो": "dekho",
    "देख": "dekh", "देखा": "dekha", "सब": "sab", "से": "se", "यह": "yeh", "वह": "woh",
    "आप": "aap", "की": "ki", "का": "ka", "के": "ke", "को": "ko", "निकालो": "nikalo",
    "जो": "jo", "कम": "kam", "ज्यादा": "zyada", "ज़्यादा": "zyada", "हो": "ho",
    "वही": "wahi", "उठा": "utha", "लो": "lo", "उठाओ": "uthao", "अब": "ab",
    "अकेला": "akela", "अकेले": "akele", "अकेली": "akeli", "कस्टमर": "customer",
    "लोग": "log", "साथ": "saath", "कर": "kar", "भी": "bhi", "नहीं": "nahi",
    "एक": "ek", "दो": "do", "तीन": "teen", "चार": "char", "पाँच": "paanch",
    "क्या": "kya", "क्यों": "kyun", "कब": "kab", "कहाँ": "kahan", "यहाँ": "yahan",
    "वहाँ": "wahan", "कोई": "koi", "बहुत": "bohot", "थोड़ा": "thoda", "अच्छा": "accha",
    "बात": "baat", "काम": "kaam", "चीज़": "cheez", "वक्त": "waqt", "टाइम": "time",
    "सवाल": "sawaal", "जवाब": "jawaab", "करना": "karna", "देना": "dena", "लेना": "lena",
    "बताना": "batana", "लगता": "lagta", "आता": "aata", "आया": "aaya", "जाना": "jaana",
    "गया": "gaya", "रहना": "rehna", "रखना": "rakhna", "सीखना": "seekhna", "बनाना": "banana",
    "ज़रूर": "zaroor", "जरूर": "zaroor", "शायद": "shayad", "बिल्कुल": "bilkul",
    "हमेशा": "hamesha", "कभी": "kabhi", "अभी": "abhi", "जैसे": "jaise", "वैसे": "waise",
    "क्योंकि": "kyunki", "इसलिए": "isliye", "अगर": "agar", "मगर": "magar",
    "अंदर": "andar", "बाहर": "baahar", "ऊपर": "ooper", "नीचे": "neeche", "सामने": "saamne",
    "ठीक": "theek", "गाड़ी": "gaadi", "सिस्टम": "system", "डेटा": "data", "वीडियो": "video",
    "फोन": "phone", "कोड": "code", "प्रॉडक्ट": "product", "सर्विस": "service", "चेक": "check"
}

DEVA_CONSONANTS: dict[str, str] = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f"
}

DEVA_VOWELS: dict[str, str] = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au"
}

DEVA_MATRAS: dict[str, str] = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ं": "n", "ँ": "n", "ः": "h"
}

def transliterate_urdu_word(word: str) -> str:
    clean = word.strip(_STRIP_PUNCT)
    punct_after = word[len(clean):] if word.startswith(clean) else ""
    punct_before = word[:len(word) - len(clean) - len(punct_after)]
    # Normalize Arabic punctuation
    punct_after = punct_after.replace("؟", "?").replace("،", ",")
    punct_before = punct_before.replace("؟", "?").replace("،", ",")
    if clean in URDU_WORD_MAP:
        return punct_before + URDU_WORD_MAP[clean] + punct_after
    res = "".join(URDU_CHAR_MAP.get(c, c) for c in clean)
    return punct_before + res + punct_after

def transliterate_deva_word(word: str) -> str:
    clean = word.strip(_STRIP_PUNCT)
    punct_after = word[len(clean):] if word.startswith(clean) else ""
    punct_before = word[:len(word) - len(clean) - len(punct_after)]
    punct_after = punct_after.replace("।", ".")
    punct_before = punct_before.replace("।", ".")
    if clean in DEVA_WORD_MAP:
        return punct_before + DEVA_WORD_MAP[clean] + punct_after

    chars = list(clean)
    out: list[str] = []
    i = 0
    n = len(chars)
    while i < n:
        c = chars[i]
        if c in DEVA_VOWELS:
            out.append(DEVA_VOWELS[c])
        elif c in DEVA_CONSONANTS:
            cons = DEVA_CONSONANTS[c]
            if i + 1 < n:
                nxt = chars[i + 1]
                if nxt == "्":
                    out.append(cons)
                    i += 1
                elif nxt in DEVA_MATRAS:
                    out.append(cons + DEVA_MATRAS[nxt])
                    i += 1
                elif nxt in DEVA_CONSONANTS or nxt in DEVA_VOWELS:
                    out.append(cons + "a")
                else:
                    out.append(cons)
            else:
                out.append(cons)
        elif c in DEVA_MATRAS:
            out.append(DEVA_MATRAS[c])
        else:
            out.append(c)
        i += 1
    return punct_before + "".join(out) + punct_after

def to_hinglish(text: str) -> str:
    """Convert text containing Urdu or Devanagari script into natural Roman Hinglish."""
    if not text:
        return ""
    has_urdu = bool(URDU_RE.search(text))
    has_deva = bool(DEVA_RE.search(text))
    if not (has_urdu or has_deva):
        return text

    words = text.split()
    converted_words: list[str] = []
    for w in words:
        if URDU_RE.search(w):
            converted_words.append(transliterate_urdu_word(w))
        elif DEVA_RE.search(w):
            converted_words.append(transliterate_deva_word(w))
        else:
            converted_words.append(w)
    return " ".join(converted_words)
