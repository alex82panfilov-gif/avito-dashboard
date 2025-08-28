# app.py (Финальное исправление ошибки TypeError при загрузке из базы)

import streamlit as st
import pandas as pd
import plotly.express as px
import io
import numpy as np
from supabase import create_client, Client

# --- НАСТРОЙКИ ---
st.set_page_config(page_title="Дашборд по мониторингу рекламы", page_icon="📊", layout="wide")
SUPABASE_TABLE_NAME = "monitoring_data" 

# --- АУТЕНТИФИКАЦИЯ (без изменений) ---
def check_password():
    def password_entered():
        if "password" in st.session_state and st.session_state["password"] == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True; del st.session_state["password"]
        else: st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state: st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.text_input("Пароль", type="password", on_change=password_entered, key="password")
        if st.session_state.get("password_correct") is False: st.error("😕 Неверный пароль.")
        return False
    else: return True

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С SUPABASE (без изменений) ---
@st.cache_resource
def init_supabase_client():
    url = st.secrets["SUPABASE_URL"]; key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def load_data_from_supabase(client: Client):
    try:
        response = client.table(SUPABASE_TABLE_NAME).select("*").execute()
        df = pd.DataFrame(response.data)
        if df.empty: return df
        df = df.drop(columns=['id', 'created_at'], errors='ignore')
        for col in ['Старт', 'Окончание']:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
        return df
    except Exception as e:
        st.error(f"Ошибка загрузки данных из базы: {e}"); return pd.DataFrame()

def save_data_to_supabase(client: Client, df: pd.DataFrame):
    client.table(SUPABASE_TABLE_NAME).delete().neq('id', 0).execute()
    data_to_insert = df.replace({np.nan: None, pd.NaT: None}).to_dict(orient='records')
    for row in data_to_insert:
        for key, value in row.items():
            if pd.isna(value): row[key] = None
        if row.get('Старт'): row['Старт'] = row['Старт'].strftime('%Y-%m-%d')
        if row.get('Окончание'): row['Окончание'] = row['Окончание'].strftime('%Y-%m-%d')
    client.table(SUPABASE_TABLE_NAME).insert(data_to_insert).execute()
    st.success("Данные успешно сохранены в базе!")

def clear_data_in_supabase(client: Client):
    client.table(SUPABASE_TABLE_NAME).delete().neq('id', 0).execute()
    st.info("Данные очищены. Можете загрузить новый файл.")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (без изменений) ---
def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    return output.getvalue()

def process_uploaded_file(uploaded_file):
    try:
        xls = pd.ExcelFile(uploaded_file)
        target_sheet_names = [name for name in xls.sheet_names if name.startswith("План vs Факт_")]
        if not target_sheet_names:
            st.error("В файле не найдено ни одного листа с названием 'План vs Факт_Месяц'.")
            return None
        df = pd.concat(list(pd.read_excel(uploaded_file, sheet_name=target_sheet_names, header=3, usecols='B:N').values()), ignore_index=True)
        df.dropna(subset=['Вертикаль', 'Кампания'], how='all', inplace=True)
        final_columns = ['Вертикаль', 'Кампания', 'Тип', 'Город', 'Подрядчик', 'Месяц', 'Старт', 'Окончание', 'Единица', 'План', 'Факт', 'Разница', 'Комментарий']
        for col in final_columns:
            if col not in df.columns: df[col] = None
        for col in ['Вертикаль', 'Кампания', 'Тип', 'Город', 'Подрядчик', 'Месяц', 'Единица', 'Комментарий']:
            df[col] = df[col].astype(str).replace('nan', None)
        df['План'] = pd.to_numeric(df['План'], errors='coerce').fillna(0).astype('int64')
        df['Факт'] = pd.to_numeric(df['Факт'], errors='coerce').fillna(0).astype('int64')
        df['Разница'] = np.where(df['План'] > 0, (df['Факт'] / df['План']) - 1, np.where(df['Факт'] > 0, 1, 0))
        df['Разница'] = pd.to_numeric(df['Разница'], errors='coerce').fillna(0).astype('float64')
        for col in ['Старт', 'Окончание']:
            df[col] = pd.to_datetime(df[col], errors='coerce')
        df = df[final_columns]
        df.replace([np.inf, -np.inf], None, inplace=True)
        df.dropna(subset=['Вертикаль', 'Кампания'], how='all', inplace=True)
        return df
    except Exception as e:
        st.error(f"Произошла критическая ошибка при обработке Excel-файла: {e}"); return None

# =============================================================================
# --- ОСНОВНАЯ ЧАСТЬ ПРИЛОЖЕНИЯ ---
# =============================================================================
st.title("📊 Интерактивный дашборд по мониторингу рекламы AVITO")
if not check_password(): st.stop()
supabase_client = init_supabase_client()
df = load_data_from_supabase(supabase_client)
if df.empty:
    st.info("База данных пуста. Загрузите отчет Excel для начала работы.")
    uploaded_file = st.file_uploader("Загрузите Excel-файл с отчетом", type=["xlsx", "xls"])
    if uploaded_file:
        with st.spinner("Обработка и сохранение данных..."):
            new_df = process_uploaded_file(uploaded_file)
            if new_df is not None and not new_df.empty:
                try:
                    save_data_to_supabase(supabase_client, new_df); st.rerun()
                except Exception as e:
                    st.error("Ошибка при сохранении данных в базу. Проверьте логи."); st.exception(e)
            elif new_df is not None and new_df.empty:
                 st.warning("В файле не найдено данных для загрузки после очистки.")
else:
    st.sidebar.header("Фильтры:")
    if st.sidebar.button("🗑️ Очистить и загрузить новый отчет"):
        clear_data_in_supabase(supabase_client); st.rerun()
    
    # <<< ИЗМЕНЕНИЕ: Добавлена недостающая строка для преобразования столбца "Подрядчик" >>>
    df['Вертикаль'] = df['Вертикаль'].astype(str)
    df['Подрядчик'] = df['Подрядчик'].astype(str) # <-- ВОТ ЭТА СТРОКА
    df['Тип'] = df['Тип'].astype(str)
    df['Город'] = df['Город'].astype(str)
    
    vertical = st.sidebar.multiselect("Вертикаль:", options=sorted(df["Вертикаль"].unique()), default=sorted(df["Вертикаль"].unique()))
    supplier = st.sidebar.multiselect("Подрядчик (Supplier):", options=sorted(df["Подрядчик"].unique()), default=sorted(df["Подрядчик"].unique()))
    media_type = st.sidebar.multiselect("Тип медиа:", options=sorted(df["Тип"].unique()), default=sorted(df["Тип"].unique()))
    city = st.sidebar.multiselect("Город:", options=sorted(df["Город"].unique()), default=sorted(df["Город"].unique()))
    
    df_selection = df.query("Вертикаль == @vertical & Подрядчик == @supplier & Тип == @media_type & Город == @city")
    
    total_plan = int(df_selection["План"].sum())
    total_fact = int(df_selection["Факт"].sum())
    if total_plan > 0: difference = (total_fact / total_plan) - 1
    else: difference = 1 if total_fact > 0 else 0
    
    st.markdown("### Ключевые показатели")
    col1, col2, col3 = st.columns(3); col1.metric("План", f"{total_plan:,}".replace(",", " ")); col2.metric("Факт", f"{total_fact:,}".replace(",", " ")); col3.metric("Разница", f"{difference:.1%}")
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        by_supplier = df_selection.groupby('Подрядчик')[['План', 'Факт']].sum().reset_index()
        fig_supplier = px.bar(by_supplier, x='Подрядчик', y=['План', 'Факт'], title="<b>План/Факт по Подрядчикам</b>", barmode='group', text_auto='.2s')
        st.plotly_chart(fig_supplier, use_container_width=True)
    with col2:
        by_type = df_selection.groupby('Тип')[['План', 'Факт']].sum().reset_index()
        fig_type = px.bar(by_type, x='Тип', y=['План', 'Факт'], title="<b>План/Факт по Типу медиа</b>", barmode='group', text_auto='.2s')
        st.plotly_chart(fig_type, use_container_width=True)
    
    by_month = df_selection.groupby('Месяц')[['План', 'Факт']].sum().reset_index()
    month_order = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
    by_month['Месяц'] = pd.Categorical(by_month['Месяц'], categories=month_order, ordered=True)
    by_month = by_month.sort_values('Месяц')
    fig_month = px.bar(by_month, x='Месяц', y=['План', 'Факт'], title="<b>План/Факт по Месяцам</b>", barmode='group', text_auto='.2s')
    st.plotly_chart(fig_month, use_container_width=True)
    
    st.markdown("### Детализация данных")
    st.dataframe(df_selection)
    
    excel_data = to_excel(df_selection)
    st.download_button(label="📥 Скачать данные в Excel", data=excel_data, file_name='dashboard_data_export.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')