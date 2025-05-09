import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_autorefresh import st_autorefresh

try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
except ImportError:
    st.error("Бібліотека streamlit-aggrid не знайдена...")
    AgGrid = None
    st.stop()

# ---- НАЛАШТУВАННЯ СТОРІНКИ ТА ТЕМИ (Залишаємо ваш приклад стилів) ----
st.set_page_config(
    page_title="Торговий Дашборд PRO",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)
# ... (Ваші кастомні стилі st.markdown залишаються тут) ...
st.markdown("""
<style>
    .main .block-container {padding-top: 2rem; padding-left: 2rem; padding-right: 2rem;}
    h1, h2, h3 {color: #2C3E50;}
    .stMetric {background-color: #ECF0F1; border-radius: 10px; padding: 1rem; border: 1px solid #BDC3C7;}
    .stMetric > label {font-weight: bold; color: #34495E;}
    .stButton>button {background-color: #3498DB; color: white; border-radius: 5px; padding: 0.5rem 1rem; border: none;}
    .stButton>button:hover {background-color: #2980B9;}
</style>
""", unsafe_allow_html=True)


# ---- АВТОМАТИЧНЕ ОНОВЛЕННЯ ----
refresh_interval_seconds = 60
refresh_count = st_autorefresh(interval=refresh_interval_seconds * 1000, limit=None, key="account_refresh")

# ---- ЗАГОЛОВОК ТА САЙДБАР (Залишаємо ваш приклад) ----
with st.sidebar:
    # st.image("your_logo.png", width=150) # Розкоментуйте та замініть на своє лого
    st.header("Фільтри та Навігація")
    st.info(f"Торговий Дашборд v1.1 (Оновлення #{refresh_count})")

st.title("💰 Торговий Дашборд з Neon DB") # Оновимо заголовок
# st.markdown("### Ваш персональний фінансовий аналітик") # Можна повернути, якщо подобається

# ---- КЕШУВАННЯ ----
@st.cache_resource
def get_db_connection():
    try:
        conn_obj = st.connection("neon_db", type="sql")
        conn_obj.query("SELECT 1;")
        if 'db_connection_successful' not in st.session_state or not st.session_state.db_connection_successful:
            # st.success("🎉 Підключення до бази даних Neon DB успішне!") # Можна прибрати, щоб не з'являлось при кожному рефреші
            st.session_state.db_connection_successful = True
        return conn_obj
    except Exception as e:
        st.error(f"Помилка підключення до бази даних: {e}")
        # Надаємо більше деталей з помилки, якщо це InterfaceError
        if "InterfaceError" in str(e) or "e3q8" in str(e):
            st.error("Деталі помилки SQLAlchemy: Схоже на проблему з драйвером БД або параметрами підключення. Перевірте конфігурацію `secrets.toml`.")
            st.error(f"Оригінальне повідомлення: {e}") # Показуємо оригінальне повідомлення
        st.session_state.db_connection_successful = False
        st.stop()

@st.cache_data(ttl=300)
def load_data(table_name: str):
    local_conn = get_db_connection()
    if not local_conn:
        return pd.DataFrame()
    
    query_table_name_for_log = table_name
    try:
        # Логіка формування назви таблиці для запиту
        # Оскільки назви таблиць тепер формату [account_id]_mt5_data, вони можуть містити цифри на початку (після account_id_)
        # і підкреслення. PostgreSQL за замовчуванням зберігає назви в нижньому регістрі, якщо вони не взяті в лапки при створенні.
        # Найбезпечніше брати назву таблиці в подвійні лапки, якщо не впевнені в регістрі або наявності спецсимволів.
        # Припускаємо, що table_name, який передається, вже є правильною назвою таблиці (наприклад, "12345_mt5_data")
        
        # Якщо ваша база даних чутлива до регістру І ви створювали таблиці з великими літерами (напр. "12345_MT5_data"),
        # то треба використовувати точний регістр. Якщо ж ні, то PostgreSQL все переведе в нижній.
        # Для безпеки, якщо назва не є простою (тільки букви, цифри, підкреслення, не починається з цифри), беремо в лапки.
        
        # Проста перевірка: якщо назва таблиці містить щось крім букв, цифр та '_', або починається з цифри,
        # або якщо ви просто хочете бути впевненими, можна взяти в лапки.
        # postgresql автоматично переводить не взяті в лапки імена в нижній регістр.
        # Якщо таблиця називається "12345_mt5_data" (створена без лапок), то запит до public.12345_mt5_data або public."12345_mt5_data" спрацює.
        
        # Ми будемо формувати назву public."table_name" для більшої надійності,
        # якщо вона не містить public. на початку
        if table_name.lower().startswith("public."):
             query_table_name = table_name # Вже з public, можливо з лапками
        else:
            # Якщо postgresql автоматично приводить до нижнього регістра, то імена ми теж приводимо
            # table_name = table_name.lower() # Розкоментуйте, якщо всі ваші таблиці в нижньому регістрі
            query_table_name = f'public."{table_name}"'


        # Залишимо логування, щоб бачити, яку таблицю намагаємось запитати
        # st.caption(f"[DEBUG] Запит до таблиці: {query_table_name}")

        full_query_text = f'SELECT * FROM {query_table_name};'
        df = local_conn.query(full_query_text)
        
        # Прибираємо попередження про порожню таблицю тут, щоб не спамити при автооновленні
        return df
    except Exception as e:
        # Якщо помилка через те, що таблиця не знайдена (це типово для ProgrammingError в psycopg2/sqlalchemy)
        # (psycopg2.errors.UndefinedTable): relation "public.some_table" does not exist
        if "UndefinedTable" in str(e) or "does not exist" in str(e) or "relation" in str(e) and "does not exist" in str(e):
            st.warning(f"Таблиця '{query_table_name if 'query_table_name' in locals() else table_name}' не знайдена в базі даних.")
        else:
            st.error(f"Помилка при завантаженні даних з '{query_table_name_for_log}' (спроба запиту до '{query_table_name if 'query_table_name' in locals() else table_name}'): {e}")
        return pd.DataFrame()

# ---- НАЗВИ ТАБЛИЦЬ ТА ІНІЦІАЛІЗАЦІЯ ----
ACCOUNTS_TABLE_NAME = "stat_user_account_v2" # Залишається без змін (якщо це так)
# НОВИЙ ШАБЛОН для таблиць позицій:
# Припускаємо, що платформа (mt5/mt4) буде відома з даних головної таблиці акаунтів
# або ви можете мати окремі функції для MT5 і MT4, якщо логіка сильно відрізняється
DYNAMIC_POSITION_TABLE_NAME_TEMPLATE = "{account_id}_{platform_suffix}_data" # platform_suffix буде 'mt5' або 'mt4'

if 'selected_account_id' not in st.session_state:
    st.session_state.selected_account_id = None
if 'selected_account_platform_suffix' not in st.session_state: # Змінено для відображення нової логіки
    st.session_state.selected_account_platform_suffix = None
if 'selected_account_positions_df' not in st.session_state:
    st.session_state.selected_account_positions_df = pd.DataFrame()
if 'current_positions_table_name' not in st.session_state:
    st.session_state.current_positions_table_name = ""

conn = get_db_connection()

# ---- ФУНКЦІЯ ВІДОБРАЖЕННЯ ГРАФІКІВ ПОЗИЦІЙ (без суттєвих змін, але увага до колонок) ----
def display_position_charts(positions_df: pd.DataFrame, table_name: str, account_id_display: str):
    if positions_df.empty:
        return

    st.header(f"Аналіз позицій для акаунту {account_id_display} (з таблиці: {table_name})")

    # ВАЖЛИВО: Перевірте, чи назви колонок 'net_profit_db', 'change_balance_acc', 'time_close'
    # залишилися такими ж у нових таблицях  `_mt5_data` / `_mt4_data`
    required_cols_positions = ['net_profit_db', 'change_balance_acc', 'time_close'] # АБО ЯК ВОНИ ТЕПЕР НАЗИВАЮТЬСЯ
    
    missing_required_cols = [col for col in required_cols_positions if col not in positions_df.columns]
    if missing_required_cols:
        st.error(f"У таблиці '{table_name}' відсутні необхідні колонки для графіків: {', '.join(missing_required_cols)}. "
                 f"Наявні колонки: {positions_df.columns.tolist()}")
        return

    # ... (решта логіки display_position_charts залишається такою ж, як раніше,
    #      за умови, що назви фінансових колонок і колонки часу не змінилися)
    positions_df_cleaned = positions_df.copy()
    for col in ['net_profit_db', 'change_balance_acc']: # Перевірте ці назви!
        positions_df_cleaned[col] = pd.to_numeric(positions_df_cleaned[col], errors='coerce')

    x_axis_data = positions_df_cleaned.index
    x_axis_label = 'Номер угоди'

    if 'time_close' in positions_df_cleaned.columns: # Перевірте цю назву!
        try:
            temp_time_close = pd.to_datetime(positions_df_cleaned['time_close'], errors='coerce')
            if temp_time_close.isnull().all():
                temp_time_close = pd.to_datetime(positions_df_cleaned['time_close'], unit='s', origin='unix', errors='coerce')
            
            if not temp_time_close.isnull().all():
                positions_df_cleaned['time_close_dt'] = temp_time_close
                positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc', 'time_close_dt'], inplace=True)
                if not positions_df_cleaned.empty:
                    positions_df_cleaned = positions_df_cleaned.sort_values(by='time_close_dt')
                    x_axis_data = positions_df_cleaned['time_close_dt']
                    x_axis_label = 'Час закриття'
                else:
                    positions_df_cleaned = positions_df.copy() 
                    for col_num in ['net_profit_db', 'change_balance_acc']:
                        positions_df_cleaned[col_num] = pd.to_numeric(positions_df_cleaned[col_num], errors='coerce')
                    st.warning(f"Обробка 'time_close' як дати призвела до порожнього датасету для '{table_name}'. Використовується сортування за індексом.")
                    positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True)

            elif positions_df_cleaned['time_close'].notna().any():
                try:
                    positions_df_cleaned['time_close_numeric'] = pd.to_numeric(positions_df_cleaned['time_close'], errors='coerce')
                    positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc', 'time_close_numeric'], inplace=True)
                    if not positions_df_cleaned.empty:
                        positions_df_cleaned = positions_df_cleaned.sort_values(by='time_close_numeric')
                        x_axis_data = positions_df_cleaned.index 
                        x_axis_label = 'Номер угоди (Відсортовано за числовим time_close)'
                except Exception as e_numeric:
                     st.error(f"Не вдалося обробити 'time_close' ні як дату/час, ні як число: {e_numeric}")
                     return
            else:
                 positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True)
        except Exception as e_datetime:
            st.warning(f"Загальна помилка при обробці 'time_close' для '{table_name}': {e_datetime}. Використовується сортування за індексом.")
            positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc'], inplace=True)
    else:
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
    # Переконайтеся, що 'change_balance_acc' все ще актуальна назва колонки
    fig_balance_change = px.line(
        positions_df_cleaned, x=x_axis_data, y='change_balance_acc', title="Динаміка балансу рахунку",
        labels={'change_balance_acc': 'Баланс', (x_axis_data.name if hasattr(x_axis_data, 'name') and x_axis_data.name else 'index'): x_axis_label}
    )
    fig_balance_change.update_layout(xaxis_title=x_axis_label, yaxis_title="Баланс рахунку ($)")
    st.plotly_chart(fig_balance_change, use_container_width=True)


# ---- ВКЛАДКИ ДЛЯ НАВІГАЦІЇ ----
tab_overview, tab_accounts, tab_positions = st.tabs([
    "📊 Загальний Огляд",
    "👤 Акаунти",
    "📈 Деталі Позицій"
])

with tab_overview:
    st.header("Ключові Показники (Заглушка)")
    # Тут можна додати агреговані дані по всіх акаунтах, якщо є
    st.info("Ця вкладка для загального огляду. Наразі в розробці.")

with tab_accounts:
    st.header(f"Інформація про акаунти (з таблиці: {ACCOUNTS_TABLE_NAME})")
    accounts_df_global = load_data(ACCOUNTS_TABLE_NAME)

    if not accounts_df_global.empty:
        # ВАЖЛИВО: Перевірте, чи є в `accounts_df_global` колонка,
        # яка вказує на тип платформи (MT5/MT4), щоб сформувати `platform_suffix`
        # Припустимо, що колонка `platform` все ще існує і містить "MT5" або "MT4" або схожі значення.
        required_account_cols = ["account_id", "platform"] # 'platform' потрібна для визначення суфікса
        if not all(col in accounts_df_global.columns for col in required_account_cols):
            missing_cols = [col for col in required_account_cols if col not in accounts_df_global.columns]
            st.error(f"Критична помилка: в таблиці '{ACCOUNTS_TABLE_NAME}' відсутні колонки: {', '.join(missing_cols)}.")
        else:
            accounts_df_global["account_id"] = accounts_df_global["account_id"].astype(str).str.strip()
            accounts_df_global["platform_original"] = accounts_df_global["platform"].astype(str).str.strip() # Зберігаємо оригінал

            # Логіка для визначення platform_suffix (mt5, mt4)
            def get_platform_suffix(platform_value):
                platform_val_lower = platform_value.lower()
                if "mt5" in platform_val_lower or "metatrader 5" in platform_val_lower:
                    return "mt5"
                elif "mt4" in platform_val_lower or "metatrader 4" in platform_val_lower:
                    return "mt4"
                return None # Або якесь значення за замовчуванням / помилка

            accounts_df_global["platform_suffix_for_table"] = accounts_df_global["platform_original"].apply(get_platform_suffix)
            
            # Відфільтровуємо акаунти, для яких не вдалося визначити суфікс, якщо потрібно
            accounts_to_display_df = accounts_df_global.dropna(subset=["platform_suffix_for_table"])
            if accounts_to_display_df.empty and not accounts_df_global.empty :
                 st.warning("Не вдалося визначити суфікс платформи (mt5/mt4) для жодного з акаунтів. Перевірте значення в колонці 'platform'.")


            columns_to_display_config = { # Тепер використовуємо platform_original для відображення
                "account_id": "ID Акаунту", "platform_original": "Платформа", "user_id": "ID Користувача",
                "broker_name": "Брокер", "server": "Сервер", "deposit_currency": "Валюта депозиту",
                "account_type": "Тип акаунту", "account_status": "Статус акаунту", "is_active": "Активний",
                "balance": "Баланс", "initial_deposit": "Початковий депозит",
                "total_deposits": "Всього депозитів", "total_withdrawals": "Всього виведено",
                "total_profit": "Загальний профіт"
                # "platform_suffix_for_table": "Суфікс для таблиці" # Для дебагу можна додати
            }
            
            existing_display_cols_keys = [k for k, v in columns_to_display_config.items() if k in accounts_to_display_df.columns]
            display_df_aggrid = accounts_to_display_df[existing_display_cols_keys].copy()
            display_df_aggrid.rename(columns=columns_to_display_config, inplace=True)

            # ... (решта коду для AgGrid, як раніше, використовуючи display_df_aggrid)
            if AgGrid and not display_df_aggrid.empty:
                gb = GridOptionsBuilder.from_dataframe(display_df_aggrid)
                # ... (конфігурація колонок)
                currency_columns_keys = ["balance", "initial_deposit", "total_deposits", "total_withdrawals", "total_profit"]
                currency_columns_renamed = [columns_to_display_config.get(key) for key in currency_columns_keys if columns_to_display_config.get(key) in display_df_aggrid.columns]

                for col_name in currency_columns_renamed:
                    if col_name in display_df_aggrid.columns:
                        gb.configure_column(col_name, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2, aggFunc='sum')
                
                active_col_renamed = columns_to_display_config.get("is_active")
                if active_col_renamed and active_col_renamed in display_df_aggrid.columns:
                    gb.configure_column(active_col_renamed, cellRenderer='agBooleanCellRenderer', editable=False, width=100)

                gb.configure_selection(selection_mode='single', use_checkbox=False)
                gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=10)
                gb.configure_default_column(editable=False, filter=True, sortable=True, resizable=True)
                gridOptions = gb.build()

                st.subheader("Оберіть акаунт для перегляду деталей позицій:")
                account_grid_response = AgGrid(
                    display_df_aggrid, gridOptions=gridOptions, data_return_mode=DataReturnMode.AS_INPUT,
                    update_mode=GridUpdateMode.MODEL_CHANGED, allow_unsafe_jscode=True, height=350,
                    width='100%', fit_columns_on_grid_load=True, theme='streamlit',
                    key=f"aggrid_accounts_{refresh_count}"
                )
                
                selected_rows_df = account_grid_response.get('selected_rows')

                if selected_rows_df is not None and not selected_rows_df.empty:
                    first_selected_row_series = selected_rows_df.iloc[0] # Це Series з вибраного рядка AgGrid
                    
                    # Отримуємо ID акаунту з AgGrid (використовуючи перейменовану назву колонки)
                    selected_account_id_from_grid = first_selected_row_series.get(columns_to_display_config.get("account_id"))
                    
                    # ВАЖЛИВО: тепер нам потрібен `platform_suffix_for_table` для цього account_id
                    # Ми повинні знайти відповідний рядок в `accounts_to_display_df` (перед перейменуванням)
                    original_account_data = accounts_to_display_df[accounts_to_display_df["account_id"] == str(selected_account_id_from_grid)]
                    
                    if not original_account_data.empty:
                        selected_platform_suffix_for_table = original_account_data.iloc[0]["platform_suffix_for_table"]
                        
                        if selected_account_id_from_grid is not None and selected_platform_suffix_for_table is not None:
                            if (st.session_state.selected_account_id != str(selected_account_id_from_grid) or
                                st.session_state.selected_account_platform_suffix != selected_platform_suffix_for_table):
                                st.session_state.selected_account_id = str(selected_account_id_from_grid)
                                st.session_state.selected_account_platform_suffix = selected_platform_suffix_for_table
                                st.session_state.selected_account_positions_df = pd.DataFrame()
                                st.session_state.current_positions_table_name = ""
                                # st.rerun() # Можна викликати, щоб перейти на вкладку позицій, якщо бажано
                                st.success(f"Акаунт {st.session_state.selected_account_id} ({st.session_state.selected_account_platform_suffix}) вибрано. Перейдіть на вкладку 'Деталі Позицій'.")

                    else:
                        st.warning("Не вдалося знайти дані платформи для вибраного акаунту.")
            elif not AgGrid:
                 st.dataframe(display_df_aggrid)
            elif display_df_aggrid.empty and not accounts_df_global.empty:
                 st.info("Немає акаунтів для відображення після фільтрації по платформі.")


    elif 'db_connection_successful' in st.session_state and st.session_state.db_connection_successful:
        st.info(f"Таблиця акаунтів '{ACCOUNTS_TABLE_NAME}' порожня або не вдалося завантажити. Оновлення через {refresh_interval_seconds} сек.")
        st.session_state.selected_account_id = None
        st.session_state.selected_account_platform_suffix = None
        st.session_state.selected_account_positions_df = pd.DataFrame()
        st.session_state.current_positions_table_name = ""

with tab_positions:
    st.header("Аналіз позицій вибраного акаунту")
    if st.session_state.selected_account_id and st.session_state.selected_account_platform_suffix:
        current_account_id = st.session_state.selected_account_id
        current_platform_suffix = st.session_state.selected_account_platform_suffix
        
        positions_table_for_account = DYNAMIC_POSITION_TABLE_NAME_TEMPLATE.format(
            account_id=current_account_id,
            platform_suffix=current_platform_suffix # тепер це 'mt5' або 'mt4'
        )
        
        st.caption(f"Акаунт: {current_account_id} (платформа: {current_platform_suffix}). "
                   f"Очікувана таблиця позицій: `{positions_table_for_account}`")

        if st.session_state.current_positions_table_name != positions_table_for_account or st.session_state.selected_account_positions_df.empty:
            with st.spinner(f"Завантаження даних позицій з {positions_table_for_account}..."):
                st.session_state.selected_account_positions_df = load_data(positions_table_for_account)
                st.session_state.current_positions_table_name = positions_table_for_account
                if not st.session_state.selected_account_positions_df.empty:
                     st.success(f"Дані позицій з '{positions_table_for_account}' успішно завантажені.")
                # Перевірка, чи таблиця існує, вже є в load_data
        
        display_position_charts(st.session_state.selected_account_positions_df, st.session_state.current_positions_table_name, current_account_id)
    else:
        st.info("Будь ласка, оберіть акаунт на вкладці 'Акаунти', щоб побачити деталі позицій.")

# ---- Підвал ----
st.markdown("---")
st.markdown("© 2024 Ваш Торговий Дашборд.")
