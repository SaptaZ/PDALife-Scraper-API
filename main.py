from fastapi import FastAPI, HTTPException, Query
import httpx
from bs4 import BeautifulSoup
import uvicorn
import os
from urllib.parse import unquote, urlparse, parse_qs
from contextlib import asynccontextmanager
import asyncio
import re
import logging
import sys

# ==========================================
# LOGGING CONFIGURATION
# ==========================================
# Konfigurasi logging agar output muncul di terminal (stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PDALifeScraper")

# ==========================================
# CONFIGURATION
# ==========================================
BASE_DOMAIN = "https://pdalife.com"
CDN_DOMAIN = "https://mobdisc.com"

# Setup Async Client
client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    logger.info("Starting application lifespan...")
    
    # Robust headers to avoid blocks
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Referer": "https://pdalife.com/",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    logger.info("Initializing HTTPX AsyncClient with custom headers.")
    # Using a standard AsyncClient with follow_redirects=True
    client = httpx.AsyncClient(
        headers=headers, 
        verify=False, 
        follow_redirects=True, 
        timeout=None
    )
    
    logger.info("Application startup complete. Ready to accept requests.")
    yield
    
    logger.info("Shutting down application. Closing HTTPX client.")
    await client.aclose()
    logger.info("HTTPX client closed. Application stopped.")

app = FastAPI(title="PDALife Scraper", lifespan=lifespan)

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def unwrap_google_url(url: str) -> str:
    """
    Membersihkan URL dari wrapper Google Translate dan menangani Relative Path
    sesuai domain aslinya (PDALife vs MobDisc).
    """
    if not url: return ""
    clean = unquote(url)
    
    # 1. Decode jika URL terbungkus format translate
    # Contoh: https://pdalife-com.translate.goog/...
    clean = clean.replace("-com.translate.goog", ".com")
    clean = clean.replace(".translate.goog", "")
    
    # 2. Hapus parameter sampah google translate
    clean = clean.split("?_x_tr_")[0]
    clean = clean.split("&_x_tr_")[0]
    
    # 3. Handle Relative URL (PENTING!)
    if clean.startswith("/"):
        # Jika path dimulai dengan /fdl/, itu pasti milik MobDisc (File Download Link)
        if clean.startswith("/fdl/"):
            return CDN_DOMAIN + clean
        # Selain itu, milik PDALife utama
        else:
            return BASE_DOMAIN + clean
            
    # 4. Handle jika URL absolut tapi masih ada sisa-sisa google
    if "https://" in clean and "http" in clean[8:]:
        # Kadang google nesting url: https://google.com/url?q=https://...
        match = re.search(r'(https?://[^&]+)', clean)
        if match:
            return match.group(1)

    return clean

async def fetch_until_success(url: str, validator_func) -> BeautifulSoup:
    """
    Mencoba fetch URL. 
    MODIFIED (FULL ASYNC): Parsing BeautifulSoup dipindah ke thread terpisah
    untuk menghindari blocking pada event loop.
    """
    target_url = url
    if target_url.startswith("/"):
        target_url = BASE_DOMAIN + target_url

    logger.info(f"Initiating fetch request for URL: {target_url}")

    attempt_count = 0
    while True:
        attempt_count += 1
        try:
            res = await client.get(target_url)
            
            # Handle 429 Too Many Requests atau Server Error -> RETRY
            if res.status_code == 429 or res.status_code >= 500:
                logger.warning(f"Received status {res.status_code} for {target_url}. Retrying (Attempt {attempt_count})...")
                continue
                
            # Handle Blocked/Legal Content (451, 403)
            if res.status_code in [403, 451]:
                logger.error(f"Access denied ({res.status_code}) for: {target_url}. Content likely blocked/DMCA.")
                return None
                
            # Handle 404 Not Found -> STOP (Jangan retry)
            if res.status_code == 404:
                logger.error(f"URL not found (404): {target_url}")
                return None

            # === FULL ASYNC MODIFICATION START ===
            # Operasi parsing BeautifulSoup adalah operasi blocking (CPU-bound).
            # Kita jalankan di thread terpisah agar tidak memblokir event loop asyncio.
            # Menggunakan res.content (bytes) agar decoding dilakukan di dalam thread juga.
            soup = await asyncio.to_thread(BeautifulSoup, res.content, 'html.parser')
            # === FULL ASYNC MODIFICATION END ===
            
            # Cek apakah HTML valid sesuai kriteria
            if validator_func(soup):
                logger.info(f"Successfully fetched and validated content from: {target_url}")
                return soup
            
            # Khusus kasus MobDisc: Redirect terjadi otomatis oleh HTTPX.
            # Jadi kita cek apakah content mengandung ciri khas MobDisc
            if "mobdisc" in str(res.url) or soup.select('a.b-download__button'):
                 logger.info(f"MobDisc content detected for: {target_url}")
                 return soup

            # MODIFIED: Jika status 200 (OK) tapi validator gagal (kolom tidak ada),
            # asumsikan memang tidak ada datanya. STOP RETRY.
            if res.status_code == 200:
                logger.warning(f"Fetched {target_url} with status 200, but validation failed (content missing). Stopping retry.")
                return None
                 
        except Exception as e:
            # MODIFIED: Biarin aja (continue), jangan sleep.
            logger.error(f"Exception occurred while fetching {target_url}: {str(e)}. Retrying (Attempt {attempt_count})...")
            continue
    
    return None

# ==========================================
# CORE LOGIC
# ==========================================

async def scan_cdn_page_loop(dwn_url: str) -> str:
    """
    Logika pengambilan link dari MobDisc berdasarkan HTML yang diberikan.
    """
    logger.info(f"Scanning CDN page loop for: {dwn_url}")
    
    def is_valid_mobdisc_page(soup):
        # Berdasarkan HTMLmu: tombol download memiliki class 'b-download__button'
        return bool(soup.select('a.b-download__button'))

    # dwn_url awalnya adalah https://pdalife.com/dwn/xxxx
    # Ini akan redirect ke https://mobdisc.com/dw....
    soup = await fetch_until_success(dwn_url, is_valid_mobdisc_page)
    
    if not soup:
        logger.warning(f"Failed to retrieve valid CDN page content for: {dwn_url}")
        return None
    
    buttons = soup.select('a.b-download__button')
    logger.info(f"Found {len(buttons)} download buttons on CDN page.")
    
    for btn in buttons:
        href = btn.get('href')
        if not href: continue
        
        # Skip link Telegram
        if "t.me" in href:
            continue
            
        # Prioritaskan link yang mengandung /fdl/ (File Download Link)
        if "/fdl/" in href:
            logger.info(f"Found FDL link: {href}")
            return unwrap_google_url(href)
            
        # Handle link yang diawali dengan #/download/ (MobDisc internal)
        if href.startswith("#/download/"):
            path = href[1:]
            logger.info(f"Found internal MobDisc hash link: {path}")
            return CDN_DOMAIN + path
            
        # Handle link download langsung lainnya yang bukan eksternal
        if "http" in href and "mobdisc.com" in href:
            logger.info(f"Found direct MobDisc link: {href}")
            return href
            
    logger.warning("No valid download link found in CDN page buttons.")
    return None

async def process_item_fully(name, detail_url, image):
    """
    Pipeline lengkap untuk satu aplikasi.
    """
    logger.info(f"Processing item: {name} | URL: {detail_url}")
    try:
        # 1. Validasi Halaman Detail
        def detail_page_valid(s):
            # Cari tombol download di accordion
            return bool(s.select('a.game-versions__downloads-button')) or bool(s.select('.accordion-item'))
        
        app_soup = await fetch_until_success(detail_url, detail_page_valid)
        if not app_soup:
            logger.error(f"Failed to load detail page for: {name}")
            return None

        # 2. Ambil SEMUA elemen download yang tersedia
        link_tags = []
        
        # Coba ambil dari list accordion (biasanya ada banyak versi)
        download_list_items = app_soup.select('.game-versions__downloads-list li')
        
        if download_list_items:
            for item in download_list_items:
                btn = item.select_one('a.game-versions__downloads-button')
                if btn:
                    link_tags.append(btn)
        else:
            # Fallback: jika tidak ada list, coba ambil semua tombol download yang terlihat
            logger.info(f"No download list found for {name}, trying standalone buttons.")
            fallback_buttons = app_soup.select('a.game-versions__downloads-button')
            link_tags.extend(fallback_buttons)

        if not link_tags:
            logger.warning(f"No download link tags found for: {name}")
            return None
            
        logger.info(f"Found {len(link_tags)} potential download links for {name}.")

        final_data_list = []
        main_size = "" # Kita ambil size dari link pertama saja sebagai referensi

        # 3. Loop dan proses setiap link yang ditemukan
        for index, link_tag in enumerate(link_tags):
            raw_link = link_tag.get('href')
            
            # Ambil ukuran file (hanya simpan yang pertama atau timpa, tapi di return kita pakai satu)
            if index == 0:
                size_tag = link_tag.select_one('.game-versions__downloads-size')
                main_size = size_tag.get_text(strip=True) if size_tag else ""
            
            if not raw_link: continue

            # === MODIFIKASI DIMULAI DARI SINI ===
            # Handle Magnet Link: Langsung simpan tanpa fetch/scan
            if raw_link.startswith("magnet:"):
                logger.info(f"Magnet link detected for {name} [{index}]. Adding directly.")
                final_data_list.append(raw_link)
                continue
            # === MODIFIKASI BERAKHIR DI SINI ===

            processed_link = None
            
            # Check if it's a direct external link (like onlinerp.me)
            if "http" in raw_link and "pdalife.com" not in raw_link and "/dwn/" not in raw_link:
                logger.info(f"External link detected for {name} [{index}]. Attempting to scan target: {raw_link}")
                direct_link = await scan_cdn_page_loop(raw_link)
                if direct_link:
                    processed_link = direct_link
                else:
                    logger.info(f"CDN scan failed for external link. Using raw link for {name} [{index}].")
                    processed_link = raw_link
            else:
                # Unwrap link /dwn/....
                dwn_link = unwrap_google_url(raw_link)
                logger.info(f"Unwrapped DWN link for {name} [{index}]: {dwn_link}")
                
                # Masuk ke MobDisc untuk ambil link asli
                direct_link = await scan_cdn_page_loop(dwn_link)
                if direct_link:
                    processed_link = direct_link
            
            if processed_link:
                final_data_list.append(processed_link)

        if not final_data_list:
            logger.warning(f"Final data list empty for {name} after processing all links.")
            return None

        # Gabungkan semua link dengan koma
        joined_downloads = ", ".join(final_data_list)
        logger.info(f"Successfully processed item: {name} with {len(final_data_list)} links.")
        
        return {
            "name": name,
            "link": unwrap_google_url(detail_url),
            "image": image,
            "download": joined_downloads, # Hasil gabungan dipisah koma
            "size": main_size 
        }
        
    except Exception as e:
        logger.error(f"Exception processing item {name}: {str(e)}")
        return None

# ==========================================
# ENDPOINTS
# ==========================================

@app.get("/")
async def root():
    return {
        "message": "Search API for PDALife.com by Bowo",
        "github": "https://github.com/SaptaZ",
        "example_usage": "/search?query=minecraft&limit=5"
    }

@app.get("/search")
async def search_apps(
    query: str = Query(..., description="App name"),
    limit: int = Query(5, description="Limit results")
):
    logger.info(f"Search request received. Query: '{query}' | Limit: {limit}")
    
    # Validator Search Page
    def search_page_valid(s):
        # Cek apakah ada item catalog atau pesan "Found 0"
        return bool(s.select('.catalog-item')) or "Found 0 responses" in s.get_text()

    collected_item_elements = []
    current_page = 1
    max_page = 1 # Default, will update from HTML if available
    
    # ---------------------------------------------------------
    # PAGINATION LOOP START
    # ---------------------------------------------------------
    while len(collected_item_elements) < limit:
        logger.info(f"Pagination: Fetching page {current_page} for query '{query}'")
        
        # Construct Search URL per Page
        if current_page == 1:
            search_url = f"{BASE_DOMAIN}/search/{query}"
        else:
            search_url = f"{BASE_DOMAIN}/search/{query}/page-{current_page}/"
        
        soup = await fetch_until_success(search_url, search_page_valid)
        
        if not soup:
            logger.warning(f"Pagination stopped. Could not fetch page {current_page}.")
            break

        # Check for empty result message
        if "Found 0 responses" in soup.get_text():
            logger.info(f"Search found 0 responses on page {current_page}.")
            break

        # Get items on current page
        page_items = soup.select('.catalog-item')
        if not page_items:
            logger.info(f"No catalog items found on page {current_page}.")
            break
            
        collected_item_elements.extend(page_items)
        logger.info(f"Collected {len(page_items)} items from page {current_page}. Total collected: {len(collected_item_elements)}")

        # Check max pages from the "Load More" button data attributes
        load_more_btn = soup.select_one('.js-load_more')
        if load_more_btn and load_more_btn.has_attr('data-max_page'):
            try:
                max_page = int(load_more_btn['data-max_page'])
                logger.info(f"Max page detected: {max_page}")
            except:
                pass
        
        # Stop if we reached the last known page
        if current_page >= max_page:
            logger.info("Reached last known page. Stopping pagination.")
            break
            
        current_page += 1
    # ---------------------------------------------------------
    # PAGINATION LOOP END
    # ---------------------------------------------------------

    if not collected_item_elements:
        logger.info(f"Search finished. No items found for query '{query}'.")
        return {"success": True, "count": 0, "results": []}

    # Slice to exact limit before processing to save resources
    items_to_process = collected_item_elements[:limit]
    logger.info(f"Starting concurrent processing for {len(items_to_process)} items.")
    
    tasks = []
    # Loop items found
    for item in items_to_process:
        title_el = item.select_one('.catalog-item__title a')
        if not title_el: continue
        
        name = title_el.get_text(strip=True)
        # Link detail (masih relative / wrapped)
        detail_href = title_el['href']
        detail_link = unwrap_google_url(detail_href) # Bersihkan dulu biar jadi absolute pdalife.com
        
        img_el = item.select_one('.catalog-item__poster img')
        image = unwrap_google_url(img_el['src']) if img_el else ""
        
        # Buat task async untuk memproses detail item ini
        tasks.append(process_item_fully(name, detail_link, image))

    # Jalankan semua task secara paralel
    results = await asyncio.gather(*tasks)
    
    # Bersihkan hasil None (gagal)
    valid_results = [r for r in results if r is not None]
    
    logger.info(f"Search request completed. Returning {len(valid_results)} valid results.")

    return {
        "success": True,
        "query": query,
        "limit": limit,
        "count": len(valid_results),
        "results": valid_results
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    logger.info(f"Starting Uvicorn server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)