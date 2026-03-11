import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import cdsapi
import tempfile
import os

st.set_page_config(page_title="Correcteur Ensoleillement PV", page_icon="☀️", layout="wide")

st.title("☀️ Correcteur d'Ensoleillement Photovoltaïque")
st.caption("Source : CAMS Solar Radiation Timeseries — Ener-Pacte")

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
    start_date = st.date_input("Date de début", value=date(2010, 1, 1), min_value=date(2004, 1, 1), max_value=date(2024, 12, 31))
with col4:
    end_date = st.date_input("Date de fin", value=date(2023, 12, 31), min_value=date(2004, 1, 1), max_value=date(2024, 12, 31))

st.header("2. Données Archelios Calc")

col5, col6 = st.columns(2)
with col5:
    arch_production = st.number_input("Production simulée Archelios (kWh/an)", min_value=0.0, value=120000.0, step=1000.0)
with col6:
    arch_irradiance = st.number_input("Ensoleillement Archelios (kWh/m²/an)", min_value=0.0, value=1650.0, step=10.0)

if st.button("🔍 Récupérer l'ensoleillement CAMS et corriger", type="primary"):

    if start_date >= end_date:
        st.error("La date de début doit être avant la date de fin.")
    else:
        try:
            status = st.empty()
            status.text("Connexion à CAMS en cours...")

            cams_url = st.secrets["CAMS_URL"]
            cams_key = st.secrets["CAMS_KEY"]

            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = os.path.join(tmpdir, "cams_result.csv")

                status.text("Envoi de la requête à CAMS (peut prendre 1 à 2 minutes)...")

                c = cdsapi.Client(url=cams_url, key=cams_key, quiet=True)

                c.retrieve(
                    "cams-solar-radiation-timeseries",
                    {
                        "sky_type": "observed_cloud",
                        "location": {
                            "latitude": float(lat),
                            "longitude": float(lon)
                        },
                        "altitude": "-999.",
                        "date": f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}",
                        "time_step": "1day",
                        "time_reference": "universal_time",
                        "format": "csv",
                    },
                    output_path
                )

                status.text("Données reçues, traitement en cours...")

                with open(output_path, "r") as f:
                    lines = f.readlines()

                data_start = 0
                for j, line in enumerate(lines):
                    if not line.startswith("#"):
                        data_start = j
                        break

                df_raw = pd.read_csv(output_path, skiprows=data_start, sep=";", on_bad_lines="skip")
                df_raw.columns = [c.strip() for c in df_raw.columns]

                with st.expander("🔧 Diagnostic — colonnes disponibles dans CAMS"):
                    st.write(list(df_raw.columns))
                    st.dataframe(df_raw.head(5))

                date_col = df_raw.columns[0]

                irr_col = None
                for candidate in ["GHI", "ghi", "G(i)", "Gi", "SRIS", "Global_horizontal_irradiance", "Radiation"]:
                    if candidate in df_raw.columns:
                        irr_col = candidate
                        break

                if irr_col is None:
                    irr_col = df_raw.columns[1]
                    st.warning(f"Colonne irradiance non identifiée automatiquement → utilisation de : **{irr_col}**")
                else:
                    st.success(f"Colonne irradiance utilisée : **{irr_col}**")

                df_raw[date_col] = pd.to_datetime(df_raw[date_col], errors="coerce")
                df_raw = df_raw.dropna(subset=[date_col])
                df_raw["Année"] = df_raw[date_col].dt.year
                df_raw[irr_col] = pd.to_numeric(df_raw[irr_col], errors="coerce")

                df_yearly = df_raw.groupby("Année")[irr_col].sum().reset_index()
                df_yearly.columns = ["Année", "Gi réel (kWh/m²/an)"]
                df_yearly["Gi réel (kWh/m²/an)"] = (df_yearly["Gi réel (kWh/m²/an)"] / 1000).round(1)

            status.empty()

            avg = df_yearly["Gi réel (kWh/m²/an)"].mean()
            df_yearly["Écart vs moyenne (%)"] = ((df_yearly["Gi réel (kWh/m²/an)"] - avg) / avg * 100).round(1)
            df_yearly["Ratio vs Archelios (%)"] = (df_yearly["Gi réel (kWh/m²/an)"] / arch_irradiance * 100).round(1)
            df_yearly["Production corrigée (kWh/an)"] = (arch_production * df_yearly["Gi réel (kWh/m²/an)"] / arch_irradiance).round(0).astype(int)

            st.header("3. Résultats")

            m1, m2, m3 = st.columns(3)
            m1.metric("Ensoleillement moyen réel", f"{avg:.1f} kWh/m²/an")
            m2.metric("Ensoleillement Archelios", f"{arch_irradiance:.1f} kWh/m²/an")
            ecart = (avg - arch_irradiance) / arch_irradiance * 100
            m3.metric("Écart global", f"{ecart:.1f} %", delta=f"{ecart:.1f} %")

            st.subheader("Tableau de correction")
            st.dataframe(df_yearly, use_container_width=True)

            st.subheader("Ensoleillement réel vs Archelios")
            fig = px.bar(df_yearly, x="Année", y="Gi réel (kWh/m²/an)", color="Écart vs moyenne (%)", color_continuous_scale="RdYlGn")
            fig.add_hline(y=arch_irradiance, line_dash="dash", line_color="blue", annotation_text=f"Archelios : {arch_irradiance} kWh/m²/an")
            fig.add_hline(y=avg, line_dash="dot", line_color="orange", annotation_text=f"Moyenne réelle : {avg:.1f} kWh/m²/an")
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Production corrigée par année")
            fig2 = px.line(df_yearly, x="Année", y="Production corrigée (kWh/an)", markers=True)
            fig2.add_hline(y=arch_production, line_dash="dash", line_color="blue", annotation_text=f"Production Archelios : {arch_production:,.0f} kWh/an")
            st.plotly_chart(fig2, use_container_width=True)

            csv = df_yearly.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
            st.download_button("📥 Télécharger les résultats (CSV)", data=csv, file_name="correction_ensoleillement.csv", mime="text/csv")

            st.info("💡 Production corrigée = Production Archelios × (Gi réel / Gi Archelios)")

        except Exception as e:
            st.error(f"Erreur : {str(e)}")
            st.warning("Vérifiez vos secrets CAMS_URL et CAMS_KEY dans Streamlit Cloud.")
