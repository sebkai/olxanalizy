import asyncio
import json
import re
import pandas as pd
from playwright.async_api import async_playwright

# ================= KONFIGURACJA DZIELNIC =================
DZIELNICE_LINKS = {
    "Kraków - Dębniki": "https://www.olx.pl/nieruchomosci/stancje-pokoje/krakow/q-pok%C3%B3j/?search%5Bdistrict_id%5D=261",
    "Kraków - Krowodrza": "https://www.olx.pl/nieruchomosci/stancje-pokoje/krakow/q-pok%C3%B3j/?search%5Bdistrict_id%5D=255",
    "Kraków - Bronowice": "https://www.olx.pl/nieruchomosci/stancje-pokoje/krakow/q-pok%C3%B3j/?search%5Bdistrict_id%5D=259"
}
LIMIT_STRON = 2  # Ile stron z każdej dzielnicy przeszukać
# =========================================================

async def pobierz_oferty(page, url):
    offers = []
    for current_page in range(1, LIMIT_STRON + 1):
        page_url = f"{url}&page={current_page}" if "?" in url else f"{url}?page={current_page}"
        try:
            await page.goto(page_url, wait_until="load", timeout=30000)
            await page.wait_for_timeout(2000)

            cards = await page.locator('[data-testid="l-card"]').all()
            for card in cards:
                try:
                    title_elem = card.locator('h6')
                    title = await title_elem.first.inner_text() if await title_elem.count() > 0 else "Brak tytułu"

                    price_elem = card.locator('[data-testid="ad-price"]')
                    price_text = await price_elem.first.inner_text() if await price_elem.count() > 0 else "Brak"

                    cleaned_price = price_text.replace("zł", "").replace("do negocjacji", "").replace(" ", "").replace("\n", "").strip()

                    link_elem = card.locator("a")
                    link = await link_elem.first.get_attribute("href") if await link_elem.count() > 0 else ""
                    if link and link.startswith("/"):
                        link = f"https://www.olx.pl{link}"

                    if link and "olx.pl" in link and cleaned_price.isdigit():
                        offers.append({
                            "title": title.strip(),
                            "price": int(cleaned_price),
                            "link": link
                        })
                except:
                    continue
        except:
            break
    return offers

async def main():
    all_data = {}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # Widoczne okno, abyś kliknął cookies!
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        for dzielnica, link in DZIELNICE_LINKS.items():
            print(f"🚀 Pobieranie danych dla: {dzielnica}...")
            wyniki = await pobierz_oferty(page, link)
            if wyniki:
                # Usuwamy duplikaty linków
                df = pd.DataFrame(wyniki).drop_duplicates(subset=["link"])
                all_data[dzielnica] = df.to_dict(orient="records")
                print(f"   ✅ Pobrano {len(df)} ogłoszeń.")
            else:
                all_data[dzielnica] = []

        await browser.close()

    # --- GENEROWANIE ŁADNEGO INTERFEJSU (HTML + WYKRESY CHART.JS) ---
    print("🎨 Budowanie pięknego interfejsu wizualnego...")
    
    html_template = """
    <!DOCTYPE html>
    <html lang="pl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Raport Cen OLX - Kraków</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { background-color: #f4f7f6; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            .card { border: none; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-radius: 10px; }
            .nav-pills .nav-link.active { background-color: #00A49F; }
            .nav-link { color: #406367; font-weight: 600; }
            th { background-color: #02282C !important; color: white !important; }
            .metric-box { text-align: center; padding: 15px; border-radius: 8px; background: #e9fcfb; color: #02282C; }
            .metric-val { font-size: 24px; font-weight: bold; color: #00A49F; }
        </style>
    </head>
    <body>
        <div class="container my-5">
            <div class="text-center mb-5">
                <h1 class="fw-bold" style="color: #02282C;">📊 Monitor Cen Mieszkań i Pokoi OLX</h1>
                <p class="text-muted">Interaktywny raport analityczny przygotowany dla Szefowej</p>
            </div>

            <ul class="nav nav-pills justify-content-center mb-4" id="pills-tab" role="tablist">
    """
    
    # Tworzenie przycisków zakładek
    for i, dzielnica in enumerate(all_data.keys()):
        active_class = "active" if i == 0 else ""
        safe_id = dzielnica.replace(" ", "_").replace("-", "_")
        html_template += f"""
        <li class="nav-item" role="presentation">
            <button class="nav-link {active_class} me-2" id="tab-{safe_id}" data-bs-toggle="pill" data-bs-target="#content-{safe_id}" type="button" role="tab">{dzielnica}</button>
        </li>
        """
    
    html_template += "</ul><div class='tab-content' id='pills-tabContent'>"
    
    # Generowanie zawartości dla każdej dzielnicy
    for i, (dzielnica, oferty) in enumerate(all_data.items()):
        active_class = "show active" if i == 0 else ""
        safe_id = dzielnica.replace(" ", "_").replace("-", "_")
        
        if oferty:
            ceny = [o['price'] for o in oferty]
            srednia = round(sum(ceny) / len(ceny))
            najtansza = min(ceny)
            najdrozsza = max(ceny)
            
            # Przygotowanie danych do wykresu kołowego / słupkowego przedziałów cenowych
            p_under_1500 = sum(1 for c in ceny if c < 1500)
            p_1500_1700 = sum(1 for c in ceny if 1500 <= c <= 1700)
            p_above_1700 = sum(1 for c in ceny if c > 1700)
        else:
            srednia, najtansza, najdrozsza = 0, 0, 0
            p_under_1500, p_1500_1700, p_above_1700 = 0, 0, 0

        html_template += f"""
        <div class="tab-pane fade {active_class}" id="content-{safe_id}" role="tabpanel">
            <div class="row g-4 mb-4">
                <div class="col-md-4"><div class="card metric-box"><p class="mb-1">Średnia Cena rynkowa</p><p class="metric-val">{srednia} PLN</p></div></div>
                <div class="col-md-4"><div class="card metric-box"><p class="mb-1">Najniższa okazja</p><p class="metric-val">{najtansza} PLN</p></div></div>
                <div class="col-md-4"><div class="card metric-box"><p class="mb-1">Najwyższa oferta</p><p class="metric-val">{najdrozsza} PLN</p></div></div>
            </div>
            
            <div class="row g-4 mb-5">
                <div class="col-md-6 mx-auto">
                    <div class="card p-4">
                        <h5 class="fw-bold mb-3 text-center" style="color: #02282C;">📊劈 Struktura cenowa ofert</h5>
                        <canvas id="chart-{safe_id}"></canvas>
                    </div>
                </div>
            </div>

            <div class="card p-4">
                <h5 class="fw-bold mb-3" style="color: #02282C;">📋 Lista dostępnych ofert (kliknij kolumnę aby sortować)</h5>
                <div class="table-responsive">
                    <table class="table table-hover table-striped" id="table-{safe_id}">
                        <thead>
                            <tr>
                                <th onclick="sortTable('{safe_id}', 0)" style="cursor:pointer">Tytuł ogłoszenia 👇</th>
                                <th onclick="sortTable('{safe_id}', 1)" style="cursor:pointer">Cena (PLN) 👇</th>
                                <th>Link bezpośredni</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        
        for o in oferty:
            html_template += f"""
                            <tr>
                                <td>{o['title']}</td>
                                <td class="fw-bold text-success" data-value="{o['price']}">{o['price']} zł</td>
                                <td><a href="{o['link']}" target="_blank" class="btn btn-sm text-white" style="background-color: #00A49F;">Otwórz w OLX ↗</a></td>
                            </tr>
            """
            
        html_template += f"""
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <script>
            new Chart(document.getElementById('chart-{safe_id}'), {{
                type: 'pie',
                data: {{
                    labels: ['Poniżej 1500 zł', '1500 - 1700 zł', 'Powyżej 1700 zł'],
                    datasets: [{{
                        data: [{p_under_1500}, {p_1500_1700}, {p_above_1700}],
                        backgroundColor: ['#23E5DB', '#00A49F', '#02282C']
                    }}]
                }}
            }});
        </script>
        """

    html_template += """
            </div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            function sortTable(safeId, colIndex) {
                let table = document.getElementById("table-" + safeId);
                let rows = Array.from(table.rows).slice(1);
                let isAsc = table.getAttribute("data-sort-asc") === "true";
                
                rows.sort((rowA, rowB) => {
                    let cellA = rowA.cells[colIndex];
                    let cellB = rowB.cells[colIndex];
                    
                    let valA = cellA.hasAttribute("data-value") ? parseFloat(cellA.getAttribute("data-value")) : cellA.innerText.toLowerCase();
                    let valB = cellB.hasAttribute("data-value") ? parseFloat(cellB.getAttribute("data-value")) : cellB.innerText.toLowerCase();
                    
                    if (typeof valA === "number") {
                        return isAsc ? valA - valB : valB - valA;
                    } else {
                        return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
                    }
                });
                
                rows.forEach(row => table.appendChild(row));
                table.setAttribute("data-sort-asc", !isAsc);
            }
        </script>
    </body>
    </html>
    """

    with open("Raport_OLX_Krakow.html", "w", encoding="utf-8") as f:
        f.write(html_template)
        
    print("\n🎉 SUKCES! Wygenerowano piękny, wizualny plik 'Raport_OLX_Krakow.html' na Twoim pulpicie.")

if __name__ == "__main__":
    asyncio.run(main())