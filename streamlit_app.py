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

@st.cache_data(ttl=300)
def load_data(table_name: str):
    local_conn = get_db_connection()
    if not local_conn: # Якщо get_db_connection викликав st.stop(), сюди не дійде
        return pd.DataFrame()
    
    query_table_name_for_log = table_name # Для логування у випадку помилки
    try:
        if table_name.lower().startswith("public."):
            actual_table_name_part = table_name.split(".", 1)[1]
            # Якщо назва після 'public.' взята в лапки, використовуємо її як є
            if actual_table_name_part.startswith('"') and actual_table_name_part.endswith('"'):
                 query_table_name = f'public.{actual_table_name_part}'
            # Інакше, якщо потрібні лапки (цифри/спецсимволи)
            elif not actual_table_name_part.replace("_", "").isalnum() or actual_table_name_part[0].isdigit():
                 query_table_name = f'public."{actual_table_name_part}"'
            else: # Проста назва
                 query_table_name = f'public.{actual_table_name_part}'
        # Якщо 'public.' немає на початку
        elif not table_name.replace("_", "").isalnum() or table_name[0].isdigit():
             query_table_name = f'public."{table_name}"'
        else: # Проста назва без public.
             query_table_name = f'public.{table_name}'
        
        query_table_name_for_log = query_table_name # Оновлюємо для логування, якщо була зміна
        query = f'SELECT * FROM {query_table_name};'
        df = local_conn.query(query)
        if df.empty:
            st.warning(f"Таблиця '{query_table_name}' (запит для '{table_name}') порожня або не знайдена.")
        return df
    except Exception as e:
        st.error(f"Помилка при завантаженні даних з таблиці '{table_name}' (спроба запиту до '{query_table_name_for_log}'): {e}")
        return pd.DataFrame()

# ---- НАЗВИ ТАБЛИЦЬ ТА ІНІЦІАЛІЗАЦІЯ ----
ACCOUNTS_TABLE_NAME = "stat_user_account_v2"
DYNAMIC_POSITION_TABLE_NAME_TEMPLATE = "{account_id}_positions_{platform}_v2"

if 'selected_account_id' not in st.session_state:
    st.session_state.selected_account_id = None
if 'selected_account_platform' not in st.session_state:
    st.session_state.selected_account_platform = None
if 'selected_account_positions_df' not in st.session_state:
    st.session_state.selected_account_positions_df = pd.DataFrame()
if 'current_positions_table_name' not in st.session_state:
    st.session_state.current_positions_table_name = ""

conn = get_db_connection()

# ---- ФУНКЦІЯ ВІДОБРАЖЕННЯ ГРАФІКІВ ПОЗИЦІЙ ----
def display_position_charts(positions_df: pd.DataFrame, table_name: str, account_id_display: str):
    if positions_df.empty:
        return

    st.header(f"Аналіз позицій для акаунту {account_id_display} (таблиця: {table_name})")

    required_cols_positions = ['net_profit_db', 'change_balance_acc', 'time_close']
    if not all(col in positions_df.columns for col in required_cols_positions):
        st.error(f"Відсутні необхідні колонки в таблиці '{table_name}'. Потрібні: {', '.join(required_cols_positions)}. Наявні: {positions_df.columns.tolist()}")
        return

    positions_df_cleaned = positions_df.copy()
    for col in ['net_profit_db', 'change_balance_acc']:
        positions_df_cleaned[col] = pd.to_numeric(positions_df_cleaned[col], errors='coerce')

    x_axis_data = positions_df_cleaned.index # За замовчуванням
    x_axis_label = 'Номер угоди' # За замовчуванням

    if 'time_close' in positions_df_cleaned.columns:
        try:
            # Спробуємо спочатку як datetime, якщо не вийде - як timestamp, потім як число
            temp_time_close = pd.to_datetime(positions_df_cleaned['time_close'], errors='coerce')
            if temp_time_close.isnull().all(): # Якщо всі NaT, спробувати як timestamp
                st.info(f"Не вдалося розпізнати 'time_close' як стандартну дату/час для '{table_name}'. Спроба розпізнати як Unix timestamp...")
                temp_time_close = pd.to_datetime(positions_df_cleaned['time_close'], unit='s', origin='unix', errors='coerce')
            
            if not temp_time_close.isnull().all(): # Якщо хоч щось розпізналося
                positions_df_cleaned['time_close_dt'] = temp_time_close
                positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc', 'time_close_dt'], inplace=True)
                positions_df_cleaned = positions_df_cleaned.sort_values(by='time_close_dt')
                x_axis_data = positions_df_cleaned['time_close_dt']
                x_axis_label = 'Час закриття'
            else: # Якщо і як timestamp не вийшло
                raise ValueError("Не вдалося розпізнати time_close як datetime або timestamp")
        except Exception as e_datetime:
            st.warning(f"Проблема з обробкою 'time_close' як дати/часу для '{table_name}': {e_datetime}. Спроба обробити як число для сортування.")
            try:
                positions_df_cleaned['time_close_numeric'] = pd.to_numeric(positions_df_cleaned['time_close'], errors='coerce')
                positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc', 'time_close_numeric'], inplace=True)
                if not positions_df_cleaned.empty:
                    positions_df_cleaned = positions_df_cleaned.sort_values(by='time_close_numeric')
                    x_axis_data = positions_df_cleaned.index 
                    x_axis_label = 'Номер угоди (Відсортовано за числом з time_close)'
                else: # Якщо після dropna порожньо
                    st.info(f"Немає валідних даних 'time_close' для сортування як число в '{table_name}'.")
                    positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True) # Сортування по індексу
            except Exception as e_numeric:
                 st.error(f"Не вдалося обробити 'time_close' ні як дату/час, ні як число: {e_numeric}")
                 return
    else:
        st.warning(f"Відсутня колонка 'time_close' для '{table_name}'. Кумулятивний графік може бути неточним (сортування по індексу).")
        positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True)

    if positions_df_cleaned.empty:
        st.info(f"Недостатньо даних для графіків '{table_name}' після очистки.")
        return

    st.subheader("Кумулятивний профіт")
    positions_df_cleaned['cumulative_profit'] = positions_df_cleaned['net_profit_db'].cumsum()
    fig_cumulative_profit = px.line(
        positions_df_cleaned, x=x_axis_data, y='cumulative_profit', title="Динаміка кумулятивного профіту",
        labels={'cumulative_profit': 'Кумулятивний профіт', x_axis_data.name if hasattr(x_axis_data, 'name') else 'index': x_axis_label }
    )
    fig_cumulative_profit.update_layout(xaxis_title=x_axis_label, yaxis_title="Кумулятивний профіт ($)")
    st.plotly_chart(fig_cumulative_profit, use_container_width=True)

    st.subheader("Динаміка балансу рахунку")
    fig_balance_change = px.line(
        positions_df_cleaned, x=x_axis_data, y='change_balance_acc', title="Динаміка балансу рахунку",
        labels={'change_balance_acc': 'Баланс', x_axis_data.name if hasattr(x_axis_data, 'name') else 'index': x_axis_label}
    )
    fig_balance_change.update_layout(xaxis_title=x_axis_label, yaxis_title="Баланс рахунку ($)")
    st.plotly_chart(fig_balance_change, use_container_width=True)

# ---- ЗАВАНТАЖЕННЯ ТА ВІДОБРАЖЕННЯ ДАНИХ ПРО АКАУНТИ ----
st.header(f"Інформація про акаунти (з таблиці: {ACCOUNTS_TABLE_NAME})")
accounts_df_global = load_data(ACCOUNTS_TABLE_NAME)

if not accounts_df_global.empty:
    required_account_cols = ["account_id", "platform"]
    if not all(col in accounts_df_global.columns for col in required_account_cols):
        missing_cols = [col for col in required_account_cols if col not in accounts_df_global.columns]
        st.error(f"Критична помилка: в таблиці '{ACCOUNTS_TABLE_NAME}' відсутні колонки: {', '.join(missing_cols)}. Інтерактивність неможлива.")
        st.stop()
    
    accounts_df_global["account_id"] = accounts_df_global["account_id"].astype(str).str.strip()
    accounts_df_global["platform"] = accounts_df_global["platform"].astype(str).str.strip()

    columns_to_display = {
        "account_id": "ID Акаунту", "platform": "Платформа", "user_id": "ID Користувача",
        "broker_name": "Брокер", "server": "Сервер", "deposit_currency": "Валюта депозиту",
        "account_type": "Тип акаунту", "account_status": "Статус акаунту", "is_active": "Активний",
        "balance": "Баланс", "initial_deposit": "Початковий депозит",
        "total_deposits": "Всього депозитів", "total_withdrawals": "Всього виведено",
        "total_profit": "Загальний профіт"
    }
    
    display_df_accounts = accounts_df_global_filtered = accounts_df_global[[col for col in columns_to_display if col in accounts_df_global.columns]].copy()
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
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=10)
    gb.configure_default_column(editable=False, filter=True, sortable=True, resizable=True)
    
    gridOptions = gb.build()

    st.subheader("Оберіть акаунт для перегляду деталей позицій:")
    account_grid_response = AgGrid(
        display_df_accounts, gridOptions=gridOptions, data_return_mode=DataReturnMode.AS_INPUT,
        update_mode=GridUpdateMode.MODEL_CHANGED, allow_unsafe_jscode=True, height=350,
        width='100%', fit_columns_on_grid_load=True, theme='streamlit'
    )
    
    selected_rows_df = account_grid_response.get('selected_rows')

    if selected_rows_df is not None and not selected_rows_df.empty:
        first_selected_row = selected_rows_df.iloc[0]
        
        # Використовуємо перейменовані назви колонок з columns_to_display для отримання значень
        id_col_name_display = columns_to_display.get("account_id")
        platform_col_name_display = columns_to_display.get("platform")

        selected_account_id_from_grid = first_selected_row.get(id_col_name_display)
        selected_platform_from_grid = first_selected_row.get(platform_col_name_display)

        if selected_account_id_from_grid is not None and selected_platform_from_grid is not None:
            st.session_state.selected_account_id = str(selected_account_id_from_grid).strip()
            st.session_state.selected_account_platform = str(selected_platform_from_grid).strip()
        else:
            missing_info = []
            if selected_account_id_from_grid is None: missing_info.append(f"'{id_col_name_display}' (оригінал: account_id)")
            if selected_platform_from_grid is None: missing_info.append(f"'{platform_col_name_display}' (оригінал: platform)")
            st.warning(f"Не вдалося отримати { ' та '.join(missing_info) } з вибраного рядка. Перевірте налаштування таблиці.")
            # Не скидаємо, щоб дозволити повторну спробу або зберегти попередній стан
else:
    if 'db_connection_successful' in st.session_state and st.session_state.db_connection_successful:
        empty_msg = "порожня або не знайдена" if not accounts_df_global.empty else "не вдалося завантажити"
        st.info(f"Таблиця акаунтів '{ACCOUNTS_TABLE_NAME}' {empty_msg}. Неможливо відобразити список акаунтів.")
    st.session_state.selected_account_id = None
    st.session_state.selected_account_platform = None

st.markdown("---")

if st.session_state.selected_account_id and st.session_state.selected_account_platform:
    current_account_id = st.session_state.selected_account_id
    current_platform = st.session_state.selected_account_platform
    
    # ВАЖЛИВО: Логіка перетворення current_platform на те, що в назві таблиці
    # Приклад: якщо current_platform="MetaTrader 5", а в назві "MT5"
    platform_for_table_name = current_platform # За замовчуванням беремо як є
    if "metatrader 5" in current_platform.lower() or "mt5" in current_platform.lower():
        platform_for_table_name = "MT5"
    elif "metatrader 4" in current_platform.lower() or "mt4" in current_platform.lower():
        platform_for_table_name = "MT4"
    # Додайте інші платформи, якщо потрібно
    # else:
    #     st.warning(f"Не вдалося визначити скорочення для платформи: '{current_platform}'. Використовується як є.")
        # platform_for_table_name = current_platform # або None, якщо не знаємо, що робити

    if platform_for_table_name:
        positions_table_for_account = DYNAMIC_POSITION_TABLE_NAME_TEMPLATE.format(
            account_id=current_account_id,
            platform=platform_for_table_name
        )
        
        st.caption(f"Акаунт: {current_account_id}, Платформа: {current_platform} (для таблиці: {platform_for_table_name}). Очікувана таблиця: `{positions_table_for_account}`")

        if st.session_state.current_positions_table_name != positions_table_for_account or st.session_state.selected_account_positions_df.empty:
            with st.spinner(f"Завантаження даних з {positions_table_for_account}..."):
                st.session_state.selected_account_positions_df = load_data(positions_table_for_account)
                st.session_state.current_positions_table_name = positions_table_for_account
                if not st.session_state.selected_account_positions_df.empty:
                     st.success(f"Дані з таблиці '{positions_table_for_account}' успішно завантажені.")
        
        display_position_charts(st.session_state.selected_account_positions_df, st.session_state.current_positions_table_name, current_account_id)
    else:
        st.error(f"Не вдалося визначити платформу для формування назви таблиці позицій для акаунту {current_account_id} (платформа: {current_platform}).")

elif not accounts_df_global.empty :
    st.info("📈 Будь ласка, оберіть акаунт з таблиці вище, щоб побачити графіки його позицій.")

st.sidebar.info("""
**Інструкція:**
1. Оберіть акаунт зі списку.
2. Графіки позицій для вибраного акаунту відобразяться нижче.
""")
if 'db_connection_successful' in st.session_state and not st.session_state.db_connection_successful:
    st.sidebar.error("Проблема з підключенням до БД!")

