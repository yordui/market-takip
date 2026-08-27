import streamlit as st
import requests
import sqlite3
import pandas as pd
import urllib3
import urllib.parse
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_URL = "https://api.marketfiyati.org.tr/api/v2/search"

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
                  ilk_ambalaj REAL, 
                  ilk_birim REAL, 
                  hedef_ambalaj REAL, 
                  hedef_birim REAL,
                  son_guncel_fiyat REAL,
                  son_guncel_birim REAL)''')
    
    try:
        c.execute("ALTER TABLE listem ADD COLUMN son_guncel_birim REAL")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

def urunu_listeye_ekle(urun_id, urun_adi, market_adi, ambalaj, birim, hedef_ambalaj, hedef_birim):
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
                 (id, urun_adi, market_adi, ilk_ambalaj, ilk_birim, hedef_ambalaj, hedef_birim, son_guncel_fiyat, son_guncel_birim) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (benzersiz_id, urun_adi, market_adi, ambalaj, birim, h_amb, h_bir, ambalaj, birim))
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

# --- API ARAMA FONKSİYONU ---
def urun_ara(kelime):
    tum_sonuclar = []
    headers_guncel = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Connection": "close"
    }
    
    for sayfa_no in range(2):
        payload = {
            "keywords": kelime,
            "pages": sayfa_no,
            "size": 50, 
            "latitude": 40.8478933942271,
            "longitude": 29.30380154036927,
            "distance": 5
        }
        
        try:
            res = requests.post(API_URL, json=payload, headers=headers_guncel, verify=False, timeout=15)
            if res.status_code == 200:
                gelen_urunler = res.json().get("content", [])
                if not gelen_urunler:
                    break
                tum_sonuclar.extend(gelen_urunler)
            else:
                break
            time.sleep(1)
        except Exception:
            break
            
    return tum_sonuclar

# --- STREAMLIT WEB ARAYÜZÜ ---
st.set_page_config(page_title="İndirim Avcısı", layout="wide")
init_db()

st.title("🛒 İndirim Avcısı")

tab1, tab2 = st.tabs(["🔍 Ürün Ara dan Ekle", "📋 Listem ve İndirimler"])

with tab1:
    MARKETLER = {"A101": "a101", "BİM": "bim", "Şok": "sok", "Migros": "migros", "CarrefourSA": "carrefour", "Hakmar": "hakmar", "Tarım Kredi": "tarim_kredi"}
    
    col_arama, col_market = st.columns([2, 1])
    with col_arama:
        aranan_kelime = st.text_input("Aramak istediğiniz ürünü yazın (Örn: Süt):")
    with col_market:
        secilen_marketler = st.multiselect("Market Seçimi", options=list(MARKETLER.keys()), default=list(MARKETLER.keys()))
    
    if st.button("Ara"):
        if aranan_kelime and secilen_marketler:
            with st.spinner('Ürünler toplanıyor...'):
                st.session_state.arama_sonuclari = urun_ara(aranan_kelime)
                if not st.session_state.arama_sonuclari:
                    st.warning("Ürün bulunamadı.")
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
        secilen_api_isimleri = [MARKETLER[m] for m in secilen_marketler]
        
        for urun in st.session_state.arama_sonuclari:
            urun_adi = urun.get("title")
            urun_id = urun.get("id")
            gorsel_url = urun.get("imageUrl")
            
            u_marka = urun.get("brand", "Belirtilmemiş")
            u_kategori = urun.get("main_category", "Belirtilmemiş")
            u_hacim = urun.get("refinedQuantityUnit") or urun.get("refinedVolumeOrWeight", "Belirtilmemiş")
            
            if secilen_markalar and u_marka not in secilen_markalar:
                continue
            if secilen_kategoriler and u_kategori not in secilen_kategoriler:
                continue
            if secilen_hacimler and u_hacim not in secilen_hacimler:
                continue
            
            for depot in urun.get("productDepotInfoList", []):
                market_kodu = depot.get("marketAdi")
                if market_kodu not in secilen_api_isimleri:
                    continue
                    
                gosterilen_urun_sayisi += 1
                market_gorsel_isim = [k for k, v in MARKETLER.items() if v == market_kodu][0]
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
                        st.write(f"**{urun_adi}** ({market_gorsel_isim})")
                        st.caption(f"{u_marka} | {u_kategori} | {u_hacim}")
                        
                        market_fiyati_linki = f"https://marketfiyati.org.tr/arama?q={urllib.parse.quote(urun_adi)}"
                        st.markdown(f"[🔗 MarketFiyatı.org.tr'de İncele]({market_fiyati_linki})", unsafe_allow_html=True)

                    with col2:
                        st.write(f"Paket: **{ambalaj_fiyat} ₺**")
                    with col3:
                        st.write(f"Birim: {birim_fiyat:.2f} ₺" if birim_fiyat else "Birim: Yok")
                    
                    with st.expander(f"🔔 {market_gorsel_isim} - Takip Et / Hedef Belirle"):
                        benzersiz_id = f"{urun_id}-{market_kodu}"
                        takip_secim = st.radio("Takip Türü:", ["Sadece İndirimleri Takip Et", "Paket Fiyatı Hedefi Gir", "Birim Fiyatı Hedefi Gir"], key=f"radio_{benzersiz_id}")
                        
                        hedef_ambalaj, hedef_birim = None, None
                        if takip_secim == "Paket Fiyatı Hedefi Gir":
                            hedef_ambalaj = st.number_input("Hedef Paket Fiyatı (₺):", min_value=0.0, value=float(ambalaj_fiyat), key=f"ambalaj_{benzersiz_id}")
                        elif takip_secim == "Birim Fiyatı Hedefi Gir" and birim_fiyat:
                            hedef_birim = st.number_input("Hedef Birim Fiyatı (₺):", min_value=0.0, value=float(birim_fiyat), key=f"birim_{benzersiz_id}")
                            
                        if st.button("Listeme Ekle", key=f"btn_{benzersiz_id}"):
                            basarili, mesaj = urunu_listeye_ekle(urun_id, urun_adi, market_gorsel_isim, ambalaj_fiyat, birim_fiyat, hedef_ambalaj, hedef_birim)
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
            
        for index, row in df.iterrows():
            with st.container():
                c1, c2, c3, c4, c5 = st.columns([2.2, 1.2, 1.2, 1.2, 0.8])
                
                guncel_fiyat = row['son_guncel_fiyat'] if row['son_guncel_fiyat'] is not None else row['ilk_ambalaj']
                guncel_birim = row['son_guncel_birim'] if 'son_guncel_birim' in row and row['son_guncel_birim'] is not None else row.get('ilk_birim')
                
                indirim_mi = guncel_fiyat < row['ilk_ambalaj']
                ikon = "📉" if indirim_mi else "📌"
                
                c1.write(f"{ikon} **{row['urun_adi']}** ({row['market_adi']})")
                
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