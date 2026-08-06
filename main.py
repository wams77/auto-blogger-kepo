import os
import time
import feedparser
import urllib.parse
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.api_core.exceptions import ResourceExhausted
import sys

# ==========================================
# 1. KONFIGURASI KREDENSIAL & API
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel('gemini-3.5-flash')
BLOG_ID = os.environ.get("BLOG_ID")
SCOPES = ['https://www.googleapis.com/auth/blogger']
TOKEN_FILE = 'token.json'
INDEXING_SCOPES = ['https://www.googleapis.com/auth/indexing']
INDEXING_KEY_FILE = 'service_account.json'
HISTORY_FILE = 'history.txt' 

# --- Inisialisasi Blogger API ---
try:
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        blogger_service = build('blogger', 'v3', credentials=creds)
        print("✅ Otentikasi Blogger berhasil.")
    else:
        raise FileNotFoundError(f"File {TOKEN_FILE} tidak ditemukan di sistem!")
except Exception as e:
    print(f"FATAL ERROR: Otentikasi Blogger Gagal: {e}")
    sys.exit(1)

# --- Inisialisasi Indexing API ---
indexing_service = None
try:
    if os.path.exists(INDEXING_KEY_FILE):
        idx_creds = service_account.Credentials.from_service_account_file(INDEXING_KEY_FILE, scopes=INDEXING_SCOPES)
        indexing_service = build('indexing', 'v3', credentials=idx_creds)
        print("✅ Google Indexing API siap digunakan.")
    else:
        print("⚠️ File service_account.json tidak ditemukan.")
except Exception as e:
    print(f"⚠️ Gagal menginisialisasi Indexing API: {e}")

# ==========================================
# 2. DAFTAR SUMBER RSS (K-POP INTERNASIONAL & LOKAL)
# ==========================================
RSS_FEEDS = [
    "https://www.soompi.com/feed",
    "https://www.allkpop.com/rss",
    "https://www.koreaboo.com/feed/",
    "https://news.google.com/rss/search?q=Artis+Korea+OR+Drama+Korea+when:1d&hl=id&gl=ID&ceid=ID:id",
    "https://news.google.com/rss/search?q=Gosip+Dating+Idol+Kpop+when:1d&hl=id&gl=ID&ceid=ID:id"
]

# ==========================================
# 3. FUNGSI UTAMA
# ==========================================
def muat_riwayat_lokal():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def simpan_riwayat_lokal(link):
    with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{link}\n")

def dapatkan_berita_dari_rss(rss_urls, limit_per_sumber=3):
    semua_berita = []
    for url in rss_urls:
        print(f"Membaca RSS dari: {url}")
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit_per_sumber]:
                gambar_url = ""
                link_asli = entry.get('link', entry.get('id', ''))
                
                try:
                    if 'media_content' in entry and len(entry.media_content) > 0:
                        gambar_url = entry.media_content[0].get('url', '')
                    elif 'links' in entry:
                        for link in entry.links:
                            if link.get('rel') == 'enclosure' and 'image' in link.get('type', ''):
                                gambar_url = link.get('href', '')
                                break
                    elif 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
                        gambar_url = entry.media_thumbnail[0].get('url', '')
                        
                    if not gambar_url:
                        prompt_gambar = f"High quality cinematic photo, Korean celebrity, K-Pop idol, glamorous style, illustration of: {entry.title}"
                        prompt_aman = urllib.parse.quote(prompt_gambar)
                        gambar_url = f"https://image.pollinations.ai/prompt/{prompt_aman}?width=800&height=400&nologo=true"
                except Exception:
                    pass

                berita = {
                    'judul': entry.title,
                    'link': link_asli,
                    'deskripsi': entry.get('summary', entry.get('description', '')),
                    'gambar': gambar_url
                }
                semua_berita.append(berita)
        except Exception as e:
            print(f"Gagal membaca RSS {url}: {e}")
    return semua_berita

def tulis_artikel_dengan_gemini(berita):
    prompt = f"""
    Bertindaklah sebagai jurnalis hiburan dan K-netz (Netizen Korea) atau K-Popers sejati yang julid, *up-to-date*, dan bersemangat. 
    Tulis ulang berita dunia hiburan Korea berikut ke dalam bahasa Indonesia yang sensasional, memancing rasa penasaran (kepo), kekinian ala anak K-Pop, dan SEO friendly.
    
    Data Berita Asli:
    Judul: {berita['judul']}
    Deskripsi: {berita['deskripsi']}
    
    Syarat penulisan:
    1. Buat Judul baru yang sangat clickbait, heboh, namun tetap relevan.
    2. Tulis isi artikel minimal 8 paragraf dengan gaya bahasa asyik (bisa menyapa 'Chingu' atau 'Yeorobun').
    3. Format artikel harus menggunakan tag HTML (seperti <h2>, <p>, <strong>).
    4. Jangan masukkan tag <html>, <head>, atau <body>.
    5. Berikan kredit sumber berita di akhir artikel (Sumber: <a href="{berita['link']}">{berita['link']}</a>).
    """
    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            return response.text
        except ResourceExhausted:
            wait_time = (attempt + 1) * 30
            print(f"⚠️ Limit API Gemini. Menunggu {wait_time} detik...")
            time.sleep(wait_time)
        except Exception as e:
            print(f"Error Gemini: {e}")
            return None
    return None

def posting_ke_blogger(judul, konten_html):
    if not BLOG_ID: return False
    post_body = {
        'title': judul,
        'content': konten_html,
        'labels': ['K-Pop', 'Gosip Artis Korea', 'Drama Korea']
    }
    try:
        request = blogger_service.posts().insert(blogId=BLOG_ID, body=post_body)
        response = request.execute()
        post_url = response.get('url')
        print(f"✅ Sukses memposting: {post_url}")
        
        if indexing_service and post_url:
            try:
                notification = {'url': post_url, 'type': 'URL_UPDATED'}
                indexing_service.urlNotifications().publish(body=notification).execute()
                print(f"🚀 [AUTO-INDEX] Ping berhasil!")
            except Exception:
                pass
        return True
    except Exception as e:
        print(f"❌ Gagal memposting: {e}")
        return False

# ==========================================
# 4. EKSEKUSI PROGRAM
# ==========================================
def main():
    print("=== Memulai Auto-Blogger Gosip K-Pop ===")
    
    # KINI HANYA MENGANDALKAN HISTORY LOKAL
    riwayat_lokal = muat_riwayat_lokal()
    print(f"📂 Ditemukan {len(riwayat_lokal)} riwayat di history.txt")
    
    link_sesi_ini = set() 
    
    daftar_berita = dapatkan_berita_dari_rss(RSS_FEEDS, limit_per_sumber=3)
    print(f"Ditemukan total {len(daftar_berita)} berita dari RSS.")
    
    for index, berita in enumerate(daftar_berita):
        print(f"\n[{index + 1}/{len(daftar_berita)}] Mengecek berita: {berita['judul']}")
        
        if not berita['link'] or len(berita['link']) < 5:
            continue

        # 1. CEK HISTORY LOKAL (Mutlak)
        if (berita['link'] in riwayat_lokal) or (berita['link'] in link_sesi_ini):
            print("⏩ Melewati berita: Sudah diposting sebelumnya (Duplikat).")
            continue
            
        link_sesi_ini.add(berita['link'])
        hasil_gemini = tulis_artikel_dengan_gemini(berita)
        
        if hasil_gemini:
            baris_teks = hasil_gemini.split('\n')
            judul_baru = baris_teks[0].replace('<h1>', '').replace('</h1>', '').replace('##', '').replace('**', '').strip()
            konten_artikel = '\n'.join(baris_teks[1:]).replace('```html', '').replace('```', '')
            
            # Tag pelacak (opsional untuk rekam jejak internal)
            tag_pelacak = f"\n"
            konten_artikel = tag_pelacak + konten_artikel
            
            if berita['gambar']:
                tag_gambar = f'<div style="text-align: center; margin-bottom: 20px;"><img src="{berita["gambar"]}" alt="{judul_baru}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);" /></div>\n'
                konten_artikel = tag_gambar + konten_artikel

            # Jika berhasil diposting ke Blogger, simpan ke file history.txt
            if posting_ke_blogger(judul_baru, konten_artikel):
                simpan_riwayat_lokal(berita['link'])
                riwayat_lokal.add(berita['link'])
            
            print("⏳ Menunggu 20 detik sebelum memproses berita selanjutnya...")
            time.sleep(20)

    print("\n=== Proses Auto-Blogger Selesai ===")

if __name__ == '__main__':
    main()
