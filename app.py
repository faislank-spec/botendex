import os
import telebot
import requests
import logging
import re
import socket
from huggingface_hub import hf_hub_download, upload_file

# ==========================================
# [ 0. DNS PATCH - JALAN NINJA ANTI-RESET ]
# ==========================================
TELEGRAM_IP = '149.154.167.200'
def apply_dns_patch():
    old_getaddrinfo = socket.getaddrinfo
    def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if host == 'api.telegram.org':
            return old_getaddrinfo(TELEGRAM_IP, port, family, type, proto, flags)
        return old_getaddrinfo(host, port, family, type, proto, flags)
    socket.getaddrinfo = new_getaddrinfo

apply_dns_patch()

# --- [ KONFIGURASI DATASET ABADI ] ---
REPO_ID = "faislank/data-nobar" 
HF_TOKEN = os.getenv("HF_TOKEN")
INDEX_FILE = "index_video.txt" 

# Daftar ID Admin
ADMIN_IDS = [8799741740, 1726259702] 

def download_index():
    if os.path.exists(INDEX_FILE): return 
    try:
        hf_hub_download(repo_id=REPO_ID, filename=INDEX_FILE, local_dir=".", repo_type="dataset", token=HF_TOKEN)
        print("✅ Database film berhasil diunduh dari Cloud!")
    except Exception as e:
        print(f"ℹ️ Belum ada database di Cloud, mulai baru.")

def sync_ke_cloud():
    try:
        upload_file(path_or_fileobj=INDEX_FILE, path_in_repo=INDEX_FILE, repo_id=REPO_ID, repo_type="dataset", token=HF_TOKEN)
    except:
        pass

# --- [ 1. INISIALISASI BOT POLLING ] ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=True)

logging.basicConfig(level=logging.INFO)

# --- [ 2. FUNGSI LISTENER & SCRAPER INDEKS ] ---
def simpan_ke_index(judul, chat_id, message_id, thread_id=None):
    if not judul: return False
    judul_clean = judul.split('\n')[0]
    judul_clean = re.sub(r'^\[.*?\]\s*', '', judul_clean).strip()
    judul_clean = re.sub(r'^(Judul:|File:)', '', judul_clean, flags=re.IGNORECASE).strip()
    judul_clean = re.sub(r'<.*?>|http\S+|t\.me\S+', '', judul_clean)
    judul_clean = judul_clean.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    judul_clean = re.sub(r'\.(mp4|mkv|avi|zip|rar)$', '', judul_clean, flags=re.IGNORECASE)
    judul_clean = re.sub(r'\s+', ' ', judul_clean).strip().lower()
    if not judul_clean: return False
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            if f"{chat_id} | {message_id}" in f.read(): return False
    entry = f"{judul_clean} | {chat_id} | {message_id} | {thread_id or ''}\n"
    with open(INDEX_FILE, "a", encoding="utf-8") as f: f.write(entry)
    return True

@bot.message_handler(content_types=['video', 'document'])
def handle_incoming_video(m):
    is_video = m.content_type == 'video' or (m.content_type == 'document' and m.document.mime_type and "video" in m.document.mime_type)
    if is_video and m.caption:
        if simpan_ke_index(m.caption, m.chat.id, m.message_id, m.message_thread_id if m.is_topic_message else None): 
            sync_ke_cloud()

# --- [ 3. FUNGSI KIRIM HASIL PENCARIAN DENGAN PAGINATION & SECURITY ] ---
def kirim_hasil_pencarian(chat_id, query, page=1, message_id=None, panggilan="", user_id=0):
    hasil = []
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            for line in f:
                data = line.strip().split(' | ')
                if len(data) >= 3 and query in data[0]: 
                    hasil.append(data)
    
    if not hasil:
        teks_kosong = f"<b>Video tidak ditemukan {panggilan}! 🌸</b>"
        try:
            if message_id:
                bot.edit_message_text(teks_kosong, chat_id, message_id, parse_mode="HTML")
            else:
                bot.send_message(chat_id, teks_kosong, parse_mode="HTML")
        except: pass
        return

    per_page = 5
    total_results = len(hasil)
    total_pages = (total_results + per_page - 1) // per_page
    
    if page > total_pages: page = 1
    elif page < 1: page = total_pages

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_data = hasil[start_idx:end_idx]

    res_txt = f"<b>🔍 Daftar Pencarian {panggilan} (Hal {page}/{total_pages}):</b>\n\n"
    for i, h in enumerate(page_data, start_idx + 1):
        clean_chat_id = h[1].replace('-100', '')
        link = f"https://t.me/c/{clean_chat_id}/{h[2]}"
        res_txt += f"👉 <b>{i}. <a href='{link}'>{h[0].upper()}</a></b>\n"

    markup = telebot.types.InlineKeyboardMarkup()
    prev_page = total_pages if page == 1 else page - 1
    next_page = 1 if page == total_pages else page + 1
    
    markup.row(
        telebot.types.InlineKeyboardButton("⬅️ Prev", callback_data=f"s_{query}_{prev_page}_{user_id}"),
        telebot.types.InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="none"),
        telebot.types.InlineKeyboardButton("Next ➡️", callback_data=f"s_{query}_{next_page}_{user_id}")
    )
    markup.row(telebot.types.InlineKeyboardButton("❌ TUTUP ❌", callback_data=f"close_0_0_{user_id}"))

    try:
        if message_id:
            bot.edit_message_text(res_txt, chat_id, message_id, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
        else:
            bot.send_message(chat_id, res_txt, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        print(f"⚠️ Gagal kirim pesan: {e}")

# --- [ 4. MAIN HANDLER UNTUK !s & HAK AKSES ] ---
@bot.message_handler(func=lambda m: True)
def handle_messages(m):
    if not m.text: return
    text_raw = m.text
    text_lower = text_raw.lower()
    u_id = m.from_user.id
    chat_type = m.chat.type
    panggilan = f"KaK {m.from_user.first_name}"

    if text_lower.startswith('!s '):
        if chat_type == "private" and u_id not in ADMIN_IDS:
            bot.reply_to(m, f"<b>Maaf {panggilan}, fitur ini khusus Admin jika di Japri! 🛡️</b>", parse_mode="HTML")
            return
        
        query = text_lower[3:].strip()
        if not query:
            bot.reply_to(m, f"<b>Format salah {panggilan}. Contoh: <code>!s panda</code></b>", parse_mode="HTML")
            return
            
        kirim_hasil_pencarian(m.chat.id, query, page=1, message_id=None, panggilan=panggilan, user_id=u_id)
        return

# --- [ 5. CALLBACK QUERY HANDLER ] ---
@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(c):
    data = c.data.split('_')
    clicker_id = c.from_user.id
    target_user_id = int(data[3]) if len(data) > 3 and data[3].isdigit() else 0

    if clicker_id != target_user_id and clicker_id not in ADMIN_IDS:
        try:
            bot.answer_callback_query(
                c.id, 
                "❌ Maaf, Anda tidak bisa mengontrol pencarian orang lain! Silakan ketik !s <judul> sendiri.", 
                show_alert=True
            )
        except: pass
        return

    if data[0] == "close":
        try: bot.delete_message(c.message.chat.id, c.message.message_id)
        except: pass
        try: bot.answer_callback_query(c.id)
        except: pass
        return

    if data[0] == "s":
        query = data[1]
        page = int(data[2])
        panggilan = f"KaK {c.from_user.first_name}"
        kirim_hasil_pencarian(c.message.chat.id, query, page=page, message_id=c.message.message_id, panggilan=panggilan, user_id=target_user_id)
        try: bot.answer_callback_query(c.id)
        except: pass

if __name__ == "__main__":
    download_index()
    
    # Bersihkan webhook sebelumnya agar mode polling bisa berjalan bersih
    try:
        bot.remove_webhook()
        print("🧹 Webhook lama berhasil dihapus.")
    except:
        pass

    print("🚀 Bot Long Polling Berjalan...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
