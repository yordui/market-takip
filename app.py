import streamlit as st
import requests
import sqlite3
import pandas as pd
import urllib3
import urllib.parse
import time
import random

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_URL = "https://api.marketfiyati.org.tr/api/v2/search"
BASE_URL = "https://marketfiyati.org.tr/"

if 'arama_sonuclari' not in st.session_state:
    st.session_state.arama_sonuclari = []

# --- VERİTABANI İŞLEMLERİ ---
def init_db():
    conn = sqlite3.connect('market.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS listem
                 (id TEXT PRIMARY KEY, 
                  urun_adi TEXT, 
                  market_adi TEXT, 
                  kategori TEXT,
                  gorsel_url TEXT,
                  ilk_ambalaj REAL, 
                  ilk_birim REAL, 
                  hedef_ambalaj REAL, 
                  hedef_birim REAL,
                  son_guncel_fiyat REAL,
                  son_guncel_birim REAL)''')
    
    for sutun, tip in [("son_guncel_birim", "REAL"), ("kategori", "TEXT"), ("gorsel_url", "TEXT")]:
        try:
            c.execute(f"ALTER TABLE listem ADD COLUMN {sutun} {tip}")
        except sqlite3.OperationalError:
            pass
        
    conn.commit()
    conn.close()

def urunu_listeye_ekle(urun_id, urun_adi, market_adi, kategori, gorsel_url, ambalaj, birim, hedef_ambalaj, hedef_birim):
    conn = sqlite3.connect('market.db')
    c = conn.cursor()
    benzersiz_id = f"{urun_id}-{market_adi}"
    
    c.execute("SELECT id FROM listem WHERE id = ?", (benzersiz_id,))
    var_mi = c.fetchone()
    
    if var_mi:
        conn.close()
        return False, "Bu ürün zaten listenizde bulunuyor!"

    h_amb = None
    h_bir = None
    if hedef_ambalaj and hedef_ambalaj > 0:
        h_amb = hedef_ambalaj
    elif hedef_birim and hedef_birim > 0:
        h_bir = hedef_birim

    c.execute('''INSERT INTO listem 
                 (id, urun_adi, market_adi, kategori, gorsel_url, ilk_ambalaj, ilk_birim, hedef_ambalaj, hedef_birim, son_guncel_fiyat, son_guncel_birim) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (benzersiz_id, urun_adi, market_adi, kategori, gorsel_url, ambalaj, birim, h_amb, h_bir, ambalaj, birim))
    conn.commit()
    conn.close()
    return True, "Ürün başarıyla listeye eklendi!"

def hedefleri_guncelle(benzersiz_id, yeni_hedef_ambalaj, yeni_hedef_birim):
    conn = sqlite3.connect('market.db')
    c = conn.cursor()
    
    h_amb = None
    h_bir = None
    if yeni_hedef_ambalaj and yeni_hedef_ambalaj > 0:
        h_amb = yeni_hedef_ambalaj
    elif yeni_hedef_birim and yeni_hedef_birim > 0:
        h_bir = yeni_hedef_birim

    c.execute("UPDATE listem SET hedef_ambalaj = ?, hedef_birim = ? WHERE id = ?", (h_amb, h_bir, benzersiz_id))
    conn.commit()
    conn.close()

def urunu_listeden_sil(benzersiz_id):
    conn = sqlite3.connect('market.db')
    c = conn.cursor()
    c.execute("DELETE FROM listem WHERE id = ?", (benzersiz_id,))
    conn.commit()
    conn.close()

# --- OTURUM (SESSION) TAKLİTLİ API ARAMASI ---
def urun_ara(kelime):
    tum_sonuclar = []
    
    # Gerçek tarayıcı kimlikleri
    headers_guncel = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
        "Origin": "https://marketfiyati.org.tr",
        "Referer": "https://marketfiyati.org.tr/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    }
    
    try:
        # 1. ADIM: Güvenlik Duvarını aşmak için kalıcı oturum (Session) başlat
        oturum = requests.Session()
        
        # 2. ADIM: Ana sayfayı ziyaret edip güvenlik çerezlerini (cookies) topla
        oturum.get(BASE_URL, headers={"User-Agent": headers_guncel["User-Agent"]}, verify=False, timeout=10)
        time.sleep(1) # Gerçek insan gibi 1 saniye bekle
        
        # 3. ADIM: Toplanan çerezlerle API sorgusu yap
        for sayfa_no in range(4):
            payload = {
                "keywords": kelime.strip(),
                "page": sayfa_no,
                "size": 25, 
                "latitude": 40.847500,
                "longitude": 29.303800,
                "distance": 30
            }
            
            res = oturum.post(API_URL, json=payload, headers=headers_guncel, verify=False, timeout=12)
            
            if res.status_code == 200:
                gelen_urunler = res.json().get("content", [])
                if not gelen_urunler:
                    break
                    
                for urun in gelen_urunler:
                    if not any(u.get("id") == urun.get("id") for u in tum_sonuclar):
                        tum_sonuclar.append(urun)
            elif res.status_code == 418:
                st.error("⚠️ Sunucu hala bizi bot olarak görüyor. (418 Hatası)")
                break
            else:
                st.warning(f"Bağlantı Hatası: Sunucu {res.status_code} döndürdü.")
                break
                
            time.sleep(random.uniform(0.5, 1.2))
            
    except Exception as e:
        st.error(f"❌ Hata oluştu: {e}")
            
    return tum_sonuclar

# --- STREAMLIT WEB ARAYÜZÜ ---
st.set_page_config(page_title="İndirim Avcısı", layout="wide")
init_db()

st.title("🛒 İndirim Avcısı")
st.caption("📍 Arama Merkezi: İçmeler Mh. Seyit Onbaşı Cd. (Tuzla/İstanbul)")

tab1, tab2 = st.tabs(["🔍 Ürün Ara dan Ekle", "📋 Listem ve İndirimler"])

with tab1:
    MARKETLER_LISTE = ["A101", "BİM", "Şok", "Migros", "CarrefourSA", "Hakmar", "Tarım Kredi"]
    MARKET_MAP = {"A101": "a101", "BİM": "bim", "Şok": "sok", "Migros": "migros", "CarrefourSA": "carrefour", "Hakmar": "hakmar", "Tarım Kredi": "tarim_kredi"}
    
    col_arama, col_market = st.columns([2, 1])
    with col_arama:
        aranan_kelime = st.text_input("Aramak istediğiniz ürünü yazın (Örn: Ayçiçek):")
    with col_market:
        secilen_marketler = st.multiselect("Market Seçimi", options=MARKETLER_LISTE, default=MARKETLER_LISTE)
    
    if st.button("Ara"):
        if aranan_kelime and secilen_marketler:
            with st.spinner('Siteye bağlanılıyor ve arama yapılıyor...'):
                st.session_state.arama_sonuclari = urun_ara(aranan_kelime)
                if not st.session_state.arama_sonuclari:
                    st.warning("Ürün bulunamadı veya sonuç gelmedi.")
        else:
            st.warning("Lütfen aranacak ürünü ve en az bir marketi seçin.")

    if st.session_state.arama_sonuclari:
        st.divider()
        st.subheader("⚙️ Sonuçları Filtrele")

        tum_markalar = set()
        tum_kategoriler = set()
        tum_hacimler = set()
        
        for u in st.session_state.arama_sonuclari:
            tum_markalar.add(u.get("brand", "Belirtilmemiş"))
            tum_kategoriler.add(u.get("main_category", "Belirtilmemiş"))
            tum_hacimler.add(u.get("refinedQuantityUnit") or u.get("refinedVolumeOrWeight", "Belirtilmemiş"))
            
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            secilen_markalar = st.multiselect("Marka Seç", sorted(list(tum_markalar)))
        with f_col2:
            secilen_kategoriler = st.multiselect("Kategori Seç", sorted(list(tum_kategoriler)))
        with f_col3:
            secilen_hacimler = st.multiselect("Hacim/Miktar Seç", sorted(list(tum_hacimler)))
            
        st.divider()
        
        gosterilen_urun_sayisi = 0
        secilen_api_isimleri = [MARKET_MAP[m].lower() for m in secilen_marketler]
        
        for urun in st.session_state.arama_sonuclari:
            urun_adi = urun.get("title")
            urun_id = urun.get("id")
            gorsel_url = urun.get("imageUrl")
            
            u_marka = urun.get("brand", "Belirtilmemiş")
            u_kategori = urun.get("main_category", "Genel")
            u_hacim = urun.get("refinedQuantityUnit") or urun.get("refinedVolumeOrWeight", "Belirtilmemiş")
            
            if secilen_markalar and u_marka not in secilen_markalar:
                continue
            if secilen_kategoriler and u_kategori not in secilen_kategoriler:
                continue
            if secilen_hacimler and u_hacim not in secilen_hacimler:
                continue
            
            for depot in urun.get("productDepotInfoList", []):
                market_kodu = str(depot.get("marketAdi", "")).strip().lower()
                eslesen_gorsel_isim = "Bilinmeyen"
                gecerli_market = False
                
                for k, v in MARKET_MAP.items():
                    if v.lower() == market_kodu or market_kodu in v.lower():
                        eslesen_gorsel_isim = k
                        if v.lower() in secilen_api_isimleri:
                            gecerli_market = True
                        break
                        
                if not gecerli_market:
                    continue
                    
                gosterilen_urun_sayisi += 1
                ambalaj_fiyat = depot.get("price")
                birim_fiyat = depot.get("unitPriceValue")
                
                with st.container():
                    img_col, col1, col2, col3 = st.columns([0.8, 2.5, 1, 1])
                    
                    with img_col:
                        if gorsel_url:
                            st.image(gorsel_url, width=70)
                        else:
                            st.write("📷 Resim Yok")
                            
                    with col1:
                        st.write(f"**{urun_adi}** ({eslesen_gorsel_isim})")
                        st.caption(f"Kategori: {u_kategori} | {u_marka} | {u_hacim}")
                        
                        market_fiyati_linki = f"https://marketfiyati.org.tr/arama?q={urllib.parse.quote(urun_adi)}"
                        st.markdown(f"[🔗 MarketFiyatı.org.tr'de İncele]({market_fiyati_linki})", unsafe_allow_html=True)

                    with col2:
                        st.write(f"Paket: **{ambalaj_fiyat} ₺**")
                    with col3:
                        st.write(f"Birim: {birim_fiyat:.2f} ₺" if birim_fiyat else "Birim: Yok")
                    
                    with st.expander(f"🔔 {eslesen_gorsel_isim} - Takip Et / Hedef Belirle"):
                        benzersiz_id = f"{urun_id}-{MARKET_MAP.get(eslesen_gorsel_isim, 'x')}"
                        takip_secim = st.radio("Takip Türü:", ["Sadece İndirimleri Takip Et", "Paket Fiyatı Hedefi Gir", "Birim Fiyatı Hedefi Gir"], key=f"radio_{benzersiz_id}")
                        
                        hedef_ambalaj, hedef_birim = None, None
                        if takip_secim == "Paket Fiyatı Hedefi Gir":
                            hedef_ambalaj = st.number_input("Hedef Paket Fiyatı (₺):", min_value=0.0, value=float(ambalaj_fiyat), key=f"ambalaj_{benzersiz_id}")
                        elif takip_secim == "Birim Fiyatı Hedefi Gir" and birim_fiyat:
                            hedef_birim = st.number_input("Hedef Birim Fiyatı (₺):", min_value=0.0, value=float(birim_fiyat), key=f"birim_{benzersiz_id}")
                            
                        if st.button("Listeme Ekle", key=f"btn_{benzersiz_id}"):
                            basarili, mesaj = urunu_listeye_ekle(urun_id, urun_adi, eslesen_gorsel_isim, u_kategori, gorsel_url, ambalaj_fiyat, birim_fiyat, hedef_ambalaj, hedef_birim)
                            if basarili:
                                st.success(mesaj)
                            else:
                                st.warning(mesaj)
                    st.divider()
        
        st.success(f"Filtrelere uygun toplam {gosterilen_urun_sayisi} adet ürün listelendi.")

with tab2:
    st.subheader("Takip Ettiğim Ürünler ve Fiyat Durumları")
    
    conn = sqlite3.connect('market.db')
    df = pd.read_sql_query("SELECT * FROM listem", conn)
    conn.close()
    
    if df.empty:
        st.info("Listeniz henüz boş. Arama sekmesinden ürün ekleyebilirsiniz.")
    else:
        sadece_indirim = st.toggle("📉 Sadece İndirimdekileri Göster")
        if sadece_indirim:
            df = df[df['son_guncel_fiyat'] < df['ilk_ambalaj']]
            
        kategoriler = ["Tümü"] + sorted(df['kategori'].dropna().unique().tolist())
        secilen_kategori_tab = st.radio("Kategoriye Göre Filtrele:", kategoriler, horizontal=True)
        
        if secilen_kategori_tab != "Tümü":
            df = df[df['kategori'] == secilen_kategori_tab]
            
        if not df.empty:
            df['siralama_birim'] = df['son_guncel_birim'].fillna(df['ilk_birim']).fillna(999999)
            df = df.sort_values(by='siralama_birim', ascending=True)
            
        st.divider()
        
        for index, row in df.iterrows():
            with st.container():
                img_col, c1, c2, c3, c4, c5 = st.columns([0.7, 2.2, 1.2, 1.2, 1.2, 0.8])
                
                with img_col:
                    gorsel = row.get('gorsel_url')
                    if gorsel and isinstance(gorsel, str) and gorsel.startswith("http"):
                        st.image(gorsel, width=65)
                    else:
                        st.write("📷 Yok")
                
                guncel_fiyat = row['son_guncel_fiyat'] if row['son_guncel_fiyat'] is not None else row['ilk_ambalaj']
                guncel_birim = row['son_guncel_birim'] if 'son_guncel_birim' in row and row['son_guncel_birim'] is not None else row.get('ilk_birim')
                
                indirim_mi = guncel_fiyat < row['ilk_ambalaj']
                ikon = "📉" if indirim_mi else "📌"
                
                kategori_adi = row['kategori'] if 'kategori' in row and row['kategori'] else "Genel"
                c1.write(f"{ikon} **{row['urun_adi']}** ({row['market_adi']})")
                c1.caption(f"📂 Kategori: {kategori_adi}")
                
                ilk_birim_deger = row['ilk_birim'] if row['ilk_birim'] is not None else 0.0
                c2.write(f"İlk Paket: {row['ilk_ambalaj']} ₺\n\nİlk Birim: {ilk_birim_deger:.2f} ₺" if ilk_birim_deger > 0 else f"İlk Paket: {row['ilk_ambalaj']} ₺")
                
                guncel_birim_deger = guncel_birim if guncel_birim is not None else 0.0
                guncel_birim_metin = f"Güncel Birim: {guncel_birim_deger:.2f} ₺" if guncel_birim_deger > 0 else "Güncel Birim: Yok"
                
                if indirim_mi:
                    c3.markdown(f"Güncel Paket: :green[{guncel_fiyat} ₺]\n\n{guncel_birim_metin}")
                else:
                    c3.write(f"Güncel Paket: {guncel_fiyat} ₺\n\n{guncel_birim_metin}")
                
                mevcut_h_amb = row['hedef_ambalaj'] if row['hedef_ambalaj'] is not None and row['hedef_ambalaj'] > 0 else 0.0
                mevcut_h_bir = row['hedef_birim'] if row['hedef_birim'] is not None and row['hedef_birim'] > 0 else 0.0
                
                if mevcut_h_amb > 0:
                    c4.write(f"🎯 Paket Hedef: {mevcut_h_amb} ₺")
                elif mevcut_h_bir > 0:
                    c4.write(f"🎯 Birim Hedef: {mevcut_h_bir} ₺")
                else:
                    c4.write("🎯 Hedef: Yok")
                
                with c4.expander("✏️ Hedef Düzenle"):
                    hedef_tipi = st.radio("Hedef Tipi:", ["Hedef Yok", "Paket Fiyatı", "Birim Fiyatı"], key=f"h_tip_{row['id']}")
                    
                    yeni_h_amb, yeni_h_bir = 0.0, 0.0
                    if hedef_tipi == "Paket Fiyatı":
                        yeni_h_amb = st.number_input("Yeni Paket Hedef (₺):", min_value=0.0, value=float(mevcut_h_amb if mevcut_h_amb > 0 else guncel_fiyat), key=f"h_amb_{row['id']}")
                    elif hedef_tipi == "Birim Fiyatı":
                        yeni_h_bir = st.number_input("Yeni Birim Hedef (₺):", min_value=0.0, value=float(mevcut_h_bir if mevcut_h_bir > 0 else (guncel_birim or 0.0)), key=f"h_bir_{row['id']}")
                    
                    if st.button("Güncelle", key=f"btn_hedef_{row['id']}"):
                        hedefleri_guncelle(row['id'], yeni_h_amb if hedef_tipi == "Paket Fiyatı" else 0, yeni_h_bir if hedef_tipi == "Birim Fiyatı" else 0)
                        st.success("Hedef güncellendi!")
                        st.rerun()

                if c5.button("🗑️ Sil", key=f"sil_{row['id']}"):
                    urunu_listeden_sil(row['id'])
                    st.success(f"\"{row['urun_adi']}\" listeden çıkarıldı!")
                    st.rerun()
                
                st.divider()