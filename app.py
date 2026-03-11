import streamlit as st
import requests
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Correcteur Ensoleillement PV", page_icon="☀️", layout="wide")

st.title("☀️ Correcteur d'Ensoleillement Photovoltaïque")
st.caption("Source : PVGIS CAMS — Ener-Pacte")

# --- PARAMÈTRES GPS ET INSTALLATION ---
st.header("1. Paramètres du site")

col1, col2 = st.columns(2)
with col1:
    lat = st.number_input("Latitude", value=43.60, format="%.5f")
    tilt = st.number_input("Inclinaison des panneaux (°)", min_value=0, max_value=90, value=30)
with col2:
    lon = st.number_input("Longitude", value=1.44, format="%.5f")
    azimuth = st.number_input("Azimuth (° — 0=Sud, -90=Est, 90=Ouest)", min_value=-180, max_value=180, value=0)

col3, col4 = st.columns(2)
with col3:
    start_year = st.number_input("Année de début", min_value=2005, max_value=2023, value=2010)
with col4:
    end_year = st.number_input("Année de fin", min_value=2005, max_value=2023, value=2023)

# --- DONNÉES ARCHELIOS ---
st.header("2. Données Archelios Calc")

col5, col6 = st.columns(2)
with col5:
    arch_production = st.number_input("Production simulée Archelios (kWh/an)", min_value=0.0, value=120000.0, step=1000.0)
with col6:
    arch_irradiance = st.number_input("Ensoleillement Archelios (kWh/m²/an)", min_value=0.0, value=1650.0, step=10.0)

# --- BOUTON ---
if st.button("🔍 Récupérer l'ensoleillement et corriger", type="primary"):

    if start_year > end_year:
        st.error("L'année de début doit être inférieure à l'année de fin.")
    else:
        results = []
        errors = []

        progress = st.progress(0)
        status = st.empty()
        total = end_year - start_year + 1

        for i, year in enumerate(range(int(start_year), int(end_year) + 1)):
            status.text(f"Récupération de l'année {year}...")
            try:
                url = "https://re.jrc.ec.europa.eu/api/v5_2/seriescalc"
                params = {
                    "lat": lat, "lon": lon,
                    "angle": tilt, "aspect": azimuth,
                    "startyear": year, "endyear": year,
                    "outputformat": "json", "browser": 0
                }
                res = requests.get(url, params=params, timeout=30)
                res.raise_for_status()
                data = res.json()
                hourly = data["outputs"]["hourly"]
                ghi = sum(h.get("G_i", 0) for h in hourly) / 1000
                results.append({"Année": year, "Gi réel (kWh/m²/an)": round(ghi, 1)})
            except Exception as e:
                errors.append(f"Année {year} : {str(e)}")

            progress.progress((i + 1) / total)

        status.empty()
        progress.empty()

        if errors:
            for err in errors:
                st.warning(err)

        if results:
            df = pd.DataFrame(results)
            avg = df["Gi réel (kWh/m²/an)"].mean()

            df["Écart vs moyenne (%)"] = ((df["Gi réel (kWh/m²/an)"] - avg) / avg * 100).round(1)
            df["Ratio ensoleillement (%)"] = (df["Gi réel (kWh/m²/an)"] / arch_irradiance * 100).round(1)
            df["Production corrigée (kWh/an)"] = (arch_production * df["Gi réel (kWh/m²/an)"] / arch_irradiance).round(0).astype(int)

            # --- RÉSULTATS ---
            st.header("3. Résultats")

            m1, m2, m3 = st.columns(3)
            m1.metric("Ensoleillement moyen réel", f"{avg:.1f} kWh/m²/an")
            m2.metric("Ensoleillement Archelios", f"{arch_irradiance:.1f} kWh/m²/an")
            m3.metric("Écart global", f"{((avg - arch_irradiance) / arch_irradiance * 100):.1f} %")

            st.subheader("Tableau de correction")
            st.dataframe(df, use_container_width=True)

            st.subheader("Graphique — Ensoleillement réel vs Archelios")
            fig = px.bar(df, x="Année", y="Gi réel (kWh/m²/an)", color="Écart vs moyenne (%)",
                         color_continuous_scale="RdYlGn",
                         labels={"Gi réel (kWh/m²/an)": "kWh/m²/an"})
            fig.add_hline(y=arch_irradiance, line_dash="dash", line_color="blue",
                          annotation_text=f"Archelios : {arch_irradiance} kWh/m²/an")
            fig.add_hline(y=avg, line_dash="dot", line_color="orange",
                          annotation_text=f"Moyenne réelle : {avg:.1f} kWh/m²/an")
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Graphique — Production corrigée par année")
            fig2 = px.line(df, x="Année", y="Production corrigée (kWh/an)", markers=True)
            fig2.add_hline(y=arch_production, line_dash="dash", line_color="blue",
                           annotation_text=f"Production Archelios : {arch_production:,.0f} kWh/an")
            st.plotly_chart(fig2, use_container_width=True)

            # --- EXPORT CSV ---
            csv = df.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
            st.download_button("📥 Télécharger les résultats (CSV)", data=csv,
                               file_name="correction_ensoleillement.csv", mime="text/csv")

            st.info("💡 Méthode : Production corrigée = Production Archelios × (Gi réel / Gi Archelios)")
