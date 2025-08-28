# app.py (добавлена выгрузка в Excel)

import streamlit as st
import pandas as pd
import plotly.express as px
import io # <-- Добавляем необходимую библиотеку

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(
    page_title="Дашборд по мониторингу рекламы",
    page_icon="📊",
    layout="wide"
)

# --- АУТЕНТИФИКАЦИЯ ПО ПАРОЛЮ ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.text_input("Пароль", type="password", on_change=password_entered, key="password")
        if st.session_state.get("password_correct") is False:
             st.error("😕 Неверный пароль. Попробуйте снова.")
        return False
    else:
        return True

# <<< ИЗМЕНЕНИЕ: Новая вспомогательная функция для конвертации в Excel >>>
@st.cache_data
def to_excel(df):
    """Конвертирует DataFrame в Excel-файл в памяти."""
    output = io.BytesIO()
    # Используем with, чтобы гарантировать правильное закрытие writer'a
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    # Получаем байты из буфера
    processed_data = output.getvalue()
    return processed_data

# --- ЗАГРУЗКА И КЭШИРОВАНИЕ ДАННЫХ ---
@st.cache_data
def load_data(uploaded_file):
    try:
        xls = pd.ExcelFile(uploaded_file)
        all_sheet_names = xls.sheet_names
        target_sheet_names = [name for name in all_sheet_names if name.startswith("План vs Факт_")]

        if not target_sheet_names:
            st.error("В файле не найдено ни одного листа с названием 'План vs Факт_Месяц'.")
            return None

        monthly_sheets_dict = pd.read_excel(
            uploaded_file, sheet_name=target_sheet_names, header=3, usecols='B:N'
        )
        
        df = pd.concat(list(monthly_sheets_dict.values()), ignore_index=True)
        
        df.dropna(subset=['Вертикаль', 'Кампания'], inplace=True)
        numeric_cols = ['План', 'Факт']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.fillna(0, inplace=True)
        df = df[(df['План'] != 0) | (df['Факт'] != 0)]
        date_cols = ['Старт', 'Окончание']
        for col in date_cols:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

        df['Подрядчик'] = df['Подрядчик'].astype(str).str.upper()
        return df
    except Exception as e:
        st.error(f"Ошибка при чтении файла: {e}")
        return None

# =============================================================================
# --- ОСНОВНАЯ ЧАСТЬ ПРИЛОЖЕНИЯ ---
# =============================================================================

st.title("📊 Интерактивный дашборд по мониторингу рекламы AVITO")

if not check_password():
    st.stop()

uploaded_file = st.file_uploader("Загрузите Excel-файл с отчетом", type=["xlsx", "xls"])

if uploaded_file is None:
    st.info("Пожалуйста, загрузите файл для начала работы.")
    st.stop()

df = load_data(uploaded_file)

if df is None or df.empty:
    st.warning("Не удалось загрузить данные или в файле нет подходящих листов.")
    st.stop()

# --- БОКОВАЯ ПАНЕЛЬ С ФИЛЬТРАМИ ---
st.sidebar.header("Фильтры:")

df['Вертикаль'] = df['Вертикаль'].astype(str)
df['Тип'] = df['Тип'].astype(str)
df['Город'] = df['Город'].astype(str)

vertical = st.sidebar.multiselect("Вертикаль:", options=sorted(df["Вертикаль"].unique()), default=sorted(df["Вертикаль"].unique()))
supplier = st.sidebar.multiselect("Подрядчик (Supplier):", options=sorted(df["Подрядчик"].unique()), default=sorted(df["Подрядчик"].unique()))
media_type = st.sidebar.multiselect("Тип медиа:", options=sorted(df["Тип"].unique()), default=sorted(df["Тип"].unique()))
city = st.sidebar.multiselect("Город:", options=sorted(df["Город"].unique()), default=sorted(df["Город"].unique()))

df_selection = df.query("Вертикаль == @vertical & Подрядчик == @supplier & Тип == @media_type & Город == @city")

# --- ОСНОВНАЯ ПАНЕЛЬ ДАШБОРДА (графики без изменений) ---
total_plan = int(df_selection["План"].sum())
total_fact = int(df_selection["Факт"].sum())
if total_plan > 0: difference = (total_fact / total_plan) - 1
else: difference = 1 if total_fact > 0 else 0

st.markdown("### Ключевые показатели")
col1, col2, col3 = st.columns(3)
col1.metric("План", f"{total_plan:,}".replace(",", " "))
col2.metric("Факт", f"{total_fact:,}".replace(",", " "))
col3.metric("Разница", f"{difference:.1%}")

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

# --- ДЕТАЛЬНАЯ ТАБЛИЦА И КНОПКА СКАЧИВАНИЯ ---
st.markdown("### Детализация данных")
st.dataframe(df_selection)

# <<< ИЗМЕНЕНИЕ: Добавляем кнопку для скачивания в формате Excel >>>
excel_data = to_excel(df_selection)
st.download_button(
    label="📥 Скачать данные в Excel",
    data=excel_data,
    file_name='dashboard_data_export.xlsx',
    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)