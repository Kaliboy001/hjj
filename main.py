import asyncio
import os
import re
import httpx
import random
import phonenumbers
import aiofiles
import socket
from pymongo import MongoClient
from collections import OrderedDict
from datetime import datetime
from phonenumbers import geocoder, carrier, timezone, phonenumberutil
from telethon import TelegramClient, events
from telethon.tl.types import InputGeoPoint, InputMediaGeoPoint
from telethon.errors.rpcerrorlist import MessageNotModifiedError, FloodWaitError, ChannelInvalidError, UserBannedInChannelError
from telethon.tl.custom import Button
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.errors import UserNotParticipantError
from ratelimit import limits, sleep_and_retry
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import Dict
import logging

# --- CONFIGURATION ---
API_ID = os.environ.get('API_ID')
API_HASH = os.environ.get('API_HASH')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
PROXYCHECK_API_KEY = os.environ.get('PROXYCHECK_API_KEY', '')
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb+srv://mrshokrullah:L7yjtsOjHzGBhaSR@cluster0.aqxyz.mongodb.net/shajyhfs?retryWrites=true&w=majority&appName=Cluster')
BOT_USERNAME = os.environ.get('BOT_USERNAME', 'YourBotUsername')

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("Missing required environment variables: API_ID, API_HASH, BOT_TOKEN")

# MongoDB Setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client['bot_databnases']
users_collection = db['usehvgrss']

# Channel Configuration
MANDATORY_CHANNEL = "@shahhaka"  # Mandatory channel
OPTIONAL_CHANNEL = "@Channel2"   # Optional channel

# Referral and Credit Configuration
CREDIT_PER_REFERRAL = 1
INITIAL_CREDIT = 1

# --- CONSTANTS ---
IP_PATTERN = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
IP_API_URL = "http://ip-api.com/json/{ip}"
PROXYCHECK_API_URL = f"http://proxycheck.io/v2/{{ip}}?key={PROXYCHECK_API_KEY}&vpn=1"
DATA_FILE = "list.txt"
NUMBER_TYPE_MAP = {
    0: "FIXED_LINE", 1: "MOBILE", 2: "FIXED_LINE_OR_MOBILE", 3: "TOLL_FREE",
    4: "PREMIUM_RATE", 5: "SHARED_COST", 6: "VOIP", 7: "PERSONAL_NUMBER",
    8: "PAGER", 9: "UAN", 10: "VOICEMAIL", 27: "UNKNOWN"
}

# --- GLOBAL STATE ---
COUNTRY_DATABASE = {}

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- LANGUAGE TRANSLATIONS ---
LANGUAGES = {
    "en": {
        "choose_language": "**Choose your language:**",
        "lang_english": "English 🇬🇧",
        "lang_persian": "Persian 🇮🇷",
        "lang_spanish": "Spanish 🇪🇸",
        "mandatory_join": "🚫 **Please join our channel(s) to use the bot:**\n\n"
                         f"1. **Mandatory:** {MANDATORY_CHANNEL}\n"
                         f"2. **Optional:** {OPTIONAL_CHANNEL}",
        "join_channel_1": "Join Channel 1 📢",
        "join_channel_2": "Join Channel 2 📢",
        "check_joined": "Joined ✅",
        "not_joined_alert": "🚫 You haven't joined the mandatory channel yet. Please join first!",
        "menu_message": "**System Interface v24.0 (Realism Max)** 🕵️‍♂️🔍\n"
                       "│   ---===[ Welcome ]===---\n"
                       "A multi-tool bot for IP intelligence and phone tracing! 🚀\n"
                       "**Choose an option:**",
        "search_phone": "Search Phone Number 📞",
        "search_ip": "Search IP Address 🌐",
        "language_button": "Language 🌐",
        "account_info_button": "Account Info ℹ️",
        "back_to_menu": "Back to Menu 🔙",
        "enter_phone": "`>>> Enter a phone number (e.g., +12025550123) 📞`\n\n**Credit Amount:** `{}`",
        "enter_ip": "`>>> Enter an IP address (e.g., 192.168.1.1) 🌐`",
        "invalid_phone": "`>>> Error: Invalid phone number format or number. Use format like +12025550123 📞`",
        "invalid_ip": "`>>> Error: Please enter a valid IP address (e.g., 192.168.1.1) 🌐`",
        "send_phone": "`>>> Please send a phone number to trace 📞`",
        "send_ip": "`>>> Please send an IP address to analyze 🌐`",
        "initializing": "`> Initializing...`",
        "no_credits": "🚫 **You don't have enough credits to use this feature.**\n"
                     "Contact {admin} to add to your balance 👨‍💻\n\n"
                     "**Your Invite Link:** `t.me/{bot}?start={user_id}`\n"
                     "**Total Invites:** {invites}\n"
                     "**Your Credit Amount:** {credits}",
        "account_info": "**Account Information**\n\n"
                       "**Your Chat ID:** `{user_id}`\n"
                       "**Your Total Credits:** `{credits}`\n"
                       "**Your Total Invites:** `{invites}`\n"
                       "**Your Invite Link:** `t.me/{bot}?start={user_id}`\n"
                       "**Admin:** {admin} to add more credits",
        "referral_notification": "🎉 **New User Invite**\n"
                                "@{username} (ID: {user_id}) was invited by you! You received {credits} credit(s).\n"
                                "**Your Total Invites:** {invites}\n"
                                "**Your Total Credits:** {credits}",
        "progress_steps_ip": {
            10: "Pinging target node...",
            20: "Establishing secure link...",
            35: "Querying ISP backbone & routing tables...",
            50: "Executing network threat assessment...",
            70: "Receiving primary data stream...",
            85: "Parsing geo-coordinate & ASN data...",
            100: "Compiling final intelligence report..."
        },
        "progress_steps_phone": {
            15: "Analyzing number signature...",
            30: "Validating format & country code...",
            50: "Querying telecom database (Carrier, Line Type)...",
            75: "Heuristic digital footprint scan (Simulated)...",
            100: "Compiling final report..."
        },
        "ip_invalid": "**ERROR:** The IP is invalid or firewalled.",
        "ip_report_header": "╭┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╮\n"
                           "      **Data Extracted Successfully**\n"
                           "╰┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╯",
        "ip_report": {
            "target_ip": "[-] 🎯 Target IP: `{}`",
            "hostname": "[-] 🖥️ Hostname: `{}`",
            "isp": "[-] 📡 Network ISP: `{}`",
            "org": "[-] 🏢 Organization: `{}`",
            "asn": "[-] 🌐 ASN: `{}`",
            "location": "[-] 📍 Location: `{}, {} {}`",
            "zip": "[-] 📮 Zip Code: `{}`",
            "timezone": "[-] ⏳ Timezone: `{}`",
            "connection_type": "[-] 📶 Connection Type: `{}`",
            "latitude": "[-] 🌐 Latitude: `{}`",
            "longitude": "[-] 🌐 Longitude: `{}`",
            "anonymity": "[-] 🛡️ Anonymity Layer: `{}`",
            "risk": "[-] 🔥 Risk Assessment: `{}`"
        },
        "ip_error": "**CRITICAL ERROR:** IP analysis failed.\n`{}`",
        "phone_invalid": "**ERROR:** Invalid number signature.",
        "phone_not_in_db": "**INFO:** Target country not in detailed simulation database. Using global data.",
        "phone_parse_error": "**ERROR:** Could not parse number. Use format like +12025550123 📞",
        "phone_error": "**CRITICAL ERROR:** Simulation failed.\n`{}`",
        "phone_report_header": "╭┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╮\n"
                              "      **Data Extracted Successfully**\n"
                              "╰┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╯",
        "phone_report": {
            "intl_format": "[-] 📞 Intl. Format: `{}`",
            "national_format": "[-] ✍️ National Format: `{}`",
            "line_type": "[-] 💡 Line Type: `{}`",
            "carrier": "[-] 📶 Carrier: `{}`",
            "country": "[-] 🌍 Country: `{}`",
            "region": "[-] 🏙️ Est. Region (Sim.): `{}`",
            "timezone": "[-] ⏳ Timezone(s): `{}`",
            "dialing_code": "[-] 🌐 Intl. Dialing Code: `{} {}`",
            "latitude": "[-] 🌐 Latitude: `{}`",
            "longitude": "[-] 🌐 Longitude: `{}`",
            "footprint_header": "\n`--- Heuristic Footprint Scan (Simulated) ---`",
            "platform_hits": "[-] 📱 Platform Hits: `{}`",
            "risk": "[-] 🔥 Risk Assessment: `{}`"
        },
        "map_ip": "`🛰️ Tactical Map Deployed (Precise Coordinates).`",
        "map_phone": "`🛰️ Tactical Map Deployed (Simulated Coordinates).`"
    },
    "fa": {
        "choose_language": "**زبان خود را انتخاب کنید:**",
        "lang_english": "انگلیسی 🇬🇧",
        "lang_persian": "فارسی 🇮🇷",
        "lang_spanish": "اسپانیایی 🇪🇸",
        "mandatory_join": "🚫 **لطفاً برای استفاده از ربات به کانال‌های ما بپیوندید:**\n\n"
                         f"1. **اجباری:** {MANDATORY_CHANNEL}\n"
                         f"2. **اختیاری:** {OPTIONAL_CHANNEL}",
        "join_channel_1": "پیوستن به کانال ۱ 📢",
        "join_channel_2": "پیوستن به کانال ۲ 📢",
        "check_joined": "پیوست شده ✅",
        "not_joined_alert": "🚫 شما هنوز به کانال اجباری نپیوستید. لطفاً ابتدا بپیوندید!",
        "menu_message": "**رابط سیستم نسخه ۲۴.۰ (حداکثر واقع‌گرایی)** 🕵️‍♂️🔍\n"
                       "│   ---===[ خوش آمدید ]===---\n"
                       "یک ربات چندمنظوره برای اطلاعات IP و ردیابی شماره تلفن! 🚀\n"
                       "**یک گزینه انتخاب کنید:**",
        "search_phone": "جستجوی شماره تلفن 📞",
        "search_ip": "جستجوی آدرس IP 🌐",
        "language_button": "زبان 🌐",
        "account_info_button": "اطلاعات حساب ℹ️",
        "back_to_menu": "بازگشت به منو 🔙",
        "enter_phone": "`>>> یک شماره تلفن وارد کنید (مثلاً +12025550123) 📞`\n\n**اعتبار:** `{}`",
        "enter_ip": "`>>> یک آدرس IP وارد کنید (مثلاً 192.168.1.1) 🌐`",
        "invalid_phone": "`>>> خطا: فرمت یا شماره تلفن نامعتبر است. از فرمت +12025550123 استفاده کنید 📞`",
        "invalid_ip": "`>>> خطا: لطفاً یک آدرس IP معتبر وارد کنید (مثلاً 192.168.1.1) 🌐`",
        "send_phone": "`>>> لطفاً یک شماره تلفن برای ردیابی ارسال کنید 📞`",
        "send_ip": "`>>> لطفاً یک آدرس IP برای تحلیل ارسال کنید 🌐`",
        "initializing": "`> در حال راه‌اندازی...`",
        "no_credits": "🚫 **اعتبار کافی ندارید.**\nبا {admin} تماس بگیرید 👨‍💻\n\n"
                     "**لینک دعوت:** `t.me/{bot}?start={user_id}`\n"
                     "**تعداد دعوت‌ها:** {invites}\n**اعتبار شما:** {credits}",
        "account_info": "**اطلاعات حساب**\n\n"
                       "**شناسه چت شما:** `{user_id}`\n"
                       "**اعتبار کل شما:** `{credits}`\n"
                       "**تعداد کل دعوت‌ها:** `{invites}`\n"
                       "**لینک دعوت شما:** `t.me/{bot}?start={user_id}`\n"
                       "**ادمین:** {admin}",
        "referral_notification": "🎉 **دعوت کاربر جدید**\n"
                                "@{username} (شناسه: {user_id}) توسط شما دعوت شد! {credits} اعتبار دریافت کردید.\n"
                                "**تعداد کل دعوت‌ها:** {invites}\n"
                                "**اعتبار کل شما:** {credits}",
        "progress_steps_ip": {
            10: "در حال پینگ کردن گره هدف...",
            20: "در حال برقراری ارتباط امن...",
            35: "در حال پرس‌وجو از جدول‌های مسیر ISP...",
            50: "در حال اجرای ارزیابی تهدید شبکه...",
            70: "در حال دریافت جریان داده اولیه...",
            85: "در حال تجزیه داده‌های مختصات جغرافیایی و ASN...",
            100: "در حال تدوین گزارش نهایی اطلاعات..."
        },
        "progress_steps_phone": {
            15: "در حال تحلیل امضای شماره...",
            30: "در حال اعتبارسنجی فرمت و کد کشور...",
            50: "در حال پرس‌وجو از پایگاه داده مخابرات (اپراتور، نوع خط)...",
            75: "اسکن ردپای دیجیتال (شبیه‌سازی شده)...",
            100: "در حال تدوین گزارش نهایی..."
        },
        "ip_invalid": "**خطا:** IP نامعتبر است یا توسط دیوار آتش مسدود شده است.",
        "ip_report_header": "╭┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╮\n"
                           "      **داده‌ها با موفقیت استخراج شدند**\n"
                           "╰┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╯",
        "ip_report": {
            "target_ip": "[-] 🎯 IP هدف: `{}`",
            "hostname": "[-] 🖥️ نام میزبان: `{}`",
            "isp": "[-] 📡 ارائه‌دهنده خدمات اینترنت: `{}`",
            "org": "[-] 🏢 سازمان: `{}`",
            "asn": "[-] 🌐 ASN: `{}`",
            "location": "[-] 📍 مکان: `{}, {} {}`",
            "zip": "[-] 📮 کد پستی: `{}`",
            "timezone": "[-] ⏳ منطقه زمانی: `{}`",
            "connection_type": "[-] 📶 نوع اتصال: `{}`",
            "latitude": "[-] 🌐 عرض جغرافیایی: `{}`",
            "longitude": "[-] 🌐 طول جغرافیایی: `{}`",
            "anonymity": "[-] 🛡️ لایه ناشناسی: `{}`",
            "risk": "[-] 🔥 ارزیابی ریسک: `{}`"
        },
        "ip_error": "**خطای بحرانی:** تحلیل IP ناموفق بود.\n`{}`",
        "phone_invalid": "**خطا:** امضای شماره نامعتبر است.",
        "phone_not_in_db": "**اطلاعات:** کشور هدف در پایگاه داده شبیه‌سازی دقیق نیست. از داده‌های جهانی استفاده می‌شود.",
        "phone_parse_error": "**خطا:** نمی‌توان شماره را تجزیه کرد. از فرمت +12025550123 استفاده کنید 📞",
        "phone_error": "**خطای بحرانی:** شبیه‌سازی ناموفق بود.\n`{}`",
        "phone_report_header": "╭┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╮\n"
                              "      **داده‌ها با موفقیت استخراج شدند**\n"
                              "╰┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╯",
        "phone_report": {
            "intl_format": "[-] 📞 فرمت بین‌المللی: `{}`",
            "national_format": "[-] ✍️ فرمت ملی: `{}`",
            "line_type": "[-] 💡 نوع خط: `{}`",
            "carrier": "[-] 📶 اپراتور: `{}`",
            "country": "[-] 🌍 کشور: `{}`",
            "region": "[-] 🏙️ منطقه تخمینی (شبیه‌سازی): `{}`",
            "timezone": "[-] ⏳ منطقه(های) زمانی: `{}`",
            "dialing_code": "[-] 🌐 کد تماس بین‌المللی: `{} {}`",
            "latitude": "[-] 🌐 عرض جغرافیایی: `{}`",
            "longitude": "[-] 🌐 طول جغرافیایی: `{}`",
            "footprint_header": "\n`--- اسکن ردپای دیجیتال (شبیه‌سازی شده) ---`",
            "platform_hits": "[-] 📱 پلتفرم‌های شناسایی‌شده: `{}`",
            "risk": "[-] 🔥 ارزیابی ریسک: `{}`"
        },
        "map_ip": "`🛰️ نقشه تاکتیکی مستقر شد (مختصات دقیق).`",
        "map_phone": "`🛰️ نقشه تاکتیکی مستقر شد (مختصات شبیه‌سازی شده).`"
    },
    "es": {
        "choose_language": "**Elige tu idioma:**",
        "lang_english": "Inglés 🇬🇧",
        "lang_persian": "Persa 🇮🇷",
        "lang_spanish": "Español 🇪🇸",
        "mandatory_join": "🚫 **Por favor, únete a nuestro(s) canal(es) para usar el bot:**\n\n"
                         f"1. **Obligatorio:** {MANDATORY_CHANNEL}\n"
                         f"2. **Opcional:** {OPTIONAL_CHANNEL}",
        "join_channel_1": "Unirse al Canal 1 📢",
        "join_channel_2": "Unirse al Canal 2 📢",
        "check_joined": "Unido ✅",
        "not_joined_alert": "🚫 Aún no te has unido al canal obligatorio. ¡Por favor, únete primero!",
        "menu_message": "**Interfaz del Sistema v24.0 (Realismo Máximo)** 🕵️‍♂️🔍\n"
                       "│   ---===[ Bienvenido ]===---\n"
                       "¡Un bot multiherramienta para inteligencia de IP y rastreo de números de teléfono! 🚀\n"
                       "**Elige una opción:**",
        "search_phone": "Buscar Número de Teléfono 📞",
        "search_ip": "Buscar Dirección IP 🌐",
        "language_button": "Idioma 🌐",
        "account_info_button": "Información ℹ️",
        "back_to_menu": "Volver al Menú 🔙",
        "enter_phone": "`>>> Ingresa un número de teléfono (por ejemplo, +12025550123) 📞`\n\n**Créditos:** `{}`",
        "enter_ip": "`>>> Ingresa una dirección IP (por ejemplo, 192.168.1.1) 🌐`",
        "invalid_phone": "`>>> Error: Formato o número de teléfono inválido. Usa el formato +12025550123 📞`",
        "invalid_ip": "`>>> Error: Por favor, ingresa una dirección IP válida (por ejemplo, 192.168.1.1) 🌐`",
        "send_phone": "`>>> Por favor, envía un número de teléfono para rastrear 📞`",
        "send_ip": "`>>> Por favor, envía una dirección IP para analizar 🌐`",
        "initializing": "`> Inicializando...`",
        "no_credits": "🚫 **No tienes suficientes créditos para usar esta función.**\n"
                     "Contacta {admin} para agregar a tu saldo 👨‍💻\n\n"
                     "**Tu Enlace de Invitación:** `t.me/{bot}?start={user_id}`\n"
                     "**Total de Invitaciones:** {invites}\n"
                     "**Tu Cantidad de Créditos:** {credits}",
        "account_info": "**Información de la Cuenta**\n\n"
                       "**Tu ID de Chat:** `{user_id}`\n"
                       "**Tus Créditos Totales:** `{credits}`\n"
                       "**Tus Invitaciones Totales:** `{invites}`\n"
                       "**Tu Enlace de Invitación:** `t.me/{bot}?start={user_id}`\n"
                       "**Administrador:** {admin}",
        "referral_notification": "🎉 **Nueva Invitación de Usuario**\n"
                                "@{username} (ID: {user_id}) fue invitado por ti! Recibiste {credits} crédito(s).\n"
                                "**Tus Invitaciones Totales:** {invites}\n"
                                "**Tus Créditos Totales:** {credits}",
        "progress_steps_ip": {
            10: "Haciendo ping al nodo objetivo...",
            20: "Estableciendo enlace seguro...",
            35: "Consultando tablas de enrutamiento e ISP...",
            50: "Ejecutando evaluación de amenazas de red...",
            70: "Recibiendo flujo de datos primario...",
            85: "Analizando datos de coordenadas geográficas y ASN...",
            100: "Compilando informe final de inteligencia..."
        },
        "progress_steps_phone": {
            15: "Analizando firma del número...",
            30: "Validando formato y código de país...",
            50: "Consultando base de datos de telecomunicaciones (Operador, Tipo de Línea)...",
            75: "Escaneo de huella digital heurística (Simulado)...",
            100: "Compilando informe final..."
        },
        "ip_invalid": "**ERROR:** La IP es inválida o está bloqueada por un firewall.",
        "ip_report_header": "╭┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╮\n"
                           "      **Datos Extraídos con Éxito**\n"
                           "╰┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╯",
        "ip_report": {
            "target_ip": "[-] 🎯 IP Objetivo: `{}`",
            "hostname": "[-] 🖥️ Nombre del Host: `{}`",
            "isp "[-] 📡 Proveedor de Servicios de Internet: `{}`",
            "org": "[-] 🏢 Organización: `{}`",
            "asn": "[-] 🌐 ASN: `{}`",
            "location": "[-] 📍 Ubicación: `{}, {} {}`",
            "zip": "[-] 📮 Código Postal: `{}`",
            "timezone": "[-] ⏳ Zona Horaria: `{}`",
            "connection_type": "[-] 📶 Tipo de Conexión: `{}`",
            "latitude": "[-] 🌐 Latitud: `{}`",
            "longitude": "[-] 🌐 Longitud: `{}`",
            "anonymity": "[-] 🛡️ Capa de Anonimato: `{}`",
            "risk": "[-] 🔥 Evaluación de Riesgo: `{}`"
        },
        "ip_error": "**ERROR CRÍTICO:** Análisis de IP fallido.\n`{}`",
        "phone_invalid": "**ERROR:** Firma del número inválida.",
        "phone_not_in_db": "**INFO:** El país objetivo no está en la base de datos de simulación detallada. Usando datos globales.",
        "phone_parse_error": "**ERROR:** No se pudo analizar el número. Usa el formato +12025550123 📞",
        "phone_error": "**ERROR CRÍTICO:** Simulación fallida.\n`{}`",
        "phone_report_header": "╭┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╮\n"
                              "      **Datos Extraídos con Éxito**\n"
                              "╰┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈╯",
        "phone_report": {
            "intl_format": "[-] 📞 Formato Internacional: `{}`",
            "national_format": "[-] ✍️ Formato Nacional: `{}`",
            "line_type": "[-] 💡 Tipo de Línea: `{}`",
            "carrier": "[-] 📶 Operador: `{}`",
            "country": "[-] 🌍 País: `{}`",
            "region": "[-] 🏙️ Región Estimada (Sim.): `{}`",
            "timezone": "[-] ⏳ Zona(s) Horaria(s): `{}`",
            "dialing_code": "[-] 🌐 Código de Marcación Internacional: `{} {}`",
            "latitude": "[-] 🌐 Latitud: `{}`",
            "longitude": "[-] 🌐 Longitud: `{}`",
            "footprint_header": "\n`--- Escaneo de Huella Digital Heurística (Simulado) ---`",
            "platform_hits": "[-] 📱 Impactos en Plataformas: `{}`",
            "risk": "[-] 🔥 Evaluación de Riesgo: `{}`"
        },
        "map_ip": "`🛰️ Mapa Táctico Desplegado (Coordenadas Precisas).`",
        "map_phone": "`� спут Tactical Map Deployed (Simulated Coordinates).`"
    }
}

# --- UTILITY FUNCTIONS ---
async def load_country_data():
    if not os.path.exists(DATA_FILE):
        logger.warning(f"Data file '{DATA_FILE}' not found. Phone trace module will be crippled.")
        return False
    logger.info(f"Loading global target database from {DATA_FILE}...")
    try:
        async with aiofiles.open(DATA_FILE, 'r', encoding='utf-8') as f:
            async for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                try:
                    main_parts = line.strip().split(',', 2)
                    code, name, locations_str = main_parts
                    locations = []
                    for part in locations_str.strip().split('|'):
                        loc_name, loc_lat, loc_lon = part.strip().split(':')
                        locations.append({'name': loc_name, 'lat': float(loc_lat), 'lon': float(loc_lon)})
                    COUNTRY_DATABASE[code] = {'name': name, 'locations': locations}
                except Exception as e:
                    logger.warning(f"Skipping malformed line: {line.strip()} - Error: {e}")
        logger.info(f"SUCCESS: Loaded data for {len(COUNTRY_DATABASE)} nations.")
        return True
    except Exception as e:
        logger.error(f"Failed to load country data: {e}")
        return False

async def progress_edit(message, text: str, buttons=None) -> None:
    try:
        await message.edit(text, parse_mode='md', buttons=buttons)
    except (MessageNotModifiedError, FloodWaitError):
        pass

async def line_by_line_edit(message_to_edit, final_text, delay=0.3):
    lines = final_text.split('\n')
    current_text = ""
    for line in lines:
        current_text += line + "\n"
        text_to_send = current_text.strip()
        try:
            if text_to_send != message_to_edit.text:
                await message_to_edit.edit(text_to_send)
                await asyncio.sleep(delay)
        except MessageNotModifiedError:
            continue
        except Exception as e:
            logger.error(f"Line-by-line edit failed: {e}")
            await message_to_edit.edit(final_text)
            return

def make_progress_bar(percentage):
    filled_blocks = int(percentage / 10)
    empty_blocks = 10 - filled_blocks
    return f"[`{'█' * filled_blocks}{'▒' * empty_blocks}`]"

@sleep_and_retry
@limits(calls=10, period=60)
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError))
)
async def make_ip_request(http_client: httpx.AsyncClient, url: str) -> Dict:
    try:
        response = await http_client.get(url, timeout=10.0)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        raise Exception(f"HTTP {e.response.status_code}: {e.response.text}")
    except httpx.RequestError as e:
        raise Exception(f"Network error: {str(e)}")

def get_flag_emoji(country_code):
    if not country_code or len(country_code) != 2:
        return "🏳️"  # Default flag if code is invalid
    return chr(ord(country_code[0].upper()) + 127397) + chr(ord(country_code[1].upper()) + 127397)

# --- USER MANAGEMENT ---
async def get_user_data(user_id):
    user = users_collection.find_one({"user_id": user_id})
    if not user:
        default_user = {"user_id": user_id, "language": "en", "credits": INITIAL_CREDIT, "invites": 0, "inviter_id": None}
        users_collection.insert_one(default_user)
        return default_user
    return user

async def set_user_language(user_id, language):
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"language": language}},
        upsert=True
    )

async def update_user_credits(user_id, credits):
    users_collection.update_one({"user_id": user_id}, {"$set": {"credits": credits}})

async def increment_user_invites_and_credits(inviter_id, referred_user_id):
    try:
        result = users_collection.update_one(
            {"user_id": inviter_id, "invites_recorded": {"$ne": str(referred_user_id)}},
            {
                "$inc": {"invites": 1, "credits": CREDIT_PER_REFERRAL},
                "$addToSet": {"invites_recorded": str(referred_user_id)}
            },
            upsert=True
        )
        if result.modified_count > 0:
            logger.info(f"Updated invites and credits for inviter {inviter_id} for referred user {referred_user_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to update invites and credits for inviter {inviter_id}: {e}")
        return False

async def has_joined_mandatory_channel(client, user_id, channel):
    try:
        await client(GetParticipantRequest(channel, user_id))
        return True
    except (UserNotParticipantError, ChannelInvalidError, UserBannedInChannelError):
        return False
    except Exception as e:
        logger.error(f"Error checking channel membership for user {user_id}: {e}")
        return False

# --- REFERRAL MANAGEMENT ---
async def process_referral(client, user_id, start_param, bot_username):
    if not start_param:
        return
    try:
        inviter_id = int(start_param)
        if inviter_id == user_id:
            logger.warning(f"User {user_id} attempted self-referral")
            return
        user_data = await get_user_data(user_id)
        if user_data.get("inviter_id"):
            logger.info(f"User {user_id} already has an inviter: {user_data['inviter_id']}")
            return
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"inviter_id": inviter_id}},
            upsert=True
        )
        logger.info(f"Recorded inviter {inviter_id} for user {user_id}")
    except ValueError:
        logger.warning(f"Invalid start_param: {start_param}")
    except Exception as e:
        logger.error(f"Error processing referral for user {user_id}: {e}")

async def award_referral_credits(client, user_id, lang):
    user_data = await get_user_data(user_id)
    inviter_id = user_data.get("inviter_id")
    if not inviter_id:
        return
    has_joined = await has_joined_mandatory_channel(client, user_id, MANDATORY_CHANNEL)
    if not has_joined:
        return
    try:
        inviter_data = await get_user_data(inviter_id)
        if await increment_user_invites_and_credits(inviter_id, user_id):
            referred_user = await client.get_entity(user_id)
            username = referred_user.username or referred_user.first_name or f"User{user_id}"
            await client.send_message(
                inviter_id,
                LANGUAGES[inviter_data.get("language", "en")]["referral_notification"].format(
                    username=username,
                    user_id=user_id,
                    credits=CREDIT_PER_REFERRAL,
                    invites=inviter_data.get("invites", 0) + 1,
                    credits_total=inviter_data.get("credits", 0) + CREDIT_PER_REFERRAL
                )
            )
            logger.info(f"Sent referral notification to inviter {inviter_id} for user {user_id}")
    except Exception as e:
        logger.error(f"Error awarding referral credits for user {user_id} to inviter {inviter_id}: {e}")

# --- MAIN TELEGRAM HANDLERS ---
client = TelegramClient('combined_bot.session', API_ID, API_HASH)

@client.on(events.NewMessage(pattern=r'^/'))
async def command_handler(event):
    user_id = event.sender_id
    user_data = await get_user_data(user_id)
    lang = user_data.get("language", "en")
    if event.text.startswith('/start'):
        start_param = event.message.text.split('/start ')[1] if ' ' in event.text else event.message.text.replace('/start', '')
        await process_referral(client, user_id, start_param, BOT_USERNAME)
        await event.reply(
            LANGUAGES[lang]["choose_language"],
            buttons=[
                [Button.inline(LANGUAGES[lang]["lang_english"], b"lang_en")],
                [Button.inline(LANGUAGES[lang]["lang_persian"], b"lang_fa")],
                [Button.inline(LANGUAGES[lang]["lang_spanish"], b"lang_es")]
            ]
        )
    elif event.text == '/menu':
        has_joined = await has_joined_mandatory_channel(client, user_id, MANDATORY_CHANNEL)
        if has_joined:
            await award_referral_credits(client, user_id, lang)
            await event.reply(
                LANGUAGES[lang]["menu_message"],
                buttons=[
                    [Button.inline(LANGUAGES[lang]["search_phone"], b"mode_phone")],
                    [Button.inline(LANGUAGES[lang]["search_ip"], b"mode_ip")],
                    [Button.inline(LANGUAGES[lang]["language_button"], b"change_language"),
                     Button.inline(LANGUAGES[lang]["account_info_button"], b"account_info")]
                ]
            )
        else:
            await event.reply(
                LANGUAGES[lang]["mandatory_join"],
                buttons=[
                    [Button.url(LANGUAGES[lang]["join_channel_1"], f"https://t.me/{MANDATORY_CHANNEL[1:]}")],
                    [Button.url(LANGUAGES[lang]["join_channel_2"], f"https://t.me/{OPTIONAL_CHANNEL[1:]}")],
                    [Button.inline(LANGUAGES[lang]["check_joined"], b"check_joined")]
                ]
            )

@client.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    user_data = await get_user_data(user_id)
    lang = user_data.get("language", "en")
    data = event.data.decode()
    msg = await event.get_message()

    try:
        if data.startswith("lang_"):
            selected_lang = data.split("_")[1]
            await set_user_language(user_id, selected_lang)
            has_joined = await has_joined_mandatory_channel(client, user_id, MANDATORY_CHANNEL)
            if has_joined:
                await award_referral_credits(client, user_id, selected_lang)
                await event.edit(
                    LANGUAGES[selected_lang]["menu_message"],
                    buttons=[
                        [Button.inline(LANGUAGES[selected_lang]["search_phone"], b"mode_phone")],
                        [Button.inline(LANGUAGES[selected_lang]["search_ip"], b"mode_ip")],
                        [Button.inline(LANGUAGES[selected_lang]["language_button"], b"change_language"),
                         Button.inline(LANGUAGES[selected_lang]["account_info_button"], b"account_info")]
                    ]
                )
            else:
                await event.edit(
                    LANGUAGES[selected_lang]["mandatory_join"],
                    buttons=[
                        [Button.url(LANGUAGES[selected_lang]["join_channel_1"], f"https://t.me/{MANDATORY_CHANNEL[1:]}")],
                        [Button.url(LANGUAGES[selected_lang]["join_channel_2"], f"https://t.me/{OPTIONAL_CHANNEL[1:]}")],
                        [Button.inline(LANGUAGES[selected_lang]["check_joined"], b"check_joined")]
                    ]
                )
        elif data == "check_joined":
            has_joined = await has_joined_mandatory_channel(client, user_id, MANDATORY_CHANNEL)
            if not has_joined:
                await event.answer(LANGUAGES[lang]["not_joined_alert"], alert=True)
            else:
                await award_referral_credits(client, user_id, lang)
                await event.edit(
                    LANGUAGES[lang]["menu_message"],
                    buttons=[
                        [Button.inline(LANGUAGES[lang]["search_phone"], b"mode_phone")],
                        [Button.inline(LANGUAGES[lang]["search_ip"], b"mode_ip")],
                        [Button.inline(LANGUAGES[lang]["language_button"], b"change_language"),
                         Button.inline(LANGUAGES[lang]["account_info_button"], b"account_info")]
                    ]
                )
        elif data == "change_language":
            await event.edit(
                LANGUAGES[lang]["choose_language"],
                buttons=[
                    [Button.inline(LANGUAGES[lang]["lang_english"], b"lang_en")],
                    [Button.inline(LANGUAGES[lang]["lang_persian"], b"lang_fa")],
                    [Button.inline(LANGUAGES[lang]["lang_spanish"], b"lang_es")]
                ]
            )
        elif data == "account_info":
            await event.edit(
                LANGUAGES[lang]["account_info"].format(
                    user_id=user_id, credits=user_data.get("credits", 0),
                    invites=user_data.get("invites", 0), bot=BOT_USERNAME, admin="@Kaliboy002"
                ),
                buttons=[Button.inline(LANGUAGES[lang]["back_to_menu"], b"back_to_menu_prompt")]
            )
        elif data == "mode_phone":
            if user_data.get("credits", 0) < 1:
                await event.edit(
                    LANGUAGES[lang]["no_credits"].format(
                        admin="@Kaliboy002", user_id=user_id, bot=BOT_USERNAME,
                        invites=user_data.get("invites", 0), credits=user_data.get("credits", 0)
                    ),
                    buttons=[Button.inline(LANGUAGES[lang]["back_to_menu"], b"back_to_menu_prompt")]
                )
            else:
                await event.edit(
                    LANGUAGES[lang]["enter_phone"].format(user_data.get("credits", 0)),
                    buttons=[Button.inline(LANGUAGES[lang]["back_to_menu"], b"back_to_menu_prompt")]
                )
                users_collection.update_one({"user_id": user_id}, {"$set": {"active_mode": "phone"}})
        elif data == "mode_ip":
            await event.edit(
                LANGUAGES[lang]["enter_ip"],
                buttons=[Button.inline(LANGUAGES[lang]["back_to_menu"], b"back_to_menu_prompt")]
            )
            users_collection.update_one({"user_id": user_id}, {"$set": {"active_mode": "ip"}})
        elif data == "back_to_menu_prompt":
            users_collection.update_one({"user_id": user_id}, {"$set": {"active_mode": None}})
            has_joined = await has_joined_mandatory_channel(client, user_id, MANDATORY_CHANNEL)
            if has_joined:
                await award_referral_credits(client, user_id, lang)
                await event.edit(
                    LANGUAGES[lang]["menu_message"],
                    buttons=[
                        [Button.inline(LANGUAGES[lang]["search_phone"], b"mode_phone")],
                        [Button.inline(LANGUAGES[lang]["search_ip"], b"mode_ip")],
                        [Button.inline(LANGUAGES[lang]["language_button"], b"change_language"),
                         Button.inline(LANGUAGES[lang]["account_info_button"], b"account_info")]
                    ]
                )
            else:
                await event.edit(
                    LANGUAGES[lang]["mandatory_join"],
                    buttons=[
                        [Button.url(LANGUAGES[lang]["join_channel_1"], f"https://t.me/{MANDATORY_CHANNEL[1:]}")],
                        [Button.url(LANGUAGES[lang]["join_channel_2"], f"https://t.me/{OPTIONAL_CHANNEL[1:]}")],
                        [Button.inline(LANGUAGES[lang]["check_joined"], b"check_joined")]
                    ]
                )
        elif data == "back_to_menu_results":
            users_collection.update_one({"user_id": user_id}, {"$set": {"active_mode": None}})
            await award_referral_credits(client, user_id, lang)
            await event.reply(
                LANGUAGES[lang]["menu_message"],
                buttons=[
                    [Button.inline(LANGUAGES[lang]["search_phone"], b"mode_phone")],
                    [Button.inline(LANGUAGES[lang]["search_ip"], b"mode_ip")],
                    [Button.inline(LANGUAGES[lang]["language_button"], b"change_language"),
                     Button.inline(LANGUAGES[lang]["account_info_button"], b"account_info")]
                ]
            )
    except Exception as e:
        logger.error(f"Error in callback_handler for user {user_id}: {e}")
        await event.answer("An error occurred. Please try again.", alert=True)

@client.on(events.NewMessage)
async def handle_input(event):
    user_id = event.sender_id
    user_data = await get_user_data(user_id)
    lang = user_data.get("language", "en")
    active_mode = user_data.get("active_mode")

    try:
        has_joined = await has_joined_mandatory_channel(client, user_id, MANDATORY_CHANNEL)
        if not has_joined:
            await event.reply(
                LANGUAGES[lang]["mandatory_join"],
                buttons=[
                    [Button.url(LANGUAGES[lang]["join_channel_1"], f"https://t.me/{MANDATORY_CHANNEL[1:]}")],
                    [Button.url(LANGUAGES[lang]["join_channel_2"], f"https://t.me/{OPTIONAL_CHANNEL[1:]}")],
                    [Button.inline(LANGUAGES[lang]["check_joined"], b"check_joined")]
                ]
            )
            return

        if not active_mode:
            if event.text == '/menu':
                await award_referral_credits(client, user_id, lang)
                await event.reply(
                    LANGUAGES[lang]["menu_message"],
                    buttons=[
                        [Button.inline(LANGUAGES[lang]["search_phone"], b"mode_phone")],
                        [Button.inline(LANGUAGES[lang]["search_ip"], b"mode_ip")],
                        [Button.inline(LANGUAGES[lang]["language_button"], b"change_language"),
                         Button.inline(LANGUAGES[lang]["account_info_button"], b"account_info")]
                    ]
                )
            return

        text = event.text.strip() if event.text else None
        if active_mode == "phone":
            if text:
                try:
                    parsed_number = phonenumberutil.parse(text, None)
                    if not phonenumbers.is_valid_number(parsed_number):
                        await event.reply(LANGUAGES[lang]["invalid_phone"])
                        return
                    if user_data.get("credits", 0) < 1:
                        await event.reply(
                            LANGUAGES[lang]["no_credits"].format(
                                admin="@Kaliboy002", user_id=user_id, bot=BOT_USERNAME,
                                invites=user_data.get("invites", 0), credits=user_data.get("credits", 0)
                            )
                        )
                        return
                    await update_user_credits(user_id, user_data.get("credits", 0) - 1)
                    await handle_phone_trace(event, text, lang)
                except phonenumbers.phonenumberutil.NumberParseException:
                    await event.reply(LANGUAGES[lang]["invalid_phone"])
            else:
                await event.reply(LANGUAGES[lang]["send_phone"])
        elif active_mode == "ip":
            if text and IP_PATTERN.match(text):
                await handle_ip_lookup(event, text, lang)
            elif text:
                await event.reply(LANGUAGES[lang]["invalid_ip"])
            else:
                await event.reply(LANGUAGES[lang]["send_ip"])
    except Exception as e:
        logger.error(f"Error in handle_input for user {user_id}: {e}")
        await event.reply("An error occurred. Please try again.")

async def handle_ip_lookup(event, ip_address, lang):
    msg = await event.reply(LANGUAGES[lang]["initializing"])
    try:
        progress_steps = LANGUAGES[lang]["progress_steps_ip"]
        ip_data, security_data = {}, {}
        async with httpx.AsyncClient() as http_client:
            for percent, status in progress_steps.items():
                await asyncio.sleep(random.uniform(0.5, 1))
                bar = make_progress_bar(percent)
                await msg.edit(f"`{bar} {percent}%`\n`> {status}`")
                if percent == 35:
                    response = await make_ip_request(http_client, IP_API_URL.format(ip=ip_address))
                    ip_data = response
                    if ip_data.get('status') == 'fail':
                        await msg.edit(LANGUAGES[lang]["ip_invalid"])
                        return
                if percent == 50:
                    response = await make_ip_request(http_client, PROXYCHECK_API_URL.format(ip=ip_address))
                    security_data = response.get(ip_address, {'proxy': 'Unknown', 'type': 'Scan Inconclusive', 'risk': 'N/A'})
        await asyncio.sleep(0.5)
        hostname = "N/A"
        try:
            hostname = socket.gethostbyaddr(ip_address)[0]
        except socket.herror:
            pass
        anonymity_status = "Not Detected"
        if security_data.get('proxy') == 'yes':
            anonymity_status = f"Detected ({security_data.get('type', 'Unknown Type').upper()})"
        connection_type = ip_data.get('mobile', 'Unknown') and 'Mobile' or ip_data.get('connection', 'Broadband')
        country_flag = get_flag_emoji(ip_data.get('countryCode', ''))
        header = LANGUAGES[lang]["ip_report_header"]
        report_lines = [
            LANGUAGES[lang]["ip_report"]["target_ip"].format(ip_data.get('query', 'N/A')),
            LANGUAGES[lang]["ip_report"]["hostname"].format(hostname),
            LANGUAGES[lang]["ip_report"]["isp"].format(ip_data.get('isp', 'N/A')),
            LANGUAGES[lang]["ip_report"]["org"].format(ip_data.get('org', 'N/A')),
            LANGUAGES[lang]["ip_report"]["asn"].format(ip_data.get('as', 'N/A')),
            LANGUAGES[lang]["ip_report"]["location"].format(ip_data.get('city', 'N/A'), ip_data.get('country', 'N/A'), country_flag),
            LANGUAGES[lang]["ip_report"]["zip"].format(ip_data.get('zip', 'N/A')),
            LANGUAGES[lang]["ip_report"]["timezone"].format(ip_data.get('timezone', 'N/A')),
            LANGUAGES[lang]["ip_report"]["connection_type"].format(connection_type),
            LANGUAGES[lang]["ip_report"]["latitude"].format(ip_data.get('lat', 'N/A')),
            LANGUAGES[lang]["ip_report"]["longitude"].format(ip_data.get('lon', 'N/A')),
            LANGUAGES[lang]["ip_report"]["anonymity"].format(anonymity_status),
            LANGUAGES[lang]["ip_report"]["risk"].format(security_data.get('risk', 'N/A (Scan Inconclusive)'))
        ]
        final_report = header + "\n\n" + "\n".join(report_lines)
        await line_by_line_edit(msg, final_report)
        await asyncio.sleep(0.5)
        lat, lon = ip_data.get('lat'), ip_data.get('lon')
        if lat and lon:
            await client.send_file(event.chat_id, file=InputMediaGeoPoint(InputGeoPoint(lat=lat, long=lon)), caption=LANGUAGES[lang]["map_ip"])
        await msg.edit(final_report, buttons=[Button.inline(LANGUAGES[lang]["back_to_menu"], b"back_to_menu_results")])
    except Exception as e:
        logger.error(f"IP lookup error for {ip_address}: {e}")
        await msg.edit(LANGUAGES[lang]["ip_error"].format(f"{e.__class__.__name__}: {e}"))

async def handle_phone_trace(event, phone_number_str, lang):
    msg = await event.reply(LANGUAGES[lang]["initializing"])
    try:
        parsed_number = phonenumberutil.parse(phone_number_str, None)
        progress_steps = LANGUAGES[lang]["progress_steps_phone"]
        country_data = None
        country_name = "Unknown"
        chosen_location_name = "N/A (Global Simulation)"
        national_format = "N/A"
        timezones_str = "N/A"
        for percent, status in progress_steps.items():
            await asyncio.sleep(random.uniform(0.5, 1))
            bar = make_progress_bar(percent)
            await msg.edit(f"`{bar} {percent}%`\n`> {status}`")
            if percent == 30:
                if not phonenumbers.is_valid_number(parsed_number):
                    await msg.edit(LANGUAGES[lang]["phone_invalid"])
                    return
                national_format = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.NATIONAL)
                timezones_str = ', '.join(timezone.time_zones_for_number(parsed_number)) or 'N/A'
            elif percent == 50:
                country_code = str(parsed_number.country_code)
                country_data = COUNTRY_DATABASE.get(country_code)
                if not country_data:
                    await msg.edit(LANGUAGES[lang]["phone_not_in_db"])
                else:
                    country_name = country_data['name']
                    chosen_location = random.choice(country_data['locations'])
                    chosen_location_name = chosen_location['name']
        number_type_code = phonenumbers.number_type(parsed_number)
        line_type = NUMBER_TYPE_MAP.get(number_type_code, "UNKNOWN")
        carrier_name = carrier.name_for_number(parsed_number, 'en') or 'Unknown'
        footprints = []
        if random.random() > 0.3: footprints.append("WhatsApp")
        if random.random() > 0.5: footprints.append("Telegram")
        if random.random() > 0.8: footprints.append("Google Account")
        threat = "Low"
        if line_type == "VOIP":
            threat = "Moderate (Potential Virtual Number)"
        elif not footprints:
            threat = "Low (Minimal Digital Presence Detected)"
        country_flag = get_flag_emoji(phonenumberutil.region_code_for_number(parsed_number))
        await asyncio.sleep(0.5)
        header = LANGUAGES[lang]["phone_report_header"]
        lat, lon = "N/A", "N/A"
        if country_data:
            chosen_loc = random.choice(country_data['locations'])
            lat, lon = chosen_loc['lat'], chosen_loc['lon']
        report_lines = [
            LANGUAGES[lang]["phone_report"]["intl_format"].format(phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)),
            LANGUAGES[lang]["phone_report"]["national_format"].format(national_format),
            LANGUAGES[lang]["phone_report"]["line_type"].format(line_type),
            LANGUAGES[lang]["phone_report"]["carrier"].format(carrier_name),
            LANGUAGES[lang]["phone_report"]["country"].format(geocoder.country_name_for_number(parsed_number, 'en') or country_name),
            LANGUAGES[lang]["phone_report"]["region"].format(chosen_location_name if country_data else 'Global Estimate'),
            LANGUAGES[lang]["phone_report"]["timezone"].format(timezones_str),
            LANGUAGES[lang]["phone_report"]["dialing_code"].format(f"+{parsed_number.country_code}", country_flag),
            LANGUAGES[lang]["phone_report"]["latitude"].format(lat),
            LANGUAGES[lang]["phone_report"]["longitude"].format(lon),
            LANGUAGES[lang]["phone_report"]["footprint_header"],
            LANGUAGES[lang]["phone_report"]["platform_hits"].format(', '.join(footprints) if footprints else 'Minimal / None Detected'),
            LANGUAGES[lang]["phone_report"]["risk"].format(threat)
        ]
        final_report = header + "\n\n" + "\n".join(report_lines)
        await line_by_line_edit(msg, final_report)
        await asyncio.sleep(0.5)
        if country_data:
            chosen_loc_for_map = random.choice(country_data['locations'])
            fake_lat = chosen_loc_for_map['lat'] + random.uniform(-0.1, 0.1)
            fake_lon = chosen_loc_for_map['lon'] + random.uniform(-0.1, 0.1)
        else:
            fake_lat, fake_lon = random.uniform(-90, 90), random.uniform(-180, 180)
        await client.send_file(event.chat_id, file=InputMediaGeoPoint(InputGeoPoint(lat=fake_lat, long=fake_lon)), caption=LANGUAGES[lang]["map_phone"])
        await msg.edit(final_report, buttons=[Button.inline(LANGUAGES[lang]["back_to_menu"], b"back_to_menu_results")])
    except phonenumbers.phonenumberutil.NumberParseException:
        await msg.edit(LANGUAGES[lang]["phone_parse_error"])
    except Exception as e:
        logger.error(f"Phone trace error for {phone_number_str}: {e}")
        await msg.edit(LANGUAGES[lang]["phone_error"].format(f"{e.__class__.__name__}: {e}"))

async def main():
    await load_country_data()
    await client.start(bot_token=BOT_TOKEN)
    logger.info("System Interface v24.0 is now active!")
    await client.run_until_disconnected()

if __name__ == "__main__":
    logger.info("Initializing system...")
    asyncio.run(main())
