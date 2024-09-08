import datetime as dt
import json
import importlib.resources as pkg_resources

from http.cookiejar import CookieJar
from typing import Tuple, Dict, Optional, Union
from urllib.parse import urljoin

import pip._vendor.requests as requests
from pip._vendor.requests.cookies import RequestsCookieJar

from collections import defaultdict

BASE_URL = 'https://dnevnik2.petersburgedu.ru/'

REFERRERS = {
    '/api/user/auth/login': '/login',
    '/api/journal/person/related-child-list': '/students/my',
    '/api/journal/group/related-group-list': '/estimate',
    '/api/group/group/get-list-period': '/estimate',
    '/api/journal/subject/list-studied': '/estimate',
}


def str_to_date(date: str) -> dt.date:
    return dt.datetime.strptime(date, '%d.%m.%Y')


def make_session() -> requests.Session:
    with pkg_resources.path(__name__, 'headers.json') as path:
        headers_path = path
    if not headers_path.exists():
        raise ValueError(f'headers file {headers_path} is missing')
    with headers_path.open('r', encoding='utf-8') as file:
        headers = json.load(file)
    session = requests.Session()
    session.headers.update(headers)
    return session


def date_to_str(date: dt.date) -> str:
    return f'{date.day}.{date.month}.{date.year}'


class Dnevnik2:
    def __init__(self, cookie_jar: CookieJar, base_url: str = BASE_URL):
        self.base_url = base_url
        self.session = make_session()
        self.session.cookies.update(cookie_jar)
        self.educations = self.fetch_children_list()['data']['items'][0]['educations'][0]
        self.jurisdiction, self.institution = self.educations['jurisdiction_id'], self.educations['institution_id']
        self.group = self.fetch_group_list(self.jurisdiction, self.institution)['data']['items'][0]['id']
        self.period_list = self.fetch_period_list(self.group)['data']['items']
        self.subjects_list = self.fetch_subjects()['data']['items']

    @staticmethod
    def _make_url_and_referer(path: str, base_url: str) -> Tuple[str, Dict[str, str]]:
        headers = {}
        url = urljoin(base_url, path)
        if path in REFERRERS:
            headers['Referer'] = urljoin(base_url, REFERRERS[path])
        return url, headers

    @classmethod
    def make_from_login_by_email(cls, email: str, password: str, base_url: str = BASE_URL) -> 'Dnevnik2':
        auth_data = {"type": "email", "login": email, "activation_code": None, "password": password, "_isEmpty": False}
        session = make_session()
        url, headers = cls._make_url_and_referer('/api/user/auth/login', base_url)
        with session.post(url, json=auth_data, headers=headers) as res:
            if 400 <= res.status_code < 500:
                raise ValueError('Some client error. Most probably login or password is wrong.')
            res.raise_for_status()
        # dnevnik: 'Dnevnik2' = cls(session.cookies, base_url=base_url)
        return cls(session.cookies, base_url)

    @classmethod
    def make_from_cookies_token(cls, token: str, base_url: str = BASE_URL) -> 'Dnevnik2':
        with pkg_resources.path(__name__, 'cookie.json') as path:
            cookie_path = path

        with open(cookie_path, 'r') as cookie_file:
            cookie = json.load(cookie_file)[0]
            cookie['value'] = token

        cookie_jar = RequestsCookieJar()
        cookie_jar.set(**cookie)
        return cls(cookie_jar, base_url)

    # def save_cookies(self, path: Path):
    #     cookies = []
    #     cookie: Cookie
    #     for cookie in self.session.cookies:
    #         cookies.append({
    #             'name': cookie.name,
    #             'value': cookie.value,
    #             'domain': cookie.domain,
    #             'path': cookie.path,
    #             'expires': cookie.expires,
    #         })
    #     with path.open('w', encoding='utf-8') as f1:
    #         json.dump(cookies, f1, indent=2, ensure_ascii=True)

    def fetch_children_list(self) -> dict:
        """Fetch the list of children for whom marks are tracked.
        """
        path = '/api/journal/person/related-child-list'
        return self._fetch_json_for_path(path)

    def _fetch_json_for_path(self, path: str, params: Optional[Dict[str, Union[int, str]]] = None) -> dict:
        url, headers = self._make_url_and_referer(path, self.base_url)
        with self.session.get(url, params=params, headers=headers) as res:
            res.raise_for_status()
            return res.json()

    def fetch_group_list(self, jurisdiction: int, institution: int, page: int = 1) -> dict:
        """Fetch the list of groups where the children study.

        jurisdiction and institutions ids can be taken from fetch_children_List result
        ('.data.items[0].educations[0]')
        """
        path = '/api/journal/group/related-group-list'
        params = {
            'p_page': page,
            'p_jurisdictions[]': self.jurisdiction,
            'p_institutions[]': self.institution,
        }
        return self._fetch_json_for_path(path, params=params)

    def fetch_period_list(self, group: int, page=1) -> dict:
        """Fetch education periods for the given group.

        group can be taken from fetch_group_list result
        """
        path = '/api/group/group/get-list-period'
        params = {
            'p_group_ids[]': self.group,
            'p_page': page,
        }
        return self._fetch_json_for_path(path, params=params)

    def fetch_marks_for_period(self, date_from: Union[str, dt.date], date_to: Union[str, dt.date],
                               limit: int = 200, page: int = 1, child_idx: int = 0, education: int = 0) -> dict:
        # if not education:
        #     children = self.fetch_children_list()
        #     assert child_idx < len(children['data']['items']), len(children['data']['items'])
        #     education = children['data']['items'][child_idx]['educations'][0]['education_id']

        path = '/api/journal/estimate/table'
        if isinstance(date_from, dt.date):
            date_from = date_to_str(date_from)
        if isinstance(date_to, dt.date):
            date_to = date_to_str(date_to)

        params = {
            'p_educations[]': self.educations['education_id'],
            'p_date_from': date_from,
            'p_date_to': date_to,
            'p_limit': limit,
            'p_page': page
        }
        return self._fetch_json_for_path(path, params=params)

    def get_period_dict(self):
        period_dict = defaultdict(tuple)

        for i in range(len(self.period_list)):
            if self.period_list[i]['education_period']['code'] != '30':
                period = self.period_list[i]
                name = period['name']
                date_from = period['date_from']
                date_to = period['date_to']
                period_dict[name] += date_from, date_to

        return dict(period_dict)

    def get_current_period(self) -> str:
        period_dict = self.get_period_dict()
        for period in period_dict:
            q_start, q_end = period_dict[period]
            q_start, q_end = str_to_date(q_start), str_to_date(q_end)
            if q_start <= dt.datetime.today() <= q_end:
                return period
        raise ValueError

    def fetch_subjects(self, period_id: int = 0, limit: int = 100, page: int = 1):
        path = '/api/journal/subject/list-studied'
        if not period_id:
            period_id = self.period_list[0]['identity']['id']

        params = {
            'p_educations[]': self.educations['education_id'],
            'p_groups[]': self.group,
            'p_periods[]': period_id,
            'p_limit': limit,
            'p_page': page
        }
        return self._fetch_json_for_path(path, params=params)

    def get_subject_dict(self) -> dict:
        subject_dict = dict()
        for i in range(len(self.subjects_list)):
            subject = self.subjects_list[i]
            name = subject['name']
            subject_id = subject['id']
            subject_dict[name] = subject_id
        return subject_dict
