import argparse
import asyncio
import ssl
from csv import DictWriter
from datetime import datetime
from pathlib import Path
from sys import exit

import aiohttp
from bs4 import BeautifulSoup
from tqdm import tqdm
from aiohttp import ClientSession
from asyncio import Semaphore

# paths/urls/constants
application_list_path = Path.cwd() / 'application_list.html'
output_csv_fieldnames = ['Application', 'Description', 'Depends on Applications:',
                         'Implicit use Applications:', 'Category', 'Subcategory', 'Risk', 'Standard Ports',
                         'Technology', 'Evasive', 'Excessive Bandwidth', 'Prone to Misuse', 'Capable of File Transfer',
                         'Tunnels Other Applications', 'Used by Malware', 'Has Known Vulnerabilities', 'Widely Used',
                         'SaaS', 'Certifications', 'Data Breaches', 'IP Based Restrictions', 'Poor Financial Viability',
                         'Poor Terms of Service']
output_directory = Path.cwd() / 'output'

# Create a custom SSL context that doesn't verify certificates
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Rate limiting and retry settings
MAX_CONCURRENT_REQUESTS = 50
RATE_LIMIT = 50  # requests per second
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
PORTS_RETRY_DELAY = 2  # seconds

rate_limiter = Semaphore(MAX_CONCURRENT_REQUESTS)


async def main():
    print("WARNING: Running at a very high rate (100 requests/second). This may cause issues with the server.")
    # obtain input
    parser = argparse.ArgumentParser(description='Exports information from the Palo Alto Applipedia database')
    parser.add_argument('-r', '--reload', action='store_true', help='reload application list (application_list.html)')
    args = parser.parse_args()

    # obtain application list
    print('Getting application list...')
    if (not application_list_path.exists()) or args.reload:
        print('\t(new application list is being downloaded)')
        application_list_html = await download_application_list()
    else:
        with application_list_path.open() as a:
            application_list_html = a.read()
    print('Done.\n')

    # tokenize
    print('Tokenizing...')
    soup = BeautifulSoup(application_list_html, 'html.parser')
    print('Done.\n')

    # query the table and output the info to a CSV
    await query_and_output(soup)


async def download_application_list():
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

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        async with session.post(url=url, headers=headers) as response:
            application_list = await response.text()

    # export HTML
    with application_list_path.open('w') as a:
        a.write(application_list)

    return application_list


async def query_and_output(soup):
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

        async with ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
            tasks = [get_detailed_info_with_retry(session, applications[application]) for application in applications]
            results = []
            for f in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
                result = await f
                if result:
                    results.append(result)

        for application, detailed_info in zip(applications, results):
            if detailed_info:
                detail_soup = BeautifulSoup(detailed_info, 'html.parser')
                row_to_write = parse_detail_soup(detail_soup)
                if row_to_write:  # Only write if we have data
                    row_to_write.update({'Application': application})
                    w.writerow(row_to_write)

        print('Done.')


def parse_detail_soup(detail_soup):
    table_root = detail_soup.div.table.tbody.tr.td
    n = table_root.find_next()
    row_to_write = {}

    while n is not None:
        try:
            if n.string and n.string.strip() in output_csv_fieldnames:
                fieldname = n.string.strip()
                n = n.find_next()

                if fieldname == 'Risk':
                    value = n.img.get('title') if n.img else ''
                else:
                    value = n.string.strip() if n.string else ''
                row_to_write.update({fieldname: value})
        except AttributeError:
            pass

        n = n.find_next()

    return row_to_write if row_to_write else None  # Return None if no data was parsed


async def get_detailed_info_with_retry(session, application_info):
    for attempt in range(MAX_RETRIES):
        try:
            async with rate_limiter:
                result = await get_detailed_info(session, application_info)
                if result:
                    detail_soup = BeautifulSoup(result, 'html.parser')
                    parsed_data = parse_detail_soup(detail_soup)
                    if parsed_data and parsed_data.get('Standard Ports', '').strip():
                        return result
                    else:
                        print(f"Empty Standard Ports for {application_info['appName']}. Retrying...")
                        await asyncio.sleep(PORTS_RETRY_DELAY)
                        continue
        except aiohttp.ClientError as e:
            print(f"Error fetching data for {application_info['appName']}: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {RETRY_DELAY} seconds...")
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"Max retries reached for {application_info['appName']}")
        await asyncio.sleep(1 / RATE_LIMIT)  # Rate limiting
    return None


async def get_detailed_info(session, application_info):
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

    async with session.post(url=url, headers=headers, data=application_info) as response:
        if response.status == 200:
            application_detail = await response.text()
            if application_detail:  # Check if the response is not empty
                return application_detail
        else:
            print(f"Received status code {response.status} for {application_info['appName']}")
    return None


if __name__ == '__main__':
    asyncio.run(main())