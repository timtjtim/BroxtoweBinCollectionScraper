import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import sys

URL = "https://selfservice.broxtowe.gov.uk/renderform.aspx?t=217&k=9D2EF214E144EE796430597FB475C3892C43C528"
ASPX_KEYS = ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]

def get_headers(delta=True):
    return {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0 BroxtoweBinCollectionScraper/1.0 (+https://github.com/timtjtim/BroxtoweBinCollectionScraper;)",
        "x-microsoftajax": f"Delta={'true' if delta else 'false'}",
        "x-requested-with": "XMLHttpRequest",
    }

def parse_bin_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find('table', {'class': 'bartec'})

    if not table:
        return None

    bins = []
    rows = table.find_all('tr')[1:]  # Skip header row

    for row in rows:
        cols = row.find_all('td')
        if len(cols) == 4:
            next_collection_raw = cols[3].text.strip()
            try:
                # Parse the date string (format: "Wednesday, 02 July 2025")
                date_obj = datetime.strptime(next_collection_raw, "%A, %d %B %Y")
                next_collection_iso = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                next_collection_iso = ""

            bin_data = {
                'type': cols[0].text.strip(),
                'next_collection_raw': next_collection_raw,
                'next_collection_iso': next_collection_iso,
            }
            bins.append(bin_data)

    return bins

def extract_aspx_fields(response_text, keys):
    keys += ASPX_KEYS
    response_parts = response_text.split('|')

    extracted = {key: None for key in keys}

    # Extract form data from response parts
    for i, part in enumerate(response_parts):
        for key in keys:
            if key == part:
                extracted[key] = response_parts[i + 1]

    return extracted

def get_bin_data(postcode, uprn):
    # Initial session to get the form
    session = requests.Session()

    # Initial GET request
    response = session.get(URL, headers=get_headers())

    # Parse the response to get form data
    soup = BeautifulSoup(response.text, 'html.parser')

    # Extract form fields

    aspx_fields = {key: soup.find("input", {"name": key})["value"] for key in ASPX_KEYS}

    # Prepare data for the AJAX request
    data = {
        "ctl00$ScriptManager1": "ctl00$ContentPlaceHolder1$APUP_5683|ctl00$ContentPlaceHolder1$FF5683BTN",
        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$FF5683BTN",
        "__EVENTARGUMENT": "",
        "ctl00$ContentPlaceHolder1$txtPositionLL": "",
        "ctl00$ContentPlaceHolder1$txtPosition": "",
        "ctl00$ContentPlaceHolder1$FF5683TB": postcode.lower().replace(" ", ""),
        "__ASYNCPOST": "true",
    }
    data.update(aspx_fields)

    # Make the AJAX request
    response = session.post(URL, headers=get_headers(), data=data)

    aspx_fields = extract_aspx_fields(
        response.text, ["ctl00_ContentPlaceHolder1_APUP_5683"]
    )
    soup = BeautifulSoup(
        aspx_fields["ctl00_ContentPlaceHolder1_APUP_5683"], "html.parser"
    )
    address_select = soup.find('select', {'name': 'ctl00$ContentPlaceHolder1$FF5683DDL'})

    if not address_select:
        return None

    addresses = []
    for option in address_select.find_all('option'):
        if option.get('value') and option.get('value') != '0':  # Skip the "Enter a different post code" option
            addresses.append({
                'uprn': option.get('value'),
                'address': option.text
            })

    if not addresses:
        return None

    # Make request with the UPRN
    data = {
        "ctl00$ScriptManager1": "ctl00$ContentPlaceHolder1$APUP_5683|ctl00$ContentPlaceHolder1$FF5683DDL",
        "ctl00$ContentPlaceHolder1$txtPositionLL": "",
        "ctl00$ContentPlaceHolder1$txtPosition": "",
        "ctl00$ContentPlaceHolder1$FF5683DDL": uprn,
        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$FF5683DDL",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__ASYNCPOST": "true",
    }
    data.update(aspx_fields)

    response = session.post(URL, headers=get_headers(), data=data)

    aspx_fields = extract_aspx_fields(
        response.text, ["ctl00_ContentPlaceHolder1_APUP_5683"]
    )

    data = {
        "ctl00$ContentPlaceHolder1$txtPositionLL": "",
        "ctl00$ContentPlaceHolder1$txtPosition": "",
        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$btnSubmit",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
    }
    data.update(aspx_fields)

    response = session.post(
        URL,
        headers=get_headers(False),
        data=data,
    )

    # Parse the bin collection data
    bin_data = parse_bin_data(response.text)

    return {
        'bin_collections': bin_data
    }

if __name__ == "__main__":
    # Example usage
    if len(sys.argv) != 3:
        print("Usage: python bins.py <postcode> <uprn>")
        sys.exit(1)

    postcode = sys.argv[1]
    uprn = sys.argv[2]

    result = get_bin_data(postcode, uprn)

    print(result)
