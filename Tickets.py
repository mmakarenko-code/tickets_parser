import time
import re
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By




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
            elem['Время проведеняи'] = driver.find_element(By.CLASS_NAME, 'sidebar-box__event-date').text.split(',')[1].strip()
        except:
            elem['Дата проведения'] = None
            elem['Время проведеняи'] = None
        try:
            elem['Площадка/место проведения'] = driver.find_element(By.CLASS_NAME, 'sidebar-box__event-venue').text.replace('\n', ' ').strip()
        except:
            elem['Площадка/место проведения'] = None
        elem['place ID афиша 24'] = None
        elem['place ID тикетпро'] = driver.find_element(By.CLASS_NAME, 'content__event-place').find_element(By.TAG_NAME, 'a').get_attribute('href')
        elem['place ID безкассира'] = None
        rubricks = driver.find_element(By.CLASS_NAME, 'breadcrumbs')
        elem['Рубрика - название'] = [rub.text.strip() for rub in rubricks.find_elements(By.TAG_NAME, 'a')]
        elem['ID рубрики афиша 24'] = None
        elem['ID рубрики тикетпро'] = [rub.get_attribute('href')[:-1].split('/')[-1] for rub in rubricks.find_elements(By.TAG_NAME, 'a')]
        elem['ID рубрики безкассира'] = None
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
        print(elem)
        out.append(elem)
    df = pd.DataFrame(out)
    df.to_csv('Tickets_test.csv')


def parse_afisha():
    out = []
    driver.get('https://24afisha.by/')
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
        elem['Время проведеняи'] = None
        try:
            elem['Площадка/место проведения'] = table.find_elements(By.CLASS_NAME, 'link-blue')[-1].text
        except:
            elem['Площадка/место проведения'] = None
        try:
            elem['place ID афиша 24'] = table.find_elements(By.CLASS_NAME, 'link-blue')[-1].get_attribute('href').split('/')[-1]
        except:
            elem['place ID афиша 24'] = None
        rubs_id = []
        rubs_name = []
        rubricks = driver.find_elements(By.CLASS_NAME, 'sub-nav__fixed-yellow__item')
        for i in range(0, len(rubricks)-1):
            rubs_id.append(rubricks[i].find_element(By.TAG_NAME, 'a').get_attribute('href').split('/')[-1])
            rubs_name.append(rubricks[i].find_element(By.TAG_NAME, 'a').text)
        try:
            dropdown = driver.find_element(By.CLASS_NAME, 'chevron')
            dropdown.click()
            time.sleep(0.5)
            for j in driver.find_elements(By.CLASS_NAME, 'dropdown-item'):
                rubs_id.append(j.find_element(By.TAG_NAME, 'a').get_attribute('href').split('/')[-1])
                rubs_name.append(j.find_element(By.TAG_NAME, 'a').text)
        except:
            pass
        elem['place ID тикетпро'] = None
        elem['place ID безкассира'] = None
        elem['Рубрика - название'] = rubs_name
        elem['ID рубрики афиша 24'] = rubs_id
        elem['ID рубрики тикетпро'] = None
        elem['ID рубрики безкассира'] = None
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
        out.append(elem)
    df = pd.DataFrame(out)
    df.to_csv('Afisha_test.csv')


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
                elem['Время проведеняи'] = time_ev
            except:
                elem['Дата проведения'] = time_event.text.strip().replace('\n', '')
                elem['Время проведеняи'] = None
        except:
            elem['Дата проведения'] = None
            elem['Время проведеняи'] = None
        try:
            elem['Площадка/место проведения'] = driver.find_elements(By.CLASS_NAME, 'sign-name').text.strip()
        except:
            elem['Площадка/место проведения'] = None
        elem['place ID афиша 24'] = None
        elem['ID тикетпроplace'] = None
        elem['place ID безкассира'] = None
        rub_tab = driver.find_element(By.CLASS_NAME, 'breadcrumbs')
        rubs_name = [rub.text for rub in rub_tab.find_elements(By.TAG_NAME, 'a')]
        rubs_id = [rub.get_attribute('href')[:-1].split('/')[-1] for rub in rub_tab.find_elements(By.TAG_NAME, 'a')]
        elem['Рубрика - название '] = rubs_name
        elem['ID рубрики афиша 24'] = None
        elem['ID  рубрики тикетпро'] = None
        elem['ID  рубрики безкассира'] = rubs_id
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
        out.append(elem)
    return out


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

