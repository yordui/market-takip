import sqlite3
import requests
import os
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_URL = "https://api.marketfiyati.org.tr/api/v2/search"

def telegram_mesaj_gonder(mesaj):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram bilgileri eksik!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mesaj,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram mesajı gönderilemedi: {e}")

def fiyatlari_kontrol_et():
    if not os.path.exists('market.db'):
        print("market.db bulunamadı.")
        return

    conn = sqlite3.connect('market.db')
    c = conn.cursor()
    c.execute("SELECT id, urun_adi, market_adi, ilk_ambalaj, ilk_birim, hedef_ambalaj, hedef_birim, son_guncel_fiyat FROM listem")
    urunler = c.fetchall()

    for row in urunler:
        u_id, urun_adi, market_adi, ilk_ambalaj, ilk_birim, hedef_ambalaj, hedef_birim, son_fiyat = row
        
        # Orijinal ID'yi almak için (id formatı: urun_id-market_kodu şeklinde saklanmıştı)
        parcalar = u_id.split("-")
        Gercek_urun_id = parcalar[0]
        market_kodu = "-".join(parcalar[1:])

        # API'den güncel fiyatı çekelim
        payload = {
            "keywords": urun_adi[:25], # Kelimeyi çok uzatmamak için
            "pages": 0,
            "size": 50,
            "latitude": 40.8478933942271,
            "longitude": 29.30380154036927,
            "distance": 5
        }
        headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

        try:
            res = requests.post(API_URL, json=payload, headers=headers, verify=False, timeout=10)
            if res.status_code == 200:
                gelen_liste = res.json().get("content", [])
                guncel_ambalaj = None
                
                for item in gelen_liste:
                    if str(item.get("id")) == str(Gercek_urun_id):
                        for depot in item.get("productDepotInfoList", []):
                            if depot.get("marketAdi") == market_kodu:
                                guncel_ambalaj = depot.get("price")
                                break
                
                if guncel_ambalaj:
                    # Veritabanındaki güncel fiyatı güncelleyelim
                    c.execute("UPDATE listem SET son_guncel_fiyat = ? WHERE id = ?", (guncel_ambalaj, u_id))
                    conn.commit()

                    # Bildirim şartları
                    # 1. Hedef paket fiyatına ulaşıldı mı?
                    if hedef_ambalaj and guncel_ambalaj <= hedef_ambalaj:
                        telegram_mesaj_gonder(f"🎯 **HEDEF FİYATA ULAŞILDI!**\n\n*{urun_adi}* ({market_adi})\nHedefiniz: {hedef_ambalaj} ₺\n**Güncel Fiyat: {guncel_ambalaj} ₺**")
                    
                    # 2. Genel bir indirim var mı (İlk fiyata göre düşüş)?
                    elif guncel_ambalaj < ilk_ambalaj:
                        telegram_mesaj_gonder(f"📉 **İNDİRİM VAR!**\n\n*{urun_adi}* ({market_adi})\nİlk Fiyat: {ilk_ambalaj} ₺\n**Yeni Fiyat: {guncel_ambalaj} ₺**")

        except Exception as e:
            print(f"Hata oluştu: {e}")

    conn.close()

if __name__ == "__main__":
    fiyatlari_kontrol_et()