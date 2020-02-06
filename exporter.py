import argparse
from bs4 import BeautifulSoup
from csv import DictWriter
from datetime import datetime
from pathlib import Path
import requests
from sys import exit
from tqdm import tqdm


# paths/urls/constants
application_list_path = Path.cwd() / 'application_list.html'
output_csv_fieldnames = ['Application', 'Description', 'Reference', 'Depends on Applications:',
                         'Implicit use Applications:', 'Category', 'Subcategory', 'Risk', 'Standard Ports',
                         'Technology', 'Evasive', 'Excessive Bandwidth', 'Prone to Misuse', 'Capable of File Transfer',
                         'Tunnels Other Applications', 'Used by Malware', 'Has Known Vulnerabilities', 'Widely Used',
                         'SaaS', 'Certifications', 'Data Breaches', 'IP Based Restrictions', 'Poor Financial Viability',
                         'Poor Terms of Service']
output_directory = Path.cwd() / 'output'


def main():
    # obtain input
    parser = argparse.ArgumentParser(description='Exports information from the Palo Alto Applipedia database')
    parser.add_argument('-r', '--reload', action='store_true', help='reload application list (application_list.html)')
    args = parser.parse_args()

    # obtain application list
    print('Getting application list...')
    if (not application_list_path.exists()) or args.reload:
        print('\t(new application list is being downloaded)')
        application_list_html = download_application_list()
    else:
        with application_list_path.open() as a:
            application_list_html = a.read()
    print('Done.\n')

    # tokenize
    print('Tokenizing...')
    soup = BeautifulSoup(application_list_html, 'html.parser')
    print('Done.\n')

    # query the table and output the info to a CSV
    query_and_output(soup)


def download_application_list():
    # get cookie
    try:
        with (Path.cwd() / 'cookie.txt').open() as c:
            cookie = c.read()
    except Exception:
        print('Add valid cookie to cookie.txt')
        exit(1)

    # send POST request
    headers = {
        "User-Agent": "foobar",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://applipedia.paloaltonetworks.com",
        "Connection": "close",
        "Referer": "https://applipedia.paloaltonetworks.com",
        "Cookie": cookie,
        "TE": "Trailers",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache"
    }
    url = 'https://applipedia.paloaltonetworks.com/Home/GetApplicationListView'
    response = requests.post(url=url, headers=headers)
    response.close()
    application_list = response.content.decode()

    # export HTML
    with application_list_path.open('w') as a:
        a.write(application_list)

    return application_list


def query_and_output(soup):
    # get output file path
    if not output_directory.exists():
        output_directory.mkdir()
    filename = f'applipedia-export-{datetime.now().strftime("%m-%d-%Y-%H-%M-%S")}.csv'
    output_path = output_directory / filename

    # obtain list of applications and respective function call data to be POSTed later
    links = soup.findAll('a')
    applications = {}
    function_calls = [link.get('onclick').split(';')[0] for link in links]
    for function_call in function_calls:
        split_call = function_call.split("'")
        applications.update({
            split_call[3]: {
                'id': split_call[1],
                'ottawagroup': split_call[5],
                'appName': split_call[3]
            }
        })

    # export detailed info for each application
    with output_path.open('w', newline='') as output_file:
        w = DictWriter(output_file, fieldnames=output_csv_fieldnames)
        w.writeheader()
        print('Exporting info for all applications...')
        for application in tqdm(applications):
            detailed_info = get_detailed_info(applications[application])
            detail_soup = BeautifulSoup(detailed_info, 'html.parser')
            row_to_write = parse_detail_soup(detail_soup)   # returns a dictionary
            row_to_write.update({'Application': application})
            w.writerow(row_to_write)

        print('Done.')


def parse_detail_soup(detail_soup):
    table_root = detail_soup.div.table.tbody.tr.td
    n = table_root.find_next()
    row_to_write = {}

    while n is not None:
        try:
            if n.string.strip() in output_csv_fieldnames:
                fieldname = n.string.strip()
                n = n.find_next()

                if fieldname == 'Reference':
                    value = str(n)
                elif fieldname == 'Risk':
                    value = n.img.get('title')
                else:
                    value = n.string.strip()
                row_to_write.update({fieldname: value})
        except AttributeError:
            pass

        n = n.find_next()

    return row_to_write


def get_detailed_info(application_info):
    # get cookie
    try:
        with (Path.cwd() / 'cookie.txt').open() as c:
            cookie = c.read()
    except Exception:
        print('Add valid cookie to cookie.txt')
        exit(1)

    # send POST request
    headers = {
        "User-Agent": "foobar",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://applipedia.paloaltonetworks.com",
        "Connection": "close",
        "Referer": "https://applipedia.paloaltonetworks.com",
        "Cookie": cookie,
        "TE": "Trailers",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache"
    }
    url = 'https://applipedia.paloaltonetworks.com/Home/GetApplicationDetailView'

    response = requests.post(url=url, headers=headers, data=application_info)
    response.close()
    application_detail = response.content.decode()

    return application_detail


if __name__ == '__main__':
    main()
