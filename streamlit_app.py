import streamlit as st
import pandas as pd
import plotly.express as px

# ---- НАЛАШТУВАННЯ СТОРІНКИ ----
st.set_page_config(
    page_title="Торговий Дашборд",
    page_icon="💹",
    layout="wide"
)

st.title("📊 Торговий Дашборд з Neon DB")

# ---- ПІДКЛЮЧЕННЯ ДО БАЗИ ДАНИХ ----
@st.cache_resource # Кешування самого об'єкту підключення
def get_db_connection():
    try:
        # Переконайтеся, що назва "neon_db" співпадає з тим, що у вас в Secrets
        # [connections.neon_db]
        conn_obj = st.connection("neon_db", type="sql")
        # Дрібна перевірка, чи з'єднання активне, роблячи простий запит
        conn_obj.query("SELECT 1;")
        st.success("🎉 Підключення до бази даних Neon DB успішне!") # Перемістимо сюди, щоб було один раз
        return conn_obj
    except Exception as e:
        st.error(f"Помилка підключення до бази даних: {e}")
        st.stop() # Зупинити виконання, якщо немає підключення

# ---- ФУНКЦІЯ ДЛЯ ЗАВАНТАЖЕННЯ ДАНИХ З КЕШУВАННЯМ ----
# Тепер load_data буде залежати тільки від table_name для кешування
@st.cache_data(ttl=600) # Кешування даних на 10 хвилин
def load_data(table_name: str): # Прибираємо 'connection' з аргументів
    local_conn = get_db_connection() # Отримуємо кешоване підключення всередині
    if not local_conn: # Якщо get_db_connection не вдалося, вона викличе st.stop()
        return pd.DataFrame() # Повертаємо порожній DataFrame, хоча до цього не дійде

    try:
        query = f'SELECT * FROM public."{table_name}";'
        df = local_conn.query(query) # Використовуємо локально отримане підключення
        if df.empty:
            st.warning(f"Таблиця 'public.\"{table_name}\"' порожня або не знайдена.")
            return pd.DataFrame()
        # Повідомлення про успішне завантаження краще винести за межі кешованої функції,
        # щоб воно показувалося щоразу, а не тільки при першому завантаженні з БД.
        # st.success(f"Дані з таблиці 'public.\"{table_name}\"' успішно завантажені!")
        return df
    except Exception as e:
        st.error(f"Помилка при завантаженні даних з таблиці 'public.\"{table_name}\"': {e}")
        return pd.DataFrame()

# ---- НАЗВИ ТАБЛИЦЬ ----
POSITIONS_TABLE_NAME = "11232052_positions_MT5_v2"
ACCOUNTS_TABLE_NAME = "stat_user_account_v2"

# Отримуємо з'єднання один раз на початку (або при необхідності)
# Це викличе get_db_connection, яка покаже повідомлення про успіх або помилку
# і поверне кешований об'єкт. Ми його тут не передаємо далі, load_data сама його візьме.
get_db_connection() # Просто викликаємо, щоб встановити і перевірити з'єднання.

# ---- ЗАВАНТАЖЕННЯ ТА ОБРОБКА ДАНИХ ДЛЯ ГРАФІКІВ ПОЗИЦІЙ ----
st.header(f"Аналіз позицій з таблиці: {POSITIONS_TABLE_NAME}")

positions_df = load_data(POSITIONS_TABLE_NAME) # Тепер передаємо тільки назву таблиці

if not positions_df.empty:
    st.success(f"Дані з таблиці 'public.\"{POSITIONS_TABLE_NAME}\"' успішно оброблені для відображення.") # Повідомлення тут
    # Переконаємося, що необхідні колонки існують
    required_cols_positions = ['net_profit_db', 'change_balance_acc', 'time_close']
    if not all(col in positions_df.columns for col in required_cols_positions):
        st.error(f"Відсутні необхідні колонки в таблиці '{POSITIONS_TABLE_NAME}'. Потрібні: {', '.join(required_cols_positions)}")
    else:
        # Очистка та підготовка даних
        positions_df_cleaned = positions_df.copy()
        
        for col in ['net_profit_db', 'change_balance_acc']:
            positions_df_cleaned[col] = pd.to_numeric(positions_df_cleaned[col], errors='coerce')
        
        if 'time_close' in positions_df_cleaned.columns:
            try:
                positions_df_cleaned['time_close'] = pd.to_datetime(positions_df_cleaned['time_close'], errors='coerce')
                positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc', 'time_close'], inplace=True)
                positions_df_cleaned = positions_df_cleaned.sort_values(by='time_close')
            except Exception as e:
                st.warning(f"Проблема з обробкою колонки 'time_close': {e}. Графіки можуть бути неточними.")
                positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True)
        else:
            st.warning("Відсутня колонка 'time_close' (або подібна) для сортування угод. Кумулятивний графік може бути неточним.")
            positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True)

        if not positions_df_cleaned.empty:
            # --- 1. Кумулятивний профіт ---
            st.subheader("Кумулятивний профіт")
            positions_df_cleaned['cumulative_profit'] = positions_df_cleaned['net_profit_db'].cumsum()
            
            fig_cumulative_profit = px.line(
                positions_df_cleaned,
                x=positions_df_cleaned.index if 'time_close' not in positions_df_cleaned.columns or positions_df_cleaned['time_close'].isnull().all() else 'time_close',
                y='cumulative_profit',
                title="Динаміка кумулятивного профіту",
                labels={'cumulative_profit': 'Кумулятивний профіт', 'index': 'Номер угоди', 'time_close': 'Час закриття'}
            )
            fig_cumulative_profit.update_layout(xaxis_title="Час/Номер угоди", yaxis_title="Кумулятивний профіт ($)")
            st.plotly_chart(fig_cumulative_profit, use_container_width=True)

            # --- 2. Баланс (зміна балансу) ---
            st.subheader("Динаміка зміни балансу (по угодах)")
            fig_balance_change = px.line(
                positions_df_cleaned,
                x=positions_df_cleaned.index if 'time_close' not in positions_df_cleaned.columns or positions_df_cleaned['time_close'].isnull().all() else 'time_close',
                y='change_balance_acc',
                title="Динаміка балансу рахунку",
                labels={'change_balance_acc': 'Баланс', 'index': 'Номер угоди', 'time_close': 'Час закриття'}
            )
            fig_balance_change.update_layout(xaxis_title="Час/Номер угоди", yaxis_title="Баланс рахунку ($)")
            st.plotly_chart(fig_balance_change, use_container_width=True)
        else:
            st.info(f"Недостатньо даних в таблиці '{POSITIONS_TABLE_NAME}' для побудови графіків після очистки.")
else:
    st.info(f"Дані з таблиці '{POSITIONS_TABLE_NAME}' ще не завантажені або таблиця порожня.")

st.markdown("---")

# ---- ЗАВАНТАЖЕННЯ ТА ВІДОБРАЖЕННЯ ДАНИХ ПРО АКАУНТИ ----
st.header(f"Інформація про акаунти з таблиці: {ACCOUNTS_TABLE_NAME}")

accounts_df = load_data(ACCOUNTS_TABLE_NAME) # Тепер передаємо тільки назву таблиці

if not accounts_df.empty:
    st.success(f"Дані з таблиці 'public.\"{ACCOUNTS_TABLE_NAME}\"' успішно оброблені для відображення.") # Повідомлення тут
    columns_to_display = {
        "account_id": "ID Акаунту", "platform": "Платформа", "user_id": "ID Користувача",
        "broker_name": "Брокер", "server": "Сервер", "deposit_currency": "Валюта депозиту",
        "account_type": "Тип акаунту", "account_status": "Статус акаунту", "is_active": "Активний",
        "balance": "Баланс", "initial_deposit": "Початковий депозит",
        "total_deposits": "Всього депозитів", "total_withdrawals": "Всього виведено",
        "total_profit": "Загальний профіт"
    }
    
    display_df = accounts_df[[col for col in columns_to_display if col in accounts_df.columns]].copy()
    display_df.rename(columns=columns_to_display, inplace=True)

    currency_columns_keys = ["balance", "initial_deposit", "total_deposits", "total_withdrawals", "total_profit"]
    currency_columns_renamed = [columns_to_display.get(key) for key in currency_columns_keys if columns_to_display.get(key) in display_df.columns]

    for col in currency_columns_renamed:
        display_df[col] = pd.to_numeric(display_df[col], errors='coerce')

    try:
        from st_aggrid import AgGrid, GridOptionsBuilder
        from st_aggrid.shared import GridUpdateMode

        gb = GridOptionsBuilder.from_dataframe(display_df)
        for col_name in currency_columns_renamed:
            gb.configure_column(col_name, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2, aggFunc='sum')
        
        active_col_renamed = columns_to_display.get("is_active")
        if active_col_renamed and active_col_renamed in display_df.columns:
             gb.configure_column(active_col_renamed, cellRenderer='agBooleanCellRenderer', editable=False, width=100) # Вказав ширину

        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=10) # Замість AutoPageSize, щоб уникнути надто великих
        gb.configure_side_bar()
        gb.configure_default_column(editable=False, filter=True, sortable=True, resizable=True, wrapText=True, autoHeight=True) # autoHeight для тексту
        
        gridOptions = gb.build()

        st.subheader("Детальна таблиця акаунтів (інтерактивна)")
        AgGrid(
            display_df,
            gridOptions=gridOptions,
            update_mode=GridUpdateMode.MODEL_CHANGED,
            allow_unsafe_jscode=True,
            height=400, # Зменшив висоту для пагінації
            width='100%',
            fit_columns_on_grid_load=False, # Краще False, якщо вручну налаштовуємо
            theme='streamlit' 
        )
    except ImportError:
        st.warning("Для відображення інтерактивної таблиці, будь ласка, встановіть 'streamlit-aggrid' та додайте до requirements.txt.")
        st.info("Відображення стандартної таблиці:")
        st.dataframe(display_df.style.format(subset=currency_columns_renamed, formatter="{:,.2f}").hide(axis="index"))
else:
    st.info(f"Дані з таблиці '{ACCOUNTS_TABLE_NAME}' ще не завантажені або таблиця порожня.")

st.sidebar.info("Тут можна додати фільтри чи іншу навігацію.")

