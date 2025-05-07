import streamlit as st
import pandas as pd
import plotly.express as px # Будемо використовувати для красивих графіків

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
        conn = st.connection("neon_db", type="sql")
        # Проста перевірка підключення
        conn.query("SELECT 1;")
        return conn
    except Exception as e:
        st.error(f"Помилка підключення до бази даних: {e}")
        st.stop()

conn = get_db_connection()
if conn:
    st.success("🎉 Підключення до бази даних Neon DB успішне!")


# ---- ФУНКЦІЯ ДЛЯ ЗАВАНТАЖЕННЯ ДАНИХ З КЕШУВАННЯМ ----
@st.cache_data(ttl=600) # Кешування даних на 10 хвилин
def load_data(table_name, connection):
    try:
        query = f'SELECT * FROM public."{table_name}";' # Взяли назву таблиці в подвійні лапки
        df = connection.query(query)
        if df.empty:
            st.warning(f"Таблиця 'public.\"{table_name}\"' порожня або не знайдена.")
            return pd.DataFrame()
        st.success(f"Дані з таблиці 'public.\"{table_name}\"' успішно завантажені!")
        return df
    except Exception as e:
        st.error(f"Помилка при завантаженні даних з таблиці 'public.\"{table_name}\"': {e}")
        return pd.DataFrame()

# ---- НАЗВИ ТАБЛИЦЬ ----
POSITIONS_TABLE_NAME = "11232052_positions_MT5_v2"
ACCOUNTS_TABLE_NAME = "stat_user_account_v2"

# ---- ЗАВАНТАЖЕННЯ ТА ОБРОБКА ДАНИХ ДЛЯ ГРАФІКІВ ПОЗИЦІЙ ----
st.header(f"Аналіз позицій з таблиці: {POSITIONS_TABLE_NAME}")

positions_df = load_data(POSITIONS_TABLE_NAME, conn)

if not positions_df.empty:
    # Переконаємося, що необхідні колонки існують
    required_cols_positions = ['net_profit_db', 'change_balance_acc', 'time_close'] # Додаємо 'time_close' для сортування
    if not all(col in positions_df.columns for col in required_cols_positions):
        st.error(f"Відсутні необхідні колонки в таблиці '{POSITIONS_TABLE_NAME}'. Потрібні: {', '.join(required_cols_positions)}")
    else:
        # Очистка та підготовка даних
        positions_df_cleaned = positions_df.copy()
        
        # Перетворення числових колонок, обробка можливих помилок
        for col in ['net_profit_db', 'change_balance_acc']:
            positions_df_cleaned[col] = pd.to_numeric(positions_df_cleaned[col], errors='coerce')
        
        # Обробка колонки дати/часу (ВАЖЛИВО: потрібна колонка для сортування угод по часу!)
        # Якщо у вас є колонка типу 'time_create', 'time_update' або 'time_close', використовуйте її
        # Припустимо, що є колонка 'time_close' для часу закриття угоди
        if 'time_close' in positions_df_cleaned.columns:
            try:
                positions_df_cleaned['time_close'] = pd.to_datetime(positions_df_cleaned['time_close'], errors='coerce')
                # Видаляємо рядки, де не вдалося розпізнати дату/час або числові значення
                positions_df_cleaned.dropna(subset=['net_profit_db', 'change_balance_acc', 'time_close'], inplace=True)
                # Сортування за часом закриття для правильного кумулятивного графіку
                positions_df_cleaned = positions_df_cleaned.sort_values(by='time_close')
            except Exception as e:
                st.warning(f"Проблема з обробкою колонки 'time_close': {e}. Графіки можуть бути неточними.")
                # Якщо немає time_close, спробуємо хоча б по індексу, але це менш надійно
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
            # Якщо 'change_balance_acc' це абсолютний баланс після кожної угоди, можна просто його відобразити
            # Якщо це зміна, то можливо, теж потрібен кумулятивний графік або початковий баланс
            # Наразі припустимо, що 'change_balance_acc' - це сам баланс після угоди
            
            # Якщо у вас є колонка з поточним балансом після кожної угоди, використовуйте її.
            # Якщо 'change_balance_acc' - це *зміна* балансу від угоди, а не абсолютний баланс,
            # то потрібно буде розрахувати поточний баланс, додавши початковий.
            # Для простоти, припустимо, що 'change_balance_acc' вже є абсолютним балансом.
            # Якщо це не так, потрібно буде коригувати (наприклад, .cumsum(), якщо це дельти)

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

accounts_df = load_data(ACCOUNTS_TABLE_NAME, conn)

if not accounts_df.empty:
    # Вибираємо та перейменовуємо колонки для кращого вигляду
    columns_to_display = {
        "account_id": "ID Акаунту",
        "platform": "Платформа",
        "user_id": "ID Користувача",
        "broker_name": "Брокер",
        "server": "Сервер",
        "deposit_currency": "Валюта депозиту",
        "account_type": "Тип акаунту",
        "account_status": "Статус акаунту",
        "is_active": "Активний",
        "balance": "Баланс",
        "initial_deposit": "Початковий депозит",
        "total_deposits": "Всього депозитів",
        "total_withdrawals": "Всього виведено",
        "total_profit": "Загальний профіт"
    }
    
    display_df = accounts_df[[col for col in columns_to_display if col in accounts_df.columns]].copy()
    display_df.rename(columns=columns_to_display, inplace=True)

    # Форматування числових колонок (валюта)
    currency_columns = [
        columns_to_display.get("balance"),
        columns_to_display.get("initial_deposit"),
        columns_to_display.get("total_deposits"),
        columns_to_display.get("total_withdrawals"),
        columns_to_display.get("total_profit")
    ]
    currency_columns = [col for col in currency_columns if col and col in display_df.columns] # Фільтруємо None та відсутні

    # Перетворення на числові перед форматуванням
    for col in currency_columns:
        display_df[col] = pd.to_numeric(display_df[col], errors='coerce')

    # Динамічна таблиця з AgGrid (потребує streamlit-aggrid)
    # ВАЖЛИВО: Додайте streamlit-aggrid до requirements.txt
    try:
        from st_aggrid import AgGrid, GridOptionsBuilder # type: ignore
        from st_aggrid.shared import GridUpdateMode

        gb = GridOptionsBuilder.from_dataframe(display_df)
        # Налаштування для числових колонок (вирівнювання, форматування)
        for col_name in currency_columns:
            gb.configure_column(col_name, type=["numericColumn", "numberColumnFilter", "customNumericFormat"], precision=2, aggFunc='sum')
        
        # Налаштування для булевої колонки "Активний"
        if columns_to_display.get("is_active") in display_df.columns:
             gb.configure_column(columns_to_display.get("is_active"), cellRenderer='agBooleanCellRenderer', editable=False)

        gb.configure_pagination(paginationAutoPageSize=True)
        gb.configure_side_bar() # Додає бічну панель для групування, фільтрації тощо
        gb.configure_default_column(editable=False, filter=True, sortable=True, resizable=True)
        
        gridOptions = gb.build()

        st.subheader("Детальна таблиця акаунтів (інтерактивна)")
        AgGrid(
            display_df,
            gridOptions=gridOptions,
            update_mode=GridUpdateMode.MODEL_CHANGED,
            allow_unsafe_jscode=True, # Потрібно для деяких функцій AgGrid
            height=600,
            width='100%',
            fit_columns_on_grid_load=True, # Автоматично підганяти ширину колонок
            theme='streamlit' # Або 'alpine', 'balham', 'material'
        )
    except ImportError:
        st.warning("Для відображення інтерактивної таблиці, будь ласка, встановіть 'streamlit-aggrid' та додайте до requirements.txt.")
        st.info("Відображення стандартної таблиці:")
        # Стилізація для стандартної таблиці
        st.dataframe(display_df.style.format(subset=currency_columns, formatter="{:,.2f}").hide(axis="index"))

else:
    st.info(f"Дані з таблиці '{ACCOUNTS_TABLE_NAME}' ще не завантажені або таблиця порожня.")

st.sidebar.info("Тут можна додати фільтри чи іншу навігацію.")
