import requests
from bs4 import BeautifulSoup
from datetime import datetime
import sys

URL = "https://selfservice.broxtowe.gov.uk/renderform.aspx?t=217&k=9D2EF214E144EE796430597FB475C3892C43C528"
ASPX_KEYS = ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]

BASE_ID = "ctl00_ContentPlaceHolder1_"
BASE_NAME = BASE_ID.replace("_", "$")

FORM_CODE = "APUP_5683"
FORM_ID = f"{BASE_ID}{FORM_CODE}"
FORM_NAME = f"{BASE_NAME}{FORM_CODE}"

POSTCODE_NAME = f"{BASE_NAME}FF5683TB"
SEARCH_NAME = f"{BASE_NAME}FF5683BTN"
ADDRESS_NAME = f"{BASE_NAME}FF5683DDL"
NEXT_BUTTON_NAME = f"{BASE_NAME}btnSubmit"

class ScraperError(Exception):
    """Base class for scraper errors"""
    pass

class ClientError(ScraperError):
    """Raised when the inputs are invalid"""
    pass

class UpstreamError(ScraperError):
    """Raised when the response back from Broxtowe is invalid"""
    pass

class ServiceUnavailableError(ScraperError):
    """Raised when the service is unavailable"""
    pass

class InvalidResponseError(ScraperError):
    """Raised when the response is invalid"""
    pass

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
        raise UpstreamError("No bin collection data found")

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

    if not bins:
        raise UpstreamError("No bin collection data found")

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

def format_uprn(uprn):
    return f"U{uprn}"

def extract_uprn(not_uprn):
    return not_uprn.lstrip("U")

def validate_response(response: requests.Response):
    """Validate the HTTP response and raise appropriate exceptions"""
    if response.status_code == 503:
        raise ServiceUnavailableError("Broxtowe Borough Council website is currently unavailable")

    if response.status_code == 404:
        raise InvalidResponseError(
            "Broxtowe Borough Council requested page was not found"
        )

    if response.status_code >= 500:
        raise ServiceUnavailableError(
            f"Server error: {response.status_code}, {response.text}"
        )

    if response.status_code >= 400:
        raise InvalidResponseError(
            f"Client error: {response.status_code}, {response.text}"
        )

    if not response.ok:
        raise InvalidResponseError(f"Unexpected response: {response.status_code}, {response.text}")

def get_bin_data(postcode, uprn):
    postcode = postcode.upper().replace(" ", "")

    # Initial session to get the form
    session = requests.Session()

    # Initial GET request
    response = session.get(URL, headers=get_headers())
    validate_response(response)

    # Parse the response to get form data
    soup = BeautifulSoup(response.text, 'html.parser')

    # Extract form fields
    aspx_fields = {key: soup.find("input", {"name": key})["value"] for key in ASPX_KEYS}

    # Prepare data for the AJAX request
    data = {
        "ctl00$ScriptManager1": f"{FORM_NAME}|{SEARCH_NAME}",
        "__EVENTTARGET": SEARCH_NAME,
        POSTCODE_NAME: postcode,
        "__ASYNCPOST": "true",
    }
    data.update(aspx_fields)

    # Make the AJAX request
    response = session.post(URL, headers=get_headers(), data=data)
    validate_response(response)

    aspx_fields = extract_aspx_fields(
        response.text, [FORM_ID]
    )
    soup = BeautifulSoup(
        aspx_fields[FORM_ID], "html.parser"
    )
    address_select = soup.find("select", {"name": ADDRESS_NAME})

    if not address_select:
        raise ClientError('No addresses for the postcode')

    addresses = []
    for option in address_select.find_all('option'):
        if option.get('value') and option.get('value') != '0':  # Skip the "Enter a different post code" option
            addresses.append({
                'uprn': extract_uprn(option.get('value')),
                'address': option.text
            })

    if not addresses:
        raise ClientError("No addresses for the postcode")

    try:
        matched_address = next(address for address in addresses if address["uprn"] == uprn)
    except StopIteration as e:
        raise ClientError("No address for the postcode and UPRN")

    # Make request with the UPRN
    data = {
        "ctl00$ScriptManager1": f"{FORM_NAME}|{ADDRESS_NAME}",
        ADDRESS_NAME: format_uprn(matched_address["uprn"]),
        "__EVENTTARGET": ADDRESS_NAME,
        "__ASYNCPOST": "true",
    }
    data.update(aspx_fields)

    response = session.post(URL, headers=get_headers(), data=data)
    validate_response(response)

    aspx_fields = extract_aspx_fields(
        response.text, [FORM_ID]
    )

    data = {
        "__EVENTTARGET": NEXT_BUTTON_NAME,
    }
    data.update(aspx_fields)

    response = session.post(
        URL,
        headers=get_headers(False),
        data=data,
    )
    validate_response(response)

    # Parse the bin collection data
    bin_data = parse_bin_data(response.text)

    return {
        'bin_collections': bin_data,
        'address': matched_address,
    }

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python bins.py <postcode> <uprn>")
        sys.exit(1)

    postcode = sys.argv[1]
    uprn = sys.argv[2]

    result = get_bin_data(postcode, uprn)

    print(result)
