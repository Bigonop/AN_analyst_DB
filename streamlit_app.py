import streamlit as st
import pandas as pd
import plotly.express as px
# Переконайтеся, що streamlit-aggrid встановлено і є в requirements.txt
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
except ImportError:
    st.error("Бібліотека streamlit-aggrid не знайдена. Будь ласка, додайте 'streamlit-aggrid' до requirements.txt та перезапустіть додаток.")
    st.stop()


# ---- НАЛАШТУВАННЯ СТОРІНКИ ----
st.set_page_config(
    page_title="Торговий Дашборд",
    page_icon="💹",
    layout="wide"
)

st.title("📊 Торговий Дашборд з Neon DB")

# ---- КЕШУВАННЯ ----
@st.cache_resource
def get_db_connection():
    try:
        conn_obj = st.connection("neon_db", type="sql")
        conn_obj.query("SELECT 1;") # Перевірка з'єднання
        if 'db_connection_successful' not in st.session_state:
            st.success("🎉 Підключення до бази даних Neon DB успішне!")
            st.session_state.db_connection_successful = True
        return conn_obj
    except Exception as e:
        st.error(f"Помилка підключення до бази даних: {e}")
        st.session_state.db_connection_successful = False
        st.stop()

@st.cache_data(ttl=300) # Зменшив TTL для тестування, потім можна повернути 600
def load_data(table_name: str):
    local_conn = get_db_connection()
    if not local_conn:
        return pd.DataFrame()
    try:
        # Формування назви таблиці для запиту (з урахуванням можливих цифр на початку/спецсимволів)
        # Важливо: PostgreSQL чутливий до регістру в назвах, якщо вони не взяті в "".
        # Якщо ваші таблиці, наприклад, "123_table", то public."123_table"
        # Якщо "MyTable", то public."MyTable" (якщо створено з великої літери без лапок, то збережеться в нижньому регістрі)
        # Найбезпечніше - завжди використовувати точну назву, як вона є в БД, і при необхідності брати в ""
        # Якщо в table_name вже є public. то не додаємо
        if table_name.lower().startswith("public."):
            query_table_name = f'"{table_name.split(".")[-1]}"' if not table_name.split(".")[-1].replace("_", "").isalnum() or table_name.split(".")[-1][0].isdigit() else table_name.split(".")[-1]
            if not query_table_name.startswith('"'): # перестраховка для прямих назв
                 query_table_name = f'public.{query_table_name}'
            else: # якщо вже з лапками, то public. не потрібне перед ними якщо вони охоплюють всю назву
                 query_table_name = f'public.{query_table_name}'
        elif not table_name.replace("_", "").isalnum() or table_name[0].isdigit():
             query_table_name = f'public."{table_name}"'
        else:
             query_table_name = f'public.{table_name}' # Для простих назв типу my_table

        query = f'SELECT * FROM {query_table_name};'
        df = local_conn.query(query)
        if df.empty:
            st.warning(f"Таблиця '{query_table_name}' (запит для '{table_name}') порожня або не знайдена.")
        return df
    except Exception as e:
        st.error(f"Помилка при завантаженні даних з таблиці '{table_name}' (запит: {query_table_name if 'query_table_name' in locals() else 'не сформовано'}): {e}")
        return pd.DataFrame()

# ---- НАЗВИ ТАБЛИЦЬ ТА ІНІЦІАЛІЗАЦІЯ ----
ACCOUNTS_TABLE_NAME = "stat_user_account_v2"
# Шаблон для динамічного формування назви таблиці позицій
DYNAMIC_POSITION_TABLE_NAME_TEMPLATE = "{account_id}_positions_{platform}_v2"

# Стан для зберігання
if 'selected_account_id' not in st.session_state:
    st.session_state.selected_account_id = None
if 'selected_account_platform' not in st.session_state: # Додано для зберігання платформи
    st.session_state.selected_account_platform = None
if 'selected_account_positions_df' not in st.session_state:
    st.session_state.selected_account_positions_df = pd.DataFrame()
if 'current_positions_table_name' not in st.session_state:
    st.session_state.current_positions_table_name = ""

# Отримуємо з'єднання на початку
conn = get_db_connection() # Це встановить st.session_state.db_connection_successful

# ---- ФУНКЦІЯ ВІДОБРАЖЕННЯ ГРАФІКІВ ПОЗИЦІЙ ----
def display_position_charts(positions_df: pd.DataFrame, table_name: str, account_id_display: str):
    if positions_df.empty:
        # st.info(f"Немає даних для відображення графіків для таблиці '{table_name}'.") # Це повідомлення вже є при завантаженні
        return

    st.header(f"Аналіз позицій для акаунту {account_id_display} (таблиця: {table_name})") # Додано ID акаунту в заголовок

    required_cols_positions = ['net_profit_db', 'change_balance_acc', 'time_close']
    if not all(col in positions_df.columns for col in required_cols_positions):
        st.error(f"Відсутні необхідні колонки в таблиці '{table_name}'. Потрібні: {', '.join(required_cols_positions)}")
        return

    positions_df_cleaned = positions_df.copy()
    for col in ['net_profit_db', 'change_balance_acc']:
        positions_df_cleaned[col] = pd.to_numeric(positions_df_cleaned[col], errors='coerce')

    if 'time_close' in positions_df_cleaned.columns:
        try:
            positions_df_cleaned['time_close'] = pd.to_datetime(positions_df_cleaned['time_close'], errors='coerce', unit_or_format='s', origin='unix') # Спробуємо з unit='s' якщо це timestamp
            positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc', 'time_close'], inplace=True)
            positions_df_cleaned = positions_df_cleaned.sort_values(by='time_close')
        except Exception as e_datetime: # Більш конкретна обробка помилки дати
            st.warning(f"Проблема з обробкою колонки 'time_close' (як datetime) для '{table_name}': {e_datetime}.")
            st.info("Спроба обробити 'time_close' як число для сортування.")
            try:
                positions_df_cleaned['time_close_numeric'] = pd.to_numeric(positions_df_cleaned['time_close'], errors='coerce')
                positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc', 'time_close_numeric'], inplace=True)
                positions_df_cleaned = positions_df_cleaned.sort_values(by='time_close_numeric')
                x_axis_data = positions_df_cleaned.index # Використовуємо індекс, якщо час не розпізнано як дата
                x_axis_label = 'Номер угоди (відсортовано за time_close як число)'
            except Exception as e_numeric:
                 st.error(f"Не вдалося обробити 'time_close' ні як дату, ні як число: {e_numeric}")
                 return # Не можемо будувати графіки
        else: # Якщо pd.to_datetime спрацювало
            x_axis_data = positions_df_cleaned['time_close']
            x_axis_label = 'Час закриття'

    else: # Якщо немає 'time_close'
        st.warning(f"Відсутня колонка 'time_close' для '{table_name}'. Кумулятивний графік може бути неточним, сортування по індексу.")
        positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True)
        x_axis_data = positions_df_cleaned.index
        x_axis_label = 'Номер угоди'


    if positions_df_cleaned.empty:
        st.info(f"Недостатньо даних для графіків після очистки для '{table_name}'.")
        return

    # --- 1. Кумулятивний профіт ---
    st.subheader("Кумулятивний профіт")
    positions_df_cleaned['cumulative_profit'] = positions_df_cleaned['net_profit_db'].cumsum()
    fig_cumulative_profit = px.line(
        positions_df_cleaned, x=x_axis_data, y='cumulative_profit', title="Динаміка кумулятивного профіту",
        labels={'cumulative_profit': 'Кумулятивний профіт', 'index': 'Номер угоди', 'time_close': x_axis_label}
    )
    fig_cumulative_profit.update_layout(xaxis_title=x_axis_label, yaxis_title="Кумулятивний профіт ($)")
    st.plotly_chart(fig_cumulative_profit, use_container_width=True)

    # --- 2. Баланс ---
    st.subheader("Динаміка балансу рахунку")
    fig_balance_change = px.line(
        positions_df_cleaned, x=x_axis_data, y='change_balance_acc', title="Динаміка балансу рахунку",
        labels={'change_balance_acc': 'Баланс', 'index': 'Номер угоди', 'time_close': x_axis_label}
    )
    fig_balance_change.update_layout(xaxis_title=x_axis_label, yaxis_title="Баланс рахунку ($)")
    st.plotly_chart(fig_balance_change, use_container_width=True)


# ---- ЗАВАНТАЖЕННЯ ТА ВІДОБРАЖЕННЯ ДАНИХ ПРО АКАУНТИ ----
st.header(f"Інформація про акаунти (з таблиці: {ACCOUNTS_TABLE_NAME})")
# Завантажуємо accounts_df тут, щоб він був доступний глобальніше для визначення платформи
accounts_df_global = load_data(ACCOUNTS_TABLE_NAME) # Використовуємо іншу назву змінної

if not accounts_df_global.empty:
    # Перевірка наявності ключових колонок
    required_account_cols = ["account_id", "platform"] # Додаємо 'platform' до обов'язкових
    if not all(col in accounts_df_global.columns for col in required_account_cols):
        missing_cols = [col for col in required_account_cols if col not in accounts_df_global.columns]
        st.error(f"Критична помилка: в таблиці '{ACCOUNTS_TABLE_NAME}' відсутні колонки: {', '.join(missing_cols)}. Інтерактивність неможлива.")
        st.stop()
    
    accounts_df_global["account_id"] = accounts_df_global["account_id"].astype(str)
    # Переконаємось, що платформа теж рядок і без зайвих пробілів
    accounts_df_global["platform"] = accounts_df_global["platform"].astype(str).str.strip()


    columns_to_display = {
        "account_id": "ID Акаунту", "platform": "Платформа", "user_id": "ID Користувача",
        "broker_name": "Брокер", "server": "Сервер", "deposit_currency": "Валюта депозиту",
        "account_type": "Тип акаунту", "account_status": "Статус акаунту", "is_active": "Активний",
        "balance": "Баланс", "initial_deposit": "Початковий депозит",
        "total_deposits": "Всього депозитів", "total_withdrawals": "Всього виведено",
        "total_profit": "Загальний профіт"
    }
    
    display_df_accounts = accounts_df_global[[col for col in columns_to_display if col in accounts_df_global.columns]].copy()
    display_df_accounts.rename(columns=columns_to_display, inplace=True)

    currency_columns_keys = ["balance", "initial_deposit", "total_deposits", "total_withdrawals", "total_profit"]
    currency_columns_renamed = [columns_to_display.get(key) for key in currency_columns_keys if columns_to_display.get(key) in display_df_accounts.columns]

    for col in currency_columns_renamed:
        display_df_accounts[col] = pd.to_numeric(display_df_accounts[col], errors='coerce')

    gb = GridOptionsBuilder.from_dataframe(display_df_accounts)
    for col_name in currency_columns_renamed:
        gb.configure_column(col_name, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2, aggFunc='sum')
    
    active_col_renamed = columns_to_display.get("is_active")
    if active_col_renamed and active_col_renamed in display_df_accounts.columns:
         gb.configure_column(active_col_renamed, cellRenderer='agBooleanCellRenderer', editable=False, width=100)

    gb.configure_selection(selection_mode='single', use_checkbox=False)
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=10) # Менший розмір для тесту
    # gb.configure_side_bar() # Можна увімкнути, якщо потрібно
    gb.configure_default_column(editable=False, filter=True, sortable=True, resizable=True) # wrapText, autoHeight за замовчуванням
    
    gridOptions = gb.build()

    st.subheader("Оберіть акаунт для перегляду деталей позицій:")
    account_grid_response = AgGrid(
        display_df_accounts, gridOptions=gridOptions, data_return_mode=DataReturnMode.AS_INPUT,
        update_mode=GridUpdateMode.MODEL_CHANGED, allow_unsafe_jscode=True, height=350, # Зменшив висоту
        width='100%', fit_columns_on_grid_load=True, theme='streamlit' # fit_columns_on_grid_load може бути корисним
    )
    
    selected_rows = account_grid_response['selected_rows']

    if selected_rows:
        selected_account_id_from_grid = selected_rows[0].get(columns_to_display.get("account_id"))
        selected_platform_from_grid = selected_rows[0].get(columns_to_display.get("platform")) # Отримуємо платформу з AgGrid

        if selected_account_id_from_grid and selected_platform_from_grid:
            st.session_state.selected_account_id = str(selected_account_id_from_grid)
            st.session_state.selected_account_platform = str(selected_platform_from_grid).strip() # Зберігаємо платформу
        else:
            missing_info = []
            if not selected_account_id_from_grid: missing_info.append("'ID Акаунту'")
            if not selected_platform_from_grid: missing_info.append("'Платформа'")
            st.warning(f"Не вдалося отримати { ' та '.join(missing_info) } з вибраного рядка.")
            st.session_state.selected_account_id = None
            st.session_state.selected_account_platform = None
else:
    if 'db_connection_successful' in st.session_state and st.session_state.db_connection_successful:
        is_empty_msg = "порожня або не знайдена" if not accounts_df_global.empty else "не вдалося завантажити"
        st.info(f"Таблиця акаунтів '{ACCOUNTS_TABLE_NAME}' {is_empty_msg}. Неможливо відобразити список акаунтів.")
    # Якщо немає успішного з'єднання, помилка вже виведена get_db_connection()
    st.session_state.selected_account_id = None
    st.session_state.selected_account_platform = None

st.markdown("---")

# ---- ВІДОБРАЖЕННЯ ГРАФІКІВ ДЛЯ ВИБРАНОГО АКАУНТУ ----
if st.session_state.selected_account_id and st.session_state.selected_account_platform:
    current_account_id = st.session_state.selected_account_id
    current_platform = st.session_state.selected_account_platform
    
    # Важливо: обробка назви платформи для відповідності назві таблиці
    # Наприклад, якщо в БД значення "MetaTrader 5", а в назві таблиці "MT5"
    # Тут потрібно буде додати логіку перетворення, якщо необхідно.
    # Припустимо, що значення платформи з accounts_df вже підходить для назви таблиці.
    # Якщо платформа може містити пробіли або спецсимволи, які не входять в назву таблиці, їх треба видалити/замінити.
    # Наприклад, .replace(" ", "").upper()
    platform_for_table_name = current_platform.replace(" ", "").upper() # Приклад: "MetaTrader 5" -> "METATRADER5"
    # Якщо у вас в назві таблиці строго MT5 або MT4, то можна так:
    # if "5" in platform_for_table_name: platform_for_table_name = "MT5"
    # elif "4" in platform_for_table_name: platform_for_table_name = "MT4"
    # else: # ? Невідома платформа
    #     st.error(f"Невідомий формат платформи: {current_platform}. Неможливо сформувати назву таблиці позицій.")
    #     platform_for_table_name = None # Або якесь значення за замовчуванням

    # Наразі, для більшої гнучкості, припустимо, що platform_for_table_name вже правильний після .replace()...
    # АБО, ЯКЩО В БД В КОЛОНЦІ platform ВЖЕ ЗНАЧЕННЯ ТИПУ "MT5", "MT4", ТО МОЖНА ПРОСТО:
    platform_for_table_name = current_platform # Якщо значення в колонці "platform" вже готові (MT5, MT4)

    if platform_for_table_name: # Перевірка, чи вдалося визначити платформу для назви
        positions_table_for_account = DYNAMIC_POSITION_TABLE_NAME_TEMPLATE.format(
            account_id=current_account_id,
            platform=platform_for_table_name  # Використовуємо оброблене значення
        )
        
        st.caption(f"Для акаунту ID: {current_account_id}, Платформа: {current_platform}. Очікувана таблиця позицій: `{positions_table_for_account}`") # Дебаг

        if st.session_state.current_positions_table_name != positions_table_for_account or st.session_state.selected_account_positions_df.empty:
            with st.spinner(f"Завантаження даних з {positions_table_for_account}..."):
                st.session_state.selected_account_positions_df = load_data(positions_table_for_account)
                st.session_state.current_positions_table_name = positions_table_for_account
                if not st.session_state.selected_account_positions_df.empty:
                     st.success(f"Дані з таблиці '{positions_table_for_account}' успішно завантажені.")
        
        display_position_charts(st.session_state.selected_account_positions_df, st.session_state.current_positions_table_name, current_account_id)
    else:
        st.error(f"Не вдалося визначити платформу для формування назви таблиці позицій для акаунту {current_account_id}.")

elif accounts_df_global.empty and ('db_connection_successful' not in st.session_state or not st.session_state.db_connection_successful) :
    pass # Помилка підключення або завантаження акаунтів вже показана
elif not accounts_df_global.empty: # Акаунти є, але не вибрано
    st.info("📈 Будь ласка, оберіть акаунт з таблиці вище, щоб побачити графіки його позицій.")
# Якщо accounts_df_global порожній, але з'єднання було, повідомлення вже виведено.

st.sidebar.info("""
**Інструкція:**
1. Оберіть акаунт зі списку.
2. Графіки позицій для вибраного акаунту відобразяться нижче.
""")
if 'db_connection_successful' in st.session_state and not st.session_state.db_connection_successful:
    st.sidebar.error("Проблема з підключенням до БД!")
