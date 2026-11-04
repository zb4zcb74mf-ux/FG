"""إعدادات البوت — عدّل الأرقام هنا بدون ما تلمس باقي الكود."""
import os

TOKEN = os.getenv("DISCORD_TOKEN", "")

# اسم السيرفر/البنك الظاهر في أعلى الصور.
BANK_NAME = os.getenv("BANK_NAME", "SCAR")

# الشعار: يُؤخذ تلقائياً من صورة البوت (Avatar).
# لو وضعت ملف assets/logo.png يُستخدم بدلاً منها.
LOGO_FILE = "assets/logo.png"

DB_PATH = os.getenv("DB_PATH", "bank.db")

# اتركها فاضية ليشتغل البوت في كل القنوات، أو حط أرقام القنوات المسموحة
ALLOWED_CHANNEL_IDS: set[int] = set()

# من يقدر يستخدم أمر "منح": أرقام ديسكورد + صلاحية إدارة السيرفر + رتب المميزين
ADMIN_IDS: set[int] = set()
PREMIUM_ROLE_IDS: set[int] = set()

# ------------------------------------------------------------ الاقتصاد
MIN_BET = 100
LOAN_AMOUNT = 100_000

SALARY_COOLDOWN = 3 * 3600
SALARY_RANGE = (8_000, 20_000)
TIP_COOLDOWN = 30 * 60
TIP_RANGE = (500, 3_000)
STEAL_COOLDOWN = 15 * 60
LUCK_COOLDOWN = 3600

TRANSFER_TAX = 0.02          # ضريبة التحويل
STEAL_BASE_CHANCE = 0.45
STEAL_PERCENT = (0.05, 0.12) # نسبة المسروق من رصيد الضحية
STEAL_MAX = 250_000
STEAL_MIN_VICTIM = 2_000
STEAL_FINE = (5_000, 20_000) # غرامة لو فشلت

SHIELD_HOUR_COST = 15_000
SHIELD_MAX_HOURS = 5

MARRY_DEFAULT_MAHR = 10_000
DIVORCE_FEE = 20_000
MARRIED_SALARY_BONUS = 0.10

PERK_BOX_COST = 50_000
PERK_MAX_LEVEL = 5

MARKET_INTERVAL = 300        # كل كم ثانية تتغير أسعار المعادن

WHEEL_PRIZES = [5_000, 20_000, 100_000, 17_000, 60_000, 130_000]
WHEEL_WEIGHTS = [30, 20, 5, 25, 12, 8]

# ------------------------------------------------------------ المتجر
STORE_ITEMS = {
    "خاتم":   {"price": 20_000,     "icon": "ring"},
    "ساعة":   {"price": 50_000,     "icon": "watch"},
    "سيارة":  {"price": 250_000,    "icon": "car"},
    "فيلا":   {"price": 2_000_000,  "icon": "villa"},
    "يخت":    {"price": 10_000_000, "icon": "yacht"},
    "طيارة":  {"price": 50_000_000, "icon": "plane"},
}
ITEM_SELL_RATIO = 0.8
