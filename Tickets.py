import time
import re
import pandas as pd
import json
from datetime import datetime
from urllib.parse import urlsplit
from fuzzywuzzy import fuzz
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains


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


def convert_bezkassira(time_event):
    months_map = {
        'янв': '01', 'фев': '02', 'мар': '03', 'апр': '04', 'май': '05', 'мая': '05',
        'июн': '06', 'июл': '07', 'авг': '08', 'сен': '09', 'окт': '10', 'ноя': '11', 'дек': '12'
    }

    cleaned = ' '.join(time_event.split())

    cleaned = re.sub(r'(\d{1,2})\s*[-–—]\s*(\d{1,2})\.(\d{2})\.(\d{4})',
                     lambda
                         m: f"{m.group(1).zfill(2)}.{m.group(3)}.{m.group(4)} — {m.group(2).zfill(2)}.{m.group(3)}.{m.group(4)}",
                     cleaned)

    cleaned = re.sub(r'(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+([а-я]+)\s+(\d{4})',
                     lambda
                         m: f"{m.group(1).zfill(2)}.{months_map[m.group(3).lower()]}.{m.group(4)} — {m.group(2).zfill(2)}.{months_map[m.group(3).lower()]}.{m.group(4)}",
                     cleaned)

    cleaned = re.sub(r'(\d{1,2})\s+([а-я]+)\s+(\d{4})',
                     lambda m: f"{m.group(1).zfill(2)}.{months_map[m.group(2).lower()]}.{m.group(3)}",
                     cleaned)

    cleaned = re.sub(r'\s*,\s*', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\b(\d):(\d{2})\b', r'0\1:\2', cleaned)

    return [cleaned]


def convert_afisha(date_list, year="2026"):
    if not date_list or not isinstance(date_list, list):
        return ""

    months_map = {
        'янв': '01', 'фев': '02', 'мар': '03', 'апр': '04',
        'мая': '05', 'май': '05', 'июн': '06', 'июл': '07', 'авг': '08',
        'сен': '09', 'окт': '10', 'ноя': '11', 'дек': '12'
    }

    pattern = r'(\d{1,2})\s+([а-яА-Я]+)\.?(?:\s+(\d{2}:\d{2}))?'

    result = []
    for date_str in date_list:
        date_str = date_str.replace('Продано', '').strip()

        date_str = re.sub(r'\b(\d):(\d{2})\b', r'0\1:\2', date_str)

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

        v1 = base.get('Дата проведения') or []
        if not isinstance(v1, list):
            v1 = [v1] if v1 else []
        v2 = row.get('Дата проведения') or []
        if not isinstance(v2, list):
            v2 = [v2] if v2 else []
        combined = sorted(set(str(d).strip() for d in (v1 + v2) if d and str(d).strip()))
        base['Дата проведения'] = ", ".join(combined)
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
    wait = WebDriverWait(driver, 15)
    menu = (By.CSS_SELECTOR, 'main nav:not([aria-label]) > a[href^="/ru/"]')
    cards = (By.CSS_SELECTOR, 'main a[class~="group/eventCard"][href^="/ru/event/"]')
    more = (By.XPATH, "//main//button[normalize-space(.)='Показать больше']")
    heading = (By.CSS_SELECTOR, "main h1")
    months = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()

    def text(selector, by=By.CSS_SELECTOR):
        return " ".join(" ".join(e.text.split()) for e in driver.find_elements(by, selector)).strip()

    def format_date(value):
        date = datetime.fromisoformat(value)
        return f"{date.day} {months[date.month - 1]} {date:%Y %H:%M}"

    driver.get("https://ticketpro.by/")
    categories = [
        (a.get_attribute("textContent").strip(), a.get_attribute("href"))
        for a in wait.until(EC.presence_of_all_elements_located(menu))
        if urlsplit(a.get_attribute("href")).path.rstrip("/") != "/ru/bilety-v-kino"
    ]
    links = {}
    for name, url in categories:
        slug = urlsplit(url).path.rstrip("/").split("/")[-1]
        driver.get(url)
        wait.until(EC.visibility_of_element_located(heading))
        while driver.find_elements(*more):
            count = len(driver.find_elements(*cards))
            button = wait.until(EC.element_to_be_clickable(more))
            driver.execute_script("arguments[0].click();", button)
            wait.until(lambda d: len(d.find_elements(*cards)) > count)
        for card in driver.find_elements(*cards):
            links.setdefault(card.get_attribute("href"), {})[name] = slug

    out = []
    for url, rubrics in links.items():
        driver.get(url)
        title = " ".join(wait.until(EC.visibility_of_element_located(heading)).text.split())
        sessions = []
        for script in driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]'):
            data = json.loads(script.get_attribute("textContent"))
            sessions.extend(item for item in data.get("@graph", [data]) if item.get("@type") == "Event")

        dates = list(dict.fromkeys(format_date(s["startDate"]) for s in sessions if s.get("startDate")))
        header_dates = driver.find_elements(By.CSS_SELECTOR, "main time[datetime]:not(a time)")
        if not dates:
            dates = [format_date(e.get_attribute("datetime")) for e in header_dates]
        if len(header_dates) == 2 and len(sessions) <= 1:
            dates = [" – ".join(format_date(e.get_attribute("datetime")) for e in header_dates)]
        venues = [s["location"] for s in sessions if s.get("location")]
        venue_names = dict.fromkeys(place["name"] for place in venues if place.get("name"))
        venue_urls = {place["url"] for place in venues if place.get("url")}
        banner = driver.find_elements(By.CSS_SELECTOR, 'meta[property="og:image"]')
        organizer = text(
            "//main//*[@role='region'][@aria-labelledby = "
            "//main//button[normalize-space(.)='Организатор']/@id]//p[1]",
            By.XPATH,
        )

        out.append({
            "Оригинальное название": "",
            "Название события": title,
            "ID События": "",
            "Дата проведения": dates or "",
            "Площадка/место проведения": ", ".join(venue_names),
            "place ID afisha24": "",
            "place ID тикетпро": next(iter(venue_urls)) if len(venue_urls) == 1 else "",
            "place ID bezkassira": "",
            "Рубрика - название": ", ".join(sorted(rubrics)),
            "ID рубрики afisha24": "",
            "ID рубрики тикетпро": [rubrics[name] for name in sorted(rubrics)],
            "ID рубрики bezkassira": "",
            "Баннер": banner[0].get_attribute("content") if banner else "",
            "Описание события": text("main .html-content"),
            "Организатор": organizer,
            "Тип интегратора": "ticketpro",
        })

    return pd.DataFrame(out)



def parse_afisha():
    out = []
    driver.get('https://24afisha.by/ru/minsk')
    time.sleep(2)

    categories = []

    navigation_bar = driver.find_element(
        By.CLASS_NAME, 'sub-nav__fixed-yellow__list'
    )

    try:
        expand = navigation_bar.find_element(
            By.CLASS_NAME, 'dropdown-toggle'
        )
        expand.click()
        time.sleep(0.5)
    except:
        pass

    for item in navigation_bar.find_elements(
        By.CSS_SELECTOR, 'li.sub-nav__fixed-yellow__item'
    ):
        for a in item.find_elements(
            By.CSS_SELECTOR, 'a[href*="/events/"]'
        ):
            href = a.get_attribute('href')
            if href:
                categories.append(href)

    categories = list(dict.fromkeys(categories))

    categories = [
        url for url in categories
        if '/events/kino' not in url
    ]

    afisha_links = []

    for i in categories:
        driver.get(i)
        time.sleep(1)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, 'events__list')
                )
            )

            events = driver.find_element(
                By.CLASS_NAME, 'events__list'
            ).find_elements(
                By.CLASS_NAME, 'events-afisha-li'
            )

            for event in events:
                elem = {}

                try:
                    elem['link'] = event.find_element(
                        By.CSS_SELECTOR, 'a[href*="/event/"]'
                    ).get_attribute('href')
                except:
                    continue

                try:
                    elem['picture'] = event.find_element(
                        By.TAG_NAME, 'img'
                    ).get_attribute('src')
                except:
                    elem['picture'] = ''

                afisha_links.append(elem)

        except:
            pass

    df = pd.DataFrame(
        afisha_links,
        columns=['link', 'picture']
    ).drop_duplicates().reset_index(drop=True)

    for i in range(0, len(df)):
        driver.get(df.loc[i, 'link'])
        time.sleep(0.5)

        elem = {}
        elem['Оригинальное название'] = ''

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, 'event-page__header')
                )
            )

            elem['Название события'] = driver.find_element(
                By.CLASS_NAME, 'event-page__header'
            ).text.strip()

        except:
            continue

        try:
            table = driver.find_element(
                By.CSS_SELECTOR, 'table.tickets__table'
            )
        except:
            table = None

        time_event = []

        if table is not None:
            for one in table.find_elements(By.TAG_NAME, 'tr'):
                try:
                    date_block = one.find_element(
                        By.CLASS_NAME, 'pad-right-td'
                    )

                    date = (
                        date_block.find_element(
                            By.CLASS_NAME, 'date-num'
                        ).text.strip()
                        + ' ' +
                        date_block.find_element(
                            By.CLASS_NAME, 'table-about__text'
                        ).text.strip()
                    )

                    try:
                        time_value = one.find_element(
                            By.CSS_SELECTOR,
                            '.button__ticket time'
                        ).get_attribute('datetime')

                        if not time_value:
                            time_value = one.find_element(
                                By.CSS_SELECTOR,
                                '.button__ticket span'
                            ).text.strip()

                        if time_value:
                            date += ' ' + time_value

                    except:
                        pass

                    time_event.append(date)

                except:
                    pass

        try:
            event_id = df.loc[i, 'link'].rstrip('/').split('/')[-1]
            elem['ID События'] = int(event_id)
        except:
            elem['ID События'] = ''

        elem['Дата проведения'] = convert_afisha(time_event)

        try:
            place = table.find_elements(
                By.CSS_SELECTOR,
                'a.link-blue[href*="/object/"]'
            )[-1]

            elem['Площадка/место проведения'] = place.text.strip()

        except:
            elem['Площадка/место проведения'] = ''

        try:
            place_id = place.get_attribute('href').rstrip('/').split('/')[-1]
            elem['place ID afisha24'] = int(place_id)
        except:
            elem['place ID afisha24'] = ''

        try:
            rubricks = driver.find_element(
                By.CSS_SELECTOR, 'div.breadcrumbs'
            )

            elements = rubricks.find_elements(
                By.CSS_SELECTOR, 'a.breadcrumbs__item'
            )[1:]

            rubs_id = [
                x.get_attribute('href')
                for x in elements
            ]

            rubs_name = ", ".join(
                sorted({
                    x.text.strip()
                    for x in elements
                    if x.text.strip()
                })
            )

        except:
            rubs_id = []
            rubs_name = ''

        elem['place ID тикетпро'] = ''
        elem['place ID bezkassira'] = ''

        elem['Рубрика - название'] = rubs_name
        elem['ID рубрики afisha24'] = rubs_id

        elem['ID рубрики тикетпро'] = ''
        elem['ID рубрики bezkassira'] = ''

        try:
            elem['Баннер'] = df.loc[i, 'picture']
        except:
            elem['Баннер'] = ''

        try:
            more = driver.find_element(
                By.CLASS_NAME, 'event-page_desc__more'
            )
            ActionChains(driver).move_to_element(
                more
            ).perform()

            time.sleep(0.3)
            more.click()

        except:
            pass

        try:
            elem['Описание события'] = driver.find_element(
                By.CLASS_NAME,
                'event-page_desc__about-body'
            ).text.strip().replace('\n', ' ')

        except:
            elem['Описание события'] = ''

        try:
            elem['Организатор'] = driver.find_element(
                By.CSS_SELECTOR,
                '.table-about__header a[href*="/organizer/"]'
            ).get_attribute('href')

        except:
            try:
                elem['Организатор'] = driver.find_element(
                    By.CSS_SELECTOR,
                    'a.link-blue[href*="/organizer/"]'
                ).get_attribute('href')
            except:
                elem['Организатор'] = ''

        elem['Тип интегратора'] = 'afisha24'

        out.append(elem)

    df = pd.DataFrame(
        out,
        columns=[
            'Оригинальное название',
            'Название события',
            'ID События',
            'Дата проведения',
            'Площадка/место проведения',
            'place ID afisha24',
            'place ID тикетпро',
            'place ID bezkassira',
            'Рубрика - название',
            'ID рубрики afisha24',
            'ID рубрики тикетпро',
            'ID рубрики bezkassira',
            'Баннер',
            'Описание события',
            'Организатор',
            'Тип интегратора'
        ]
    )

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
        if link.startswith('https://bezkassira'):
            driver.get(link)
            elem = {}
            elem['Оригинальное название'] = ''
            try:
                elem['Название события'] = driver.find_element(By.CLASS_NAME, 'activity-name').text.strip()
            except:
                elem['Название события'] = ''
            try:
                elem['ID События'] = int(link.split('-')[-1].replace('/', ''))
            except:
                elem['ID События'] = ''
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

afisha.to_csv('afisha_17.11.csv')

# df_combined = pd.concat([ticket, kass, afisha], ignore_index=True)
# df_combined['Оригинальное название'] = df_combined['Название события']
# df_combined['Название события'] = df_combined['Название события'].apply(clean_string)
# driver.close()
# result = final_collapse(df_combined)
# result['Дата проведения'] = result['Дата проведения'].astype(str).str.replace(r"[\[\]']", "", regex=True)
