import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import date

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
    start_date = st.date_input("Date de début", value=date(2010, 1, 1), min_value=date(2005, 1, 1), max_value=date(2023, 12, 31))
with col4:
    end_date = st.date_input("Date de fin", value=date(2023, 12, 31), min_value=date(2005, 1, 1), max_value=date(2023, 12, 31))

# --- DONNÉES ARCHELIOS ---
st.header("2. Données Archelios Calc")

col5, col6 = st.columns(2)
with col5:
    arch_production = st.number_input("Production simulée Archelios (kWh/an)", min_value=0.0, value=120000.0, step=1000.0)
with col6:
    arch_irradiance = st.number_input("Ensoleillement Archelios (kWh/m²/an)", min_value=0.0, value=1650.0, step=10.0)

# --- BOUTON ---
if st.button("🔍 Récupérer l'ensoleillement et corriger", type="primary"):

    if start_date >= end_date:
        st.error("La date de début doit être avant la date de fin.")
    else:
        results = []
        errors = []
        found_field = None

        start_year = start_date.year
        end_year = end_date.year
        total = end_year - start_year + 1

        progress = st.progress(0)
        status = st.empty()

        for i, year in enumerate(range(start_year, end_year + 1)):
            status.text(f"Récupération de l'année {year}...")

            try:
                url = "https://re.jrc.ec.europa.eu/api/v5_2/seriescalc"
                params = {
                    "lat": lat,
                    "lon": lon,
                    "angle": tilt,
                    "aspect": azimuth,
                    "startyear": year,
                    "endyear": year,
                    "outputformat": "json",
                    "browser": 0,
                    "components": 1,
                }
                res = requests.get(url, params=params, timeout=60)
                res.raise_for_status()
                data = res.json()
                hourly = data["outputs"]["hourly"]

                # Identifier le bon champ irradiance sur plan incliné
                if found_field is None:
                    for field in ["G(i)", "Gb(i)", "Gi", "G_i", "H(i)"]:
                        if field in hourly[0]:
                            found_field = field
                            break

                if found_field:
                    ghi_sum = sum(h.get(found_field, 0) for h in hourly) / 1000
                else:
                    # Reconstituer depuis composantes Gb + Gd + Gr
                    ghi_sum = sum(
                        h.get("Gb(i)", 0) + h.get("Gd(i)", 0) + h.get("Gr(i)", 0)
                        for h in hourly
                    ) / 1000

                results.append({
                    "Année": year,
                    "Gi réel (kWh/m²/an)": round(ghi_sum, 1)
                })

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
            df["Ratio vs Archelios (%)"] = (df["Gi réel (kWh/m²/an)"] / arch_irradiance * 100).round(1)
            df["Production corrigée (kWh/an)"] = (
                arch_production * df["Gi réel (kWh/m²/an)"] / arch_irradiance
            ).round(0).astype(int)

            # --- RÉSULTATS ---
            st.header("3. Résultats")

            m1, m2, m3 = st.columns(3)
            m1.metric("Ensoleillement moyen réel", f"{avg:.1f} kWh/m²/an")
            m2.metric("Ensoleillement Archelios", f"{arch_irradiance:.1f} kWh/m²/an")
            ecart = (avg - arch_irradiance) / arch_irradiance * 100
            m3.metric("Écart global", f"{ecart:.1f} %", delta=f"{ecart:.1f} %")

            st.subheader("Tableau de correction")
            st.dataframe(df, use_container_width=True)

            st.subheader("Ensoleillement réel vs Archelios")
            fig = px.bar(df, x="Année", y="Gi réel (kWh/m²/an)",
                         color="Écart vs moyenne (%)",
                         color_continuous_scale="RdYlGn")
            fig.add_hline(y=arch_irradiance, line_dash="dash", line_color="blue",
                          annotation_text=f"Archelios : {arch_irradiance} kWh/m²/an")
            fig.add_hline(y=avg, line_dash="dot", line_color="orange",
                          annotation_text=f"Moyenne réelle : {avg:.1f} kWh/m²/an")
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Production corrigée par année")
            fig2 = px.line(df, x="Année", y="Production corrigée (kWh/an)", markers=True)
            fig2.add_hline(y=arch_production, line_dash="dash", line_color="blue",
                           annotation_text=f"Production Archelios : {arch_production:,.0f} kWh/an")
            st.plotly_chart(fig2, use_container_width=True)

            # Diagnostic technique
            with st.expander("🔧 Diagnostic technique"):
                try:
                    sample = data["outputs"]["hourly"][0]
                    st.write(f"Champs disponibles dans l'API : `{list(sample.keys())}`")
                    st.write(f"Champ utilisé : `{found_field if found_field else 'reconstitution Gb(i)+Gd(i)+Gr(i)'}`")
                except:
                    pass

            # Export CSV
            csv = df.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
            st.download_button("📥 Télécharger les résultats (CSV)", data=csv,
                               file_name="correction_ensoleillement.csv", mime="text/csv")

            st.info("💡 Production corrigée = Production Archelios × (Gi réel / Gi Archelios)")
