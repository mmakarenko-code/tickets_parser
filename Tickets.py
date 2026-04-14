import time
import re
import pandas as pd
from fuzzywuzzy import fuzz
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


def clean_tags(value):
    if is_empty(value):
        return set()
    cleaned = re.sub(r"[\[\]'\" ]", " ", str(value))
    return {x.strip() for x in cleaned.split(',') if not is_empty(x.strip())}

def get_clean_ids(val):
    if is_empty(val):
        return set()
    raw_list = str(val).split(', ')
    clean_set = {
        str(int(float(x)))
        for x in raw_list
        if x and str(x).lower() not in ['nan', 'none', '']
    }
    return clean_set


def clean_string(text):
    if pd.isna(text) or not isinstance(text, str):
        return ""
    text = text.lower().replace('ё', 'е')
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def convert_bezkassira(text):
    if not text or not isinstance(text, str):
        return ""

    months_map = {
        'янв': '01', 'фев': '02', 'мар': '03', 'апр': '04', 'май': '05', 'мая': '05',
        'июн': '06', 'июл': '07', 'авг': '08', 'сен': '09', 'окт': '10', 'ноя': '11', 'дек': '12'
    }

    cleaned = ' '.join(text.split())

    date_pattern = r'(\d{1,2})\s+([а-я]+)\s+(\d{4})'
    matches = list(re.finditer(date_pattern, cleaned))

    for match in reversed(matches):
        day = match.group(1).zfill(2)
        month_ru = match.group(2).lower()
        year = match.group(3)

        month = months_map.get(month_ru, months_map.get(month_ru[:3], '??'))

        start, end = match.start(), match.end()
        cleaned = cleaned[:start] + f"{day}.{month}.{year}" + cleaned[end:]

    cleaned = re.sub(r'\s*,\s*', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return [f"{cleaned}"]


def convert_afisha(date_list, year="2026"):
    if not date_list or not isinstance(date_list, list):
        return ""

    months_map = {
        'янв': '01', 'фев': '02', 'мар': '03', 'апр': '04',
        'мая': '05', 'июн': '06', 'июл': '07', 'авг': '08',
        'сен': '09', 'окт': '10', 'ноя': '11', 'дек': '12'
    }
    pattern = r'(\d{1,2})\s+([а-яА-Я]+)\.?(?:\s+(\d{2}:\d{2}))?'

    result = []
    for date_str in date_list:
        date_str = date_str.replace('Продано', '').strip()
        match = re.search(pattern, date_str)
        if match:
            day, month_str, time = match.groups()
            month_key = month_str[:3].lower()
            month_num = months_map.get(month_key, '01')

            formatted_date = f"{int(day):02d}.{month_num}.{year}"
            if time:
                formatted_date += f" {time}"

            result.append(formatted_date)
        else:
            result.append(date_str)

    return result


def is_empty(val):
    if isinstance(val, (list, dict, str)) and len(val) == 0: return True
    if str(val).strip().lower() in ['none', '[]', '']: return True
    return False


def merge_records(group):
    priority_map = {'ticketpro': 1, 'afisha24': 2, 'bezkassira': 3}
    group['priority'] = group['Тип интегратора'].map(priority_map).fillna(99)
    group = group.sort_values('priority')

    base = group.iloc[0].to_dict()

    for _, row in group.iloc[1:].iterrows():
        n1, n2 = str(base.get('Название события', '')), str(row.get('Название события', ''))
        if fuzz.token_sort_ratio(n1, n2) < 70:
            if len(n2) > len(n1):
                base['Название события'] = n2

        ids_1 = get_clean_ids(base.get('ID События', ''))
        ids_2 = get_clean_ids(row.get('ID События', ''))
        combined_ids = sorted(list(ids_1 | ids_2), key=lambda x: int(x) if str(x).isdigit() else 0)
        base['ID События'] = ", ".join(map(str, combined_ids))

        v1 = base['Дата проведения'] if isinstance(base['Дата проведения'], list) else (
            [base['Дата проведения']] if not is_empty(base['Дата проведения']) else [])
        v2 = row['Дата проведения'] if isinstance(row['Дата проведения'], list) else (
            [row['Дата проведения']] if not is_empty(row['Дата проведения']) else [])

        combined = sorted(set(str(d).strip('[]').strip() for d in (v1 + v2) if not is_empty(d)))
        base['Дата проведения'] = ", ".join(combined) if combined else ""

        for col in ['Площадка/место проведения', 'Описание события', 'Организатор']:
            if is_empty(base.get(col)) and not is_empty(row.get(col)):
                base[col] = row[col]

        c1 = clean_tags(base.get('Рубрика - название', ''))
        c2 = clean_tags(row.get('Рубрика - название', ''))
        base['Рубрика - название'] = ", ".join(sorted(list(c1.union(c2))))

        if 'afisha24' in str(row.get('Тип интегратора', '')).lower() and not is_empty(row.get('Баннер')):
            base['Баннер'] = row['Баннер']

        for col in list(base.keys()):
            if ('ID рубрики' in col or 'place ID' in col):
                if is_empty(base.get(col)) and not is_empty(row.get(col)):
                    base[col] = row[col]

    return pd.Series(base)


def final_collapse(df):
    df = df.copy()

    processed_indices = set()
    final_rows = []

    records = df.to_dict('records')

    for i in range(len(records)):
        if i in processed_indices: continue

        current_group = [records[i]]
        processed_indices.add(i)

        for j in range(i + 1, len(records)):
            if j in processed_indices: continue

            score = fuzz.token_sort_ratio(records[i]['Название события'], records[j]['Название события'])

            if score >= 85:
                current_group.append(records[j])
                processed_indices.add(j)

        if len(current_group) > 1:
            final_rows.append(merge_records(pd.DataFrame(current_group)))
        else:
            final_rows.append(pd.Series(records[i]))

    return pd.DataFrame(final_rows).drop(columns=['priority'], errors='ignore')


def parse_ticket():
    out = []
    driver.get('https://www.ticketpro.by/')
    categories = []
    navigation_bar = driver.find_element(By.CLASS_NAME, 'top-menu')
    for cat in navigation_bar.find_elements(By.TAG_NAME, 'li'):
        categories.append(cat.find_element(By.TAG_NAME, 'a').get_attribute('href'))
    links = []
    for one in categories:
        driver.get(one)
        try:
            tab = driver.find_element(By.CLASS_NAME, 'pjax-preloader')
            for item in tab.find_elements(By.CLASS_NAME, 'event-box'):
                links.append(item.find_element(By.TAG_NAME, 'a').get_attribute('href'))
        except:
            pass
    links = list(set(links))
    for link in links:
        driver.get(link)
        elem = {}
        elem['Оригинальное название'] = ''
        elem['Название события'] = driver.find_element(By.CLASS_NAME, 'title').text.replace('\n', ' ').strip()
        elem['ID События'] = ""
        try:
            elem['Дата проведения'] = driver.find_element(By.CLASS_NAME, 'content__event-date').text.strip() + ' ' +  \
                                driver.find_element(By.CLASS_NAME, 'sidebar-box__event-date').text.split(',')[1].strip()
            try:
                time_event = driver.find_element(By.CLASS_NAME, 'sidebar-box__event-date').text.split(',')[1].strip()
                elem['Дата проведения'] = driver.find_element(By.CLASS_NAME, 'content__event-date').text.strip().replace(time_event, '') + ' ' + time_event
            except:
                pass
        except:
            elem['Дата проведения'] = ''
        if elem['Дата проведения'] != '':
            elem['Дата проведения'] = [re.sub(r',\s+', ' ', elem['Дата проведения'])]
        try:
            elem['Площадка/место проведения'] = driver.find_element(By.CLASS_NAME, 'sidebar-box__event-venue').text.replace('\n', ' ').strip()
        except:
            elem['Площадка/место проведения'] = ''
        elem['place ID afisha24'] = ''
        elem['place ID тикетпро'] = driver.find_element(By.CLASS_NAME, 'content__event-place').find_element(By.TAG_NAME, 'a').get_attribute('href')
        elem['place ID bezkassira'] = ''
        rubricks = driver.find_element(By.CLASS_NAME, 'breadcrumbs')
        elements = rubricks.find_elements(By.TAG_NAME, 'a')[1:]
        elem['Рубрика - название'] = ", ".join(sorted({x.text.strip() for x in elements if x.text.strip()}))
        elem['ID рубрики afisha24'] = ''
        elem['ID рубрики тикетпро'] = [rub.get_attribute('href')[:-1].split('/')[-1] for rub in elements]
        elem['ID рубрики bezkassira'] = ''
        try:
            elem['Баннер'] = driver.find_element(By.CLASS_NAME, 'sidebar-event__head').find_element(By.TAG_NAME,
                                                                                            'img').get_attribute('src')
        except:
            elem['Баннер'] = ''
        try:
            elem['Описание события'] = driver.find_element(By.CLASS_NAME,
                                                           'sidebar-box__event-title').text.strip().replace('\n',
                                                                                                               ' ')
        except:
            elem['Описание события'] = ''
        for i in driver.find_elements(By.CLASS_NAME, 'sidebar-box'):
            if 'Организатор' in i.text:
                elem['Организатор'] = i.find_element(By.CLASS_NAME, 'sidebar-box__text').text.strip()
        elem['Тип интегратора'] = 'ticketpro'
        out.append(elem)
    df = pd.DataFrame(out)
    return df


def parse_afisha():
    out = []
    driver.get('https://24afisha.by/')
    time.sleep(1)
    categories = []
    navigation_bar = driver.find_element(By.CLASS_NAME, 'sub-nav__fixed-yellow__list')
    expand = navigation_bar.find_element(By.CLASS_NAME, 'dropdown-toggle')
    expand.click()
    time.sleep(1)
    for item in navigation_bar.find_elements(By.TAG_NAME, 'li'):
        categories.append(item.find_element(By.TAG_NAME, 'a').get_attribute('href'))
    categories = [url for url in categories if url != 'https://24afisha.by/ru/minsk/events/kino']
    afisha_links = []
    for i in categories:
        driver.get(i)
        time.sleep(0.5)
        try:
            for event in driver.find_element(By.CLASS_NAME, 'events__list').find_elements(By.CLASS_NAME, 'events-afisha-li'):
                afisha_links.append(event.find_element(By.TAG_NAME, 'a').get_attribute('href'))
        except:
            pass
    df = pd.DataFrame(afisha_links, columns=['links']).drop_duplicates().reset_index(drop=True)
    for i in range(0, len(df)):
        driver.get(df.loc[i, 'links'])
        time.sleep(0.5)
        elem = {}
        elem['Оригинальное название'] = ''
        try:
            elem['Название события'] = driver.find_element(By.CLASS_NAME, 'event-page__header').text.strip()
        except:
            continue
        table = driver.find_element(By.CLASS_NAME, 'tickets__table')
        time_event = []
        for one in table.find_elements(By.TAG_NAME, 'tr'):
            try:
                date_block = one.find_element(By.CLASS_NAME, 'pad-right-td')
                date = re.sub(r'\n.*?\n', ' ', date_block.text.strip())
                try:
                    date = date + ' ' + one.find_element(By.CLASS_NAME, 'button__ticket').find_element(By.TAG_NAME, 'span').text.strip()
                except:
                    pass
                time_event.append(date)
            except:
                pass
        elem['ID События'] = int(df.loc[i, 'links'].split('/')[-1])
        elem['Дата проведения'] = convert_afisha(time_event)
        try:
            elem['Площадка/место проведения'] = table.find_elements(By.CLASS_NAME, 'link-blue')[-1].text
        except:
            elem['Площадка/место проведения'] = ''
        try:
            elem['place ID afisha24'] = int(table.find_elements(By.CLASS_NAME, 'link-blue')[-1].get_attribute('href').split('/')[-1])
        except:
            elem['place ID afisha24'] = ''
        rubricks = driver.find_element(By.CLASS_NAME, 'breadcrumbs')
        elements = rubricks.find_elements(By.TAG_NAME, 'a')[1:]
        rubs_id = [x.get_attribute('href') for x in elements]
        rubs_name = ", ".join(sorted({x.text.strip() for x in elements if x.text.strip()}))
        elem['place ID тикетпро'] = ''
        elem['place ID bezkassira'] = ''
        elem['Рубрика - название'] = rubs_name
        elem['ID рубрики afisha24'] = rubs_id
        elem['ID рубрики тикетпро'] = ''
        elem['ID рубрики bezkassira'] = ''
        try:
            elem['Баннер'] = driver.find_element(By.CLASS_NAME, 'event-image').find_element(By.TAG_NAME, 'img').get_attribute('src')
        except:
            elem['Баннер'] = ''
        try:
            ActionChains(driver).move_to_element(
                driver.find_element(By.CLASS_NAME, 'event-page_desc__more')).perform()
            time.sleep(0.5)
            driver.find_element(By.CLASS_NAME, 'event-page_desc__more').click()
            elem['Описание события'] = driver.find_element(By.CLASS_NAME, 'event-page_desc__about-body').text.strip().replace('\n', ' ')
        except:
            try:
                elem['Описание события'] = driver.find_element(By.CLASS_NAME,
                                                               'event-page_desc__about-body').text.strip().replace('\n',
                                                                                                                   ' ')
            except:
                elem['Описание события'] = ''
        try:
            elem['Организатор'] = driver.find_element(By.CLASS_NAME, 'create-company').find_element(By.TAG_NAME, 'a').get_attribute('href')
        except:
            elem['Организатор'] = ''
        elem['Тип интегратора'] = 'afisha24'
        out.append(elem)
    df = pd.DataFrame(out)
    return df


def parse_bezkassira():
    out = []
    driver.get('https://bezkassira.by/')
    navbar = driver.find_element(By.CLASS_NAME, 'custom')
    categories = []
    for i in navbar.find_elements(By.TAG_NAME, 'li'):
        categories.append(i.find_element(By.TAG_NAME, 'a').get_attribute('href'))
    links = []
    for cat in categories:
        driver.get(cat)
        time.sleep(0.5)
        for j in driver.find_elements(By.CLASS_NAME, 'thumbnail'):
            links.append(j.find_element(By.TAG_NAME, 'a').get_attribute('href'))
    links = list(set(links))
    for link in links:
        driver.get(link)
        elem = {}
        elem['Оригинальное название'] = ''
        elem['Название события'] = driver.find_element(By.CLASS_NAME, 'activity-name').text.strip()
        elem['ID События'] = int(link.split('-')[-1].replace('/', ''))
        try:
            time_event = driver.find_element(By.CLASS_NAME, 'add-calendar')
            try:
                enter = time_event.find_element(By.CLASS_NAME, 'time-enter').text
                time_event = time_event.text.replace(enter, '').replace('\n', ' ').strip()
            except:
                time_event = time_event.text.replace('\n', '').strip()
            time_event = re.sub(r'(\d)(—)', r'\1 —', time_event)
            elem['Дата проведения'] = convert_bezkassira(time_event)
        except:
            elem['Дата проведения'] = ''
        try:
            elem['Площадка/место проведения'] = driver.find_elements(By.CLASS_NAME, 'sign-name').text.strip()
        except:
            elem['Площадка/место проведения'] = ''
        elem['place ID afisha24'] = ''
        elem['ID тикетпроplace'] = ''
        elem['place ID bezkassira'] = ''
        rub_tab = driver.find_element(By.CLASS_NAME, 'breadcrumbs')
        elements = rub_tab.find_elements(By.TAG_NAME, 'a')[1:]
        rubs_name = ", ".join(sorted({x.text.strip() for x in elements if x.text.strip()}))
        rubs_id = [rub.get_attribute('href')[:-1].split('/')[-1] for rub in elements]
        elem['Рубрика - название '] = rubs_name
        elem['ID рубрики afisha24'] = ''
        elem['ID  рубрики тикетпро'] = ''
        elem['ID  рубрики bezkassira'] = rubs_id
        try:
            banner = driver.find_element(By.CLASS_NAME, 'img-content')
            elem['Баннер'] = banner.find_element(By.TAG_NAME, 'img').get_attribute('src')
        except:
            elem['Баннер'] = ''
        try:
            discription = driver.find_element(By.CLASS_NAME, 'description')
            elem['Описание события'] = discription.find_element(By.TAG_NAME, 'p').text.strip().replace('\n', ' ')
        except:
            elem['Описание события'] = ''
        try:
            organise = driver.find_elements(By.CLASS_NAME, 'organise-block')[-1]
            elem['Организатор'] = organise.find_element(By.CLASS_NAME, 'organise-event__logo').find_element(By.TAG_NAME, 'a').get_attribute('href')
        except:
            elem['Организатор'] = ''
        elem['Тип интегратора'] = 'bezkassira'
        out.append(elem)
    df = pd.DataFrame(out)
    return df


ticket_map = {}
afisha_map = {}
bezkassira = {}

chrome_options = Options()
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--start-maximized")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)


afisha = parse_afisha()
kass = parse_bezkassira()
ticket = parse_ticket()


df_combined = pd.concat([ticket, kass, afisha], ignore_index=True)
df_combined['Оригинальное название'] = df_combined['Название события']
df_combined['Название события'] = df_combined['Название события'].apply(clean_string)
driver.close()
result = final_collapse(df_combined)
result['Дата проведения'] = result['Дата проведения'].astype(str).str.replace(r"[\[\]']", "", regex=True)
