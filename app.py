import streamlit as st
import pandas as pd
import asyncio
import plotly.express as px
from playwright.async_api import async_playwright

# Ustawienia wyglądu strony (m.in. responsywność pod telefony)
st.set_page_config(page_title="Monitor Cen OLX", layout="wide")

# Słownik z gotowymi linkami dla poszczególnych dzielnic (bez limitów cenowych)
DZIELNICE_LINKS = {
    "Kraków - Dębniki": "https://www.olx.pl/nieruchomosci/stancje-pokoje/krakow/q-pok%C3%B3j/?search%5Bdistrict_id%5D=261",
    "Kraków - Krowodrza": "https://www.olx.pl/nieruchomosci/stancje-pokoje/krakow/q-pok%C3%B3j/?search%5Bdistrict_id%5D=255",
    "Kraków - Bronowice": "https://www.olx.pl/nieruchomosci/stancje-pokoje/krakow/q-pok%C3%B3j/?search%5Bdistrict_id%5D=259"
}

# Stabilna funkcja scrapująca dostosowana do działania na serwerze (Chmura)
async def scrape_olx_for_app(url, pages):
    all_offers = []
    async with async_playwright() as p:
        # Headless=True jest wymagane, ponieważ serwer w chmurze nie ma fizycznego monitora
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for current_page in range(1, pages + 1):
            page_url = f"{url}&page={current_page}" if "?" in url else f"{url}?page={current_page}"
            try:
                await page.goto(page_url, wait_until="load", timeout=45000)
                await page.wait_for_timeout(2000)

                # Automat klika RODO za nas, ponieważ działamy w tle i nie widzimy okna
                if current_page == 1:
                    try:
                        cookie_button = page.locator('button:has-text("Anuluj"), button:has-text("Akceptuję"), button:has-text("Zgadzam się"), #onetrust-accept-btn-handler').first
                        if await cookie_button.count() > 0:
                            await cookie_button.click()
                            await page.wait_for_timeout(1000)
                    except:
                        pass

                cards = await page.locator('[data-testid="l-card"]').all()
                for card in cards:
                    try:
                        title_elem = card.locator('h6')
                        title = await title_elem.first.inner_text() if await title_elem.count() > 0 else "Brak tytułu"

                        price_elem = card.locator('[data-testid="ad-price"]')
                        price_text = await price_elem.first.inner_text() if await price_elem.count() > 0 else "Brak"

                        # Oczyszczanie tekstu ceny do samych cyfr
                        cleaned_price = price_text.replace("zł", "").replace("do negocjacji", "").replace(" ", "").replace("\n", "").strip()

                        link_elem = card.locator("a")
                        link = await link_elem.first.get_attribute("href") if await link_elem.count() > 0 else ""
                        if link and link.startswith("/"):
                            link = f"https://www.olx.pl{link}"

                        if link and "olx.pl" in link and cleaned_price.isdigit():
                            all_offers.append({
                                "Tytuł": title.strip(),
                                "Cena (PLN)": int(cleaned_price),
                                "Link": link
                            })
                    except:
                        continue
            except:
                break
        await browser.close()
    return all_offers

# --- INTERFEJS STRONY STREAMLIT ---
st.title("📊 Panel Analizy Cen Pokoi - OLX")
st.write("Wybierz rejon, aby wygenerować raport i wykresy bezpośrednio w przeglądarce.")

# Menu wyboru rejonu i slider głębokości stron
wybrana_dzielnica = st.selectbox("Wybierz rejon / dzielnicę:", list(DZIELNICE_LINKS.keys()))
limit_stron = st.slider("Głębokość przeszukiwania (ile stron ogłoszeń):", min_value=1, max_value=5, value=2)

# Pobranie linku przypisanego do wybranej opcji
selected_url = DZIELNICE_LINKS[wybrana_dzielnica]

# Główny przycisk uruchamiający analizę w chmurze
if st.button("🚀 SPRAWDŹ I ANALIZUJ", type="primary"):
    with st.spinner(f"Chmura pobiera i analizuje dane z OLX dla rejonu: {wybrana_dzielnica}..."):
        
        # Inicjalizacja pętli zdarzeń dla środowiska Streamlit
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        data = loop.run_until_complete(scrape_olx_for_app(selected_url, limit_stron))
        
        if data:
            df = pd.DataFrame(data)
            df = df.drop_duplicates(subset=["Link"])

            # --- STATYSTYKI KPI ---
            st.success(f"Analiza zakończona sukcesem! Znaleziono {len(df)} pasujących ogłoszeń.")
            
            s1, s2, s3 = st.columns(3)
            s1.metric("Średnia Cena rynkowa", f"{round(df['Cena (PLN)'].mean())} PLN")
            s2.metric("Najniższa Cena w rejonie", f"{df['Cena (PLN)'].min()} PLN")
            s3.metric("Najwyższa Cena w rejonie", f"{df['Cena (PLN)'].max()} PLN")

            # --- INTERAKTYWNY WYKRES ---
            st.subheader("📈 Rozkład cen w wybranym rejonie")
            fig = px.histogram(df, x="Cena (PLN)", title="Liczba dostępnych ofert w danych przedziałach cenowych", 
                               labels={"count": "Liczba ofert"}, color_discrete_sequence=['#00A49F'])
            st.plotly_chart(fig, use_container_width=True)

            # --- INTERAKTYWNA TABELA WYNIKÓW ---
            st.subheader("📋 Czysta lista aktualnych ogłoszeń")
            st.write("Klikaj w nagłówki kolumn poniżej, aby sortować ceny od najniższych lub najwyższych.")
            
            st.dataframe(
                df, 
                column_config={"Link": st.column_config.LinkColumn("Link bezpośredni do OLX ↗")},
                use_container_width=True,
                hide_index=True
            )
        else:
            st.error("Brak aktualnych ofert dla tego rejonu spełniających kryteria lub serwer OLX zablokował zapytanie. Spróbuj ponownie za chwilę.")
