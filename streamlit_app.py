import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_autorefresh import st_autorefresh # <--- ІМПОРТ

# Переконайтеся, що streamlit-aggrid встановлено
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
except ImportError:
    st.error("Бібліотека streamlit-aggrid не знайдена. Будь ласка, додайте 'streamlit-aggrid' до requirements.txt та перезапустіть додаток.")
    AgGrid = None # Щоб уникнути подальших помилок, якщо не встановлено
    st.stop()

# ---- НАЛАШТУВАННЯ СТОРІНКИ ----
st.set_page_config(
    page_title="Торговий Дашборд",
    page_icon="💹",
    layout="wide"
)

# ---- АВТОМАТИЧНЕ ОНОВЛЕННЯ ----
# Оновлювати кожні 60 секунд (60000 мілісекунд).
# Можете налаштувати цей інтервал.
# limit - максимальна кількість оновлень (опціонально, для дебагу або щоб не оновлювало вічно)
# key - унікальний ключ для компонента, якщо їх декілька.
refresh_interval_seconds = 60
refresh_count = st_autorefresh(interval=refresh_interval_seconds * 1000, limit=None, key="account_refresh")

st.title("📊 Торговий Дашборд з Neon DB")
if refresh_count > 0: # Показувати, що оновлення відбуваються, тільки якщо це не перший запуск
    st.caption(f"Сторінка автоматично оновлюється кожні {refresh_interval_seconds} секунд. Оновлення #{refresh_count}")


# ---- КЕШУВАННЯ ----
@st.cache_resource # Для об'єктів, які не можна хешувати для st.cache_data (наприклад, з'єднання)
def get_db_connection():
    try:
        conn_obj = st.connection("neon_db", type="sql")
        conn_obj.query("SELECT 1;")
        if 'db_connection_successful' not in st.session_state or not st.session_state.db_connection_successful :
            st.success("🎉 Підключення до бази даних Neon DB успішне!") # Показуємо один раз
            st.session_state.db_connection_successful = True
        return conn_obj
    except Exception as e:
        st.error(f"Помилка підключення до бази даних: {e}")
        st.session_state.db_connection_successful = False
        st.stop()

# Зверніть увагу на TTL. Якщо він великий, дані з БД не будуть оновлюватися частіше, ніж TTL.
# Для таблиці акаунтів, якщо вона має оновлюватися кожні 60с, TTL теж має бути ~60с або менше.
# Або ми можемо не кешувати завантаження акаунтів, якщо оновлення часте.
# Поки що залишимо загальний TTL, оскільки autorefresh на 60с, а TTL на 300с означає,
# що дані акаунтів реально з БД будуть перевірятися кожні 300с (5 хв),
# а сам скрипт буде перезапускатися кожні 60с.
@st.cache_data(ttl=300) # Кешування на 5 хвилин
def load_data(table_name: str):
    local_conn = get_db_connection()
    if not local_conn:
        return pd.DataFrame()
    
    query_table_name_for_log = table_name
    try:
        # (Ваша логіка формування query_table_name залишається без змін)
        if table_name.lower().startswith("public."):
            actual_table_name_part = table_name.split(".", 1)[1]
            if actual_table_name_part.startswith('"') and actual_table_name_part.endswith('"'):
                 query_table_name = f'public.{actual_table_name_part}'
            elif not actual_table_name_part.replace("_", "").isalnum() or actual_table_name_part[0].isdigit():
                 query_table_name = f'public."{actual_table_name_part}"'
            else:
                 query_table_name = f'public.{actual_table_name_part}'
        elif not table_name.replace("_", "").isalnum() or table_name[0].isdigit():
             query_table_name = f'public."{table_name}"'
        else:
             query_table_name = f'public.{table_name}'
        
        query_table_name_for_log = query_table_name
        query = f'SELECT * FROM {query_table_name};'
        df = local_conn.query(query)
        # Не виводимо тут warning, якщо порожня, щоб не спамити при автооновленні
        # if df.empty:
        #     st.warning(f"Таблиця '{query_table_name}' (запит для '{table_name}') порожня або не знайдена.")
        return df
    except Exception as e:
        st.error(f"Помилка при завантаженні даних з таблиці '{table_name}' (спроба запиту до '{query_table_name_for_log}'): {e}")
        return pd.DataFrame()

# ---- НАЗВИ ТАБЛИЦЬ ТА ІНІЦІАЛІЗАЦІЯ ----
ACCOUNTS_TABLE_NAME = "stat_user_account_v2"
DYNAMIC_POSITION_TABLE_NAME_TEMPLATE = "{account_id}_positions_{platform}_v2"

# Ініціалізація стану (залишається без змін)
if 'selected_account_id' not in st.session_state:
    st.session_state.selected_account_id = None
if 'selected_account_platform' not in st.session_state:
    st.session_state.selected_account_platform = None
if 'selected_account_positions_df' not in st.session_state:
    st.session_state.selected_account_positions_df = pd.DataFrame()
if 'current_positions_table_name' not in st.session_state:
    st.session_state.current_positions_table_name = ""

# Отримуємо з'єднання
conn = get_db_connection()

# ---- ФУНКЦІЯ ВІДОБРАЖЕННЯ ГРАФІКІВ ПОЗИЦІЙ (без змін) ----
def display_position_charts(positions_df: pd.DataFrame, table_name: str, account_id_display: str):
    if positions_df.empty:
        # Повідомлення про порожні дані позицій може бути тут, якщо це не результат помилки завантаження
        # st.info(f"Для акаунту {account_id_display} (таблиця {table_name}) немає даних позицій для відображення.")
        return

    st.header(f"Аналіз позицій для акаунту {account_id_display} (таблиця: {table_name})")

    required_cols_positions = ['net_profit_db', 'change_balance_acc', 'time_close']
    if not all(col in positions_df.columns for col in required_cols_positions):
        st.error(f"Відсутні необхідні колонки в таблиці '{table_name}'. Потрібні: {', '.join(required_cols_positions)}. Наявні: {positions_df.columns.tolist()}")
        return

    positions_df_cleaned = positions_df.copy()
    for col in ['net_profit_db', 'change_balance_acc']:
        positions_df_cleaned[col] = pd.to_numeric(positions_df_cleaned[col], errors='coerce')

    x_axis_data = positions_df_cleaned.index
    x_axis_label = 'Номер угоди'

    if 'time_close' in positions_df_cleaned.columns:
        try:
            temp_time_close = pd.to_datetime(positions_df_cleaned['time_close'], errors='coerce')
            if temp_time_close.isnull().all():
                #st.info(f"Не вдалося розпізнати 'time_close' як стандартну дату/час для '{table_name}'. Спроба розпізнати як Unix timestamp...")
                temp_time_close = pd.to_datetime(positions_df_cleaned['time_close'], unit='s', origin='unix', errors='coerce')
            
            if not temp_time_close.isnull().all():
                positions_df_cleaned['time_close_dt'] = temp_time_close
                positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc', 'time_close_dt'], inplace=True)
                if not positions_df_cleaned.empty: # Перевірка після dropna
                    positions_df_cleaned = positions_df_cleaned.sort_values(by='time_close_dt')
                    x_axis_data = positions_df_cleaned['time_close_dt']
                    x_axis_label = 'Час закриття'
                else: # Якщо порожньо після dropna з time_close_dt
                    # Спробуємо без time_close_dt, якщо воно призвело до видалення всіх даних
                    positions_df_cleaned = positions_df.copy() # Повертаємося до оригінальних даних для цієї гілки
                    for col_num in ['net_profit_db', 'change_balance_acc']: # Повторне перетворення числових
                        positions_df_cleaned[col_num] = pd.to_numeric(positions_df_cleaned[col_num], errors='coerce')
                    st.warning(f"Обробка 'time_close' як дати призвела до порожнього датасету для '{table_name}'. Використовується сортування за індексом.")
                    positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True)

            # Якщо temp_time_close все ще містить тільки NaT
            elif positions_df_cleaned['time_close'].notna().any(): # Якщо є хоч якісь не-NaN значення в оригінальному time_close
                #st.warning(f"Проблема з обробкою 'time_close' як дати/часу для '{table_name}'. Спроба обробити як число для сортування.")
                try:
                    positions_df_cleaned['time_close_numeric'] = pd.to_numeric(positions_df_cleaned['time_close'], errors='coerce')
                    positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc', 'time_close_numeric'], inplace=True)
                    if not positions_df_cleaned.empty:
                        positions_df_cleaned = positions_df_cleaned.sort_values(by='time_close_numeric')
                        x_axis_data = positions_df_cleaned.index 
                        x_axis_label = 'Номер угоди (Відсортовано за числовим time_close)'
                except Exception as e_numeric:
                     st.error(f"Не вдалося обробити 'time_close' ні як дату/час, ні як число: {e_numeric}")
                     return # Не можемо будувати графіки
            else: # Якщо оригінальний time_close порожній або весь NaN
                 positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True)


        except Exception as e_datetime: # Загальна помилка обробки time_close
            st.warning(f"Загальна помилка при обробці 'time_close' для '{table_name}': {e_datetime}. Використовується сортування за індексом.")
            positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True)
    else: # Немає колонки 'time_close'
        #st.warning(f"Відсутня колонка 'time_close' для '{table_name}'. Кумулятивний графік може бути неточним (сортування по індексу).")
        positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True)

    if positions_df_cleaned.empty:
        st.info(f"Недостатньо даних для графіків '{table_name}' після очистки.")
        return

    st.subheader("Кумулятивний профіт")
    positions_df_cleaned['cumulative_profit'] = positions_df_cleaned['net_profit_db'].cumsum()
    fig_cumulative_profit = px.line(
        positions_df_cleaned, x=x_axis_data, y='cumulative_profit', title="Динаміка кумулятивного профіту",
        labels={'cumulative_profit': 'Кумулятивний профіт', (x_axis_data.name if hasattr(x_axis_data, 'name') and x_axis_data.name else 'index'): x_axis_label }
    )
    fig_cumulative_profit.update_layout(xaxis_title=x_axis_label, yaxis_title="Кумулятивний профіт ($)")
    st.plotly_chart(fig_cumulative_profit, use_container_width=True)

    st.subheader("Динаміка балансу рахунку")
    fig_balance_change = px.line(
        positions_df_cleaned, x=x_axis_data, y='change_balance_acc', title="Динаміка балансу рахунку",
        labels={'change_balance_acc': 'Баланс', (x_axis_data.name if hasattr(x_axis_data, 'name') and x_axis_data.name else 'index'): x_axis_label}
    )
    fig_balance_change.update_layout(xaxis_title=x_axis_label, yaxis_title="Баланс рахунку ($)")
    st.plotly_chart(fig_balance_change, use_container_width=True)


# ---- ЗАВАНТАЖЕННЯ ТА ВІДОБРАЖЕННЯ ДАНИХ ПРО АКАУНТИ ----
st.header(f"Інформація про акаунти (з таблиці: {ACCOUNTS_TABLE_NAME})")
accounts_df_global = load_data(ACCOUNTS_TABLE_NAME) # Ця функція тепер буде викликатися при кожному автооновленні

if not accounts_df_global.empty:
    # (Решта коду для обробки accounts_df_global та AgGrid залишається практично без змін)
    required_account_cols = ["account_id", "platform"]
    if not all(col in accounts_df_global.columns for col in required_account_cols):
        missing_cols = [col for col in required_account_cols if col not in accounts_df_global.columns]
        st.error(f"Критична помилка: в таблиці '{ACCOUNTS_TABLE_NAME}' відсутні колонки: {', '.join(missing_cols)}. Інтерактивність неможлива.")
        # Не зупиняємо додаток, щоб автооновлення продовжило працювати і, можливо, колонка з'явиться
    else: # Продовжуємо, тільки якщо ключові колонки є
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
        
        # Фільтруємо колонки, які реально є в DataFrame, перед перейменуванням
        existing_cols_for_display = {k: v for k, v in columns_to_display.items() if k in accounts_df_global.columns}
        display_df_accounts = accounts_df_global[list(existing_cols_for_display.keys())].copy()
        display_df_accounts.rename(columns=existing_cols_for_display, inplace=True)


        currency_columns_keys = ["balance", "initial_deposit", "total_deposits", "total_withdrawals", "total_profit"]
        # Використовуємо перейменовані назви колонок для налаштування AgGrid
        currency_columns_renamed = [existing_cols_for_display.get(key) for key in currency_columns_keys if existing_cols_for_display.get(key) in display_df_accounts.columns]

        for col in currency_columns_renamed:
            if col in display_df_accounts.columns: # Додаткова перевірка
                display_df_accounts[col] = pd.to_numeric(display_df_accounts[col], errors='coerce')

        gb = GridOptionsBuilder.from_dataframe(display_df_accounts)
        for col_name in currency_columns_renamed:
            if col_name in display_df_accounts.columns:
                gb.configure_column(col_name, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2, aggFunc='sum')
        
        active_col_renamed = existing_cols_for_display.get("is_active")
        if active_col_renamed and active_col_renamed in display_df_accounts.columns:
             gb.configure_column(active_col_renamed, cellRenderer='agBooleanCellRenderer', editable=False, width=100)

        gb.configure_selection(selection_mode='single', use_checkbox=False)
        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=10)
        gb.configure_default_column(editable=False, filter=True, sortable=True, resizable=True)
        gridOptions = gb.build()

        st.subheader("Оберіть акаунт для перегляду деталей позицій:")
        if AgGrid: # Перевірка, чи AgGrid було успішно імпортовано
            account_grid_response = AgGrid(
                display_df_accounts, gridOptions=gridOptions, data_return_mode=DataReturnMode.AS_INPUT,
                update_mode=GridUpdateMode.MODEL_CHANGED, allow_unsafe_jscode=True, height=350,
                width='100%', fit_columns_on_grid_load=True, theme='streamlit',
                key=f"aggrid_accounts_{refresh_count}" # Додаємо refresh_count до ключа AgGrid, щоб воно оновлювалось
            )
            
            selected_rows_df = account_grid_response.get('selected_rows')

            if selected_rows_df is not None and not selected_rows_df.empty:
                first_selected_row = selected_rows_df.iloc[0]
                
                id_col_name_display = existing_cols_for_display.get("account_id")
                platform_col_name_display = existing_cols_for_display.get("platform")

                # Перевіряємо, чи ці колонки існують у first_selected_row (Series)
                selected_account_id_from_grid = first_selected_row.get(id_col_name_display) if id_col_name_display else None
                selected_platform_from_grid = first_selected_row.get(platform_col_name_display) if platform_col_name_display else None


                if selected_account_id_from_grid is not None and selected_platform_from_grid is not None:
                    # Перевіряємо, чи вибір змінився порівняно з session_state
                    if (st.session_state.selected_account_id != str(selected_account_id_from_grid).strip() or
                        st.session_state.selected_account_platform != str(selected_platform_from_grid).strip()):
                        st.session_state.selected_account_id = str(selected_account_id_from_grid).strip()
                        st.session_state.selected_account_platform = str(selected_platform_from_grid).strip()
                        # Скидаємо дані позицій, щоб вони перезавантажились для нового вибору
                        st.session_state.selected_account_positions_df = pd.DataFrame()
                        st.session_state.current_positions_table_name = ""
                        st.rerun() # Примусовий перезапуск для оновлення графіків під новий вибір
                # Якщо ID або платформа не отримані, але раніше був вибір, не скидаємо його,
                # щоб уникнути мерехтіння, якщо таблиця тимчасово "неправильно" оновилась.
                # elif st.session_state.selected_account_id is not None:
                #    pass # Залишаємо попередній вибір

            # Навіть якщо нічого не вибрано, але був попередній вибір, ми його не скидаємо автоматично,
            # хіба що список акаунтів став порожнім
        else: # Якщо AgGrid не імпортовано
            st.dataframe(display_df_accounts)


elif 'db_connection_successful' in st.session_state and st.session_state.db_connection_successful:
    st.info(f"Таблиця акаунтів '{ACCOUNTS_TABLE_NAME}' порожня або не вдалося завантажити дані. Оновлення через {refresh_interval_seconds} сек.")
    # Скидаємо вибір, якщо акаунтів немає
    st.session_state.selected_account_id = None
    st.session_state.selected_account_platform = None
    st.session_state.selected_account_positions_df = pd.DataFrame()
    st.session_state.current_positions_table_name = ""


st.markdown("---")

# ---- ВІДОБРАЖЕННЯ ГРАФІКІВ ДЛЯ ВИБРАНОГО АКАУНТУ (логіка залишається схожою) ----
if st.session_state.selected_account_id and st.session_state.selected_account_platform:
    current_account_id = st.session_state.selected_account_id
    current_platform = st.session_state.selected_account_platform
    
    platform_for_table_name = current_platform
    if "metatrader 5" in current_platform.lower() or "mt5" in current_platform.lower():
        platform_for_table_name = "MT5"
    elif "metatrader 4" in current_platform.lower() or "mt4" in current_platform.lower():
        platform_for_table_name = "MT4"

    if platform_for_table_name:
        positions_table_for_account = DYNAMIC_POSITION_TABLE_NAME_TEMPLATE.format(
            account_id=current_account_id,
            platform=platform_for_table_name
        )
        
        # Умова перезавантаження даних позицій
        # Перезавантажуємо, якщо:
        # 1. Назва таблиці змінилася (вибрали інший акаунт).
        # 2. DataFrame позицій порожній (перший раз завантажуємо для цього акаунту, або попереднє завантаження не вдалося).
        # 3. `refresh_count` змінився, І назва таблиці *не* змінилася (щоб оновити дані для *того самого* акаунту).
        #    Ця третя умова тут не потрібна, бо load_data для позицій має свій TTL.
        #    Авторефреш оновлює список акаунтів. Якщо користувач потім знову клікне на той самий акаунт,
        #    або якщо ми хочемо, щоб дані позицій теж автооновлювались, потрібно окрему логіку.
        #    Поки що дані позицій оновлюються при зміні вибору акаунту, або якщо їх TTL в load_data вичерпався.

        if st.session_state.current_positions_table_name != positions_table_for_account or st.session_state.selected_account_positions_df.empty:
            st.caption(f"Акаунт: {current_account_id}, Платформа: {current_platform} (для таблиці: {platform_for_table_name}). Очікувана таблиця: `{positions_table_for_account}`")
            with st.spinner(f"Завантаження даних позицій з {positions_table_for_account}..."):
                st.session_state.selected_account_positions_df = load_data(positions_table_for_account)
                st.session_state.current_positions_table_name = positions_table_for_account
                if not st.session_state.selected_account_positions_df.empty:
                     st.success(f"Дані позицій з '{positions_table_for_account}' успішно завантажені.")
                elif not conn.query(f"SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename  = '{positions_table_for_account.split('.')[-1].replace('\"','')}');").iloc[0,0]:
                    st.error(f"Таблиця позицій '{positions_table_for_account}' не знайдена в базі даних.")
                else:
                    st.warning(f"Таблиця позицій '{positions_table_for_account}' завантажена, але порожня або не містить потрібних даних.")


        # Передаємо ID акаунту для заголовка графіків
        display_position_charts(st.session_state.selected_account_positions_df, st.session_state.current_positions_table_name, current_account_id)
    else: # Якщо platform_for_table_name не визначено
        st.error(f"Не вдалося визначити платформу для формування назви таблиці позицій для акаунту {current_account_id} (платформа: {current_platform}).")

elif not accounts_df_global.empty : # Акаунти є, але не вибрано
    st.info("📈 Будь ласка, оберіть акаунт з таблиці вище, щоб побачити графіки його позицій.")
# Якщо accounts_df_global порожній, але з'єднання було, відповідне повідомлення вже виведене.

st.sidebar.info("""
**Інструкція:**
1. Оберіть акаунт зі списку.
2. Графіки позицій для вибраного акаунту відобразяться нижче.
3. Список акаунтів оновлюється автоматично.
""")
if 'db_connection_successful' in st.session_state and not st.session_state.db_connection_successful:
    st.sidebar.error("Проблема з підключенням до БД!")
