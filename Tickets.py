import time
import re
import pandas as pd
from fuzzywuzzy import fuzz
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By


def clean_string(text):
    if pd.isna(text) or not isinstance(text, str):
        return ""
    text = text.lower().replace('ё', 'е')
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def convert_date(data):
    m_map = {
        'янв': '01', 'фев': '02', 'мар': '03', 'апр': '04', 'мая': '05', 'май': '05',
        'июн': '06', 'июл': '07', 'авг': '08', 'сен': '09', 'окт': '10', 'ноя': '11', 'дек': '12'
    }

    current_year = datetime.now().year
    clean_str = re.sub(r"[\[\]'\" ]", " ", str(data)).lower().strip()
    raw_items = [x.strip() for x in clean_str.split(',') if x.strip()]

    result = set()
    for entry in raw_items:
        entry = entry.replace('.', '')
        found = False
        for root, num in m_map.items():
            if root in entry:
                processed = re.sub(r'[а-яё]+', f' {num} ', entry)

                if not re.search(r'\b\d{4}\b', processed):
                    processed = f"{processed} {current_year}"

                try:
                    dt = pd.to_datetime(processed, dayfirst=True, errors='coerce')
                    if pd.notnull(dt):
                        result.add(dt.strftime('%d.%m.%Y'))
                        found = True
                        break
                except:
                    continue

        if not found and entry:
            result.add(entry)

    return list(result)


def is_empty(val):
    if pd.isna(val) or val is None: return True
    if isinstance(val, (list, dict, str)) and len(val) == 0: return True
    if str(val).strip().lower() in ['none', '[]', '']: return True
    return False


def merge_records(group):
    priority_map = {'ticketpro': 1, 'afisha24': 2, 'bezkassira': 3}
    group['priority'] = group['Тип интегратора'].map(priority_map).fillna(99)

    group = group.sort_values('priority')

    base = group.iloc[0].to_dict()

    for _, row in group.iloc[1:].iterrows():
        n1, n2 = str(base['Название события']), str(row['Название события'])
        if fuzz.token_sort_ratio(n1, n2) < 70:
            if len(n2) > len(n1):
                base['Название события'] = n2

        ids = set(str(base['ID События']).split(', ') + str(row['ID События']).split(', '))
        base['ID События'] = ", ".join(sorted(filter(lambda x: not is_empty(x), ids)))

        for col in ['Дата проведения', 'Время проведения']:
            v1 = base[col] if isinstance(base[col], list) else []
            v2 = row[col] if isinstance(row[col], list) else []
            combined = set(v1 + v2)
            clean_values = sorted([str(x) for x in combined if not is_empty(x)])
            base[col] = ", ".join(clean_values)

        for col in ['Площадка/место проведения', 'Описание события', 'Организатор']:
            if is_empty(base[col]) and not is_empty(row[col]):
                base[col] = row[col]

        c1 = set(str(base['Рубрика - название']).split(', ')) if not is_empty(base['Рубрика - название']) else set()
        c2 = set(str(row['Рубрика - название']).split(', ')) if not is_empty(row['Рубрика - название']) else set()
        base['Рубрика - название'] = ", ".join(filter(lambda x: not is_empty(x), c1.union(c2)))

        if 'afisha24' in str(row['Тип интегратора']).lower() and not is_empty(row['Баннер']):
            base['Баннер'] = row['Баннер']

        for col in base.keys():
            if ('ID рубрики' in col or 'place ID' in col) and is_empty(base[col]):
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

    return pd.DataFrame(final_rows).drop(columns=['Название события', 'priority'], errors='ignore')


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
        elem['Название события'] = driver.find_element(By.CLASS_NAME, 'title').text.replace('\n', ' ').strip()
        elem['ID События'] = None
        try:
            elem['Дата проведения'] = driver.find_element(By.CLASS_NAME, 'sidebar-box__event-date').text.split(',')[0].strip()
            elem['Время проведения'] = driver.find_element(By.CLASS_NAME, 'sidebar-box__event-date').text.split(',')[1].strip()
        except:
            elem['Дата проведения'] = None
            elem['Время проведения'] = None
        try:
            elem['Площадка/место проведения'] = driver.find_element(By.CLASS_NAME, 'sidebar-box__event-venue').text.replace('\n', ' ').strip()
        except:
            elem['Площадка/место проведения'] = None
        elem['place ID afisha24'] = None
        elem['place ID тикетпро'] = driver.find_element(By.CLASS_NAME, 'content__event-place').find_element(By.TAG_NAME, 'a').get_attribute('href')
        elem['place ID bezkassira'] = None
        rubricks = driver.find_element(By.CLASS_NAME, 'breadcrumbs')
        elem['Рубрика - название'] = [rub.text.strip() for rub in rubricks.find_elements(By.TAG_NAME, 'a')]
        elem['ID рубрики afisha24'] = None
        elem['ID рубрики тикетпро'] = [rub.get_attribute('href')[:-1].split('/')[-1] for rub in rubricks.find_elements(By.TAG_NAME, 'a')]
        elem['ID рубрики bezkassira'] = None
        try:
            elem['Баннер'] = driver.find_element(By.CLASS_NAME, 'sidebar-event__head').find_element(By.TAG_NAME,
                                                                                            'img').get_attribute('src')
        except:
            elem['Баннер'] = None
        try:
            elem['Описание события'] = driver.find_element(By.CLASS_NAME,
                                                           'sidebar-box__event-title').text.strip().replace('\n',
                                                                                                               ' ')
        except:
            elem['Описание события'] = None
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
        elem['Название события'] = driver.find_element(By.CLASS_NAME, 'event-page__header').text.strip()
        table = driver.find_element(By.CLASS_NAME, 'tickets__table')
        time_event = []
        times = table.find_elements(By.CLASS_NAME, 'pad-right-td')
        for one in times:
            time_event.append(re.sub(r'\n.*?\n', ' ', one.text.strip()))
        elem['ID События'] = df.loc[i, 'links'].split('/')[-1]
        elem['Дата проведения'] = time_event
        elem['Время проведения'] = None
        try:
            elem['Площадка/место проведения'] = table.find_elements(By.CLASS_NAME, 'link-blue')[-1].text
        except:
            elem['Площадка/место проведения'] = None
        try:
            elem['place ID afisha24'] = table.find_elements(By.CLASS_NAME, 'link-blue')[-1].get_attribute('href').split('/')[-1]
        except:
            elem['place ID afisha24'] = None
        rubricks = driver.find_element(By.CLASS_NAME, 'breadcrumbs')
        rubs_id = [x.get_attribute('href') for x in rubricks.find_elements(By.TAG_NAME, 'a')]
        rubs_name = [x.text.strip() for x in rubricks.find_elements(By.TAG_NAME, 'a')]
        elem['place ID тикетпро'] = None
        elem['place ID bezkassira'] = None
        elem['Рубрика - название'] = rubs_name
        elem['ID рубрики afisha24'] = rubs_id
        elem['ID рубрики тикетпро'] = None
        elem['ID рубрики bezkassira'] = None
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
                elem['Описание события'] = None
        try:
            elem['Организатор'] = driver.find_element(By.CLASS_NAME, 'create-company').find_element(By.TAG_NAME, 'a').get_attribute('href')
        except:
            elem['Организатор'] = None
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
        elem['Название события'] = driver.find_element(By.CLASS_NAME, 'activity-name').text.strip()
        elem['ID События'] = link.split('-')[-1].replace('/', '')
        try:
            time_event = driver.find_element(By.CLASS_NAME, 'add-calendar')
            try:
                time_ev = time_event.find_element(By.TAG_NAME, 'small').text
                elem['Дата проведения'] = time_event.text.replace(time_ev, '').strip().replace('\n', '')
                elem['Время проведения'] = time_ev
            except:
                elem['Дата проведения'] = time_event.text.strip().replace('\n', '')
                elem['Время проведения'] = None
        except:
            elem['Дата проведения'] = None
            elem['Время проведения'] = None
        try:
            elem['Площадка/место проведения'] = driver.find_elements(By.CLASS_NAME, 'sign-name').text.strip()
        except:
            elem['Площадка/место проведения'] = None
        elem['place ID afisha24'] = None
        elem['ID тикетпроplace'] = None
        elem['place ID bezkassira'] = None
        rub_tab = driver.find_element(By.CLASS_NAME, 'breadcrumbs')
        rubs_name = [rub.text for rub in rub_tab.find_elements(By.TAG_NAME, 'a')]
        rubs_id = [rub.get_attribute('href')[:-1].split('/')[-1] for rub in rub_tab.find_elements(By.TAG_NAME, 'a')]
        elem['Рубрика - название '] = rubs_name
        elem['ID рубрики afisha24'] = None
        elem['ID  рубрики тикетпро'] = None
        elem['ID  рубрики bezkassira'] = rubs_id
        try:
            banner = driver.find_element(By.CLASS_NAME, 'img-content')
            elem['Баннер'] = banner.find_element(By.TAG_NAME, 'img').get_attribute('src')
        except:
            elem['Баннер'] = None
        try:
            discription = driver.find_element(By.CLASS_NAME, 'description')
            elem['Описание события'] = discription.find_element(By.TAG_NAME, 'p').text.strip().replace('\n', ' ')
        except:
            elem['Описание события'] = None
        try:
            organise = driver.find_elements(By.CLASS_NAME, 'organise-block')[-1]
            elem['Организатор'] = organise.find_element(By.CLASS_NAME, 'organise-event__logo').find_element(By.TAG_NAME, 'a').get_attribute('href')
        except:
            elem['Организатор'] = None
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
df_combined['Название события'] = df_combined['Название события'].apply(clean_string)
df_combined['Дата проведения'] = df_combined['Дата проведения'].apply(convert_date)

driver.close()
result = final_collapse(df_combined)

